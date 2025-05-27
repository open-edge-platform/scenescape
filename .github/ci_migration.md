# 🧭 CI Migration Tracker: Jenkins → GitHub Actions

This document tracks the progress of migrating our CI/CD pipelines from **Jenkins (Jenkinsfile + Groovy)** to **GitHub Actions**.

---

## 📦 Migration Goals

- ✅ Replace Jenkins stages with GitHub Actions workflows or composite actions
- ✅ Reuse modular scripts (`.sh`) and composite actions (`action.yml`)
- ✅ Maintain feature parity (build types, environments, artifacts, ...)
- ✅ Improve transparency and ease of collaboration

---

## 🗂️ Migration Status Overview

| Jenkins Stage               | Status          | GitHub Actions Equivalent            | Assigned To    | Notes              |
|-----------------------------|-----------------|--------------------------------------|----------------|--------------------|
| `Workspace`                 | 🟡 In Progress  | `.github/actions/workspace-setup`    | @sbelhaik      | Testing ongoing    |
| `Build`                     | 🟡 In Progress  | `Makefile`                           | @sbelhaik      | Testing ongoing    |
| `Run Tests`                 | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Run Performance Tests`     | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Run Stability Tests`       | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Publish Test Report`       | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Coverage Report`           | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Metrics`                   | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Upload docker image`       | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Release burndown chart`    | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Virus Scan`                | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Trivy Docker Scan`         | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Pre-Requisites for OSPDT`  | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Create Release Package`    | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Generate Release Notes`    | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Protex`                    | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Protex Commercial`         | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Code Review`               | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `1CICD: SCANS`              | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `SDLE Upload artifact`      | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Static Code Analysis`      | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Upload to Artifactory`     | ⬜ Not Started  | TBD                                  | Unassigned     |                    |
| `Post upload validation`    | ⬜ Not Started  | TBD                                  | Unassigned     |                    |

---

## ✅ Completed Migration Details

### 1. `Workspace` Stage

- Migrated to: `.github/actions/workspace-setup`
- Includes:
  - `check_and_set-build-type.sh`
  - `checkout-autolm-scripts.sh`
- Sets: `BUILD_TYPE`, `VERSION`, `ARTIFACTORY_PATH`, `SW_PACKAGE_DIR`, `TEST_TEMPLATE`

### 2. `Tests & Scans - Build` Stage

- Create docker image for SceneScape in `Makefile`
- Use `open-edge-platform/orch-ci/.github/workflows/pre-merge.yml@main`to run build

---

## 🧪 Migration Testing Workflow

A temporary GitHub Actions workflow is used to test each migrated stage individually.

**File**: `.github/workflows/migration-tests.yml`
**Trigger**: Manual via `workflow_dispatch` or on `ci/migration-*` branches

---

## 🧑‍💻 Collaboration Guidelines

- Branch naming: `ci/migration-<stage>`
- Open PRs referencing this file and the relevant issue
- Use checklist in PRs:
  - [ ] Replicate stage logic
  - [ ] Create/Update composite action
  - [ ] Add necessary bash script
  - [ ] Validate output with debug
  - [ ] Document result here

---

## 🔗 Related Resources

- Jenkinsfile (legacy): `[ci/Jenkinsfile](https://github.com/intel-innersource/applications.ai.scene-intelligence.opensail/blob/main/ci/Jenkinsfile)`
- GitHub Actions reference: [docs.github.com/actions](https://docs.github.com/actions)
- Migration planning issue: [issues](https://github.com/open-edge-platform/scenescape/issues)
- Central hub for CI: [orch-ci](https://github.com/open-edge-platform/orch-ci)

---
