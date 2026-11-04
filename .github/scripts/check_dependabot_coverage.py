# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Verify that .github/dependabot.yml covers every dependency manifest in the repository.

Checks performed:
  1. Every Git-tracked dependency manifest lives in a directory configured for the
     matching Dependabot package-ecosystem.
  2. Every YAML file that defines top-level `services:` (i.e. a Docker Compose file)
     is named so that Dependabot's docker-compose file fetcher picks it up.
  3. No configured directory is stale (contains no manifest of its ecosystem).
  4. No manifest of a Dependabot ecosystem outside ECOSYSTEMS appears in the repository,
     and dependabot.yml configures no ecosystem this script cannot verify. Either case
     means a new ecosystem was introduced: add it to dependabot.yml and to ECOSYSTEMS.

Intentional exceptions are listed in .github/resources/dependabot-coverage-ignore.txt.
"""

import argparse
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ".github/dependabot.yml"
IGNORE_FILE = ".github/resources/dependabot-coverage-ignore.txt"
SCRIPT = ".github/scripts/check_dependabot_coverage.py"
COMPOSE_NAMING = "compose-naming"

# Mirrors dependabot-core docker/lib/dependabot/docker_compose/file_fetcher.rb
COMPOSE_FILENAME_REGEX = re.compile(r"(docker-)?compose(-[\w]+)?(?>\.[\w-]+)?\.ya?ml", re.IGNORECASE)
# Mirrors dependabot-core docker/lib/dependabot/docker/file_fetcher.rb
DOCKERFILE_REGEX = re.compile(r"dockerfile|containerfile", re.IGNORECASE)
REQUIREMENTS_REGEX = re.compile(r"requirements.*\.(txt|in)$", re.IGNORECASE)
YAML_SUFFIXES = (".yml", ".yaml")


@dataclass(frozen=True)
class Finding:
  """A single coverage problem."""

  kind: str
  ecosystem: str
  path: str
  hint: str

  def __str__(self) -> str:
    return f"[{self.kind}] {self.ecosystem}: {self.path}\n    -> {self.hint}"


def git_files() -> list[str]:
  """Return tracked and untracked-but-not-ignored files, relative to the repository root."""
  out = subprocess.run(
    ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
    cwd=ROOT, check=True, capture_output=True,
  ).stdout.decode()
  return sorted({f for f in out.split("\0") if f and (ROOT / f).is_file()})


def read_text(path: str) -> str:
  try:
    return (ROOT / path).read_text(encoding="utf-8")
  except (OSError, UnicodeDecodeError):
    return ""


def is_pyproject_with_deps(path: str) -> bool:
  try:
    data = tomllib.loads(read_text(path))
  except tomllib.TOMLDecodeError:
    return False
  project = data.get("project", {})
  poetry = data.get("tool", {}).get("poetry", {})
  return bool(project.get("dependencies") or project.get("optional-dependencies")
              or data.get("build-system", {}).get("requires")
              or any(data.get("dependency-groups", {}).values())
              or poetry.get("dependencies") or poetry.get("dev-dependencies")
              or any(group.get("dependencies") for group in poetry.get("group", {}).values()))


def is_pip_manifest(path: str) -> bool:
  name = PurePosixPath(path).name
  if REQUIREMENTS_REGEX.search(name) or name in ("Pipfile", "Pipfile.lock"):
    return True
  if name == "pyproject.toml":
    return is_pyproject_with_deps(path)
  if name in ("setup.py", "setup.cfg"):
    return "install_requires" in read_text(path)
  return False


def is_actions_manifest(path: str) -> bool:
  p = PurePosixPath(path)
  if p.parent.as_posix() == ".github/workflows":
    return p.suffix in YAML_SUFFIXES
  return p.name in ("action.yml", "action.yaml")


def actions_directory(path: str) -> str:
  p = PurePosixPath(path)
  if p.parent.as_posix() == ".github/workflows":
    return "/"
  return to_dependabot_dir(p.parent.as_posix())


def is_dockerfile(path: str) -> bool:
  name = PurePosixPath(path).name
  return bool(DOCKERFILE_REGEX.search(name)) and not name.endswith((".md", ".dockerignore"))


def is_compose_file(path: str) -> bool:
  return bool(COMPOSE_FILENAME_REGEX.search(PurePosixPath(path).name))


def is_named(*names: str) -> Callable[[str], bool]:
  return lambda path: PurePosixPath(path).name in names


def is_suffixed(*suffixes: str) -> Callable[[str], bool]:
  return lambda path: PurePosixPath(path).name.endswith(suffixes)


def to_dependabot_dir(directory: str) -> str:
  return "/" if directory in ("", ".") else "/" + directory.strip("/")


def default_directory(path: str) -> str:
  return to_dependabot_dir(PurePosixPath(path).parent.as_posix())


# Ecosystems used in this repository and verified directory by directory.
# package-ecosystem -> (manifest detector, manifest -> Dependabot directory)
ECOSYSTEMS: dict[str, tuple[Callable[[str], bool], Callable[[str], str]]] = {
  "github-actions": (is_actions_manifest, actions_directory),
  "docker": (is_dockerfile, default_directory),
  "docker-compose": (is_compose_file, default_directory),
  "pip": (is_pip_manifest, default_directory),
  "npm": (is_named("package.json"), default_directory),
  "helm": (is_named("Chart.yaml"), default_directory),
}

# Other Dependabot ecosystems not used yet. A matching file means a new ecosystem was
# introduced; move its entry to ECOSYSTEMS once it is configured in dependabot.yml.
NEW_ECOSYSTEM_DETECTORS: dict[str, Callable[[str], bool]] = {
  "bun": is_named("bun.lock", "bun.lockb"),
  "bundler": is_named("Gemfile", "Gemfile.lock"),
  "cargo": is_named("Cargo.toml"),
  "composer": is_named("composer.json"),
  "devcontainers": is_named("devcontainer.json", ".devcontainer.json"),
  "dotnet-sdk": is_named("global.json"),
  "elm": is_named("elm.json"),
  "gitsubmodule": lambda path: PurePosixPath(path).name == ".gitmodules" and "[submodule" in read_text(path),
  "gomod": is_named("go.mod"),
  "gradle": is_named("build.gradle", "build.gradle.kts", "libs.versions.toml"),
  "maven": is_named("pom.xml"),
  "mix": is_named("mix.exs"),
  "nuget": is_suffixed(".csproj", ".fsproj", ".vbproj", ".sln", "packages.config"),
  "pub": is_named("pubspec.yaml"),
  "rust-toolchain": is_named("rust-toolchain", "rust-toolchain.toml"),
  "swift": is_named("Package.swift"),
  "terraform": is_suffixed(".tf", ".hcl"),
  "uv": is_named("uv.lock"),
}
SKIPPED_PARTS = {"node_modules", ".venv", "venv", "__pycache__", ".git"}


def glob_to_regex(pattern: str) -> re.Pattern[str]:
  """Translate a Dependabot directory glob (`*`, `**`) into a regex."""
  pattern = to_dependabot_dir(pattern)
  out = []
  for token in re.split(r"(\*\*/?|\*)", pattern):
    if token.startswith("**"):
      out.append(r"(?:.*/)?" if token.endswith("/") else r".*")
    elif token == "*":
      out.append(r"[^/]*")
    else:
      out.append(re.escape(token))
  return re.compile("".join(out).rstrip("/") + "/?" if pattern != "/" else "/")


def matches_any(directory: str, patterns: Iterable[str]) -> bool:
  return any(glob_to_regex(p).fullmatch(directory) for p in patterns)


def load_config(text: str) -> dict[str, list[str]]:
  """Return package-ecosystem -> configured directory patterns."""
  config = yaml.safe_load(text) or {}
  configured: dict[str, list[str]] = defaultdict(list)
  for update in config.get("updates", []):
    dirs = update.get("directories") or [update.get("directory")]
    configured[update["package-ecosystem"]].extend(to_dependabot_dir(d) for d in dirs if d)
  return configured


def load_ignores(text: str) -> dict[str, list[str]]:
  """Read `<ecosystem|compose-naming> <directory-or-file-glob>` lines."""
  ignores: dict[str, list[str]] = defaultdict(list)
  for line_number, raw in enumerate(text.splitlines(), 1):
    line = raw.split("#", 1)[0].strip()
    if not line:
      continue
    fields = line.split()
    known = fields[0] in ECOSYSTEMS or fields[0] in NEW_ECOSYSTEM_DETECTORS or fields[0] == COMPOSE_NAMING
    if len(fields) != 2 or not known:
      raise ValueError(f"{IGNORE_FILE}:{line_number}: expected '<ecosystem> <path>': {raw}")
    ignores[fields[0]].append(fields[1])
  return ignores


def all_detectors() -> Iterable[tuple[str, Callable[[str], bool], Callable[[str], str]]]:
  for ecosystem, (detect, directory_of) in ECOSYSTEMS.items():
    yield ecosystem, detect, directory_of
  for ecosystem, detect in NEW_ECOSYSTEM_DETECTORS.items():
    yield ecosystem, detect, default_directory


def find_manifests(files: Iterable[str]) -> dict[str, dict[str, list[str]]]:
  """Return ecosystem -> Dependabot directory -> manifest files."""
  found: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
  detectors = list(all_detectors())
  for path in files:
    if SKIPPED_PARTS.intersection(PurePosixPath(path).parts):
      continue
    for ecosystem, detect, directory_of in detectors:
      if detect(path):
        found[ecosystem][directory_of(path)].append(path)
  return found


def defines_compose_services(path: str) -> bool:
  try:
    documents = list(yaml.safe_load_all(read_text(path)))
  except yaml.YAMLError:
    return False
  return any(isinstance(doc, dict) and isinstance(doc.get("services"), dict) for doc in documents)


def check_compose_naming(files: Iterable[str], ignores: list[str]) -> list[Finding]:
  findings = []
  for path in files:
    if not path.endswith(YAML_SUFFIXES) or is_compose_file(path) or path.startswith(".github/"):
      continue
    if matches_any("/" + path, ignores) or not defines_compose_services(path):
      continue
    findings.append(Finding(
      "naming", "docker-compose", path,
      f"defines 'services:' but does not match Dependabot's pattern "
      f"{COMPOSE_FILENAME_REGEX.pattern}; rename it (e.g. compose.<name>.yml, "
      f"compose-<name>.yml, docker-compose.<name>.yml) or add "
      f"'{COMPOSE_NAMING} /{path}' to {IGNORE_FILE}"))
  return findings


def uncovered_hint(ecosystem: str, directory: str, paths: list[str]) -> str:
  files = ", ".join(paths)
  if ecosystem in NEW_ECOSYSTEM_DETECTORS:
    return (f"{files} introduce(s) the new '{ecosystem}' ecosystem; add a '{ecosystem}' "
            f"entry covering '{directory}' to {CONFIG} and move '{ecosystem}' from "
            f"NEW_ECOSYSTEM_DETECTORS to ECOSYSTEMS in {SCRIPT}, or add "
            f"'{ecosystem} {directory}' to {IGNORE_FILE}")
  return (f"{files} not tracked; add '{directory}' to the '{ecosystem}' entry in "
          f"{CONFIG} or add '{ecosystem} {directory}' to {IGNORE_FILE}")


def check_coverage(manifests: dict[str, dict[str, list[str]]], configured: dict[str, list[str]],
                   ignores: dict[str, list[str]]) -> list[Finding]:
  findings = []
  for ecosystem, directories in sorted(manifests.items()):
    kind = "new-ecosystem" if ecosystem in NEW_ECOSYSTEM_DETECTORS else "uncovered"
    for directory, paths in sorted(directories.items()):
      if ecosystem in ECOSYSTEMS and matches_any(directory, configured.get(ecosystem, [])):
        continue
      if matches_any(directory, ignores[ecosystem]):
        continue
      findings.append(Finding(kind, ecosystem, directory, uncovered_hint(ecosystem, directory, paths)))
  return findings


def check_stale(manifests: dict[str, dict[str, list[str]]], configured: dict[str, list[str]]) -> list[Finding]:
  findings = []
  for ecosystem, patterns in sorted(configured.items()):
    if ecosystem not in ECOSYSTEMS:
      findings.append(Finding(
        "unverified-ecosystem", ecosystem, CONFIG,
        f"'{ecosystem}' is configured in {CONFIG} but {SCRIPT} cannot verify its coverage; "
        f"add a '{ecosystem}' manifest detector to ECOSYSTEMS"))
      continue
    for pattern in patterns:
      if not any(matches_any(d, [pattern]) for d in manifests.get(ecosystem, {})):
        findings.append(Finding(
          "stale", ecosystem, pattern,
          f"no {ecosystem} manifest found there; remove it from {CONFIG} or fix the path"))
  return findings


def run(files: list[str], config_text: str, ignore_text: str) -> list[Finding]:
  configured = load_config(config_text)
  ignores = load_ignores(ignore_text)
  manifests = find_manifests(files)
  return (check_compose_naming(files, ignores[COMPOSE_NAMING])
          + check_coverage(manifests, configured, ignores)
          + check_stale(manifests, configured))


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--list", action="store_true", help="print detected manifests per ecosystem")
  args = parser.parse_args()

  files = git_files()
  if args.list:
    for ecosystem, directories in sorted(find_manifests(files).items()):
      for directory, paths in sorted(directories.items()):
        print(f"{ecosystem:15} {directory:45} {', '.join(PurePosixPath(p).name for p in paths)}")
    return 0

  ignore_path = ROOT / IGNORE_FILE
  ignore_text = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
  findings = run(files, read_text(CONFIG), ignore_text)
  for finding in findings:
    print(finding)
  if findings:
    print(f"\nDependabot coverage check FAILED: {len(findings)} problem(s) found.")
    return 1
  print("Dependabot coverage check passed: all dependency manifests are tracked.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
