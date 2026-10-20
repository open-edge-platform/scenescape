<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Positioning Service

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/scenescape/tree/main/positioning">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/scenescape/blob/main/positioning/README.md">
     Readme
  </a>
</div>
hide_directive-->

The Positioning service is the deployment boundary for live source-pose capabilities.
The service shell connects to MQTT, publishes resolver status, and exposes health
checks. When PTZ sources are configured, it polls each ONVIF PTZ camera, passes raw
`PTZSample` messages in-process to the PTZ Resolver, and publishes one resolved
`PoseContext` per accepted sample.

> **Note:** Controller and Tracker do not consume resolved poses yet, so publishing
> poses does not change how detections are tracked.

## How It Works

The service connects to the MQTT broker over TLS with its own broker account
(`positioning.auth`) and client certificate (`scenescape-positioning`). After it
connects, it publishes a retained status message and registers an offline last-will
message on:

```text
scenescape/positioning/status/{resolver_id}
```

The payload contains `resolver_id`, `status` (`online` or `offline`), and
`timestamp`. For the last-will message, the timestamp is the session start time,
not the time the connection was lost.

Manager's ACL policy grants the broker identity write access only to its own status
topic and to resolved-pose topics (`scenescape/positioning/pose/{source_id}`), and read
access only to camera-configuration change notifications
(`scenescape/cmd/camera/config/{camera_id}`). Writes to any other topic, including
another resolver's status topic, are denied. The bundled Mosquitto configuration
does not enforce topic ACLs; deployments requiring enforcement must configure broker
authorization as described in the [hardening guide](../../additional-resources/hardening-guide.md).
The container reports healthy only while it is connected to the broker.

### PTZ polling

One poller thread per configured source calls ONVIF PTZ `GetStatus` every
`poll_interval_s` (default 0.2 s, 5 Hz), including while the camera is stationary.
If a call overruns its tick, missed ticks are skipped; no burst, retry queue, or
replay follows. Each reading becomes one generated `scenescape.ptz.v1.PTZSample`
and is passed in-process to the sample sink:

| Field                      | Value                                                                                                 |
| -------------------------- | ----------------------------------------------------------------------------------------------------- |
| `camera_id`                | Configured `source_id` (the Manager camera UID)                                                       |
| `adapter_instance_id`      | New UUID each time the service starts a poller; unchanged across device reconnects                    |
| `sequence`                 | Starts at 1 and increments by one per emitted sample within `adapter_instance_id`                     |
| `measured_at`              | Host wall-clock midpoint of the GetStatus request/response interval                                   |
| `timestamp_uncertainty_ns` | Half the measured round trip, rounded up (never 0)                                                    |
| `position`                 | Raw pan/tilt (and zoom when reported); the reported space URI and its advertised `GetNodes` ranges    |
| `reported_move_status`     | Advisory only; from `GetStatus` MoveStatus, a vendor move event, or `UNSPECIFIED` (see `move_status`) |

If the device reports a position space that its PTZ node does not advertise, the
ranges are NaN so the Resolver can reject the sample. The poller applies no
calibration math and never writes to Manager or MQTT. After `max_consecutive_failures`
failed polls (default 5), it reconnects with exponential backoff capped at 30 s.

### Move events

Some cameras publish a vendor "is moving" property event. For example, Axis cameras
publish `tns1:PTZController/tnsaxis:Move/Channel_1` with the `is_moving` data item.
When `move_event` is configured, a separate thread holds an ONVIF PullPoint
subscription, renews it, and always unsubscribes on shutdown, because devices limit
concurrent PullPoints. Each state change is logged as a structured
`ptz_move_event` JSON record containing `source_id`, `is_moving`,
`property_operation`, `device_utc_time`, and `received_at`. These records are
evidence for calibration. If `move_status` is `event`, the latest event state also
sets `reported_move_status`. Move events never establish pose validity: the Resolver
derives motion from position history.

### ONVIF client

