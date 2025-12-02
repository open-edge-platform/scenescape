# How to Upgrade Intel® SceneScape

This guide provides step-by-step instructions to upgrade your Intel® SceneScape deployment to a new version. By completing this guide, you will:

- Migrate configuration and data directories.
- Deploy the latest version of Intel® SceneScape.
- Validate and troubleshoot common upgrade issues.

This task is essential for maintaining access to the latest features and fixes in Intel® SceneScape while preserving existing data and services.

## Prerequisites

Before You Begin, ensure the following:

- You have an existing Intel® SceneScape v1.4.0 installation with volumes `scenescape_vol-db`, `scenescape_vol-media`, `scenescape_vol-migrations`, and `scenescape_vol-models` or directory `model_installer/models/`.

## How to Upgrade Intel® SceneScape from v1.4.0

1. **Checkout latest sources**:

   ```bash
   git checkout main
   ```

2. **Back up old database**:

   ```bash
   make backupdb
   ```

3. **Build the New Release**:

   ```bash
   make rebuild-all
   ```

4. **Run the upgrade-database script**:

   ```bash
   bash manager/tools/upgrade-database
   ```

5. **Bring up services to verify upgrade**:

   ```bash
   SUPASS=<password> make demo
   ```

6. **Log in to the Web UI** and verify that data and configurations are intact.

## Model Management During Upgrade

Starting from 1.4.0 version, Intel® SceneScape stores models in Docker volumes instead of the host filesystem. This provides several benefits:

- **Automatic Preservation**: Models are automatically preserved during upgrades as Docker volumes persist across container recreations.
- **No Manual Copy Required**: You no longer need to manually copy `model_installer/models/` during upgrades.
- **Reduced Disk Usage**: Models are not duplicated between host filesystem and containers.

### Managing Models

- **To reinstall models**: `make install-models`
- **To clean models**: `make clean-models` (this will remove the Docker volume)
- **To check existing models in volume**: `docker volume ls | grep vol-models`

### Legacy Installations

If upgrading from a version that used host filesystem model storage (`model_installer/models/`), the models will be automatically reinstalled to the new Docker volume during the first deployment.

## Troubleshooting

1. **pg_backup Container Already Running Error**:
   - Stop all active containers:
     ```bash
     docker stop $(docker ps -q)
     ```
   - Re-run the above steps for upgrade.
