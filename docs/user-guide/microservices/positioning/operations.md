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

In Phase 3a, Positioning is allowed to publish only its own status on the configured
`scenescape/positioning/status/{resolver_id}` topic. Manager restricts the
`positioning` username to writes on that topic and provisions no pose-write ACL.
Publishing to `scenescape/positioning/pose/{source_id}` is deferred to Phase 3b,
which will update both the ACL guard and the provisioned
permissions when the poller and Resolver implement pose publishing. Adding a
pose-write ACL alone does not override the current guard.

Demo and deploy Compose include Positioning with the `controller` and `tracker`
profiles in `sample_data/compose/compose.dl-streamer-example.yml`. Test stacks that
launch a Controller or Tracker also include it through
`tests/compose/compose.positioning.yml`.

## Source Ownership

The current service-shell configuration contains no camera list. Deployment source
ownership is represented by `deployment/positioning-assignments.json`. The current
manifest is empty:

```json
{}
```

When sources are assigned, each `source_id` maps to exactly one `resolver_id`; this
manifest does not assign cameras to scenes. Manager remains authoritative for camera
calibration and camera-to-scene membership. Future PTZ camera configuration and
runtime behavior are specified in the
[PTZ pose design](../../../design/ptz-camera-pose-service.md).

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

The current service publishes no pose and does not alter detections. Roll back by disabling
the Positioning deployment. Later PTZ rollout rollback is per consumer: disable the
corresponding Controller or Tracker PTZ flag and return to static projection.
