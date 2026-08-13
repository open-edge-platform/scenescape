<!-- Template: substitute every {{...}} token, then write the result to <deploy_dir>/README.md -->
# SceneScape Deployment — {{SCENE_NAME}}

Multi-camera detection and cross-camera object tracking built with Intel® SceneScape.
Per-camera detections are fused into one scene-level map so an object moving between
cameras keeps a single identity.

- Deploy directory: `{{DEPLOY_DIR}}`
- Scene UID: `{{SCENE_UID}}`
- Cameras: {{CAMERA_IDS}}

## Access

| What | Where |
| --- | --- |
| Scene Management UI | https://{{HOST_IP}}/ |
| Login user | `admin` |
| Login password | contents of `secrets/supass` (`cat secrets/supass`) |

The UI uses a self-signed certificate; accept the browser warning to continue.

## Notifications (MQTT)

Detections and fused tracks are published to the broker (`scenescape-broker-1`, TLS
on port 1883 inside the compose network).

- Fused cross-camera tracks: `scenescape/data/scene/{{SCENE_UID}}/person`
- Per-camera detections:      `scenescape/data/camera/<camera-id>`

Example subscription:

```bash
docker compose exec broker mosquitto_sub \
  --cafile /run/secrets/certs/scenescape-ca.pem \
  -h broker.scenescape.intel.com -p 1883 \
  -t 'scenescape/data/scene/{{SCENE_UID}}/person'
```

## Operating the stack

```bash
cd {{DEPLOY_DIR}}
docker compose ps            # status of every service
docker compose up -d         # start / recreate the stack
docker compose stop          # stop without deleting data
docker compose start         # restart after a stop
docker compose logs -f scene # follow the scene controller
docker compose down          # remove containers (keeps volumes; add -v to wipe data)
```

## Architecture

Each camera runs an independent detection pipeline (DL Streamer Pipeline Server)
that publishes per-camera detections to the MQTT broker. The scene controller
consumes those detections, projects them into a shared scene coordinate frame
using each camera's calibration, and fuses them across cameras and over time into
persistent object tracks. The web/manager service serves the Scene Management UI
and REST API and stores scenes, cameras, and calibration in PostgreSQL.

```
cameras ─▶ DL Streamer pipelines ─▶ MQTT broker ─▶ scene controller ─▶ fused tracks
   (per-camera detections)          (Mosquitto)      (project + fuse)   (MQTT scene topic)
                                                            │
                                        web / manager (UI + REST) ◀─▶ PostgreSQL
```

| Container | Role |
| --- | --- |
| `scenescape-video-analytics-*` | Per-camera detection pipelines (DL Streamer Pipeline Server) |
| `scenescape-broker-*` | MQTT broker (Mosquitto) — detection + scene message bus |
| `scenescape-scene-*` | Scene controller — projects and fuses detections into tracks |
| `scenescape-web-*` | Scene Management UI + REST API |
| `scenescape-pgserver-*` | PostgreSQL — scenes, cameras, calibration |
| `scenescape-ntpserv-*` | Time sync for cross-camera detection correlation |

## Tests

The SceneScape repository ships a pytest-based suite (functional, UI, unit, and
security) that runs against a Docker Compose or Kubernetes (KinD + Helm) backend.
From a repository clone:

```bash
# Build images, generate secrets, install the pytest virtualenv
SUPASS=change_me make && make setup-tests

make run_tests                 # full suite
make run_unit_tests            # unit tests only (tests/sscape_tests)

# Or invoke pytest directly against a running deployment:
pytest tests/functional
pytest -k mqtt_roi             # a single test by ID
pytest --backend=kubernetes    # run against the Kubernetes backend
```

See `tests/README.md` in the repository for prerequisites (Firefox-ESR, system
packages) and the full backend/marker reference.

## References

- SceneScape repository: https://github.com/open-edge-platform/scenescape
- User guide: https://github.com/open-edge-platform/scenescape/tree/main/docs/user-guide
- Tests guide: https://github.com/open-edge-platform/scenescape/blob/main/tests/README.md

## Security note (demo configuration)

Single-host demo deployment. `secrets/certs/scenescape-mapping.key` is readable by
non-owner container UIDs so the `mapping` and `video-analytics` services can start.
Restrict that key and replace the self-signed certificates with CA-signed ones
before exposing this host beyond a trusted network.
