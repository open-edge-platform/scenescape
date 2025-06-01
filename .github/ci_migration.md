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

| Jenkins Stage               | Status          | GitHub Actions Equivalent                             | Assigned To    | Notes              |
|-----------------------------|-----------------|-------------------------------------------------------|----------------|--------------------|
| `Workspace`                 | ✅ Done         | `pre-merge` job `Setup environment` step              | @sbelhaik      |                    |
| `Build`                     | 🟡 In Progress  | `pre-merge-pipeline` job `Build Project` step         | @sbelhaik      | Code review        |
| `Run Tests`                 | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Run Performance Tests`     | 🟡 In Progress  | `pre-merge-pipeline` job `Run Performance Tests` step | @sbelhaik      | Code review        |
| `Run Stability Tests`       | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Publish Test Report`       | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Coverage Report`           | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Metrics`                   | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Upload docker image`       | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Release burndown chart`    | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Virus Scan`                | ⬜ Not Started  | TBD                                                   | @dmytroye      |                    |
| `License Check`             | ⬜ Not Started  | TBD                                                   | @dmytroye      |                    |
| `Trivy Docker Scan`         | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Pre-Requisites for OSPDT`  | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Create Release Package`    | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Generate Release Notes`    | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Protex`                    | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Protex Commercial`         | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Code Review`               | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `1CICD: SCANS`              | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `SDLE Upload artifact`      | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Static Code Analysis`      | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Upload to Artifactory`     | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |
| `Post upload validation`    | ⬜ Not Started  | TBD                                                   | Unassigned     |                    |

---

## ✅ Completed Migration Details

### 1. `Workspace` Stage

- Migrated to: `.github/workflows/migration-tests.yml`
- Includes:
  - `check_and_set-build-type.sh`
- Sets: `BUILD_TYPE`, `VERSION`, `ARTIFACTORY_PATH`, `SW_PACKAGE_DIR`, `TEST_TEMPLATE`
- Makefile target `build: check-tag build-certificates build-images`
- Workflow: `.github/workflows/migration-tests.yml`
- Job: `pre-merge`
- Step: `Setup environment`

### 2. `Tests & Scans - Build` Stage

- Create docker image for SceneScape in `Makefile`
- Workflow: `.github/workflows/migration-tests.yml`
- Job: `pre-merge-pipeline`
- Step: `Build Project`

### 3. `Tests & Scans - Run Performance Tests` Stage

- Create docker image for SceneScape in `Makefile`
- Workflow: `.github/workflows/migration-tests.yml`
- Job: `pre-merge-pipeline`
- Step: `Run Performance Tests`
- Note: comment the step because the original stage was explicitely disabled in Jenkinsfile using `when { expression { false } }`

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
