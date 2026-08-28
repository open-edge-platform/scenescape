# Stream Manager — Event-Based Video Storage and Retrieval

## Scope

This folder covers **one** possible use case: **ONVIF cameras synchronized with NTP**, so
frame timestamps are carried in the RTSP stream and can be used to align and retrieve video
around analytics events.

**Out of scope:**

- Replay / restreaming of stored video.
- Cameras that do **not** provide synchronized timestamps in the stream.

Streams are discovered and referenced by `sensor_id` (Sensor Manager namespace); optional
camera control is handled by the Sensor Manager API.

## Contents

- [stream-manager.md](stream-manager.md) — design doc (arch & sequence diagrams + API summary)
- [stream-manager-api.yaml](stream-manager-api.yaml) — OpenAPI spec

## Viewing the API spec with Swagger UI

```bash
# Check out the branch with the specs
git fetch origin
git checkout tdorau/stream-manager-api-draft

# Serve the spec with a live Swagger UI (default: http://localhost:8000)
npx swagger-ui-watcher docs/design/stream-manager/stream-manager-api.yaml
```

If you are working on a remote machine, forward the port (e.g. `8000`) to your local
machine. This is easiest via your IDE's port-forwarding feature, after which open
<http://localhost:8000> in your browser.
