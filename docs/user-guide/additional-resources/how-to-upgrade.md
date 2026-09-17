# How to Upgrade Scenescape

Scenescape supports only release-to-next-release transitions listed in
`tools/upgrade/compatibility.json`. Upgrade through each adjacent release when
more than one transition is required. Unknown transitions and downgrades are
refused.

The automated workflow supports Docker Compose deployments. Kubernetes users
must use the read-only readiness report and operator guidance in the
[Kubernetes README](../../../kubernetes/README.md#upgrade-readiness-and-guardrails).

## Prerequisites

- Keep the source deployment available until post-upgrade verification passes.
- Use the same Compose files, profiles, project name, and secrets directory as
  the running deployment.
- Provide enough space for a PostgreSQL logical dump and archives of every
  persistent Docker volume.
- Resolve uncommitted deployment changes before upgrading, or explicitly accept
  them with `ALLOW_DIRTY=true` after review.
- Schedule downtime. Backup creation stops and restarts the deployment without
  deleting volumes.

## Plan the upgrade

Run preflight from the target release checkout:

```bash
make upgrade-plan \
   SOURCE_VERSION=<installed-version> \
   TARGET_VERSION=<target-version> \
   COMPOSE_PROJECT_NAME=<project-name>
```

Review the JSON report. It includes resolved services, Compose inputs, profiles,
volumes, Git state, and transition metadata. An `unsupported` status means no
authorized adjacent path exists. An `action_required` status identifies warnings
that require review.

For custom Compose files or profiles, invoke the CLI directly and repeat each
argument:

```bash
tools/upgrade/scenescape-upgrade release-plan \
   --source-version <installed-version> \
   --target-version <target-version> \
   --project-name <project-name> \
   --compose-file compose.yml \
   --compose-file compose.override.yml \
   --profile controller
```

## Back up before cutover

Create and verify a PostgreSQL dump, persistent-volume archives, deployment
configuration, and secrets:

```bash
make upgrade-apply \
   SOURCE_VERSION=<installed-version> \
   TARGET_VERSION=<target-version> \
   COMPOSE_PROJECT_NAME=<project-name> \
   BACKUP_DIR=<protected-backup-parent> \
   UPGRADE_STATE_DIR=<protected-operation-directory>
```

The command stops at `awaiting_database_cutover` after checksum verification.
Store the backup and operation directory securely; both contain sensitive
deployment material. Do not continue if verification fails.

## Confirm cutover and resume

After reviewing the verified backup, prepare target images, recreate services,
apply committed Django migrations, and check Compose service health:

```bash
make upgrade-resume \
   UPGRADE_STATE_DIR=<protected-operation-directory> \
   IMAGE_ACTION=pull
```

Use `IMAGE_ACTION=build` for a source-built deployment or `IMAGE_ACTION=none`
when target images were prepared separately. The operation state and append-only
event log allow a failed operation to resume from the same command.

## Verify

Re-run migration and Compose health verification at any time:

```bash
make upgrade-verify UPGRADE_STATE_DIR=<protected-operation-directory>
```

Also verify deployment-specific behavior: log in to the manager, inspect scene
and camera configuration, confirm media access, publish detector data through
MQTT, and exercise enabled mapping, analytics, and ReID services.

## Roll back data

Rollback is destructive: it overwrites target Docker volumes with the verified
pre-upgrade archives.

```bash
make upgrade-rollback UPGRADE_STATE_DIR=<protected-operation-directory>
```

After restoration, start the source release using the Compose configuration
saved in the backup. The command does not automatically switch Git revisions or
image tags.

Never use `rebuild-core`, `rebuild-all`, `clean-volumes`, `demo-close`, or
`docker compose down -v` during an upgrade. Those commands can remove data.

## Certificate-only maintenance

Certificate renewal is independent of release upgrades:

```bash
make certificate-check MINIMUM_VALID_DAYS=30
make certificate-renew COMPOSE_PROJECT_NAME=<project-name>
```

Renewal preserves Django, database, MQTT, and service authentication secrets.
It rotates the complete generated TLS trust set and recreates Compose services.
Distribute the new CA certificate to browsers, adapters, and external clients.