The poller uses a small in-tree SOAP 1.2 client
(`positioning/src/positioning/onvif/`) built on `requests` and `defusedxml`, both
pinned with hashes in `requirements-runtime.txt`. It implements only
`GetSystemDateAndTime`, `GetCapabilities`, `GetDeviceInformation`, `GetProfiles`,
`GetNodes`, `GetStatus`, `GetEventProperties`, and PullPoint create, pull, renew, and
unsubscribe operations. These alternatives were evaluated:

| Option                                                             | Decision and reason                                                                                                                                                                                                                              |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `onvif-zeep` 0.2.12 (MIT)                                          | Rejected: last released in 2018 and unmaintained. The PoC needed monkey patches for drifting device clocks and Axis subscription reference parameters.                                                                                           |
| `onvif-zeep-async` (MIT)                                           | Not selected: it is maintained, but it is async-only and pulls in zeep, lxml, httpx, and their transitive tree, which must all be hash-pinned. It also loads WSDLs at startup, while the poller needs fewer than ten operations.                 |
| `dlstreamer.onvif`                                                 | Rejected: it is not published as a package, and the plan forbids cloning or vendoring source during an image build.                                                                                                                              |
| In-tree SOAP (`requests`, `defusedxml`) (Apache-2.0, MIT, PSF-2.0) | Selected: two small, actively maintained dependencies that support Python 3.11. Device XML is parsed with DTDs and entities forbidden, and responses are limited to 1 MiB. The client times the actual HTTP exchange for the midpoint timestamp. |

Authentication uses WS-Security UsernameToken `PasswordDigest`. The device clock
offset is read with an unauthenticated `GetSystemDateAndTime` and resynchronized after
a `NotAuthorized` fault, so a drifting camera clock does not block authentication.
HTTP Digest is used only if the device sends a 401 challenge. Host HTTP proxy
variables are ignored for camera traffic. Service addresses advertised by the device
keep their path and port, but the configured camera host is always used, so
credentials are never sent to a different host. Plain `http` sends a digest rather
than the password; use `https` where the camera supports it, and keep cameras on an
isolated network.

The design rationale is in the
[PTZ pose design](../../../design/ptz-camera-pose-service.md).

### Pose resolution

The Resolver validates every sample before accepting it: finite position and ranges,
position inside the advertised ranges, a position space URI and ranges matching the
calibration, timestamp uncertainty within `max_timestamp_uncertainty_s`, and a
strictly increasing sequence and timestamp. Duplicate, out-of-order, malformed, or
unassigned samples produce no `PoseContext`; consumers see them as sequence gaps. A
new `adapter_instance_id` (poller restart) or a sequence gap resets motion and
backlash history.

Every accepted sample publishes exactly one retained QoS 0 `PoseContext` on
`scenescape/positioning/pose/{source_id}`. A pose is valid only when all of these hold:

