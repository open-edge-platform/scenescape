<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Zephyr Test Management Tools

Command line tools for managing Scenescape test cycles and results in Jira Zephyr.

| Script                   | Purpose                                                                   |
| ------------------------ | ------------------------------------------------------------------------- |
| `create_zephyr_cycle.py` | Create a test cycle (test run) and optionally populate it with test cases |
| `upload_to_zephyr.py`    | Publish pytest/xUnit results into an existing test cycle                  |

## Contents

- [Setup](#setup)
- [create_zephyr_cycle.py](#create_zephyr_cyclepy)
- [upload_to_zephyr.py](#upload_to_zephyrpy)
- [End-to-end pipeline](#end-to-end-pipeline)
- [How it works](#how-it-works)
- [Troubleshooting](#troubleshooting)

## Setup

Configuration is read from environment variables provided by `utils/.env`:

| Variable          | Purpose                                                    |
| ----------------- | ---------------------------------------------------------- |
| `JIRA_TEAM`       | Team custom field value (`Vision_AI`)                      |
| `JIRA_PROJECT`    | Zephyr project key (`ITEP`)                                |
| `ZEPHYR_API_BASE` | `https://jira.devtools.intel.com/rest/atm/1.0/`            |
| `JIRA_API_BASE`   | `https://jira.devtools.intel.com/rest/api/2/`              |
| `JIRA_TOKEN`      | `<jira personal access token>`                             |
| `JIRA_USER`       | Jira user key recorded as the executor of uploaded results |

## create_zephyr_cycle.py

Creates a Zephyr test cycle and optionally adds test cases to it.

### Options

| Flag                  | Required | Meaning                                                |
| --------------------- | -------- | ------------------------------------------------------ |
| `--jira-token`        | yes      | Personal access token                                  |
| `--folder`            | yes      | Folder where the **cycle** is created                  |
| `--test-cases-folder` | yes      | Folder(s) to pull **test cases** from                  |
| `--version`           | yes      | Fix version, validated against `libraries/versions.py` |
| `--cycle`             | no       | Cycle name, defaults to `YYYY-MM-DD HH:MM:SS`          |
| `--add-tests`         | no       | Populate the cycle with test cases                     |
| `--status`            | no       | Comma-separated statuses to include                    |
| `--automated`         | no       | `true` = automated only, `false` = manual only         |
| `--debug`             | no       | Verbose logging                                        |

Valid `--version` values are listed in `libraries/versions.py`

### Create empty cycle, auto-named

```bash
python utils/create_zephyr_cycle.py --jira-token=$JIRA_TOKEN \
  --folder="/Vision_AI/SceneScape/Daily" \
  --test-cases-folder="/Vision_AI/SceneScape/Functional Tests" \
  --version="EAL-2026.3"
```

### Create empty cycle with an explicit name

```bash
python utils/create_zephyr_cycle.py --jira-token=$JIRA_TOKEN \
  --folder="/Vision_AI/SceneScape/Daily" \
  --test-cases-folder="/Vision_AI/SceneScape/Functional Tests" \
  --version="EAL-2026.3" \
  --cycle="Release candidate smoke"
```

### Create cycle containing every test case in the folder

```bash
python utils/create_zephyr_cycle.py --jira-token=$JIRA_TOKEN \
  --folder="/Vision_AI/SceneScape/Daily" \
  --test-cases-folder="/Vision_AI/SceneScape/Functional Tests" \
  --version="EAL-2026.3" --add-tests
```

### Create cycle with approved and automated tests only

```bash
python utils/create_zephyr_cycle.py --jira-token=$JIRA_TOKEN \
  --folder="/Vision_AI/SceneScape/Daily" \
  --test-cases-folder="/Vision_AI/SceneScape/Functional Tests" \
  --version="EAL-2026.3" --add-tests \
  --status="Approved" --automated=true
```

### Manual test pass for QA

```bash
python utils/create_zephyr_cycle.py --jira-token=$JIRA_TOKEN \
  --folder="/Vision_AI/SceneScape/Daily" \
  --test-cases-folder="/Vision_AI/SceneScape/Functional Tests" \
  --version="EAL-2026.3" --add-tests \
  --status="Approved" --automated=false \
  --cycle="Manual regression EAL-2026.3"
```

### Include draft cases

```bash
python utils/create_zephyr_cycle.py --jira-token=$JIRA_TOKEN \
  --folder="/Vision_AI/SceneScape/Daily" \
  --test-cases-folder="/Vision_AI/SceneScape/Functional Tests" \
  --version="EAL-2026.3" --add-tests \
  --status="Draft,Approved"
```

### Pull test cases from several folders

Zephyr matches folders exactly, so every subfolder must be listed explicitly:

```bash
python utils/create_zephyr_cycle.py --jira-token=$JIRA_TOKEN \
  --folder="/Vision_AI/SceneScape/Daily" \
  --test-cases-folder="/Vision_AI/SceneScape/ADMIN,/Vision_AI/SceneScape/Functional Tests,/Vision_AI/SceneScape/Performance Tests,/Vision_AI/SceneScape/UI Tests" \
  --version="EAL-2026.3" --add-tests \
  --status="Approved" --automated=true
```

The cycle key is printed in the log as `Created test cycle with key: NEX-Cxxxx`.

## upload_to_zephyr.py

Reads a JUnit/xUnit XML report and writes each outcome into a test cycle.

### Options

| Flag                 | Required | Meaning                                                          |
| -------------------- | -------- | ---------------------------------------------------------------- |
| `path` (positional)  | yes      | Path to the JUnit/xUnit XML file                                 |
| `-a`, `--jira-token` | yes      | Personal access token                                            |
| `-F`, `--folder`     | no       | Comma-separated folders used to build the test case lookup table |
| `-C`, `--cycle`      | no       | Cycle name                                                       |
| `--cycle-key`        | no       | Cycle key, for example `NEX-T#####`                              |
| `--comment`          | no       | Comment attached to every execution                              |
| `--debug`            | no       | Verbose logging                                                  |

### Result mapping

`libraries/xunit.py` reads the `name` attribute of each `<testcase>` element
(falling back to `classname`) and extracts a key matching `NEX-T\d{5,6}`:

| XML child element        | Zephyr status  |
| ------------------------ | -------------- |
| `<failure>` or `<error>` | `Fail`         |
| `<skipped>`              | `Not Executed` |
| none                     | `Pass`         |

### Upload by cycle key

```bash
python utils/upload_to_zephyr.py -a $JIRA_TOKEN \
  --cycle-key="NEX-Cxxxx" \
  -F "/Vision_AI/SceneScape/Functional Tests" \
  reports/functional_results.xml
```

### Upload against several lookup folders

```bash
python utils/upload_to_zephyr.py -a $JIRA_TOKEN \
  --cycle-key="NEX-Cxxxx" \
  -F "/Vision_AI/SceneScape/ADMIN,/Vision_AI/SceneScape/Functional Tests,/Vision_AI/SceneScape/Performance Tests,/Vision_AI/SceneScape/UI Tests" \
  reports/functional_results.xml
```

### Annotated upload with build provenance

```bash
python utils/upload_to_zephyr.py -a $JIRA_TOKEN \
  --cycle-key="NEX-Cxxxx" \
  -F "/Vision_AI/SceneScape/Functional Tests" \
  --comment="Build ${BUILD_NUMBER} - commit $(git rev-parse --short HEAD)" \
  reports/functional_results.xml
```

### Troubleshoot tests upload

```bash
python utils/upload_to_zephyr.py --debug -a $JIRA_TOKEN \
  --cycle-key="NEX-Cxxxx" \
  -F "/Vision_AI/SceneScape/Functional Tests" \
  reports/functional_results.xml
```

Test names with no counterpart in Jira are skipped with a warning and written to
`/tmp/not_found.txt`, the remaining results still upload.

## End-to-end pipeline

```bash

# 1. Create the nightly cycle with approved automated tests
python utils/create_zephyr_cycle.py --jira-token=$JIRA_TOKEN \
  --folder="/Vision_AI/SceneScape/Daily" \
  --test-cases-folder="/Vision_AI/SceneScape/Functional Tests" \
  --version="EAL-2026.3" --add-tests \
  --status="Approved" --automated=true

# 2. Run the suite, producing reports/functional_results.xml
pytest tests/functional --junitxml=reports/functional_results.xml --log-level=ERROR

# 3. Publish results into the cycle key logged by step 1
python utils/upload_to_zephyr.py -a $JIRA_TOKEN \
  --cycle-key="NEX-Cxxxx" \
  -F "/Vision_AI/SceneScape/Functional Tests" \
  --comment="Nightly EAL-2026.3" \
  reports/functional_results.xml
```

Use the same folder list in both steps. A test case that is not on the cycle can
still receive a result, but the cycle then contains cases the run never scoped.
