# How to Upgrade Scenescape

This guide provides step-by-step instructions to upgrade your Scenescape deployment to a new version. By completing this guide, you will:

- Migrate configuration and data directories.
- Deploy the latest version of Scenescape.
- Validate and troubleshoot common upgrade issues.

This task is essential for maintaining access to the latest features and fixes in Scenescape while preserving existing data and services.

## Prerequisites

Before You Begin, ensure the following:

- You have an existing Scenescape v1.4.0 installation with volumes `scenescape_vol-db`, `scenescape_vol-media`, `scenescape_vol-migrations`, and `scenescape_vol-models` or directory `model_installer/models/`.

## How to Upgrade Scenescape from v1.4.0

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

## Re-check 2D Regions, Tripwires, and Sensor Areas on GLB Scenes

Starting with 2026.3.0, the 2D view positions content using the world coordinates of the map image's bottom-left corner (the map origin). Before, it assumed this corner was at world `(0, 0)`. The database upgrade regenerates the 2D thumbnail, scale, and origin for every scene whose map is a `.glb` file.

For scenes that get a non-zero origin, regions, tripwires, and singleton sensor areas (circle or polygon) drawn in the 2D view before the upgrade will appear shifted on the 2D map. This is expected. Their stored world coordinates are not modified, and the new position on the map is their true world position. Shapes placed by eye against the old map were placed in the wrong world location, and analytics have been evaluated against that location.

The upgrade logs a warning for each affected scene, for example:

```text
Scene 3 (Warehouse) now has 2D map origin (-12.400, -8.150) m. Its 4 region(s), 1 tripwire(s) and 0 sensor area(s) keep their stored world coordinates but will appear shifted on the 2D map; re-check them.
```

For each scene listed, open it in the Web UI, compare the regions, tripwires, and sensor areas with the floor plan and the 3D view, and redraw any that are misplaced.

## Model Management During Upgrade

Starting from 1.4.0 version, Scenescape stores models in Docker volumes instead of the host filesystem. This provides several benefits:

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
