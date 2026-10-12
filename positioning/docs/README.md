<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Positioning Operations

## Service Shell

The 3a shell runs without PTZ configuration. It connects to MQTT with the dedicated
`positioning.auth` identity and client certificate, publishes retained
`scenescape/positioning/status/{resolver_id}` status at QoS 0, and registers an
offline last will. Its status payload contains only `resolver_id`, `status`, and
`timestamp`; an LWT timestamp describes the MQTT session start. Health becomes ready
only after a successful broker connection.

Use `make positioning` to build the runtime image and `make init-secrets` to create
the broker identity and `scenescape-positioning` client certificate/key. Start the
service through the test Compose profile or the Helm chart. Both mount the CA,
client certificate, private key, and auth file read-only. The generated Manager account
has read access to camera configuration invalidations and write access to resolver
status, and it is not a superuser. The bundled Mosquitto configuration does not
enforce service credentials or topic ACLs; deployments requiring enforcement must
configure broker authentication and authorization as described in the
[hardening guide](../../docs/user-guide/additional-resources/hardening-guide.md).

The test image is built by `make setup-tests`; its unit suite runs from the root
`make run_unit_tests` target. Test service compositions that include the Controller
or Tracker also include `tests/compose/compose.positioning.yml`.

## Camera Onboarding

The current shell does not poll cameras. When the PTZ runtime and Manager calibration
API are available, add each camera through deployment-owned configuration rather
than editing service code:

1. Calibrate the camera's home pose and PTZ model using the documented hardware
   procedure. Store the validated `ptz_calibration` on the Manager camera record;
   the Resolver reads it and never changes or re-baselines it.
2. Add the camera to the `cameras` list in `positioning/config/positioning.json`
   (mounted from deployment configuration, not edited in the image). An entry holds
   the Manager camera UID, ONVIF host and port, and the path of the mounted secret
   that holds its ONVIF credentials.
   Cameras listed in an instance's config are owned by that instance's
   `resolver_id`; list each camera in exactly one instance. Scene membership stays
   in Manager, which remains authoritative for scenes and consumer ACL scope.
3. Put the ONVIF username and password in a deployment secret, never in
   `positioning.json`. Do not commit camera addresses or credentials, and do not copy
   values from the local PoC setup into product defaults.
4. Every camera is polled with `GetStatus` at 5 Hz, including while stationary. Any
   position change counts as motion until the position has been unchanged for
   1 second. If the camera reports the ONVIF `IsMoving` status, it is used only as
   additional information; it never replaces position polling or shortens the settle
   interval. The stored calibration is used to calculate the new pose; the service
   neither recalibrates nor writes the home pose.
5. Keep detections from the source out of tracking while moving, settling, or
   completing the configured dwell. Controller and Tracker enforce this admission
   independently; turning on either feature flag requires its own shadow-mode
   acceptance.

Continuous polling provides the timestamped samples needed for dwell and sequence
continuity. Camera-specific calibration,
timing bounds, and credentials are not part of this 3a shell and must be completed in
their owning implementation phases.

## Deployments and Rollback

Compose tests include the Positioning service only in profiles that launch a Scene
Controller or Tracker. Helm installs it when `positioning.enabled=true`; it has one
replica because source ownership is single-writer. The `cameras` list in
`positioning/config/positioning.json` starts empty; the 3a shell does not read it.

The 3a service publishes no pose and does not alter detections. Roll back by disabling
the Positioning deployment. Later PTZ rollout rollback is per consumer: disable the
corresponding Controller or Tracker PTZ flag and return to static projection.
