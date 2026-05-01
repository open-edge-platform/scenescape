<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Manager - Agent Guide

## Why This Service Exists

- Provides the control plane for SceneScape: user-facing management APIs/UI and persistent metadata.
- Coordinates configuration workflows across services without owning real-time object tracking state.

## What Matters Most

- Correct persistence and migration safety.
- API contract stability for operators and service integrations.
- Security posture for auth, input validation, and secret handling.

## Non-Obvious Constraints

- Manager is authoritative for configuration metadata; runtime tracking state is external.
- Database migration quality is a production safety issue, not a housekeeping task.
- Cross-service workflows depend on contract consistency more than UI presentation details.
- Operational failures often surface as partial workflow completion across services; preserve transactional intent where possible.

## KPI Targets

| KPI                                          |    Target | Why                              |
| -------------------------------------------- | --------: | -------------------------------- |
| API latency (p95) for control operations     | <= 200 ms | UX and automation responsiveness |
| Migration success rate in CI and staging     |      100% | Upgrade safety                   |
| Auth/permission regression count             |         0 | Security and compliance          |
| Config write-to-read consistency delay (p95) |    <= 1 s | Operational predictability       |
| 5xx rate on core management endpoints        |    < 0.1% | Reliability                      |

## Change Guidance

- Treat schema/model changes as migration-driven changes with rollback thinking.
- Keep API behavior stable; version explicitly if breaking changes are unavoidable.
- Preserve server-side authorization checks near protected operations.
- Do not leak sensitive fields in logs, errors, or serialized responses.

## When Editing This Service

- If models change, include migration review and compatibility notes.
- If API serializers/views change, verify permission boundaries and negative cases.
- If workflow orchestration changes, validate end-to-end behavior across dependent services.

## Verification Gate (Standardized)

| Change class                              | Command path                                                                                                                                                                                                                                                    | Pass criteria                                                                                                    |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| API/schema contracts                      | `make manager && make -C manager test-build && http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests django-integration-unit` | Exit code 0; no new API contract/schema/permission regressions.                                                  |
| Workflow/business logic                   | `http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests logic-unit-tests`                                                      | Exit code 0; changed workflow tests pass for positive and negative paths.                                        |
| Performance/reliability-sensitive changes | `http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests openapi-validation`                                                    | Exit code 0; no new endpoint failures and measured p95 API latency regression is within agreed budget.           |
| Migrations/persistence                    | `make manager && make -C manager test-build && http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests django-integration-unit` | Exit code 0; migration-related tests pass and DB-impacting changes include apply/check evidence in the PR notes. |
