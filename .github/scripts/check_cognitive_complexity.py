# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Enforce per-function complexipy scores and a Git-backed, shrink-only baseline."""

import argparse
import ast
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from fnmatch import fnmatchcase
from importlib.metadata import version
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import tokenize
import tomllib

from complexipy import code_complexity, file_complexity


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ".github/resources/cognitive-complexity-baseline.txt"
THRESHOLD = 12
Key = tuple[str, str]
Definition = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class Function:
  """A measured function, identified independently of its source line."""

  path: str
  name: str
  score: int
  line: int

  @property
  def key(self) -> Key:
    return self.path, self.name


def read_baseline(text: str) -> dict[Key, int]:
  """Read tab-separated path, qualified name, and maximum score entries."""
  entries: dict[Key, int] = {}
  for line_number, line in enumerate(text.splitlines(), 1):
    if not line.strip() or line.startswith("#"):
      continue
    fields = line.split("\t")
    if len(fields) != 3:
      raise ValueError(f"{BASELINE}:{line_number}: expected path<TAB>name<TAB>score")
    path, name, maximum = fields
    key = path, name
    score = int(maximum)
    if key in entries or score <= THRESHOLD or not name or not path.endswith(".py"):
      raise ValueError(f"{BASELINE}:{line_number}: duplicate or invalid entry: {line}")
    entries[key] = score
  return entries


def committed_baseline(root: Path, ref: str) -> dict[Key, int] | None:
  """Use HEAD locally and the PR base commit in CI; never trust a changed baseline."""
  commit = subprocess.check_output(
    ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
    cwd=root, text=True,
  ).strip()
  tracked = subprocess.check_output(
    ["git", "ls-tree", "--name-only", commit, "--", BASELINE], cwd=root, text=True,
  )
  if not tracked.strip():
    return None  # Initial rollout: all entries must still match measured scores exactly.
  text = subprocess.check_output(
    ["git", "show", f"{commit}:{BASELINE}"], cwd=root, text=True,
  )
  return read_baseline(text)


def excluded(path: str, patterns: list[str]) -> bool:
  """Match repository-relative directory and filename exclusions."""
  return any(fnmatchcase(path, pattern) for pattern in patterns)


def measure(root: Path, trees: list[str], patterns: list[str]) -> list[Function]:
  """Run complexipy on every application file, without honoring inline suppressions."""
  return [
    function
    for tree in trees
    for path in application_files(root, tree, patterns)
    for function in measure_file(root, path)
  ]


def application_files(root: Path, tree: str, patterns: list[str]) -> Iterator[str]:
  """Traverse one application tree, pruning excluded directories."""
  directory = root / tree
  if not directory.is_dir():
    raise ValueError(f"Application tree does not exist: {tree}")
  for current, directories, files in os.walk(directory, onerror=raise_walk_error):
    relative = Path(current).relative_to(root)
    directories[:] = sorted(
      name for name in directories
      if not excluded((relative / name).as_posix() + "/", patterns)
    )
    for name in sorted(files):
      path = (relative / name).as_posix()
      if name.endswith(".py") and not excluded(path, patterns):
        yield path


def measure_file(root: Path, path: str) -> list[Function]:
  """Measure all definitions, including nested functions not emitted by file_complexity."""
  with tokenize.open(root / path) as handle:
    source = handle.read()
  lines = source.splitlines(keepends=True)
  result = file_complexity(str(root / path), no_ignore=True)
  reported = {function.line_start: function.complexity for function in result.functions}
  functions = []
  for node, name in definitions(ast.parse(source, filename=path)):
    start = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list])
    score = reported.get(start)
    if score is None:
      # complexipy includes closures in the outer score; also gate each closure
      # independently, using the same engine rather than implementing a metric.
      snippet = textwrap.dedent("".join(lines[node.lineno - 1:node.end_lineno]))
      score = code_complexity(snippet, no_ignore=True).functions[0].complexity
    functions.append(Function(path, name, score, node.lineno))
  return distinguish_duplicates(functions)


def definitions(node: ast.AST, scope: tuple[str, ...] = ()) -> Iterator[tuple[Definition, str]]:
  """Find fully qualified definitions, retaining enclosing class and function names."""
  for child in ast.iter_child_nodes(node):
    child_scope = scope
    if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
      child_scope = (*scope, child.name)
    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
      yield child, "::".join(child_scope)
    yield from definitions(child, child_scope)


