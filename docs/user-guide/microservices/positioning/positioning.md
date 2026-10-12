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

The Positioning service resolves the live pose of sources whose position changes at
runtime, starting with ONVIF pan-tilt-zoom (PTZ) cameras. It reads each camera's
calibrated home pose from the Manager and publishes a timestamped pose context that
the Scene Controller and Tracker use to project detections from that camera.

> **Note:** The current release contains the service shell only. It connects to the
> MQTT broker, publishes its status, and exposes health checks. It does not yet
> connect to cameras, publish poses, or change how detections are tracked.

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

The broker account can publish only to its own status topic and can read only
camera-configuration change notifications
(`scenescape/cmd/camera/config/{camera_id}`). The container reports healthy only
while it is connected to the broker.

### PTZ Motion Sources

When camera support is added, the service selects a motion source for each camera
when it connects:

- **Event mode**: used for cameras that advertise the ONVIF `IsMoving` event. The
  camera's position is not polled. A moving event invalidates the pose immediately;
  a stopped event triggers a position read, followed by a confirming read after the
  settle interval.
- **Polling mode**: used for cameras without that event. The service polls the
  camera position at 5 Hz and treats any position change as motion until the
  position has been unchanged for 1 second.

While a camera is moving or settling, the Scene Controller and Tracker do not use its
detections for tracking.

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

## Test

Build and run the service test image:

```bash
make -C positioning test-build
docker run --rm intel/scenescape-positioning-test:$(cat version.txt)
```

`make setup-tests` builds the test image, and `make run_unit_tests` also runs the
service unit tests. Test stacks that start the Scene Controller or Tracker include
the Positioning service automatically.

## Configure

The service reads `/app/config/positioning.json`:

```json
{
  "resolver_id": "positioning-default",
  "cameras": []
}
```

| Field         | Description                                                                                                                                                                                                        |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `resolver_id` | Identifies this service instance in its status topic. Must be a single MQTT topic segment (no `/`, `+`, or `#`).                                                                                                   |
| `cameras`     | PTZ cameras owned by this instance. Each entry holds the Manager camera UID, ONVIF host and port, `motion_source` (`auto`, `events`, or `polling`), and the path of the mounted secret with the ONVIF credentials. |

List each camera in exactly one service instance. Do not put ONVIF usernames or
passwords in `positioning.json`; provide them as deployment secrets. Each camera's
home pose and PTZ calibration are stored on its Manager camera record, not in this
file.

> **Note:** The current service shell does not read the `cameras` list.

The service accepts these command-line options:

| Option         | Default                                         |
| -------------- | ----------------------------------------------- |
| `--broker`     | `broker.scenescape.intel.com`                   |
| `--brokerauth` | `/run/secrets/positioning.auth`                 |
| `--cert`       | `/run/secrets/certs/scenescape-positioning.crt` |
| `--keyfile`    | `/run/secrets/certs/scenescape-positioning.key` |
| `--rootcert`   | `/run/secrets/certs/scenescape-ca.pem`          |
| `--config`     | `/app/config/positioning.json`                  |

## Deploy

On Kubernetes, enable the service with `positioning.enabled=true`. See
[Deploy Scenescape on Kubernetes](../../how-to-guides/deployment/deploy-kubernetes.md#configure-the-positioning-service)
for the related Helm values. The chart runs one replica, because only one instance may
publish poses for a given camera.

To roll back, disable the Positioning deployment. The current service publishes no
poses, so disabling it does not change tracking.

## Supporting Resources

- [Positioning service README](https://github.com/open-edge-platform/scenescape/blob/main/positioning/README.md)
- [PTZ pose design](https://github.com/open-edge-platform/scenescape/blob/main/docs/design/ptz-camera-pose-service.md)
