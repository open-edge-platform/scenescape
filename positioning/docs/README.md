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
client certificate, private key, and auth file read-only. The identity may publish
only resolver status and may read camera configuration invalidations. It is not a
superuser.

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
2. Add the Manager camera UID to `deployment/positioning-assignments.json`, mapped
   to exactly one configured `resolver_id`. Do not put scene membership in this
   manifest; Manager remains authoritative for scenes and consumer ACL scope.
3. Supply the camera's ONVIF endpoint and credentials through deployment secrets.
   Do not commit camera addresses or credentials, and do not copy values from the
   local PoC setup into product defaults.
4. Select the supported motion signal for the device. For an ONVIF `IsMoving`
   event source, motion must invalidate the pose immediately; on the transition to
   not-moving, fetch a fresh `GetStatus` sample and continue stationary sampling
   for the dwell proof. For a device without that event, poll status at 5 Hz and
   treat any position change as motion until position has remained unchanged for
   at least 1 second. Both paths use the stored calibration to calculate the new
   pose; neither recalibrates nor writes the home pose.
5. Keep detections from the source out of tracking while moving, settling, or
   completing the configured dwell. Controller and Tracker enforce this admission
   independently; turning on either feature flag requires its own shadow-mode
   acceptance.

The event path is an early motion signal, not a replacement for timestamped pose
samples. Continued samples after stop are required to prove dwell and sequence
continuity. Camera-specific calibration, timing bounds, and credentials are not
part of this 3a shell and must be completed in their owning implementation phases.

## Deployments and Rollback

Compose tests include the Positioning service only in profiles that launch a Scene
Controller or Tracker. Helm installs it when `positioning.enabled=true`; it has one
replica because source ownership is single-writer. The shared
`deployment/positioning-assignments.json` starts empty and maps source IDs to
resolver IDs only.

The 3a service publishes no pose and does not alter detections. Roll back by disabling
the Positioning deployment. Later PTZ rollout rollback is per consumer: disable the
corresponding Controller or Tracker PTZ flag and return to static projection.
