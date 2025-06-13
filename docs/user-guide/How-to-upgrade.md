# How to Upgrade Intel® SceneScape

This guide provides step-by-step instructions to upgrade your Intel® SceneScape deployment to a new version. By completing this guide, you will:

- Back up your existing Intel® SceneScape deployment.
- Migrate configuration and data directories.
- Deploy the latest version of Intel® SceneScape.
- Validate and troubleshoot common upgrade issues.

This task is essential for maintaining access to the latest features and fixes in Intel® SceneScape while preserving existing data and services.

## Prerequisites

Before You Begin, ensure the following:

- You have an existing Intel® SceneScape installation with directories `db/`, `media/`, `migrations/`, `secrets/`, `model_installer/models/`, and a `docker-compose.yml` file.
- You have obtained the latest Intel® SceneScape release tar file (`NEW_SCENESCAPE_TAR`).
- You know the path to your current installation (`OLD_PATH`).

## Steps to Upgrade Intel® SceneScape

1. **Backup the Current Installation**:

   ```bash
   tar -cpzf backup_scenescape_${OLD_VERSION}.tar.gz OLD_PATH
   ```

2. **Extract the New Release**:

   ```bash
   tar -xzf NEW_SCENESCAPE_TAR -C NEW_SCENESCAPE_DIR
   ```

3. **Copy Configuration and Data**:

   ```bash
   cp -r ${OLD_PATH}/model_installer/models ${NEW_SCENESCAPE_DIR}/
   cp -r ${OLD_PATH}/manager/secrets ${NEW_SCENESCAPE_DIR}/
   cp ${OLD_PATH}/docker-compose.yml ${NEW_SCENESCAPE_DIR}/
   ```

4. **Regenerate TLS Certificates**:

   ```bash
   make -BC ./tools/certificates deploy-certificates
   ```

   > **Warning**: This will overwrite any existing self-signed certificates. If using a custom PKI, follow your own certificate provisioning process.

5. **Run the Deployment Script**:

   ```bash
   ./deploy.sh
   ```

   Proceed with "yes" when prompted to back up the database.

6. **Verify Deployment**:
   - Confirm that Intel® SceneScape starts correctly and the web UI is accessible.

7. **Restore Additional Services** (if applicable):
   - Edit `docker-compose.yml` in `NEW_SCENESCAPE_DIR` to merge previous service definitions.
   - Use `sample_data/docker-compose-example.yml` as a reference.

   Restart the updated deployment:

   ```bash
   docker compose up
   ```

8. **Log in to the Web UI** and verify that data and configurations are intact.

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

3. **TLS Certificate Issues**:
   - Re-run:
     ```bash
     make -BC ./tools/certificates deploy-certificates
     ```

4. **Tracker Failures in UI**:
   - Verify that `percebro` containers are correctly configured with updated arguments.
