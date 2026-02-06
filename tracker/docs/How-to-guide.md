# How to Deploy Intel® SceneScape with Tracker Service alongside Controller in Analytics-Only Mode

This guide explains how to deploy Intel® SceneScape with the separate Tracker service, where the Scene Controller runs in analytics-only mode and consumes tracked objects from the Tracker service via MQTT.

## Overview

The Tracker service is a high-performance C++ microservice that handles multi-object tracking, coordinate transformation, and Kalman filtering. When deployed, the Scene Controller operates in analytics-only mode, focusing on analytics processing (regions, tripwires, sensors) while the Tracker service manages object tracking across cameras.

### Limitations (Experimental Feature)

- Child scenes are not supported in analytics-only mode
- Camera and scene detection data processing is skipped in the Controller
- The Controller's internal tracker is disabled

## Docker Compose deployment

The simplest way to deploy with the Tracker service is using the `demo-tracker` make target.

### Build and Start

```bash
# Set super user password
export SUPASS=<your-password>

# Build all images (including tracker) and start demo
make demo-tracker
```

This command:
1. Builds all Intel® SceneScape images including the Tracker service
2. Initializes sample data volumes
3. Sets `CONTROLLER_ENABLE_ANALYTICS_ONLY=true` environment variable
4. Starts services using Docker Compose with the `tracker` profile

Note: demo-tracker uses build-all to ensure the tracker image (a non-core service)
is built alongside core services. The tracker compose profile does not enable the
experimental mapping or cluster_analytics services even though their images exist.

### Stop

```bash
docker compose --profile tracker down
```

### Restart

After initial setup, you can restart without rebuilding:

```bash
export SUPASS=<your-password>
docker compose --profile tracker up -d
```

## Related Documentation

- [Tracker Service Documentation](../README.md)
- [Tracker Service Architecture](../../docs/design/tracker-service.md)
- [Controller User Guide](../../controller/docs/user-guide/overview.md)
- [Controller Analytics-Only Mode](../../controller/docs/user-guide/get-started.md#running-in-analytics-only-mode)
