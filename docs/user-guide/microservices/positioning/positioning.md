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
checks. When PTZ sources are configured, it also polls each ONVIF PTZ camera and
produces raw `PTZSample` messages in-process.

> **Note:** The PTZ Pose Resolver is not part of this release. Raw samples go to an
> interim sink that only logs periodic polling statistics. The service does not
> publish poses or change how detections are tracked.

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
topic and read access only to camera-configuration change notifications
(`scenescape/cmd/camera/config/{camera_id}`). The bundled Mosquitto configuration
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

Future PTZ polling, pose resolution, and motion handling are specified in the
[PTZ pose design](../../../design/ptz-camera-pose-service.md); they are not part of the
current service shell.

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
  "sources": {
    "<manager-camera-uid>": {
      "type": "onvif_ptz",
      "host": "<camera-host>",
      "port": 80,
      "credentials_file": "/run/secrets/onvif/<manager-camera-uid>.json",
      "move_status": "event",
      "move_event": { "topic": "PTZController/Move", "data_item": "is_moving" }
    }
  }
}
```

| Field                   | Default      | Description                                                                                                                                           |
| ----------------------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `poll_interval_s`       | `0.2`        | Positive poll period for every source                                                                                                                 |
| `sources.<id>`          | -            | Key is the `source_id` (Manager camera UID, single topic segment)                                                                                     |
| `type`                  | required     | `onvif_ptz`                                                                                                                                           |
| `host`, `port`          | -, `80`      | Camera ONVIF endpoint; `host` is a bare hostname or IP                                                                                                |
| `scheme`, `tls_ca_file` | `http`, -    | `https` with optional CA bundle path                                                                                                                  |
| `profile_token`         | first PTZ    | Media profile whose PTZ configuration is polled                                                                                                       |
| `credentials_file`      | required     | Mounted secret: `{"username": "...", "password": "..."}`. Credentials are never accepted inline.                                                      |
| `request_timeout_s`     | `1.0`        | Per-request HTTP timeout                                                                                                                              |
| `move_status`           | `get_status` | Source of advisory `reported_move_status`: `get_status`, `event` (requires `move_event`), or `none`                                                   |
| `move_event`            | -            | `topic` (event topic prefix without namespace prefixes) and `data_item` of a boolean move event; when set, `ptz_move_event` records are always logged |

Unknown keys are rejected at startup. Device credentials must never be committed. Keep
them in deployment secrets mounted read-only into the container.

Source ownership is recorded separately in `deployment/positioning-assignments.json`
as a `source_id` to `resolver_id` mapping. The image contains the empty default at
`/app/deployment/positioning-assignments.json`; mount the deployment manifest over it.
At startup, every configured source must be assigned to this `resolver_id`, and every
entry assigned to this `resolver_id` must be configured; otherwise the service exits.
Manager remains authoritative for camera-to-scene membership and camera calibration.

The service accepts these command-line options:

| Option          | Default                                         |
| --------------- | ----------------------------------------------- |
| `--broker`      | `broker.scenescape.intel.com`                   |
| `--brokerauth`  | `/run/secrets/positioning.auth`                 |
| `--cert`        | `/run/secrets/certs/scenescape-positioning.crt` |
| `--keyfile`     | `/run/secrets/certs/scenescape-positioning.key` |
| `--rootcert`    | `/run/secrets/certs/scenescape-ca.pem`          |
| `--config`      | `/app/config/positioning.json`                  |
| `--assignments` | `/app/deployment/positioning-assignments.json`  |

## Deploy

On Kubernetes, enable the service with `positioning.enabled=true`. See
[Deploy Scenescape on Kubernetes](../../how-to-guides/deployment/deploy-kubernetes.md#configure-the-positioning-service)
for the related Helm values. The chart runs one replica, because only one instance may
publish poses for a given camera.

To roll back, disable the Positioning deployment or remove its `sources`. The service
publishes no poses, so either change leaves tracking unchanged.

## Supporting Resources

- [Positioning operations](operations.md)
- [PTZ pose design](../../../design/ptz-camera-pose-service.md)
