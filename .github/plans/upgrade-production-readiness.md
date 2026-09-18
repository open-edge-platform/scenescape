<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Upgrade Production Readiness

## Status

Future work. The repository has deterministic Docker Compose upgrade primitives, an adjacent-release
compatibility manifest, unit tests, operator documentation, and the `scenescape-upgrade` skill. This
plan records work deferred from the original implementation and gaps found while reviewing upgrades
of an active production deployment.

Do not describe the upgrade workflow as production-safe for deployments accepting writes until
Phases 1, 2, and 6 pass their acceptance gates.

## Current baseline

The current implementation supports:

- Explicit adjacent transitions from `1.4.0` through `2026.2.0`.
- Separate source and target Compose definitions and checkouts.
- Project-aware logical database dumps and persistent-volume archives.
- PostgreSQL 15 to 17.6 logical transfer.
- Legacy runtime migrations, the validated `0001_initial` bridge, and committed migrations.
- Resumable operation state, backup verification, rollback primitives, certificate trust-set
  replacement, and read-only Kubernetes reporting.
- Stable JSON statuses and a focused unit-test target.

The current backup sequence takes a PostgreSQL dump while the source is running, stops the source
for volume archives, and restarts it while awaiting cutover confirmation. Writes accepted after the
dump can therefore be absent from the target and rollback state. This is the primary production
safety gap.

## Goals

1. Make upgrades of active Compose deployments write-consistent and mutually exclusive.
2. Make interruption, abort, resume, and rollback behavior deterministic at every mutation boundary.
3. Complete the metadata, backup, restore, certificate, and verification contracts deferred from
   the original implementation.
4. Prove supported release transitions with isolated runtime tests, not mocks alone.
5. Keep all operational decisions in `tools/upgrade/`; the skill remains a thin router over stable
   commands and JSON.

## Phase 1: Active-instance maintenance protocol

1. Add explicit operation modes:
   - `online-logical`: a convenience backup that does not claim full rollback consistency.
   - `upgrade`: an authoritative backup taken after writers are quiesced and kept stopped.
2. Discover and record whether source services are running before mutation. Store container IDs,
   Compose project identity, service states, and the observed database endpoint in operation state.
3. Introduce a maintenance boundary before the authoritative dump:
   - Stop or fence every service capable of writing PostgreSQL or persistent application data.
   - Keep only the minimum database service alive for `pg_dump`.
   - Verify no known writer service remains active before dumping.
   - Record the maintenance transition in the append-only event log.
4. Keep the source deployment stopped after the authoritative backup. Do not restart it while
   awaiting database-cutover confirmation.
5. Add an explicit pre-cutover abort command. It may restart the source only if no target mutation
   or irreversible cutover marker has been recorded.
6. Before starting target services, verify that no source service for the saved project is running.
   Refuse cutover if source and target identities cannot be distinguished or exclusivity cannot be
   proven.
7. Define behavior for external writers that are not represented by Compose. Preflight must require
   operator acknowledgement of integrations that can write through APIs, MQTT, or direct database
   access, and the guide must explain how to fence them.

### Phase 1 acceptance

- A write attempted after quiescence is rejected or cannot reach the source deployment.
- The authoritative dump and cold volume archives represent the same maintenance window.
- `release-apply` leaves the source stopped at `awaiting_database_cutover`.
- `release-abort` restores the exact pre-upgrade running state before cutover.
- `release-resume` refuses to start the target while any saved source writer remains active.
- No code path can run source and target writers concurrently against shared persistent data.

## Phase 2: Transactional state and recovery

1. Replace the coarse `awaiting_database_cutover`/`failed` model with durable checkpoints for:
   discovery, maintenance entry, authoritative dump, cold snapshot, backup verification, source
   stopped, target image preparation, database initialization, logical restore, Django migration,
   target startup, service verification, and operator acceptance.
2. Persist an irreversible cutover marker before the first target data mutation. Permit source
   restart only before this marker; afterward permit only forward resume or verified rollback.