def distinguish_duplicates(measured: list[Function]) -> list[Function]:
  """Never let a duplicate definition inherit an unrelated function's allowance."""
  counts = Counter(function.name for function in measured)
  occurrences: Counter[str] = Counter()
  functions = []
  for function in measured:
    name = function.name
    occurrences[name] += 1
    if counts[name] > 1:
      name = f"{name}[{occurrences[name]}]"
    functions.append(Function(function.path, name, function.score, function.line))
  return functions


def raise_walk_error(error: OSError) -> None:
  """Do not silently skip unreadable application directories."""
  raise error


def baseline_edit_errors(
    current: dict[Key, int],
    previous: dict[Key, int] | None,
    functions: list[Function],
) -> list[str]:
  """Allow only deletions and lower maxima after the initial rollout."""
  if previous is None:
    return []
  measured = {function.key: function for function in functions}
  return [
    f"{path.split('/')[0]} {path}:{measured[(path, name)].line if (path, name) in measured else 0} "
    f"{name} complexity={measured[(path, name)].score if (path, name) in measured else 'missing'}: "
    "baseline entry added or maximum raised"
    for (path, name), score in sorted(current.items())
    if (path, name) not in previous or score > previous[(path, name)]
  ]


def score_errors(functions: list[Function], baseline: dict[Key, int]) -> list[str]:
  """Reject new/worsened offenders and stale allowances, reporting every failure."""
  errors = []
  measured = {function.key: function.score for function in functions}
  for function in functions:
    maximum = baseline.get(function.key, THRESHOLD)
    if function.score > maximum:
      errors.append(
        f"{function.path.split('/')[0]} {function.path}:{function.line} "
        f"{function.name} complexity={function.score}: exceeds maximum {maximum}"
      )
  locations = {function.key: function.line for function in functions}
  for (path, name), maximum in sorted(baseline.items()):
    score = measured.get((path, name))
    if score is None or score < maximum:
      errors.append(
        f"{path.split('/')[0]} {path}:{locations.get((path, name), 0)} "
        f"{name} complexity={score if score is not None else 'missing'}: "
        f"remove or lower stale baseline maximum {maximum}"
      )
  return errors


def exclusions(root: Path) -> list[str]:
  """Load and validate the shared complexipy configuration."""
  config = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["complexipy"]
  if config["max-complexity-allowed"] != THRESHOLD or not config["no-ignore"]:
    raise ValueError("complexipy must use threshold 12 and no-ignore = true")
  return config["exclude"]


def status(function: Function, baseline: dict[Key, int]) -> str:
  """Classify a score as within the limit, a tolerated legacy offender, or a failure."""
  if function.score <= THRESHOLD:
    return "ok"
  return "legacy" if function.score <= baseline.get(function.key, THRESHOLD) else "fail"


def summary_rows(functions: list[Function], baseline: dict[Key, int]) -> list[tuple]:
  """Aggregate per-service statistics, followed by a TOTAL row."""
  groups: dict[str, list[Function]] = {}
  for function in functions:
    groups.setdefault(function.path.split("/")[0], []).append(function)
  groups = dict(sorted(groups.items()))
  groups["TOTAL"] = functions
  rows = []
  for service, members in groups.items():
    scores = [function.score for function in members]
    states = Counter(status(function, baseline) for function in members)
    rows.append((
      service, len(scores), sum(scores), f"{sum(scores) / max(len(scores), 1):.2f}",
      max(scores, default=0), states["legacy"] + states["fail"], states["legacy"], states["fail"],
    ))
  return rows


def format_report(functions: list[Function], baseline: dict[Key, int], top: int) -> str:
  """Render a coverage-style summary table and the highest-scoring functions."""
  header = ("Service", "Functions", "Total", "Mean", "Max", f">{THRESHOLD}", "Legacy", "Fail")
  rows = summary_rows(functions, baseline)
  widths = [max(len(str(row[i])) for row in [header, *rows]) for i in range(len(header))]

  def line(row: tuple) -> str:
    return "  ".join(
      str(value).ljust(widths[i]) if i == 0 else str(value).rjust(widths[i])
      for i, value in enumerate(row)
    )

  separator = "-" * len(line(header))
  table = [line(header), separator, *map(line, rows[:-1]), separator, line(rows[-1])]
  ranked = sorted(functions, key=lambda function: (-function.score, function.path, function.line))
  worst = [
    f"{function.score:>4}  {status(function, baseline):<6}  "
    f"{function.path}:{function.line}  {function.name}"
    for function in ranked[:top]
  ]
  return "\n".join([*table, "", f"Top {len(worst)} functions by cognitive complexity:", *worst])


