<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Positioning Operations

## Service Shell

The current service shell runs without PTZ configuration. It connects to MQTT with the dedicated
`positioning.auth` identity and client certificate, publishes retained
`scenescape/positioning/status/{resolver_id}` status at QoS 0, and registers an
offline last will. Its status payload contains only `resolver_id`, `status`, and
`timestamp`; an LWT timestamp describes the MQTT session start. Health becomes ready
only after a successful broker connection.

Use `make positioning` to build the runtime image and `make init-secrets` to create
the broker identity and `scenescape-positioning` client certificate/key. Start the
service with the Docker Compose `controller` or `tracker` profile (`make demo` /
`make deploy`), the test Compose stack, or the Helm chart. All three mount the CA,
client certificate, private key, and auth file read-only. The generated Manager account
has read access to camera configuration invalidations and write access to resolver
status, and it is not a superuser. The bundled Mosquitto configuration does not
enforce service credentials or topic ACLs; deployments requiring enforcement must
configure broker authentication and authorization as described in the
[hardening guide](../../additional-resources/hardening-guide.md).

Demo and deploy Compose include Positioning with the `controller` and `tracker`
profiles in `sample_data/compose/compose.dl-streamer-example.yml`. Test stacks that
launch a Controller or Tracker also include it through
`tests/compose/compose.positioning.yml`.

## Source Ownership

The checked-in configuration contains no camera list. Deployment source ownership is
represented by `deployment/positioning-assignments.json`. The checked-in manifest is
empty:

```json
{}
```

When sources are assigned, each `source_id` maps to exactly one `resolver_id`; this
manifest does not assign cameras to scenes. The service refuses to start if a
configured source is not assigned to its `resolver_id`, or if an entry for its
`resolver_id` is not configured. Manager remains authoritative for camera
calibration and camera-to-scene membership. Source configuration is described in
[Positioning Service](positioning.md#configure).

## PTZ Camera Onboarding Check

Before assigning a camera, verify its ONVIF PTZ endpoint with the same client and
poller the service uses. The probe prints device identity, the selected PTZ profile,
advertised absolute pan/tilt spaces, and optionally event topics. It then polls and
reports achieved rate, interval, timestamp uncertainty, position range, and the
reported move-status mix:

```bash
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -v "$PWD/positioning/.local/secrets/<camera>.json:/run/secrets/onvif/<camera>.json:ro" \
  --entrypoint python3 intel/scenescape-positioning:$(cat version.txt) \
  -m positioning.onvif.probe --host <camera-host> --port <onvif-port> \
  --credentials-file /run/secrets/onvif/<camera>.json --list-topics --duration 30
```

Add `--samples` to print each `PTZSample` as JSON. Add
`--move-event-topic PTZController/Move` to subscribe to a vendor move event. Read
credentials from a file or from `ONVIF_USERNAME`/`ONVIF_PASSWORD`; the probe does not
accept them as command-line arguments. Compare the reported space URI and ranges with
the camera's `ptz_calibration.position_space`. If `reported_move_status` is always
`IDLE` while the camera moves, configure `move_status` as `none` or `event`.

Keep lab configurations and credentials under `positioning/.local/`, which is
git-ignored. Never place camera endpoints or credentials in tracked files.

## Shadow Validation Artifacts

When Controller and Tracker shadow profiles are implemented, each emits sampled,
structured JSONL records to stdout only. Records share a `run_id`; the acceptance
harness combines both profiles by that ID into the immutable
`tests/artifacts/ptz/shadow/<run_id>.jsonl` artifact and publishes it with the CI or
acceptance run. Services do not write local artifact files or require production
artifact volumes. Field runs export an equivalently named bundle from structured logs.

## Deployments and Rollback

Demo, deploy, and Compose tests include the Positioning service with the Scene
Controller or Tracker profiles. Helm installs it when `positioning.enabled=true`; it
has one replica to preserve single-writer source ownership.

The service does not publish poses and does not alter detections. Roll back PTZ
polling by removing `sources` from the deployment configuration, or roll back the
whole service by disabling the Positioning deployment. Later PTZ rollout rollback is
per consumer: disable the corresponding Controller or Tracker PTZ flag and return to
static projection.