3. Make every phase idempotent. Record created containers, networks, volumes, temporary paths, and
   completed validation so resume can distinguish retry from first execution.
4. Generate temporary resource names from Compose project and operation ID. Add checked cleanup for
   temporary resources without deleting deployment volumes or secrets.
5. Retain the original database volume until explicit post-upgrade acceptance. If renaming or
   retaining it is impossible, require and test an immutable equivalent with documented recovery
   guarantees.
6. Harden rollback:
   - Stop and verify target services are inactive.
   - Restore source configuration, secrets, and selected volumes from the verified bundle.
   - Prevent target restart during restoration.
   - Start the source with its saved Compose inputs and verify health.
7. Convert all subprocess, filesystem, JSON, and validation failures into redacted stable JSON with
   the documented `failed` exit code. Never leak a traceback or secret-bearing command context.

### Phase 2 acceptance

- Failure injection after every checkpoint can resume without repeating an unsafe mutation.
- Abort is accepted only before the irreversible marker.
- Rollback from every post-cutover checkpoint restores and verifies the source deployment.
- Repeated resume and rollback commands are idempotent or fail closed with an actionable status.
- Every command failure produces valid redacted JSON.

## Phase 3: Complete preflight and compatibility contracts

1. Extend preflight with:
   - Effective `SECRETSDIR` and required-file presence without secret values.
   - Running container and writer inventory.
   - Actual PostgreSQL server/data version rather than manifest expectation alone.
   - Named-volume labels, bind mounts, ownership, sizes, and free-space estimates.
   - ReID backend and persistence classification.
   - Certificate subjects, SANs, usages, issuers, and expiry.
   - Source/target image digests and configuration fingerprints.
2. Extend each compatibility transition with explicit preconditions, pre/post steps, data migration
   strategy, required free space, rollback prerequisites, and accepted source/target database
   versions.
3. Detect a Helm/Kubernetes deployment rather than trusting only a caller-provided deployment type.
   Compose mutation commands must fail closed when Kubernetes ownership is detected.
4. Detect configuration-file basename collisions when creating backup bundles and preserve relative
   paths instead of overwriting files with the same name.
5. Keep skipped releases, unknown versions, downgrades, physical volume renames, unclassified data,
   and unknown migration strategies fail-closed.

### Phase 3 acceptance

- Preflight reports every item above in redacted machine-readable JSON.
- Insufficient disk space, unknown writers, unsupported database versions, missing secrets, and
  ephemeral required data block mutation.
- Tests cover custom Compose stacks, bind mounts, external volume names, and Kubernetes detection.

## Phase 4: Backup and restore completeness

1. Discover volumes through resolved Compose data and Docker labels; do not rely only on logical
   names or the default project convention.
2. Expand the backup manifest with artifact size, ownership, permissions, source image digest,
   PostgreSQL version, backend identity, consistency mode, and cache inclusion policy.
3. Capture data-bearing bind mounts or reject the upgrade with a precise blocker. Do not silently
   omit host-mounted media, models, datasets, videos, mappings, or ReID data.
4. Preserve migrations, media, datasets, videos, models, NetVLAD data, mapping assets, requested
   caches, ReID data, Compose inputs, `.env`, profile data, and secrets with their permissions.
5. Add compatibility validation before restore, including backend identity and target database
   version checks.
6. Support named-component restore while leaving the original backup immutable.
7. Restore configuration and secrets as explicit components, with collision checks and restrictive
   permissions.
8. Retain `backupdb` as a compatibility wrapper only for the documented deprecation window, then
   remove or redirect legacy `check-db-upgrade` and `upgrade-database` targets away from the
   hard-coded privileged script.

### Phase 4 acceptance

- A non-default project with custom Compose files, bind mounts, secrets path, and both ReID backends
  can be backed up, deleted in an isolated test environment, restored, and compared by checksums,
  ownership, database counts, and backend records.