def write_report(root: Path, trees: list[str], output: Path, top: int) -> int:
  """Measure every function and write a summary plus a full per-function TSV."""
  functions = measure(root, trees, exclusions(root))
  baseline = read_baseline((root / BASELINE).read_text())
  output.mkdir(parents=True, exist_ok=True)
  ranked = sorted(functions, key=lambda function: (-function.score, function.path, function.line))
  rows = ["service\tpath\tline\tfunction\tscore\tlimit\tstatus"] + [
    f"{function.path.split('/')[0]}\t{function.path}\t{function.line}\t{function.name}\t"
    f"{function.score}\t{baseline.get(function.key, THRESHOLD)}\t{status(function, baseline)}"
    for function in ranked
  ]
  (output / "functions.tsv").write_text("\n".join(rows) + "\n")
  text = format_report(functions, baseline, top)
  (output / "summary.txt").write_text(text + "\n")
  print(text)
  print(f"\nFull report: {output / 'summary.txt'}, {output / 'functions.tsv'}")
  return 0


def check_service(root: Path, trees: list[str], service: str, ref: str) -> int:
  """Validate the baseline and check all application trees belonging to one service."""
  patterns = exclusions(root)
  baseline = read_baseline((root / BASELINE).read_text())
  previous = committed_baseline(root, ref)
  errors = []
  for (path, name), score in sorted(baseline.items()):
    if not any(path.startswith(tree + "/") for tree in trees) or excluded(path, patterns):
      errors.append(
        f"{path.split('/')[0]} {path}:0 {name} complexity={score}: baseline path outside scope"
      )
  selected = [tree for tree in trees if tree.split("/")[0] == service]
  if not selected:
    raise ValueError(f"Unknown complexity service: {service}")
  functions = measure(root, selected, patterns)
  service_baseline = {
    key: score for key, score in baseline.items() if key[0].split("/")[0] == service
  }
  errors.extend(baseline_edit_errors(service_baseline, previous, functions))
  errors.extend(score_errors(functions, service_baseline))
  for error in errors:
    print(error)
  print(f"{service}: {len(functions)} functions, {len(service_baseline)} legacy allowances, "
        f"{'FAIL' if errors else 'PASS'}")
  return int(bool(errors))


def main() -> int:
  """CLI entry point used by the root Makefile's complexity targets."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--service", help="check one service (required unless --report is given)")
  parser.add_argument("--trees", nargs="+", required=True)
  parser.add_argument("--base-ref", default=os.environ.get("COMPLEXITY_BASE_REF", "HEAD"))
  parser.add_argument("--report", type=Path, metavar="DIR",
                      help="write a score report to DIR instead of enforcing the gate")
  parser.add_argument("--top", type=int, default=20, help="functions listed in the report")
  args = parser.parse_args()
  if not args.report and not args.service:
    parser.error("--service is required unless --report is given")
  try:
    pin = next(
      line.split("==")[1].strip()
      for line in (ROOT / ".github/resources/requirements.txt").read_text().splitlines()
      if line.startswith("complexipy ")
    )
    if version("complexipy") != pin:
      raise ValueError(f"Install the pinned analyzer: python3 -m pip install complexipy=={pin}")
    if args.report:
      trees = [tree for tree in args.trees if args.service in (None, tree.split("/")[0])]
      if not trees:
        raise ValueError(f"Unknown complexity service: {args.service}")
      return write_report(ROOT, trees, args.report, args.top)
    return check_service(ROOT, args.trees, args.service, args.base_ref)
  except (OSError, ValueError, SyntaxError, subprocess.CalledProcessError) as error:
    print(f"{args.service or 'report'}: cognitive complexity check failed: {error}",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
  sys.exit(main())
