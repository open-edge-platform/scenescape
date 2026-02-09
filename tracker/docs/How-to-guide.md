# How to Deploy Intel® SceneScape with Tracker Service alongside Controller in Analytics-Only Mode

This guide explains the updated Docker Compose workflow to deploy the Tracker service while running the Scene Controller in analytics-only mode.

## Build and start Tracker + Controller (analytics-only)

1. Export the super-user password (required by the web service):

```bash
export SUPASS=<your-password>
```

2. Build images (ensure the `tracker` image is available):

```bash
# Builds all images including non-core tracker image
make build-all
```

3. Start the Controller in analytics-only mode together with the Tracker service:

```bash
# Start analytics-only controller + tracker
docker compose --profile analytics --profile tracker up -d
```

Notes:
- The `analytics` profile sets `CONTROLLER_ENABLE_ANALYTICS_ONLY=true` in the compose file.
- If you also need experimental services (mapping, cluster-analytics), add `--profile experimental`.

### Stop

```bash
# Stop analytics + tracker
docker compose --profile analytics --profile tracker down
```

### Restart (no rebuild)

```bash
export SUPASS=<your-password>
docker compose --profile analytics --profile tracker up -d
```

## Start full demo with `demo-all`

The repository `Makefile` provides a `demo-all` target which builds everything, initializes sample data and starts Docker Compose with the `analytics`, `tracker`, and `experimental` profiles.

Usage:

```bash
# Set super-user password then run demo-all
export SUPASS=<your-password>
make demo-all
```

What `demo-all` does:
- Runs `make build-all` to build all images (core + experimental)
- Runs `make init-sample-data` to prepare volumes and sample files
- Invokes the compose helper with: `--profile analytics --profile tracker --profile experimental`

### Stop the full demo:

```bash
docker compose --profile analytics --profile tracker --profile experimental down
```

### Restart the full demo:

```bash
docker compose --profile analytics --profile tracker --profile experimental up -d
```

## Related Documentation

- [Tracker Service Documentation](../README.md)
- [Tracker Service Architecture](../../docs/design/tracker-service.md)
- [Controller User Guide](../../controller/docs/user-guide/overview.md)
- [Controller Analytics-Only Mode](../../controller/docs/user-guide/get-started.md#running-in-analytics-only-mode)
