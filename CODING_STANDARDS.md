# SceneScape Coding Standards & Practices

## Table of Contents

- [Overview](#overview)
- [Python Standards](#python-standards)
- [JavaScript Standards](#javascript-standards)
- [C++ Standards](#c-standards)
- [Development Tools](#development-tools)
- [Branches and Commits](#branches-and-commits)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Test Writing Standards](#test-writing-standards)
- [Makefile Standards](#makefile-standards)

## Overview

When developing in SceneScape, use the following standards and practices to ensure your commits are accepted. While we do our best to make sure these practices are consistent, they are subject to change.

## Python Standards

### Imports

The order of file imports should be:

1. System imports (os, sys; python-native modules)
2. Third party imports (scipy, numpy; modules you have to pip-install)
3. SceneScape imports

Within each section, order imports alphabetically.

```python
# System imports
import os
import sys

# Third party imports
import numpy as np
import scipy

# SceneScape imports
from sscape.utils import helper
```

### Style Guidelines

The team follows [PEP 8](https://peps.python.org/pep-0008/) with the following SceneScape-specific modifications:

#### Line Length

- Lines should not be longer than **95 characters** as a general rule
- Some exceptions for readability are acceptable for very long shell commands

#### Indentation

- Python indent is **2 spaces**, with space characters not tabs

#### Blank Lines

- Only use a **single blank line** as a separator, never 2 or more

#### Naming Conventions

- **CamelCase/CapWords** for class names and class methods
  - Class names begin with an uppercase letter
  - Method names begin with a lowercase letter
- **snake_case** for variables (e.g., `my_variable`)
- **ALL_CAPS** for constants
- **Acronyms** must be in ALL CAPS
  - If you start an acronym with a capital letter, make the rest ALL CAPS too
  - Example: `updateROI` not `updateRoi`
  - Abbreviations are not acronyms: `CamCalib` (Camera Calibration) should not be ALL CAPS
- **Non-public class attributes** begin with an underscore

#### Functions and Methods

- Must end with a **return statement**, even if they don't return any values
- If the docstring is longer than the function, the function is probably not necessary
- If a method is not cohesive (random collection of things), refactor it
- Cohesive methods cannot have names like: `something_and_something_else`
- Use **type hints** to specify expected types of arguments and return types

#### License Headers

- Review existing files and ensure new files have the same license header

#### Command Line Programs

Python programs meant to be run from the command line:

- Must have `#!/usr/bin/env python3` shebang as first line
- Must have executable bits set in filesystem (`chmod +x`)
- File name must be **all lowercase**
- Should **not** have `.py` extension on filename

#### Preferred (Not Strictly Enforced)

- Line break **before** binary operator
- String quotes:
  - Single quotes for dictionary keys
  - Double quotes for strings with more than one character
  - Single quotes for strings with a single character
- Whitespace in expressions and statements: identical to PEP-8

### Design Principles

#### Exception Handling

- Avoid using try-catch with the generic `Exception` type
- Always use the **specific exception type** you want to handle (improves testability)
- **Never suppress an exception** unless the function can proceed normally after the exception
- If an exception cannot be handled within the containing method, **bubble up the error** to where it can be properly handled

## JavaScript Standards

Follow the coding style from [JavaScript Standard Style](https://github.com/standard/standard/blob/master/RULES.md) with these exceptions:

- **Use semicolons** after statements
- **No space required** after function name in declaration

## C++ Standards

### Includes

Follow the same principles as Python:

1. System includes (`<cmath>`, `<iostream>`)
2. Third party includes (`<pybind11>`, etc.)
3. SceneScape includes

Add macros at the top of the file, after includes, unless a specific header needs a specific definition.

### Focus on Readability

#### Object/Memory Access

- Use explicit `this->` for modifying/accessing members
- Avoid using memory directly in vectors/arrays
- When looping vectors/arrays, check range once then use `vector[idx]` instead of `vector.at(idx)`
- **Pass C++ objects by reference** unless absolutely necessary
- Arguments in macros should always be used inside parentheses

#### Code Style

- Use opening brace `{` on a **new line** (makes it easier to know where blocks begin)
- **One line for each logic test**:

```cpp
if (point->is3D()
    && abs(point->x()))
```

#### Comparisons

Use **"RHS LHS"** format in conditional statements:

```cpp
// Good
if (value == variable) { ... }
if (nullptr != pointer) { ... }

// Bad (traditional but not preferred)
if (variable == value) { ... }
if (pointer) { ... }
```

This makes it explicit you're handling pointers or expecting specific variable types, and avoids assignments in conditionals by mistake.

Note: `if (false == function(var))` explicitly calls out the comparison against Boolean, which is implicit in `if (!function(var))`.

#### General Requirements

- All functions should end with a **return statement**, even void functions
- All code should be compiled with flags so compiler treats **warnings as errors** (`CFLAGS -Werror -Wall -Wextra`)
- Make the code easier to read and understand for humans

## Development Tools

### Recommended IDEs

- **emacs** or **vscode**

### VS Code Configuration

If using VS Code, configure your IDE with these settings:

```json
{
  "editor.tabSize": 2,
  "python.linting.pycodestyleEnabled": true,
  "python.linting.pycodestyleArgs": [
    "--indent-size=2",
    "--ignore=E121,E302",
    "--max-line-length=95"
  ]
}
```

### Code Quality Extensions

- Use **Sourcery** and/or **Radon** extensions for cyclomatic complexity and code improvement hints
- Use **CodeMetrics** extension for JavaScript code metrics

## Branches and Commits

### Branch Naming

- **Bug fixes**: `fix/xxx`
- **New features**: `feature/xxx`
- **Release hotfixes**: `hotfix/xxx`

### Commit Guidelines

- Pull/merge requests should contain **only one thing**, not a mixture of fixes or features
- If something broken outside your feature/fix prevents merging, fix that in a **separate pull request** first
- **Do not submit** pull/merge requests until someone has verified your work is complete and working

## Pull Request Guidelines

### PR Requirements

- **Title** must contain the JIRA ticket ID
- **Merge commit** must also contain the JIRA ticket ID
- **Description** must contain:
  1. Steps on how to verify the changes work
  2. Draft test case link

### PR Process

- If PR is not ready for review, **convert to draft**
- Before requesting review, ensure associated **JIRA ticket is in current sprint**
- Add description providing context missing from JIRA ticket
- Include **"How to verify"** section if acceptance criteria doesn't cover it
- Prefer **smaller, self-contained PRs** (easier to review, catch bugs, merge faster)
- **Attribution**: Use honor system - add co-authors in commit message if someone helped with code/design

## Test Writing Standards

### Event Handling

- **Avoid arbitrary sleep** to wait for events
- Instead, set timeout while waiting such that:
  - If event fires before timeout → test succeeds
  - If event doesn't fire before timeout → test fails
- When sleep is unavoidable, use **iterative sleep** (sleep short time, check condition) for early completion

### Test Naming

#### Makefile Target

- `<descriptive-name-with-words-separated-by-dashes>`
- All lowercase
- **Never exceed 28 characters**
- Examples:
  - Old: `test-scene-crud` → New: `scene-crud`
  - Old: `test-sail-53` → New: `upload-different-format-maps`

#### Test Source Files

- **TEST_NAME**: `SAIL-T<ZEPHYR_SCALE_TICKET_NUMBER>`
- **File name**: `tc_<description>.py` (e.g., `tc_different_format_maps.py`)

### Test Implementation

- **Test ordering**: Alphabetically in Makefile unless comments specify otherwise
- Tests should log **PASS or FAIL** via `record_test_result` function
- **Failed tests** must exit so `make` reports the error
- Tests must output errors visible in developer console and Jenkins log
- Tests must report output for Jenkins Tests tab
- **Single test** = **single entry** in Jenkins Tests tab
- If exception occurs and test can't still pass → try/except doesn't belong
- If conditional fails and test can't still pass → use `assert` not `if`

### Selenium Tests

- **Do not use `By.XPATH`** to find elements (fragile to document structure changes)
- Instead, add unique ID or name to element and use `By.ID` or `By.NAME`

### Test Class Inheritance

- **Non-unit tests** must inherit from `Diagnostic` class
- **Functional tests** must inherit from `FunctionalTest`
- **UI tests** must inherit from `UserInterfaceTest`
- **New tests** must not add new things to `diagnostic.py`, `functional.py`, or `userinterface.py`
- Methods can be moved from existing tests if they'll be used by new test and existing test
- **New tests** must not import `common_test_utils.py` or `common_ui_test_utils.py`

## Makefile Standards

Based on the existing Makefile patterns in the SceneScape project:

### Structure and Organization

- Use **SPDX license headers** at the top of every Makefile
- Set `SHELL=/bin/bash` and `.SHELLFLAGS=-o pipefail -c` for robust script execution
- Group related targets logically, not alphabetically (except where noted)
- Include descriptive comments with issue numbers (e.g., `# NEX-T10422`)

### Variable Definitions

- Use `:=` for immediate assignment (evaluated once), `=` for recursive assignment (evaluated each time used)
- Define reusable variables at the top (`IMAGE`, `VERSION`, `TEST_DATA`, etc.)
- Use `$(eval ...)` for complex variable assignments within recipes
- Use `?=` for variables that can be overridden (e.g., `NPROCS?=...`)

### Recipe Standards

- Start recipes with `@set -ex` for error handling and debugging
- Use `$(eval VAR=value)` to set recipe-local variables
- Always include logging with timestamps: `$(shell date -u +"%F-%T")`
- Use `tee -i $(LOGFILE)` for output capture
- Include "MAKE_TARGET: $@" in log files
- End with descriptive echo statements

### Test Organization

- Group tests into logical categories (`basic-acceptance-tests`, `standard-tests`, etc.)
- Use underscore prefix for internal targets (e.g., `_functional-tests`)
- Include parallel execution where appropriate (`-j $(NPROCS)`)
- Use `-k` flag to continue on errors during test suites

### Logging Standards

- Create timestamped log files: `$@-$(shell date -u +"%F-%T").log`
- Store logs in organized directories under `$(TEST_DATA)`
- Always include the make target name in log files
- Use consistent log file naming patterns