- Online logical backups are clearly marked insufficient for full release rollback.
- Restore refuses active services, incompatible artifacts, missing checksums, and non-empty targets
  without explicit confirmation.

## Phase 5: Automated post-upgrade verification

1. Capture pre-upgrade invariants in the operation state: representative table counts, scene and
   camera identities/counts, media references and hashes, ReID backend/counts, and enabled optional
   services.
2. Verify after migration:
   - PostgreSQL server version and connectivity.
   - Django `showmigrations` and `migrate --plan` state.
   - Representative row-count and relationship invariants.
   - Manager HTTPS/API reachability and authenticated login.
   - Scene/camera inventory and media access.
   - MQTT publish/subscribe and controller readiness.
   - Enabled mapping, analytics, tracker, and ReID services.
3. Record every check as pass, fail, skipped, or operator-required in stable JSON. A process merely
   being `running` is not sufficient for upgrade success.
4. Keep rollback available until automated checks and explicit operator acceptance both pass. Add a
   finalization command that records acceptance and only then permits cleanup of retained source
   data.

### Phase 5 acceptance

- A successful result proves data and service behavior, not just container health.
- Failed invariants block finalization and preserve rollback assets.
- Optional-service verification follows the resolved Compose profiles and does not assume defaults.

## Phase 6: Runtime and failure-injection test gate

1. Add isolated Docker integration fixtures for every adjacent transition:
   `1.4.0 -> 2025.2 -> 2026.0.0 -> 2026.1.0 -> 2026.2.0`.
2. Seed scenes, cameras, media, users, and representative migration-sensitive records. Verify each
   hop independently before starting the next.
3. Add the active-write race test: attempt a write after backup begins and prove it is rejected or
   included in the authoritative cutover state.
4. Inject failures after every durable checkpoint and verify safe resume, pre-cutover abort, and
   post-cutover rollback.
5. Test non-default project names, custom secrets directories, repeated Compose files, profiles,
   external volume names, and changed source/target Compose definitions.
6. Test VDMS and Qdrant persistence across forced recreation. Treat backend switching as
   incompatible unless a future explicit converter is implemented.
7. Verify hashes of MQTT auth, Django, database, admin, and service credentials remain unchanged
   across upgrade and certificate operations.
8. Add CLI contract tests for all statuses and errors, including malformed manifests, missing
   volumes, insufficient space, bad checksums, unsupported transitions, subprocess failures, and
   redaction.
9. Add canonical Make targets for unit and isolated integration suites. Require both in the upgrade
   readiness gate, along with Python lint, shell lint, formatting, REUSE, documentation links/build,
   and `git diff --check`.

### Phase 6 acceptance

- Every adjacent release fixture passes backup, cutover, migration, verification, and rollback.
- Every interruption point has a passing recovery test.
- The active-write race and source/target exclusivity tests pass.
- The repository has one documented command that runs the complete production-readiness gate.

## Phase 7: Certificate lifecycle completion

1. Add standalone trust-set verification and an affected-services/clients report.
2. Preserve and validate `CERTDOMAIN`, IP SANs, extra DNS SANs, key usages, issuer, expiration,
   secrets directory, and CA handling from the deployed certificate set.
3. Validate key/certificate matches and full chains before activation.
4. Support same-CA leaf renewal only when usable CA material is available. Otherwise fail closed and
   offer separately confirmed full CA replacement.
5. Restart only services consuming changed certificates and verify HTTPS, MQTT TLS/client auth,
   autocalibration, mapping, ReID, hierarchy peers, and external trust distribution.
6. Preserve unrelated credentials and prove preservation through hashes in integration tests.

### Phase 7 acceptance

- Invalid keys, chains, SANs, usages, or expiration fail before installation.
- Failure during activation atomically restores the previous trust set.
- Endpoint tests pass after renewal, and external CA redistribution remains an explicit operator
  action when the CA changes.

## Phase 8: Skill and operator workflow hardening

