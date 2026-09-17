---
name: scenescape-upgrade
description: >-
  Safely plan, execute, resume, verify, or roll back SceneScape upgrades and renew deployment
  certificates without losing data or rotating unrelated credentials. Use this skill whenever a
  user mentions upgrading or updating SceneScape, moving between releases, database or Django
  migrations, expired or expiring certificates, backup/restore for an upgrade, rollback, or Helm
  and Kubernetes upgrade readiness. Route all operations through tools/upgrade/scenescape-upgrade;
  never improvise destructive Docker, volume, database, or secret commands.
license: Apache-2.0
compatibility: >-
  Requires a SceneScape checkout containing tools/upgrade/scenescape-upgrade. Docker Compose is
  required for mutating deployment operations. Helm and kubectl are required for the read-only
  Kubernetes report.
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
metadata:
  argument-hint: "<operation> <deployment-root> [source-version] [target-version]"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# SceneScape Upgrade

## Purpose

Guide an operator through supported upgrade and certificate workflows while preserving deployment
data and credentials. Repository tooling owns discovery, compatibility rules, backup, migration,
certificate replacement, state, verification, and rollback. This skill only gathers inputs,
invokes that tooling, interprets its JSON, and enforces confirmation boundaries.

## Canonical sources

- CLI and behavior: `tools/upgrade/scenescape-upgrade`
- Supported release transitions: `tools/upgrade/compatibility.json`
- Operator guide: `docs/user-guide/additional-resources/how-to-upgrade.md`
- Kubernetes limitations: `kubernetes/README.md#upgrade-readiness-and-guardrails`

Read the compatibility manifest before discussing release support. Do not copy its transition
matrix into this skill or infer support from version ordering.

## Safety rules

- Run discovery and planning before mutation. Summarize impact, downtime, warnings, and blockers.
- Treat CLI JSON and its `status` field as authoritative. Expected `action_required` and
  `unsupported` results use nonzero exit codes; parse the JSON instead of describing them as tool
  crashes.
- Never print, request, or place passwords, tokens, CA passphrases, private keys, or secret file
  contents in chat or command arguments.
- Preserve the exact deployment root, Compose project name, repeated Compose files, profiles,
  secrets directory, certificate domain, and SAN settings discovered or supplied by the user.
- Ask for explicit confirmation immediately before certificate renewal, database cutover, or
  destructive restore. A general request to "upgrade" is not confirmation for those boundaries.
- Never invoke `rebuild-core`, `rebuild-all`, `clean-*`, `demo-close`,
  `docker compose down -v`, or ad hoc volume deletion during an upgrade.
- Do not use `clean-secrets` or `init-secrets` to renew certificates. Certificate renewal must
  preserve Django, database, MQTT, admin, and service authentication credentials.
- Do not automate Kubernetes backup, restore, application upgrade, or rollback. The supported
  Kubernetes operation is a read-only report followed by operator guidance.
- Credential rotation is outside this skill. Clearly distinguish it from TLS certificate renewal.
- Stop on malformed JSON, `failed`, `unsupported`, missing backup verification, or unresolved
  blockers. Do not invent a workaround that bypasses the repository tooling.

## Gather inputs

Reuse values already supplied in the conversation. Ask only for missing information needed by the
selected route:

1. Operation: release plan/apply/resume/verify/rollback, certificate check/renewal, standalone
   backup/verification/restore, database check/migration, or Kubernetes readiness.
2. Deployment type: Docker Compose or Kubernetes/Helm.
3. Deployment root containing the target SceneScape checkout.
4. For release/database work: installed source version and desired target version.
5. For Compose: project name, all Compose files in precedence order, enabled profiles, and custom
   secrets directory. Use defaults only when the user confirms the standard deployment layout.
6. For stateful operations: protected backup parent and operation-state directory.
7. For certificate work: minimum validity threshold, certificate domain, and existing extra broker,
   web, and ReID server SAN host labels.
8. For Kubernetes: Helm release and namespace.

Do not ask for secret values. If a terminal prompts for one, instruct the user to enter it directly
in the terminal.

## Build the common CLI arguments

Run the CLI from the target checkout. Prefer it over Make wrappers when custom Compose files,
profiles, deployment roots, or secrets directories are involved.

```bash
cd <deployment-root>
tools/upgrade/scenescape-upgrade <command> \
  --deployment-root <deployment-root> \
  --project-name <project-name> \
  --compose-file <base-compose-file> \
  --compose-file <override-compose-file> \
  --profile <profile>
```

