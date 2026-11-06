# Simulated Drone Camera — External-Source Demo

A self-contained example of feeding Scenescape from a **moving camera** via
the external-source contract
([External Source Input Message Format](../../docs/user-guide/microservices/controller/data_formats.md#external-source-input-message-format)):
a DL Streamer pipeline consumes a simulated drone view built from the Queuing
sample recording, detects people, and publishes them as `external_source`
messages enriched with the simulated drone pose and camera calibration. It
publishes on the `drone` thing-type topic: Scenescape uses that category for
the drone platform object, while each camera detection retains its `person`
category. The Scene Controller localizes the pixel detections into a scene you
create, so tracked people stay at stable positions while the camera view
visibly moves.
The live (warped) drone view can be watched directly in the Scenescape web UI.

## How the simulation works

Warping a fixed camera's video cannot create parallax, so the simulated drone
**hovers** at the recording camera's optical center with a sweeping gimbal
(yaw/pitch/roll) and varying zoom. Each frame is warped with the homography
`H(t) = K'(t) · R(t)ᵀ · K₀⁻¹`, and the **same** `R(t)` and `K'(t)` drive the
published `pose` and `cameras[*].intrinsics` — the published geometry always
matches the warped pixels.

## Contents

```text
sample_data/drone_sim/
├── README.md                  This guide
├── compose.drone-video.yml    Video source + DL Streamer Pipeline Server deployment
├── drone-video-config.json    DL Streamer Pipeline Server pipeline definition
├── drone_sim_config.json      Camera calibration, flight profile, publisher identity
├── drone_cam_sim.py           Flight-profile and warp/pose geometry (numpy + cv2)
└── python/                    GStreamer plugins (loaded via ADDITIONAL_GST_PLUGIN_PATH)
    ├── sscape_drone_motion_sim.py       Warps frames, attaches pose metadata
    └── sscape_external_source_publish.py  Publishes external_source messages
                                           and serves the web UI live view
```

## The pipeline

`drone-video-config.json` defines the GStreamer pipeline run by DL Streamer
Pipeline Server:

```text
rtspsrc (drone-cam1 loop)
  → decode → BGR
  → sscape_drone_motion_sim      warp frame per flight profile; attach pose,
  │                              mount, and zoomed intrinsics as GVA JSON meta
  → gvadetect                    person-detection-retail-0013
  → gvametaconvert
  → sscape_external_source_publish
                                 build the external_source message and publish to
                                 scenescape/external/sim-drone-qcam1/drone;
                                 answer web UI "getimage" commands with JPEG frames
```

Each message carries the scene-frame `pose` of the drone body, one `cameras`
entry (`id`, `mount`, per-frame `intrinsics`), and the person detections as
`bounding_box_px` observations. Frames without detections still publish,
refreshing the controller's cached pose. The topic's final segment (`drone`)
sets the platform category; the detections remain `person`. `track: true`
routes the observations through Scenescape tracking.

Pipeline parameters (adjustable via the DL Streamer Pipeline Server REST API
or the `payload.parameters` block): `detection_threshold`, `show_hud` (draw
yaw/pitch/roll/zoom onto the frames), `thing_type` (the drone platform category;
leave it as `drone`), `detection_labels` (the detected categories; leave it as
`person`), `track`, and `cameraid` (the web UI camera served with live frames;
see below).

## Set up the demo

Prerequisites: a running Scenescape stack with the
`person-detection-retail-0013` model in the models volume (see the
[DL Streamer Pipeline Server guide](../../dlstreamer-pipeline-server/README.md)).

### 1. Create a scene

In the web UI, create a new scene (for example `Drone Demo`). For a meaningful
map that matches the recording, extract `Queuing.png` from
`sample_data/demo_scenes/Queuing/Queuing.zip`, upload it as the scene map, and
set the scale to **157 pixels per meter** (the drone's published poses use the
coordinate frame of that map's calibration). Note the new scene's uid, shown
on the scene card and in its page URL.

### 2. Define the drone object and upload your model

In the Scenescape Object Library, create an object named exactly `drone`. For this object you can
upload your own `.glb` file as its 3D model. The external topic ends in `/drone`,
so the Scene Controller creates the platform object with this category; its
`id` is the publisher's `source_id`. Keep the model origin at the drone body
origin and adjust its scale, orientation, and offset in the Object Library as
needed. See
[How to Define Object Properties](../../docs/user-guide/other-topics/how-to-define-object-properties.md)
for the Object Library steps. This demo does not include a drone model.

### 3. Register a camera for the live drone view (optional)

The web UI displays camera video by requesting JPEG frames over MQTT; the
publisher element serves that protocol, so the warped drone view can be
watched in the UI. In the new scene, add a camera with **Camera ID**
`sim-drone-view` (any name). No video pipeline is attached to this camera in
Scenescape itself — the demo publisher answers its image requests. To skip
this, set the `cameraid` payload parameter in `drone-video-config.json` to an
empty string.

### 4. Bind the publisher to the scene

The pose uses the `scene` reference frame, which requires a manual binding and
positioning trust. Add to `.env` at the repository root:

```sh
CONTROLLER_EXTERNAL_SOURCE_BINDINGS=sim-drone-qcam1:<scene-uid>
CONTROLLER_TRUSTED_POSITIONING_SOURCES=sim-drone-qcam1
```

and recreate the Scene Controller to ingest these new settings:

```sh
docker compose --profile controller up -d scene
```

### 5. Start the video source and pipeline

Shares the running stack's network and models volume:

```sh
docker compose --project-directory . -f sample_data/drone_sim/compose.drone-video.yml up -d
```

### 6. Watch it work

- **Web UI**: open the new scene. Tracked people appear on the map, localized
  from the drone's moving view. If the `.glb` asset has been defined - the drone platform
  appears as it. Open the `sim-drone-view` camera (scene page camera panel or camera detail page) and
  enable live view to watch the warped, annotated drone frames — with
  `show_hud` enabled the current yaw/pitch/roll/zoom is drawn on each frame.

Stop the demo:

```sh
docker compose --project-directory . -f sample_data/drone_sim/compose.drone-video.yml down
```

## Tuning the flight

Edit `flight` in `drone_sim_config.json` (`period_s`, per-axis amplitudes in
degrees, zoom range) and restart the `drone-video` service. Keep amplitudes
modest: the warp must never sample outside the original frame or black
borders appear at the view edges (the defaults keep ≈20 px of margin).

## Adapting to another scene or camera

- Point `base_camera` in `drone_sim_config.json` at your camera's intrinsics,
  resolution, and calibrated pose (translation in metres, XYZ Euler rotation
  in degrees, as shown on the camera calibration page). The published poses
  are expressed in that calibration's scene coordinate frame, so the bound
  scene must use the same map and scale.
- Replace the looped recording in `compose.drone-video.yml` (`drone-cam`
  service) with your own video or live RTSP source of that camera.
- Choose a persistent `source_id` and update the controller binding
  environment variables accordingly.
