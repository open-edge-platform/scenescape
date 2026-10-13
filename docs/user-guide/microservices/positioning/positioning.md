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
The current service shell connects to MQTT, publishes resolver status, and exposes
health checks. It does not poll cameras or publish poses.

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

Manager's ACL policy grants the broker identity write access only to its own status
topic and read access only to camera-configuration change notifications
(`scenescape/cmd/camera/config/{camera_id}`). The bundled Mosquitto configuration
does not enforce topic ACLs; deployments requiring enforcement must configure broker
authorization as described in the [hardening guide](../../additional-resources/hardening-guide.md).
The container reports healthy only while it is connected to the broker.

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

| Field         | Description                                                                                                            |
| ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `resolver_id` | Identifies this service instance in its status topic. Must be a single MQTT topic segment (no `/`, `+`, or `#`).      |

Source ownership is recorded separately in `deployment/positioning-assignments.json`
as a `source_id` to `resolver_id` mapping. The current manifest is empty. Manager
remains authoritative for camera-to-scene membership and camera calibration.

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

- [Positioning operations](operations.md)
- [PTZ pose design](../../../design/ptz-camera-pose-service.md)
