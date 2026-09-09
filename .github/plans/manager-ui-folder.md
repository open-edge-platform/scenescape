## Plan: Manager Backend Frontend Migration

Move the Django source tree to `manager/backend` and the React/Vite package to `manager/frontend`, while preserving Django imports, runtime paths, generated static assets, bundle names, and `/static/ui/...` URLs.

**Steps**

1. **Establish the target contract**
   - Target layout:
     - `manager/backend/manage.py`
     - `manager/backend/manager/`
     - `manager/frontend/`
   - Preserve the Django package name `manager`.
   - Preserve `/home/scenescape/Scenescape/manager` inside containers.
   - Keep generated UI assets at `manager/backend/manager/static/ui/`.
   - Keep bundle names and Django `{% static 'ui/...' %}` references unchanged.

2. **Move the source trees**
   - Move `manager/src/*` to `manager/backend/`.
   - Move `manager/ui/` to `manager/frontend/`.
   - Preserve package files, templates, migrations, static assets, lockfiles, and SPDX headers.

3. **Update frontend build configuration**
   - Update `manager/frontend/vite.config.ts` to output to `../backend/manager/static/ui`.
   - Keep the six JavaScript entry points and `manager-ui.css`.
   - Update frontend README paths and commands.

4. **Update Makefile orchestration**
   - Change frontend commands from `cd ui` to `cd frontend`.
   - Update `JSLIBDIR`, Prettier paths, generated-output paths, and secret symlink paths.
   - Preserve `ui-install`, `ui-build`, `build-image`, and `SKIP_UI=1` behavior.

5. **Update Docker and Python packaging**
   - Update `manager/Dockerfile` copy, install, permission, static, OpenCV hash, and test-image paths.
   - Verify `setup.py`, `settings.py`, `BASE_DIR`, version lookup, static paths, and package discovery after relocation.
   - Keep runtime image and service names unchanged.

6. **Update tests and migration tooling**
   - Update:
     - `tests/sscape_tests/conftest.py`
     - `tests/sscape_tests/settings_unittest.py`
     - `tests/sscape_tests/secrets.sh`
     - `manager/tools/generate_migrations.sh`
     - `manager/MIGRATIONS.md`
   - Search for stale `manager/src`, `src/manager`, and `manager/src/django` references.

7. **Update documentation and metadata**
   - Update `manager/Agents.md`, the frontend README, `.github/plans/manager-ui.md`, editor setup docs, JavaScript skill guidance, `.gitignore`, `REUSE.toml`, and CI path assumptions.
   - Keep root Makefile and workflow entry points stable where possible.

8. **Audit and clean up**
   - Run a repository-wide search for old paths.
   - Remove stale references and verify that templates still use the unchanged `/static/ui/...` contract.
   - Do not retain compatibility symlinks unless a temporary transition is specifically required.

**Verification**

1. Run `make -C manager ui-install` and `make -C manager ui-build`.
2. Verify all six bundles, `manager-ui.css`, SPDX headers, and generated output location.
3. Run frontend typecheck and lint.
4. Run `python manage.py check`, package/import smoke checks, migrations, and `collectstatic --noinput`.
5. Build the manager and test images with `make -C manager` and `make -C manager test-build`.
6. Run repository lint, formatting, Docker, and REUSE checks.
7. Run focused manager and UI tests, rebuilding container images first.
8. Perform a runtime smoke test covering manager startup, login, migrations, representative pages, and static asset HTTP responses.

**Scope decisions**

- Included: source layout, build paths, packaging paths, tests, tooling, documentation, and CI references.
- Excluded: API behavior changes, Django package renaming, image/service renaming, moving assets to `frontend/dist`, and Python packaging normalization.
- A future asset move to `frontend/dist` should be a separate change with an explicit copy or `collectstatic` contract.
