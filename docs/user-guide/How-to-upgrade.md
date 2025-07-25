# How to Upgrade Intel® SceneScape

This guide provides step-by-step instructions to upgrade your Intel® SceneScape deployment to a new version. By completing this guide, you will:

- Migrate configuration and data directories.
- Deploy the latest version of Intel® SceneScape.
- Validate and troubleshoot common upgrade issues.

This task is essential for maintaining access to the latest features and fixes in Intel® SceneScape while preserving existing data and services.

## Prerequisites

Before You Begin, ensure the following:

- You have an existing Intel® SceneScape v1.3.0 installation with directories `db/`, `media/`, `migrations/`, `secrets/`, `model_installer/models/`, and a `docker-compose.yml` file.

# How to Upgrade Intel® SceneScape from v1.3.0

1. **Checkout latest SceneScape sources**:

   ```bash
   git checkout main
   ```

2. **Build the New Release**:

   ```bash
   make build-all
   ```

3. **Run the upgrade-database script**:

   ```bash
   bash manager/tools/upgrade-database
   ```

4. **Bring up services to verify upgrade**:

   ```bash
   make demo
   ```

5. **Log in to the Web UI** and verify that data and configurations are intact.

## Troubleshooting

1. **Accidental Execution of deploy.sh in New Directory Before Migration**:
   - Delete `db/`, `media/`, `migrations/`, `secrets/`, `model_installer/models/`, and `docker-compose.yml` in `NEW_SCENESCAPE_DIR`
   - Restart from Step 3

2. **pg_backup Container Already Running Error**:
   - Stop all active containers:
     ```bash
     docker stop $(docker ps -q)
     ```
   - Re-run the deploy script:
     ```bash
     ./deploy.sh
     ```