- The clock is synchronized (see [Clock synchronization](#clock-synchronization)).
- The sample is younger than `max_pose_age_s`; otherwise `sample_stale`.
- A Manager calibration is loaded; otherwise `calibration_missing`.
- Backlash is known on both axes. After a restart, gap, or calibration change, an axis
  becomes known only when the camera reports a position within
  `backlash_home_tolerance_deg` of its calibrated home; otherwise `backlash_unknown`.
- The camera is stationary: no axis moved more than `settle_angular_threshold_deg`
  between samples (`slewing`, reason `moving`), and the history covers a full
  `settle_interval_s` window without motion (`settling`).
- The calibration's `reprojection_rms_px` does not exceed `target_reprojection_rms_px`,
  and the Manager home pose is a rigid transform.

The resolved orientation composes the backlash-corrected pan and tilt deltas about the
calibrated axes in the calibration's `composition_order`. Translation, intrinsics, and
distortion stay those of the home calibration.

### Calibration reload

Calibration comes only from Manager. When Manager publishes
`scenescape/cmd/camera/config/{camera_id}` for an assigned source, the Resolver drops
the cached calibration immediately: the next pose reports `calibration_changed`, and
later poses report `calibration_missing` until a reload succeeds. Reloads run on a
background worker, not in the MQTT callback. Every `calibration_refresh_interval_s`
the service also rereads all sources, which recovers from a failed reload. A changed
calibration resets motion and backlash history, so a valid pose again requires a full
settle window.

### Clock synchronization

Poses are timestamped with the host clock, so the service checks it against the NTP
server given by `--ntp` (default: the `POSITIONING_NTP_SERVER` environment variable)
at startup and every 30 s, and logs the measured offset. While the absolute offset
exceeds `max_clock_offset_s`, no NTP server is configured, or no successful
measurement is younger than 90 s, every source publishes invalid poses with reason
`invalid_sample` and motion history is discarded. The service keeps running and
recovers automatically once synchronization returns.

### Runtime metrics

Every 60 s the service logs one structured `positioning_metrics` JSON record:

| Metric                                 | Type                   | Labels                      |
| -------------------------------------- | ---------------------- | --------------------------- |
| `positioning_pose_age_seconds`         | Histogram              | `source_id`                 |
| `positioning_pose_sequence_gaps_total` | Counter                | `source_id`                 |
| `positioning_rejected_samples_total`   | Counter                | `source_id`, `result`       |
| `positioning_motion_state_seconds`     | Histogram (time spent) | `source_id`, `motion_state` |
| `positioning_calibration_version_info` | Info                   | `source_id`                 |
| `positioning_clock_offset_seconds`     | Gauge                  | -                           |

Dwell-rejection and projection-drift metrics belong to the Controller and Tracker
consumers, which see detections; the Positioning service does not.

## Build

Build the runtime image from the repository root:

```bash
make positioning
```

The image is also built by `make build-core` and `make build-all`. Generate the
broker account and client certificate with:

```bash
make init-secrets
```

This creates `manager/secrets/positioning.auth`,
`manager/secrets/certs/scenescape-positioning.crt`, and
`manager/secrets/certs/scenescape-positioning.key`.

## Configure

The service reads `/app/config/positioning.json`:

```json
{
  "resolver_id": "positioning-default"
}
```

| Field         | Description                                                                                                      |
| ------------- | ---------------------------------------------------------------------------------------------------------------- |
| `resolver_id` | Identifies this service instance in its status topic. Must be a single MQTT topic segment (no `/`, `+`, or `#`). |

PTZ sources are optional and come from deployment configuration. The checked-in
configuration has none:

```json
{
  "resolver_id": "positioning-default",
  "poll_interval_s": 0.2,
  "max_pose_age_s": 0.5,
  "max_timestamp_uncertainty_s": 0.01,
  "max_clock_offset_s": 0.05,
  "target_reprojection_rms_px": 3.0,
  "sample_ring_buffer_size": 64,
  "calibration_refresh_interval_s": 30.0,
  "sources": {
    "<manager-camera-uid>": {
      "type": "onvif_ptz",
      "host": "<camera-host>",
      "scheme": "https",
      "port": 443,
      "credentials_file": "/run/secrets/onvif/<manager-camera-uid>.json",
      "move_status": "event",
      "move_event": { "topic": "PTZController/Move", "data_item": "is_moving" }
    }
  }
}
```

| Field                            | Default               | Description                                                                                                                                           |
| -------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `poll_interval_s`                | `0.2`                 | Positive poll period for every source                                                                                                                 |
| `sources.<id>`                   | -                     | Key is the `source_id` (Manager camera UID, single topic segment)                                                                                     |
| `type`                           | required              | `onvif_ptz`                                                                                                                                           |
| `host`, `port`                   | -, `443`              | Camera ONVIF endpoint; `host` is a bare hostname or IP                                                                                                |
| `scheme`, `tls_ca_file`          | `https`, -            | HTTPS is the default; optionally provide the CA bundle path for a private camera certificate                                                          |
| `profile_token`                  | first PTZ             | Media profile whose PTZ configuration is polled                                                                                                       |
| `credentials_file`               | required              | Mounted secret: `{"username": "...", "password": "..."}`. Credentials are never accepted inline.                                                      |
| `request_timeout_s`              | `1.0`                 | Per-request HTTP timeout                                                                                                                              |
| `move_status`                    | `get_status`          | Source of advisory `reported_move_status`: `get_status`, `event` (requires `move_event`), or `none`                                                   |
| `move_event`                     | -                     | `topic` (event topic prefix without namespace prefixes) and `data_item` of a boolean move event; when set, `ptz_move_event` records are always logged |
| `max_pose_age_s`                 | required with sources | Positive maximum sample age; at least `poll_interval_s + max_timestamp_uncertainty_s`                                                                 |
| `max_timestamp_uncertainty_s`    | required with sources | Finite nonnegative upper bound for poller timestamp uncertainty                                                                                       |
| `max_clock_offset_s`             | required with sources | Positive bound on the measured NTP offset; larger offsets invalidate all poses                                                                        |
| `target_reprojection_rms_px`     | required with sources | Positive calibration-quality limit; larger Manager residuals invalidate poses                                                                         |
| `sample_ring_buffer_size`        | `64`                  | Must cover the largest settle/backlash history: `ceil(max_history_s / poll_interval_s) + 2`                                                           |
| `calibration_refresh_interval_s` | `30.0`                | Positive retry interval for Manager calibration loads                                                                                                 |

Unknown keys are rejected at startup. Device credentials must never be committed. Keep
them in deployment secrets mounted read-only into the container.

Source ownership is recorded separately in `deployment/positioning-assignments.json`
as a `source_id` to `resolver_id` mapping. The image contains the empty default at
`/app/deployment/positioning-assignments.json`; mount the deployment manifest over it.
At startup, every configured source must be assigned to this `resolver_id`, and every
entry assigned to this `resolver_id` must be configured; otherwise the service exits.
Manager remains authoritative for camera-to-scene membership and camera calibration.
The service loads each camera's `ptz_calibration`, computed `pose_matrix`, and scene
through the read-only Manager API. It subscribes only to configuration invalidations
for its assigned sources and retries calibration reads periodically. Failed or
incomplete calibration keeps the source invalid; a live pose is never used as a home
fallback. Accepted samples publish retained QoS 0 contexts on
`scenescape/positioning/pose/{source_id}`; malformed raw samples produce no context.

The service accepts these command-line options:

| Option           | Default                                         |
| ---------------- | ----------------------------------------------- |
| `--broker`       | `broker.scenescape.intel.com`                   |
| `--brokerauth`   | `/run/secrets/positioning.auth`                 |
| `--cert`         | `/run/secrets/certs/scenescape-positioning.crt` |
| `--keyfile`      | `/run/secrets/certs/scenescape-positioning.key` |
| `--rootcert`     | `/run/secrets/certs/scenescape-ca.pem`          |
| `--manager-url`  | `https://web.scenescape.intel.com/api/v1`       |
| `--manager-auth` | defaults to `--brokerauth`                      |
| `--ntp`          | `POSITIONING_NTP_SERVER` environment variable   |
| `--config`       | `/app/config/positioning.json`                  |
| `--assignments`  | `/app/deployment/positioning-assignments.json`  |

## Deploy

On Kubernetes, enable the service with `positioning.enabled=true`. See
[Deploy Scenescape on Kubernetes](../../how-to-guides/deployment/deploy-kubernetes.md#configure-the-positioning-service)
for the related Helm values. The chart runs one replica, because only one instance may
publish poses for a given camera.

To roll back, disable the Positioning deployment or remove its `sources`. Without
sources the service publishes no poses. Controller and Tracker do not consume poses
yet, so either change leaves tracking unchanged.

## Supporting Resources

- [Positioning operations](operations.md)
- [PTZ pose design](../../../design/ptz-camera-pose-service.md)
