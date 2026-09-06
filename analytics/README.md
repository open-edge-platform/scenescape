# Scenescape's Analytics Service

The Analytics microservice is a dedicated MQTT service that computes
region, tripwire, and sensor analytics for objects tracked in a Scenescape
scene, and publishes the resulting detections and events for downstream
consumers. It is deployed as its own container and cooperates with the
broker, Manager, and an upstream Tracker to do so (see
[Quick Start](#quick-start)).

## Key Features

- **Region analytics**: Enter/exit detection and dwell-time tracking for
  polygonal and volumetric regions, including scene-wide sensor regions.
- **Tripwire analytics**: Directional line-crossing detection for tracked
  objects.
- **Sensor analytics**: Correlates environmental (numeric) and attribute
  (discrete) sensor readings with objects located inside a sensor's region,
  maintaining reading/event history per object.
- **Regulated & unregulated detections**: Publishes rate-limited
  (`regulated`) or full-rate (`unregulated`) object detections per scene, with
  per-camera visibility-derived publish rates.
- **Per-region detections**: Publishes the subset of tracked objects
  currently inside each region, filtered by detection type.
- **Event publishing**: Serializes and publishes region/tripwire/sensor
  events (entered, exited, counts, values) with debounce to avoid event
  flooding.
- **Tracker-independent**: Consumes tracked-object messages produced by any
  upstream tracker (e.g. the Tracker service) via a stable `AnalyticsObject`
  contract, with no dependency on the `robot_vision` C++ extension.
- **Multi-scene**: Loads scene configuration (regions, tripwires, sensors,
  cameras) from the REST API or local JSON files and keeps them in sync via
  MQTT database-update notifications.
- **Health check**: Optional HTTP `/healthz` endpoint for container
  orchestration liveness/readiness probes.

## Architecture

```text
Tracker service ──MQTT──▶ Analytics service ──MQTT──▶ Manager / subscribers
                              │
                              ├─ region.py     (enter/exit + dwell)
                              ├─ tripwire.py   (line-crossing)
                              ├─ sensors.py    (environmental/attribute)
                              ├─ engine.py     (per-frame orchestration)
                              ├─ event_publisher.py / event_serializer.py
                              └─ adapters/scene_model.py (AnalyticsScene)
```

- `AnalyticsService` (`service.py`) is the MQTT controller: it subscribes to
  scene-data and sensor topics, drives per-frame analytics, and publishes
  detections and events.
- `AnalyticsScene` (`adapters/scene_model.py`) is a lightweight `SceneModel`
  subclass — regions, tripwires, sensors, and cameras only, with no tracker
  or pose-adjustment state.
- `AnalyticsObject` (`analytics_models.py`) is the stable contract between
  tracked objects and analytics code, decoupling analytics logic from the
  upstream tracker's internal data structures.
- `AnalyticsStateStore` (`state.py`) owns all per-region/per-tripwire
  analytics state per scene.

## MQTT Topics

| Direction | Topic                                                                | Purpose                                                           |
| --------- | -------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Subscribe | `scenescape/data/scene/<scene_id>/<thing_type>`                      | Tracked-object messages from the Tracker service                  |
| Subscribe | `scenescape/data/sensor/<sensor_id>`                                 | Raw sensor readings                                               |
| Subscribe | `scenescape/cmd/database`                                            | Notification to reload scene configuration                        |
| Publish   | `scenescape/regulated/scene/<scene_id>`                              | Rate-limited detections (`--visibility_topic regulated`, default) |
| Publish   | `scenescape/data/region/<scene_id>/<region_id>/<thing_type>`         | Objects currently inside a region                                 |
| Publish   | `scenescape/event/<region_type>/<event_type>/<scene_id>/<region_id>` | Region/tripwire/sensor events                                     |

## Configuration

The service is configured via CLI flags (see `analytics-cmd --help`):

| Flag                 | Default                                   | Description                                       |
| -------------------- | ----------------------------------------- | ------------------------------------------------- |
| `--broker`           | `broker.scenescape.intel.com:1883`        | MQTT broker host[:port]                           |
| `--brokerauth`       | `/run/secrets/controller.auth`            | MQTT auth (user:password or JSON file)            |
| `--resturl`          | `https://web.scenescape.intel.com/api/v1` | Manager REST API URL                              |
| `--restauth`         | —                                         | REST auth (user:password or JSON file)            |
| `--rootcert`         | `/run/secrets/certs/scenescape-ca.pem`    | CA certificate                                    |
| `--cert`             | —                                         | Client certificate                                |
| `--data_source`      | —                                         | Scene JSON files (bypasses REST for scene config) |
| `--schema_file`      | bundled `metadata.schema.json`            | Sensor message schema                             |
| `--visibility_topic` | `regulated`                               | `regulated`, `unregulated`, or `none`             |
| `--rewriteAllTime`   | off                                       | Rewrite all timestamps to current time            |
| `--healthcheck_port` | `0` (disabled)                            | HTTP port for `/healthz`                          |
| `--verbose`          | off                                       | Verbose debug logging                             |

## Quick Start

The `analytics` service cooperates with the `broker`, `web`, and `ntpserv`
services (started automatically via Docker Compose `depends_on`), and with
an upstream Tracker (or other producer) publishing tracked-object messages
on `data/scene/<scene_id>/<thing_type>` — it has no tracking logic of its
own.

```bash
# Build the service image
make -C analytics
```

To bring up the full dependency stack (broker, Manager, NTP, Tracker, and
Analytics) via the `tracker` Compose profile:

```bash
SUPASS=<password> make demo-tracker
```

If the rest of the stack is already running, you can start just this
service:

```bash
docker compose up -d analytics
```

## Testing

```bash
# Unit tests (no Docker required), from repo root
python -m pytest tests/sscape_tests/scenescape/ -k analytics -v -p no:django
python -m pytest tests/sscape_tests/scene_pytest/ -k analytics -v -p no:django

# Build the test image (only needed once per code change)
make -C analytics test-build
```

## License

Apache 2.0 License - See LICENSE file for details