Omit only arguments that genuinely do not apply. Repeat `--compose-file` and `--profile` in the
user's effective order; never collapse them into a guessed default command.

## Route the operation

### Release upgrade

1. Read `tools/upgrade/compatibility.json` and confirm the exact adjacent transition exists.
2. Run `release-plan` with source/target versions and the common Compose arguments.
3. Present `blockers`, `warnings`, detected volumes, Git state, image action, expected downtime,
   and backup destination. A dirty checkout requires the user to resolve it or explicitly approve
   `--allow-dirty` after reviewing the changed paths.
4. Ask whether to create the verified pre-upgrade backup.
5. After confirmation, run `release-apply` with `--operation-dir`, `--output-dir`, and
   `--secrets-dir` when custom. It must stop at `awaiting_database_cutover`.
6. Report the backup path and verification result. Ask separately for database cutover confirmation.
7. After confirmation, run `release-resume --confirm-database-cutover` with the saved operation
   directory and the correct `--image-action` (`pull`, `build`, or `none`).
8. Run `release-verify`, summarize migration and Compose health, then ask the user to validate
   manager login/API, scene and camera counts, media, MQTT, controller readiness, and enabled
   optional services.

For an interrupted operation, inspect `<operation-dir>/upgrade-state.json`, report its phase, and
resume only through the matching CLI command. Do not rerun earlier phases manually.

### Release rollback

Read the saved operation state and verify that `rollback_available` is true. Explain that restoring
volumes overwrites target data and that the source release must subsequently be started with the
saved deployment configuration. After explicit destructive confirmation, run:

```bash
tools/upgrade/scenescape-upgrade release-rollback \
  --operation-dir <operation-dir> \
  --confirm-destructive-restore \
  --overwrite
```

### Certificate lifecycle

Run `certificate-check` first. Summarize missing, valid, and renewal-required certificates without
displaying certificate contents. Preserve certificate identity arguments from the existing
deployment.

Explain that default deployments cannot re-sign individual leaves because the generated CA
passphrase is not retained. `certificate-renew` therefore stages and validates a complete TLS trust
set, backs up the old TLS material, preserves non-TLS credentials, atomically replaces TLS files,
and recreates services. Explain that external clients must receive the new CA. Ask for confirmation,
then run `certificate-renew` with all discovered Compose, domain, SAN, secrets, and output settings.

### Standalone backup and restore

Use `backup`, then `backup-verify`. Report the generated directory and manifest verification. For
restore, verify first, explain that non-empty volumes require overwrite, and ask for explicit
destructive confirmation before passing `--overwrite`.

### Database-only migration

Run `database-check` for an exact manifest transition. Report expected, applied, and pending
committed migrations. Ask for cutover confirmation before `database-migrate`. Never run
`makemigrations`, direct SQL, or the legacy database script as a substitute. PostgreSQL engine
upgrades remain unsupported unless the manifest and canonical tooling explicitly implement them.

### Kubernetes or Helm

Run only:

```bash
tools/upgrade/scenescape-upgrade kubernetes-report \
  --release <release> \
  --namespace <namespace>
```

Report the Helm revision, PVCs, StatefulSets, Certificate readiness, and every `emptyDir` warning.
State that automated Kubernetes backup, restore, apply, and rollback are unsupported. Refer the
operator to the canonical dry-run, rollout, history, and rollback guidance; do not execute mutating
Helm or kubectl commands.

## Status handling

| JSON status       | Meaning                          | Action                                                                     |
| ----------------- | -------------------------------- | -------------------------------------------------------------------------- |
| `ready`           | Check or phase completed         | Continue only to the next documented boundary                              |
| `action_required` | Review or confirmation is needed | Summarize required action and pause                                        |
| `unsupported`     | No canonical path exists         | Stop and identify the unsupported transition/operation                     |
| `failed`          | Operation failed                 | Report the redacted error and saved state; offer supported resume/rollback |

## Completion report

Report:

- operation and source/target versions;
- deployment type, project/release, Compose inputs or namespace;
- final JSON status and saved operation phase;
- backup and operation-state paths without secret contents;
- verification performed and any checks still requiring the operator;
- rollback availability and exact next supported command when incomplete.

Do not claim a successful upgrade until `release-verify` returns `ready` and the operator-facing
service checks are either completed or clearly listed as pending.
