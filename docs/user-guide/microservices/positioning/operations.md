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
status and resolved-pose topics, and it is not a superuser. The bundled Mosquitto configuration does not
enforce service credentials or topic ACLs; deployments requiring enforcement must
configure broker authentication and authorization as described in the
[hardening guide](../../additional-resources/hardening-guide.md).

Positioning may publish only its configured
`scenescape/positioning/status/{resolver_id}` topic and registered
`scenescape/positioning/pose/{source_id}` topics. Manager requires explicit ACLs
for both topic classes; writes to unrelated topics and another resolver's status
topic are denied. Source ownership is enforced by the Positioning assignment
manifest and Resolver validation, not by broadening the Manager ACL to unrelated
topic families.

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

Manager reads the same manifest (`POSITIONING_ASSIGNMENTS_FILE`) to authorize
broker writes to `scenescape/positioning/pose/{source_id}`: a pose write is allowed
only for a source assigned to Manager's `POSITIONING_RESOLVER_ID`, whatever the
publishing identity's topic ACL grants. A missing or invalid manifest assigns
nothing, so all pose writes are denied. Mount the deployment manifest into both
Positioning and Manager (web) and keep `POSITIONING_RESOLVER_ID` equal to the
service's `resolver_id`.

## Enable ONVIF Access on the Camera

The Positioning service talks to cameras only through ONVIF over HTTP or HTTPS. It
needs the Device, Media, and PTZ services, and optionally the Events service.
Settings names differ by vendor; apply these steps on each camera before you probe
it:

1. **Enable ONVIF.** Many cameras ship with ONVIF disabled, or enable it only after
   an administrator password is set. Look for **ONVIF**, **Integration protocol**,
   or **Network services** in the web UI. On Axis, ONVIF settings are under
   **System > ONVIF** after the first web user exists. On TP-Link VIGI, look under
   the network settings for ONVIF.
2. **Create a dedicated ONVIF account** for SceneScape. Some vendors keep ONVIF users
   separate from web UI users (Axis: **System > Accounts > ONVIF accounts**).
   Choose the lowest role that allows PTZ status and events, typically **Operator**.
   Do not reuse the administrator account.
3. **Note the ONVIF port.** It is often 80 or 443, but some cameras use a separate
   port (TP-Link VIGI uses 2020). The device service path is
   `/onvif/device_service`.
4. **Make sure a media profile has a PTZ configuration.** The poller uses the first
   profile that has one, or the profile named by `profile_token`.
