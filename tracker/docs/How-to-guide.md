# How to Deploy Scenescape with Tracker + Analytics

This guide explains the Docker Compose workflow to deploy the Tracker service
together with the standalone Analytics service (without the Scene Controller).

The Tracker publishes tracked objects on `scenescape/data/scene/...`. The
Analytics service consumes that topic and publishes regulated detections,
region/tripwire events, and sensor-correlated output.

## Supported detection inputs

Tracker subscribes to `scenescape/data/camera/{sensor_id}` for sensor IDs
registered in the scene. Each detection must use exactly one of these forms:

- `bounding_box_px`: pixel-space box projected using the sensor's configured
  camera calibration.
- `translation` and `size`: sensor-frame position and dimensions in metres.
  Tracker transforms the position with the pose configured for that sensor ID.

Either form may include an optional `rotation` quaternion in `[x, y, z, w]`
order. Tracker composes it with the sensor pose and tracks the resulting world
Z-yaw; pitch and roll are not retained. A zero-norm quaternion is treated as no
orientation. The complete input contract is in
[`camera-data.schema.json`](../schema/camera-data.schema.json).

For example, a 3D vehicle detection can be sent as:

```json
{
  "id": "atag-qcam1",
  "timestamp": "2026-01-20T10:05:01.482Z",
  "objects": {
    "vehicle": [
      {
        "translation": [1.25, -2.5, 0.75],
        "size": [4.0, 1.8, 1.6],
        "rotation": [0.0, -0.3429, 0.0, 0.9394]
      }
    ]
  }
}
```

## Build and start Tracker + Analytics

1. Export the super-user password (required by the web service):

```bash
export SUPASS=<your-password>
```

2. Build images (ensure the `tracker` and `analytics` images are available):

```bash
# Builds all images including non-core tracker image
make build-all
```

3. Start the Tracker and Analytics services:

```bash
# Starts tracker + analytics (analytics is included in the tracker profile)
docker compose --profile tracker up -d
```

Notes:

- The `tracker` Compose profile starts both the `tracker` and `analytics`
  services. The Scene Controller (`scene`) is not started.
- If you also need the mapping or cluster-analytics services, add
  `--profile mapping` and/or `--profile cluster-analytics`.

### Stop

```bash
docker compose --profile tracker down
```

## Start Tracker + Analytics demo with `demo-tracker`

The repository `Makefile` provides a `demo-tracker` target which builds
everything, initializes sample data, and starts Docker Compose with the
`tracker` profile.

Usage:

```bash
# Set super-user password then run demo-tracker
export SUPASS=<your-password>
make demo-tracker
```

What `demo-tracker` does:

- Runs `make build-all` to build all images
- Runs `make video-source-up` to convert sample videos and start the
  standalone mediamtx/ffmpeg video-source stack
- Invokes the compose helper with: `--profile tracker`

### Stop Tracker + Analytics demo

```bash
docker compose --profile tracker down
```

### Restart Tracker + Analytics demo

```bash
docker compose --profile tracker up -d
```

## Related Documentation

- [Tracker Service Documentation](../README.md)
- [Tracker Service Architecture](../../docs/design/tracker-service.md)
- [Analytics Service Documentation](../../docs/user-guide/microservices/analytics/analytics.md)
- [Controller User Guide](../../docs/user-guide/microservices/controller/controller.md)
- [How to Enable Observability (Experimental)](../../docs/user-guide/other-topics/how-to-enable-observability.md) — enabling OpenTelemetry metrics and tracing for the tracker service.
