# Stream Manager — Event-Based Video Storage and Retrieval

## Scope

This folder covers **one** possible use case: **ONVIF cameras synchronized with NTP**, so
frame timestamps are carried in the RTSP stream and can be used to align and retrieve video
around analytics events.

**Out of scope:**

- Replay / restreaming of stored video.
- Cameras that do **not** provide synchronized timestamps in the stream.

Two variants are documented:

- **Without Sensor Manager** — streams are registered manually by `source_uri` / camera id.
- **With Sensor Manager** — streams are discovered and referenced by `sensor_id` (Sensor
  Manager namespace); optional camera control is handled by the Sensor Manager API.

## Contents

| Variant | Design doc (arch & sequence diagrams + API summary) | OpenAPI spec |
| --- | --- | --- |
| Without Sensor Manager | [stream-manager-without-sensor-manager.md](stream-manager-without-sensor-manager.md) | [stream-manager-api-without-sensor-manager.yaml](stream-manager-api-without-sensor-manager.yaml) |
| With Sensor Manager | [stream-manager-with-sensor-manager.md](stream-manager-with-sensor-manager.md) | [stream-manager-api-with-sensor-manager.yaml](stream-manager-api-with-sensor-manager.yaml) |

## Viewing the API spec with Swagger UI

```bash
# Check out the branch with the specs
git fetch origin
git checkout tdorau/stream-manager-api-draft

# Serve the spec with a live Swagger UI (default: http://localhost:8000)
npx swagger-ui-watcher docs/design/stream-manager/stream-manager-api-without-sensor-manager.yaml
# or the with-Sensor-Manager variant:
npx swagger-ui-watcher docs/design/stream-manager/stream-manager-api-with-sensor-manager.yaml
```

If you are working on a remote machine, forward the port (e.g. `8000`) to your local
machine. This is easiest via your IDE's port-forwarding feature, after which open
<http://localhost:8000> in your browser.