5. **Synchronize the camera clock with NTP.** Point the camera at the same NTP
   source as the SceneScape host (**Date and time** settings). WS-Security
   authentication depends on the camera clock; see
   [Troubleshoot ONVIF Access](#troubleshoot-onvif-access).
6. **Keep the camera's security features enabled.** The poller works with replay
   attack protection and brute-force protection on (verified on AXIS M5526-E).
   Use HTTPS (`"scheme": "https"`, the default) in production and keep certificate
   verification enabled. Set `tls_ca_file` for a private camera CA. If a camera has no
   HTTPS support, explicitly select HTTP only on an isolated network or protected tunnel.
7. **Allow network access** from the SceneScape host to the camera's ONVIF port. For
   move events, the poller uses PullPoint subscriptions, so the camera does not need
   to reach the host. Host HTTP proxy variables are ignored for camera traffic.

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

## Configure Your Own PTZ Camera Locally

Use the git-ignored `positioning/.local/` directory for lab cameras. A complete
setup looks like this:

```text
positioning/.local/
├── positioning.json                 # service config with your sources
├── positioning-assignments.json     # source_id -> resolver_id
├── compose.override.yml             # mounts the files above into the container
└── secrets/
    └── <source_id>.json             # ONVIF credentials, mode 0600
```

1. Create the directory and a credentials file for each camera. Use the ONVIF
   account from
   [Enable ONVIF Access on the Camera](#enable-onvif-access-on-the-camera).

   ```bash
   mkdir -p positioning/.local/secrets && chmod 700 positioning/.local/secrets
   cat > positioning/.local/secrets/lab-ptz-1.json <<'EOF'
   {"username": "<onvif-user>", "password": "<onvif-password>"}
   EOF
   chmod 600 positioning/.local/secrets/lab-ptz-1.json
   ```

   Edit the file in an editor rather than typing the password into shell history.

2. Verify each camera with the probe (see
   [PTZ Camera Onboarding Check](#ptz-camera-onboarding-check)). Note the ONVIF
   port, the profile token if you need a specific one, whether
   `reported_move_status` changes to `MOVING` while the camera moves, and whether
   the event topic list contains a move event.

3. Create `positioning/.local/positioning.json`. Each key under `sources` is the
   Manager camera UID. This example has one camera that only supports `GetStatus`
   and one that also publishes an Axis-style `is_moving` event:

   ```json
   {
     "resolver_id": "positioning-lab",
     "poll_interval_s": 0.2,
     "max_pose_age_s": 0.5,
     "max_timestamp_uncertainty_s": 0.01,
     "max_clock_offset_s": 0.05,
     "target_reprojection_rms_px": 3.0,
     "sources": {
       "lab-ptz-1": {
         "type": "onvif_ptz",
         "host": "<camera-1-ip>",
         "scheme": "http",
         "port": 2020,
         "credentials_file": "/run/secrets/onvif/lab-ptz-1.json",
         "move_status": "get_status"
       },
       "lab-ptz-2": {
         "type": "onvif_ptz",
         "host": "<camera-2-ip>",
         "scheme": "http",
         "port": 80,
         "credentials_file": "/run/secrets/onvif/lab-ptz-2.json",
         "move_status": "event",
         "move_event": {
           "topic": "PTZController/Move",
           "data_item": "is_moving"
         }
       }
     }
   }
   ```

   The four Resolver limits are required whenever `sources` is not empty; the
   service exits at startup if any is missing. `max_pose_age_s` must be at least
   `poll_interval_s + max_timestamp_uncertainty_s`. See
   [Configure](positioning.md#configure) for their meaning.

   These examples explicitly use HTTP for isolated lab cameras. Production
   configurations should use HTTPS; HTTP is only appropriate on an isolated network
   or protected tunnel.

   Choose `move_status` per camera:

   | Camera behavior during the probe                             | Setting                                          |
   | ------------------------------------------------------------ | ------------------------------------------------ |
   | `GetStatus` reports `MOVING` while moving                    | `"move_status": "get_status"`                    |
   | `GetStatus` always reports `IDLE`, a move event is available | `"move_status": "event"` plus `move_event`       |
   | Neither is reliable                                          | `"move_status": "none"`                          |
   | You want event records for calibration only                  | Keep `get_status` or `none` and add `move_event` |

   `credentials_file` is the path inside the container, not on the host.

4. Assign every configured source to the same `resolver_id` in
   `positioning/.local/positioning-assignments.json`:

   ```json
   {
     "lab-ptz-1": "positioning-lab",
     "lab-ptz-2": "positioning-lab"
   }
   ```

5. Create `positioning/.local/compose.override.yml` to mount the configuration,
   manifest, and credentials into the Positioning service, and the same manifest
   and `resolver_id` into Manager (`web`), which authorizes pose writes only for
   sources assigned to that resolver. Compose replaces the
   whole `command` list, so repeat the broker and NTP options; without `--ntp`,
   clock synchronization cannot be verified and every pose is invalid. Set `user`
   to your host user and group IDs (`id -u` and `id -g`) so the service can read
   the `0600` credential files:

   ```yaml
   services:
     positioning:
       user: "1000:1000"
       command:
         - --broker
         - broker.scenescape.intel.com
         - --brokerauth
         - /run/secrets/positioning.auth
         - --cert
         - /run/secrets/certs/scenescape-positioning.crt
         - --keyfile
         - /run/secrets/certs/scenescape-positioning.key
         - --rootcert
         - /run/secrets/certs/scenescape-ca.pem
         - --ntp
         - ntpserv
         - --config
         - /run/positioning/positioning.json
         - --assignments
         - /run/positioning/positioning-assignments.json
       volumes:
         - ./positioning/.local/positioning.json:/run/positioning/positioning.json:ro
         - ./positioning/.local/positioning-assignments.json:/run/positioning/positioning-assignments.json:ro
         - ./positioning/.local/secrets:/run/secrets/onvif:ro
     web:
       environment:
         - POSITIONING_RESOLVER_ID=positioning-lab
       volumes:
         - ./positioning/.local/positioning-assignments.json:/run/positioning/positioning-assignments.json:ro
   ```

   The secret files mounted by the base Compose file (broker auth and
   certificates) must also be readable by the user ID you set.

6. Start the demo stack, then recreate only the Positioning service with the
   override. `make demo` generates the root `docker-compose.yml` and starts
   Positioning with the default configuration, which has no sources:

   ```bash
   SUPASS=<password> make build-core demo
   ```

   From the repository root, apply the override and follow the service logs:

   ```bash
   docker compose -f docker-compose.yml -f positioning/.local/compose.override.yml \
     --profile controller up -d positioning web
   docker compose logs -f positioning
   ```

   The first command merges the override into the `positioning` and `web` services
   and recreates only those containers. The broker and other services keep running. Use
   `--profile tracker` instead if the stack runs the Tracker profile. Run the
   command again after you edit any file in `positioning/.local/`. The files are
   read only at startup.

At startup the service logs `Configured PTZ sources: [...]` and
`PTZ source <id> connected: ...` for each camera. Default INFO logs show a short
`Camera <id>: ready (stationary)` or `Camera <id>: unavailable (<reason>)`
message only when the resolved state or calibration version changes. Unchanged
samples and periodic metrics do not produce INFO entries. Warnings and errors
remain visible.

The `calibration=...` suffix identifies the PTZ movement-model version loaded
from Manager's `camera.ptz_calibration.calibration_version`. It is chosen by
the operator or export tool, not generated by Positioning, and is separate from
the static AprilTag/manual reference pose. It does not indicate when the latest
UI calibration was saved or prove current projection accuracy. See
[Understanding the Model Version](../../positioning-api-reference.md#understanding-the-model-version)
and the [ideal-camera example](../../positioning-api-reference.md#ideal-camera-example).

Add `--log-level DEBUG` to the Positioning service command to include the
structured `ptz_move_event` records and full `positioning_metrics` snapshots
every 60 seconds. Metrics collection and MQTT pose publication are unchanged
by log verbosity. Configuration errors,
such as a source missing from the manifest, unknown keys, or an unreadable
credentials file, stop the service with a message that names the source.

For Helm, set `positioning.logLevel=DEBUG` in your deployment values (or use
`helm upgrade --set positioning.logLevel=DEBUG`). Return to `INFO` after
diagnostics if the extra event and metrics records are not needed.

To return to the default service shell, recreate the service without the override
file:

```bash
docker compose --profile controller up -d positioning
```

If `pgserver` fails at startup because it found PostgreSQL data from another
checkout, the checkouts share Compose volumes, which are prefixed `scenescape_` by
default. Set a distinct `COMPOSE_PROJECT_NAME` for this checkout before
`make demo`, and pass the same value to the `docker compose` commands above.

## Troubleshoot ONVIF Access

Start with the probe (see
[PTZ Camera Onboarding Check](#ptz-camera-onboarding-check)). It reports the same
errors as the service, and its `clock_offset_s` field shows the camera clock minus
the host clock.

### Clocks not synchronized

ONVIF uses WS-Security `UsernameToken` digest authentication. The token includes a
`Created` timestamp, and cameras reject tokens outside a short window around their
own clock, often about 5 seconds. Replay attack protection also rejects reused
nonces. Without clock compensation, a camera whose clock differs from the host
rejects correct credentials with:

```text
SOAP fault ...:Sender/ter:NotAuthorized: Sender not authorized
```

The poller handles this. Before authenticating, it reads the camera clock with an
unauthenticated `GetSystemDateAndTime` call and offsets `Created` by the measured
difference. After any `NotAuthorized` fault, it reads the camera clock again and
retries once. A camera clock that is off by minutes or years therefore still
authenticates. Do not disable replay protection to work around clock skew; other
ONVIF tools that do not compensate for skew may fail where the poller succeeds.

You may still see clock-related failures in these cases:

- **The camera clock drifts quickly.** One lab camera without NTP drifted about
  7 seconds per hour. Each time the drift exceeds the camera's window, one request
  fails, the clock is resynchronized, and the retry succeeds. That sample has a
  larger timestamp uncertainty. Enable NTP on the camera to avoid this.
- **The camera returns an unreadable time.** The service reports
  `Malformed GetSystemDateAndTime response`. Set the camera time manually or
  through NTP.
- **The host clock is wrong.** Samples are timestamped with the host clock, not the
  camera clock. Check that the host is synchronized:

  ```bash
  timedatectl | grep -i synchronized   # expect: System clock synchronized: yes
  ```

To read the camera clock without credentials:

```bash
curl -s --noproxy '*' -H 'Content-Type: application/soap+xml' \
  -d '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>' \
  http://<camera-host>:<onvif-port>/onvif/device_service
```

The `UTCDateTime` element in the response is the camera's UTC time.

### Other common errors

| Message in probe or service logs                                | Likely cause and fix                                                                                                                                                                     |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NotAuthorized` that persists after the camera clock is correct | Wrong username or password, or a web UI account instead of an ONVIF account. Check the ONVIF user list on the camera.                                                                    |
| `HTTP 401 without SOAP body`                                    | The camera requires HTTP Digest and rejected the credentials. Verify the account and its role.                                                                                           |
| `HTTP 403 without SOAP body` after failed attempts              | Brute-force protection temporarily blocked the host IP. Wait a few minutes before retrying; the service backs off automatically.                                                         |
| `ConnectTimeout calling ...` or `ConnectionError calling ...`   | Wrong host or port, ONVIF disabled, or a firewall in between. Check the port from the host, for example with the `curl` command above.                                                   |
| `Device does not advertise ONVIF Media and PTZ services`        | ONVIF PTZ is not enabled, or the camera is not a PTZ model.                                                                                                                              |
| `No media profile with a PTZ configuration`                     | No media profile has a PTZ configuration, or `profile_token` names a profile without one. Add PTZ to a profile, or remove `profile_token`.                                               |
| `PTZ move event subscription ... failed`                        | The camera has no free PullPoint subscriptions. Cameras limit concurrent subscriptions (Axis: 4), and other clients may hold them. Stop other ONVIF event clients or restart the camera. |
| Samples with NaN ranges                                         | The position space reported by `GetStatus` is not advertised by the PTZ node. Check the camera's PTZ configuration and firmware.                                                         |

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
has one replica and uses a `Recreate` rollout to prevent old and new resolver pods
from publishing simultaneously for the same source. This preserves single-writer
ownership at the cost of a brief interruption during upgrades. Do not scale the
deployment above one replica; the service has no leader election.

For Helm ONVIF credentials, prefer a pre-created Kubernetes Secret and set
`positioning.onvifCredentials.existingSecret` to its name. Store one key named
`<source_id>.json` per camera; each file contains its ONVIF username and password.
For example:

```bash
kubectl create secret generic positioning-onvif \
  --from-file='<source_id>.json=./<source_id>.json' -n <NAMESPACE>
helm upgrade scenescape kubernetes/scenescape-chart -n <NAMESPACE> \
  --reuse-values --set positioning.onvifCredentials.existingSecret=positioning-onvif
```

Do not put production credentials in Helm values: Helm release records retain
provided values, even when a chart renders them into a Kubernetes Secret. The
chart's `positioning.onvifCredentials.sources` option is intended for disposable
development installations. After changing or rotating a mounted ONVIF Secret,
increment `positioning.onvifCredentials.rolloutRevision` in the Helm upgrade so
the pollers restart and load the new credentials. The pod template records only
this caller-supplied revision, not credential data or a credential-derived hash.

The service publishes resolved poses but does not alter detections, because Controller
and Tracker do not consume them yet. Roll back PTZ polling and pose publishing by
removing `sources` from the deployment configuration, or roll back the
whole service by disabling the Positioning deployment. Later PTZ rollout rollback is
per consumer: disable the corresponding Controller or Tracker PTZ flag and return to
static projection.