1. Update the skill and operator guide only after the corresponding tooling and runtime tests land.
2. Make maintenance entry, source-stopped waiting, cutover, abort, rollback, verification, and
   final acceptance distinct confirmation boundaries.
3. Have the skill consume JSON artifacts instead of reconstructing service inventories, transition
   rules, commands, or recovery decisions in conversation.
4. Add skill evaluations for:
   - An active deployment receiving writes.
   - Aborting before cutover.
   - Failure after irreversible cutover.
   - Source/target concurrency detection.
   - Bind-mounted persistent data.
   - Non-default project/profile/secrets inputs.
   - Multi-hop upgrades with independent acceptance at every hop.
5. Keep output concise by reporting status deltas and next supported actions from saved state rather
   than repeating the full procedure on every resume.

### Phase 8 acceptance

- The skill never asks the model to invent a migration or destructive recovery command.
- Every mutating action maps to a tested CLI command and an explicit confirmation boundary.
- Skill claims exactly match the production-readiness test gate.

## Deferred feature scope

These items were excluded from the initial implementation. They remain separate projects unless
explicitly promoted:

- **Credential rotation:** MQTT credentials, Django secret, database password, admin credentials,
  and service authentication. Certificate operations must continue preserving them.
- **Automated Kubernetes mutation:** application upgrade, database/PVC backup and restore, rollback,
  and ReID persistence migration. Continue providing read-only reporting and guarded operator
  guidance until storage-class-aware snapshots and database procedures are implemented and tested.
- **Kubernetes ReID persistence:** the current `emptyDir` must continue blocking claims of complete
  data preservation.
- **Cross-backend ReID conversion:** VDMS and Qdrant backups restore only to the same backend.
- **Skipped-release upgrades:** execute and verify every manifest-listed adjacent hop independently.
- **Generic downgrade and reverse Django migrations:** rollback restores the preserved source state;
  it does not reverse application migrations.
- **Zero-downtime upgrades:** the production-safe target is controlled downtime with writer
  quiescence. High-availability rolling upgrades require a separate compatibility and replication
  design.
- **Default same-CA leaf renewal without retained CA credentials:** full trust-set replacement
  remains the supported fallback and requires external CA redistribution.

## Safety invariants

- Never run `docker compose down -v`, `clean-*`, `demo-close`, or ad hoc destructive commands.
- Never regenerate unrelated secrets during upgrade or certificate maintenance.
- Never print or persist secret values in logs, JSON reports, or command arguments.
- Never infer compatibility from version ordering; use the manifest.
- Never infer source and target Compose definitions are identical.
- Never delete rollback assets before automated verification and explicit operator acceptance.
- Never claim full data preservation when a required volume or bind mount is unclassified,
  ephemeral, or omitted.

## Primary implementation surfaces

- `tools/upgrade/scenescape-upgrade`
- `tools/upgrade/orchestrator.py`
- `tools/upgrade/backup.py`
- `tools/upgrade/preflight.py`
- `tools/upgrade/migration.py`
- `tools/upgrade/certificates.py`
- `tools/upgrade/kubernetes.py`
- `tools/upgrade/compatibility.json`
- `tests/sscape_tests/upgrade/`
- `tests/functional/` or `tests/system/`
- `Makefile`
- `.github/skills/scenescape-upgrade/`
- `docs/user-guide/additional-resources/how-to-upgrade.md`
- `docs/user-guide/additional-resources/hardening-guide.md`
- `docs/user-guide/other-topics/how-to-enable-reidentification.md`
- `kubernetes/README.md`

## Delivery order

Implement Phases 1 and 2 first. Phase 3 can proceed in parallel once the operation-state schema is
stable. Complete Phase 4 before broad runtime rehearsals. Phase 5 defines the evidence consumed by
Phase 6. Phase 7 can proceed independently except for shared state and integration-test plumbing.
Update the skill and final operator claims in Phase 8 only after the relevant gates pass.