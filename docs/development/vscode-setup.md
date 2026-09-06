# VS Code Setup for Scenescape

This guide configures Visual Studio Code for optimal Scenescape development with cross-module navigation and IntelliSense.

## Prerequisites

- Ubuntu 24.04 LTS
- Python 3.12
- Git
- Visual Studio Code

### Initial Setup

Before configuring VS Code, set up the project environment:

1. **Clone the repository**

   ```bash
   git clone https://github.com/open-edge-platform/scenescape.git -b main
   cd scenescape
   ```

2. **Create and activate virtual environment**

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python dependencies**

   ```bash
   pip install --upgrade pip
   pip install -r controller/requirements-runtime.txt
   pip install -r manager/requirements-runtime.txt
   pip install -r autocalibration/requirements-runtime.txt
   pip install -r model_installer/requirements-runtime.txt

   # Optional: Install test requirements
   pip install -r manager/test/requirements-test.txt
   ```

4. **Build project components**
   ```bash
   make
   ```

## Quick Setup

Assuming you have the Scenescape project cloned and Python environment ready:

1. Open VS Code
2. Use **File → Open Folder** and select the `scenescape` directory
3. VS Code will load the workspace with the project structure

## Required Extensions

Install these essential VS Code extensions for Python development:

### Python Extension Pack

- **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** (Microsoft)
  - Core Python language support
  - Debugging, linting, and code formatting
  - Extension ID: `ms-python.python`

- **[Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance)** (Microsoft)
  - Fast Python language server
  - Type checking and IntelliSense
  - Auto-imports and code navigation
  - Extension ID: `ms-python.vscode-pylance`

### Installation Steps

1. Open Extensions view (`Ctrl+Shift+X`)
2. Search for "Python" and install the **Microsoft** Python extension
3. Search for "Pylance" and install the **Microsoft** Pylance extension

> **Tip:** You can also copy and paste the extension IDs directly into the search box:
>
> - `ms-python.python`
> - `ms-python.vscode-pylance`

## Workspace Configuration

Create `.vscode/settings.json` in the project root, or press `Ctrl+Shift+P` → "Preferences: Open Workspace Settings (JSON)"

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.terminal.activateEnvironment": true,
  "python.analysis.extraPaths": [
    "${workspaceFolder}",
    "${workspaceFolder}/manager/src/manager",
    "${workspaceFolder}/tests",
    "${workspaceFolder}/scene_common/src",
    "${workspaceFolder}/controller/src",
    "${workspaceFolder}/autocalibration/src",
    "${workspaceFolder}/manager/src"
  ],
  "python.analysis.autoImportCompletions": true,
  "python.analysis.autoSearchPaths": true
}
```

## What This Configuration Enables

- **Automatic Python Environment**: Uses `.venv/bin/python` automatically
- **Cross-Module Navigation**: Jump between modules with F12 (Go to Definition)
- **IntelliSense**: Auto-completion across all project components
- **Import Resolution**: Finds imports in `scene_common`, `controller`, `manager`, `autocalibration`, and `tests`

## Verify Setup

1. Open any Python file in `scene_common/src/` or `controller/src/`
2. Check that VS Code status bar shows Python interpreter from `.venv`
3. Verify that imports and IntelliSense work across modules
4. Test cross-module navigation:
   - Right-click on any import from `scene_common` → "Go to Definition" (F12)
   - Use "Find All References" (Shift+F12) on functions/classes
   - Verify autocomplete works for imports from other modules

## Troubleshooting

- If Python interpreter is not detected, press `Ctrl+Shift+P` → "Python: Select Interpreter" → Choose `.venv/bin/python`
- If imports are not resolved, restart VS Code or reload the window (`Ctrl+Shift+P` → "Developer: Reload Window")

## Testing Configuration

VS Code's Python test extension discovers tests via pytest. The configuration in `.vscode/settings.json` controls which test directories are scanned:

```json
{
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": [
    "tests",
    "cluster_analytics/tests/service",
    "--import-mode=importlib"
  ]
}
```

**Configuration details:**

- `"tests"` — Discovers all tests in the main test directory, including cluster analytics unit tests
- `"cluster_analytics/tests/service"` — Discovers component tests for the cluster analytics service
- `"--import-mode=importlib"` — Uses importlib import mode to avoid namespace collisions between isolated test packages

**Note:** Cluster analytics unit tests have their own `pytest.ini` configuration (`tests/sscape_tests/cluster_analytics/pytest.ini`) that disables the Django plugin. This is necessary because these tests don't require Django and would fail trying to import `manager.secrets` if Django initialization were attempted.

**To view tests in VS Code:**

1. Open the **Test Explorer** panel (left sidebar, flask icon)
2. Click the refresh button to rescan for tests
3. Expand the test tree to see all tests, including cluster analytics tests
