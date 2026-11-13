# How to Use the MLOps Flow

> **⚠️ Experimental feature.** The MLOps Flow is an **experimental**
> capability. The user interface, the Manager option, the environment variables
> and the behavior described here may change or be removed between releases
> without following the usual deprecation policy. It is supported only in
> Docker Compose deployments; the Helm chart provides no configuration for it.
> Do not use it in production deployments.

The MLOps Flow is the first stage of the MLOps integration described in
[ADR 12](https://github.com/open-edge-platform/scenescape/blob/main/docs/adr/0012-mlops-integration-reuse.md) and the
[MLOps integration design document](https://github.com/open-edge-platform/scenescape/blob/main/docs/design/mlops-integration-reuse.md):
pipelines are authored in ViPPET (Visual Pipeline and Platform Evaluation
Tool), and Scenescape runs them on DL Streamer Pipeline Server 2.0 (DLSPS).

The **Pipelines** page stores named GStreamer pipeline strings. Superusers can
create them by hand or import them from ViPPET. Selecting a stored pipeline on
a camera runs it on DLSPS.

For a ready-to-run setup with an external ViPPET, see the
[MLOps Flow demo](/sample_data/mlops_flow/README.md).

## Enabling the MLOps Flow

The MLOps Flow is disabled by default. While it is disabled, the pipelines
stay visible read-only: **Sync with ViPPET**, **+ New Pipeline**, edit and
delete, and the camera **Pipeline** selector are greyed out with a tooltip on
how to enable them. Their URLs return HTTP 403, existing camera selections are
kept unchanged, and Scenescape never contacts ViPPET or DLSPS. Enable it with
any of:

- the `--enable-mlops-flow` option of the Manager `webserver` command,
- `ENABLE_MLOPS_FLOW=true` in the environment of the `web` service.

## Configuration

Set these variables for the `web` (Manager) service. Leaving a variable empty
disables the matching feature, and the UI reports that it is not configured.

| Variable     | Example                     | Purpose                                   |
| ------------ | --------------------------- | ----------------------------------------- |
| `VIPPET_URL` | `http://vippet:7860/api/v1` | ViPPET REST API root, including `/api/v1` |
| `DLSPS_URL`  | `http://dlsps:8080`         | DLSPS 2.0 REST API root                   |

Export the variables before `make deploy`; Docker Compose passes them to the
`web` service.

## Sync with ViPPET

Click **Sync with ViPPET** on the **Pipelines** page to import ViPPET vision
pipelines. Each hardware variant becomes its own stored pipeline:

- **Name**: `<pipeline name> (<variant name>)`, for example `People (CPU)`.
- **Pipeline string**: the variant's GStreamer launch string from ViPPET.
- **ViPPET pipeline / variant ID**: `<pipeline id>/<variant id>`, shown
  read-only and used to match the pipeline on later syncs.

To import only some pipelines, enter ViPPET tags, separated by commas, in the
field next to the button, for example `Scenescape, Retail`, and choose how they
match:

- **Any**: the pipeline has at least one of the tags (default).
- **All**: the pipeline has every tag.

Tags match whole values and ignore case, so `scenescape` matches `Scenescape`
but `Retail` does not match `Retail Analytics`. An empty field imports every
pipeline. The filter only limits new imports: pipelines imported by an earlier
sync are still updated even if they no longer match. The sync summary shows
how many ViPPET pipelines matched, and your last filter is pre-filled for the
next sync.

A sync updates the name and string of previously imported pipelines, so local
edits to them are overwritten. Pipelines removed from ViPPET are kept. A variant
whose name is already used by another stored pipeline is skipped and listed in
the sync summary. When the string of a pipeline assigned to a camera changes,
that camera's DLSPS instance is restarted.

The imported strings still reference ViPPET-side model and video paths, which
must also be reachable from the DLSPS container.

## Running a Pipeline for a Camera

The **Pipeline** selector is available on the camera create, management and
calibration pages. Each stored pipeline can be assigned to at most one camera,
so the selector offers only unassigned pipelines plus the camera's current one.
When the camera is saved, Manager makes its DLSPS instance match the selected
pipeline:

| Situation                                                             | DLSPS action                           |
| --------------------------------------------------------------------- | -------------------------------------- |
| Pipeline selected, no instance running                                | Start an instance                      |
| Pipeline, its string or the Camera ID changed                         | Stop the old instance, start a new one |
| Pipeline cleared                                                      | Stop the instance                      |
| Recorded instance failed, ended, or is unknown to DLSPS               | Start a new one if a pipeline is set   |
| Recorded instance runs the selected pipeline and is queued or running | No action                              |

Instances are started with automatic restarts enabled (up to 5 attempts, 30
seconds apart) on pipeline error or end of stream. Beneath the **Pipeline**
selector, the camera pages show the UUID of the recorded instance and its live
DLSPS state (for example `QUEUED`, `RUNNING` or `ERROR`) with the DLSPS error
message, if any. DLSPS checks a pipeline after accepting it, so a rejected
pipeline shows as `ERROR` there a few seconds after the save; saving the camera
again reports the error and starts a new instance.

Before starting an instance, Manager sets `cameraid` on every
`sscape_post_inference_data_publish` element to the camera's ID, replacing any
value in the stored string, so detections are published for the camera the
pipeline is assigned to. Only element declarations are changed; text inside
quoted property values is left as it is. Changing the Camera ID, in the UI or
through the REST API, restarts the pipeline with the new ID. The Camera ID is
used as one MQTT topic level, so the camera pages, like the REST API, reject IDs
containing `/`, `+` or `#`.

Manager also appends an unlinked element, `identity name=sscape-launch-<uuid>`,
to every string it starts. It receives no data and does not change what the
pipeline does; its unique name lets Manager find the instance again if the
answer to the start request is lost, so you see it in the DLSPS
`launch_command`.

Related events:

- Editing the string of an assigned pipeline restarts that camera's instance.
- Deleting a camera stops its instance.
- Deleting a pipeline clears the camera's selection only; the running instance
  is stopped the next time the camera is saved.
- Concurrent saves of the same camera, from the camera pages or the REST API, are
  applied one after another, each from the latest saved state.

Before starting a replacement, Manager waits up to 10 seconds
(`DLSPS_STOP_TIMEOUT_S` in the `web` environment) for DLSPS to report that the
old instance has ended. If it has not ended by then (DLSPS
versions that cannot stop a `QUEUED` instance are asked again until it runs), or
if DLSPS is unreachable, the old instance stays recorded, no new one is started,
and a warning asks you to save the camera again. If DLSPS rejects a start, the camera is still saved
with a warning; saving it again retries. If DLSPS does not answer a start
request (for example, it times out), the camera page shows
`START UNCONFIRMED`; the next save looks in DLSPS for the instance carrying that
start's `sscape-launch-<uuid>` element and keeps it instead of starting a second
one. Instances of other starts, including other cameras running an identical
string, are never taken over, and nothing is started while DLSPS cannot be
checked. Manager commits the camera configuration before reconciling and
records a unique launch attempt before contacting DLSPS. If the worker exits
after the start, the next save can find the instance using that attempt.
Deleting a camera queues the stop of its instance together with the deletion;
a stop that cannot be confirmed right away is retried on later camera saves
and syncs, up to 10 times.

Limitations:

- A timed-out start can still reach DLSPS after an empty recovery scan. DLSPS
  has no caller-supplied idempotency key, so retrying may create a duplicate;
  check DLSPS for duplicates after retrying an unconfirmed start.
- Instances are not recreated automatically if DLSPS restarts; save the camera
  again to start a new one.
- ViPPET calls run during the request, and DLSPS reconciliation runs after its
  transaction commits but before the response is sent. Either can take several
  seconds when a service is slow.
- If the worker exits before the post-commit reconciliation runs, save the
  camera again to apply its selection. There is no background retry job.
- This mechanism is independent of the camera-settings based pipelines described
  in [How to Configure Deep Learning Streamer Video Pipeline](./how-to-configure-dlstreamer-video-pipeline.md).
