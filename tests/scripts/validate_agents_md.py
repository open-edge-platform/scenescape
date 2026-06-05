#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Validate that agent instruction files stay consistent with the codebase.

The agent instruction set for SceneScape is intentionally split across several
router files (`AGENTS.md`, `.github/copilot-instructions.md`,
`.cursor/rules/scenescape.mdc`), per-service `Agents.md` guides, and procedural
skill files under `.github/skills/`. These files point agents at concrete files
(skills, configs, docs) and concrete `make` commands. When the code moves but
the docs do not, autonomous agents follow stale instructions.

This script catches that drift by verifying, for every agent instruction file:

  1. AGENTS.md exists at the repository root and is substantive (>100 chars).
  2. Every relative Markdown link target resolves to a real file/directory.
  3. Every documented `make <target>` command is a real target in the root
     Makefile or one of the service Makefiles.

It exits non-zero (with a clear report) when any reference is broken, so it can
be wired into CI / a pre-commit hook as an agent-instruction freshness gate.
"""

import os
import re
import subprocess
import sys

TEST_NAME = "NEX-T10590"

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Router / instruction files that make navigational and command claims.
AGENT_DOC_GLOBS = [
  "AGENTS.md",
  ".github/copilot-instructions.md",
  ".cursor/rules/scenescape.mdc",
]

# Markdown inline link: [text](target)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Documented make invocations: backtick-wrapped or at line start (outside fences).
MAKE_CMD_BACKTICK_RE = re.compile(r"`make\s+([A-Za-z0-9][A-Za-z0-9_./-]*)")
MAKE_CMD_LINE_RE = re.compile(
  r"^\s*make\s+([A-Za-z0-9][A-Za-z0-9_./-]*)", re.MULTILINE
)

# `make FOO=bar` passes a variable, not a target; ignore well-known ones plus any
# token immediately followed by '='.
MAKE_VARIABLE_TOKENS = {
  "JOBS", "FOLDERS", "SUPASS", "CERTDOMAIN", "BUILD_DIR", "HOURS",
  "COMPOSE_PROJECT_NAME", "DEMO_K8S_MODE", "FILE", "BACKEND",
}


def find_agent_docs():
  """Return absolute paths of all existing agent instruction files."""
  docs = []
  for rel in AGENT_DOC_GLOBS:
    path = os.path.join(REPO_ROOT, rel)
    if os.path.isfile(path):
      docs.append(path)
  # Per-service guides: <service>/Agents.md
  for entry in sorted(os.listdir(REPO_ROOT)):
    candidate = os.path.join(REPO_ROOT, entry, "Agents.md")
    if os.path.isfile(candidate):
      docs.append(candidate)
  # Procedural skills: .github/skills/**/*.md
  skills_dir = os.path.join(REPO_ROOT, ".github", "skills")
  if os.path.isdir(skills_dir):
    for root, _dirs, files in os.walk(skills_dir):
      for name in sorted(files):
        if name.endswith(".md"):
          docs.append(os.path.join(root, name))
  return sorted(docs)


def read_text(path):
  with open(path, "r", encoding="utf-8") as handle:
    return handle.read()


def is_external_link(target):
  target = target.strip()
  if not target:
    return True
  if target.startswith("#"):
    return True
  return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target))


def check_links(doc_path):
  """Verify every relative Markdown link in doc_path resolves to a real path."""
  failures = []
  doc_dir = os.path.dirname(doc_path)
  text = read_text(doc_path)
  for raw_target in MARKDOWN_LINK_RE.findall(text):
    target = raw_target.strip()
    if is_external_link(target):
      continue
    # Drop anchors / query fragments: docs/foo.md#section -> docs/foo.md
    clean = target.split("#", 1)[0].split("?", 1)[0]
    if not clean:
      continue
    resolved = os.path.normpath(os.path.join(doc_dir, clean))
    if not os.path.exists(resolved):
      rel_doc = os.path.relpath(doc_path, REPO_ROOT)
      failures.append(f"{rel_doc}: broken link -> '{target}'")
  return failures


def discover_make_targets():
  """Collect make targets from the root Makefile and every service Makefile.

  Uses `make -rpn` (dry-run database print) which expands generated targets
  (e.g. per-folder build/rebuild rules) without executing any recipe.
  """
  targets = set()
  make_dirs = [REPO_ROOT]
  for entry in sorted(os.listdir(REPO_ROOT)):
    sub = os.path.join(REPO_ROOT, entry)
    if os.path.isfile(os.path.join(sub, "Makefile")):
      make_dirs.append(sub)

  target_line = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_./-]*)\s*:")
  for directory in make_dirs:
    try:
      result = subprocess.run(
        ["make", "-rpn"],
        cwd=directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=120,
      )
    except (OSError, subprocess.SubprocessError):
      continue
    for line in result.stdout.decode("utf-8", errors="ignore").splitlines():
      match = target_line.match(line)
      if match:
        targets.add(match.group(1))
  return targets


def strip_fenced_code_blocks(text):
  """Return doc text with fenced code blocks removed.

  Skills and guides often embed Makefile examples (e.g. `print-%` pattern rules)
  that teach conventions rather than name repo targets. Prose like "where to
  make changes" is also common; line-start matching is limited to non-fence text.
  """
  lines = []
  in_fence = False
  for line in text.splitlines():
    if line.strip().startswith("```"):
      in_fence = not in_fence
      continue
    if not in_fence:
      lines.append(line)
  return "\n".join(lines)


def _skip_make_token(source, match):
  """True when the captured token is not a concrete make target."""
  end = match.end(1)
  if end < len(source) and source[end] in "=*":
    return True
  return False


def extract_documented_make_targets(text):
  """Collect make targets from intentional command references in doc text."""
  targets = []
  for match in MAKE_CMD_BACKTICK_RE.finditer(text):
    if _skip_make_token(text, match):
      continue
    targets.append(match.group(1))
  unfenced = strip_fenced_code_blocks(text)
  for match in MAKE_CMD_LINE_RE.finditer(unfenced):
    if _skip_make_token(unfenced, match):
      continue
    targets.append(match.group(1))
  return targets


def check_make_commands(doc_path, known_targets):
  """Verify every documented `make <target>` references a real target."""
  failures = []
  text = read_text(doc_path)
  rel_doc = os.path.relpath(doc_path, REPO_ROOT)
  for target in extract_documented_make_targets(text):
    if target in MAKE_VARIABLE_TOKENS:
      continue
    if target not in known_targets:
      failures.append(f"{rel_doc}: documented 'make {target}' has no matching Makefile target")
  return failures


def main():
  failures = []

  agents_md = os.path.join(REPO_ROOT, "AGENTS.md")
  if not os.path.isfile(agents_md):
    failures.append("AGENTS.md is missing from the repository root")
  elif len(read_text(agents_md).strip()) <= 100:
    failures.append("AGENTS.md exists but is not substantive (<= 100 characters)")

  docs = find_agent_docs()
  if not docs:
    failures.append("No agent instruction files found to validate")

  known_targets = discover_make_targets()
  if not known_targets:
    failures.append("Could not enumerate any make targets; cannot validate documented commands")

  for doc in docs:
    failures.extend(check_links(doc))
    if known_targets:
      failures.extend(check_make_commands(doc, known_targets))

  if failures:
    print(f"{TEST_NAME}: FAIL")
    print("AGENTS.md validation found stale references:")
    for failure in failures:
      print(f"  - {failure}")
    return 1

  print(f"Validated {len(docs)} agent instruction file(s) against the codebase.")
  print(f"{TEST_NAME}: PASS")
  return 0


if __name__ == "__main__":
  sys.exit(main())
