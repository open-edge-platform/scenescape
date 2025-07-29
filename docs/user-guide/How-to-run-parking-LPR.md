# Parking License Plate Recognition (LPR) Setup Guide

This guide explains how to set up and run the parking License Plate Recognition system using the DeepScenario pipeline.

## Prerequisites

- Docker and Docker Compose installed
- Access to the encoded model files and password
- SceneScape environment set up

## Setup Steps

### 1. Prepare the Encoded Model

Copy your encoded model files and password to the dlstreamer-pipeline-server user_scripts directory:

```bash
# Navigate to the user_scripts directory
cd scenescape/dlstreamer-pipeline-server/user_scripts/

# Copy your model files
cp /path/to/your/model.enc .
cp /path/to/your/password.txt .

# Ensure the DeepScenario.py and deepscenario_utils.py are present
ls -la DeepScenario.py deepscenario_utils.py
```

Make sure the `utils.py` script provided is renamed to `deepscenario_utils.py`.
This is necessary to avoid a name clash inside dl-streamer-pipeline server container.

### 2. Download Required Models

To download the required models for license plate detection and optical character recognition please refer to
the [dl-streamer gstreamer example](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/dl-streamer/samples/gstreamer/gst_launch/license_plate_recognition#models).

The expected location of the models is `scenescape/model_installer/models/public/`

### 3. Copy the parking lot video to sample_data

```bash
cd scenescape/sample_data

cp /path/to/your/parkingVideo.mp4 SampleVideo.mp4
```

### 4. Build the extended Docker container based on the DL Streamer Pipeline Server docker image

Running the `DeepScenario` script requires additional Python modules installed in the container,
which are not present present in the released DL Streamer Pipeline Server docker image.

This can be done using the following Dockerfile:

```Dockerfile
FROM dls-ps-3.1.0-extended # TODO reference publicly available image

USER root

RUN pip3 install scipy argon2-cffi cryptography opencv-python numpy openvino onnxruntime

RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

USER intelmicroserviceuser
```

And then building the image with:

```bash
docker build . -t dls-pipeline-server-extended
```

### 5. Modify Docker Compose Configuration

Edit the `docker-compose-dl-streamer-example.yml` file to disable the retail and queuing video services and enable the deepscenario service:

**Comment out the following sections:**

- `retail-video` service (lines ~170-220)
- `queuing-video` service (lines ~222-280)

**Ensure the deepscenario section is active:**

```yaml
deepscenario:
  image: dls-pipeline-server-extended
  privileged: true
  networks:
    scenescape:
  tty: true
  entrypoint: ["./run.sh"]
  ports:
    - "8082:8080"
    - "8556:8554"
  devices:
    - "/dev/dri:/dev/dri"
  depends_on:
    broker:
      condition: service_started
    ntpserv:
      condition: service_started
  environment:
    - RUN_MODE=EVA
    - DETECTION_DEVICE=CPU
    - CLASSIFICATION_DEVICE=CPU
    - ENABLE_RTSP=true
    - RTSP_PORT=8554
    - REST_SERVER_PORT=8080
    - GENICAM=Balluff
    - GST_DEBUG=GST_TRACER:7
    - ADD_UTCTIME_TO_METADATA=true
    - APPEND_PIPELINE_NAME_TO_PUBLISHER_TOPIC=false
    - MQTT_HOST=broker.scenescape.intel.com
    - MQTT_PORT=1883
  volumes:
    - ./dlstreamer-pipeline-server/deepscenario-config.json:/home/pipeline-server/config.json
    - ./dlstreamer-pipeline-server/user_scripts:/home/pipeline-server/user_scripts
    - vol-dlstreamer-pipeline-server-pipeline-root:/var/cache/pipeline_root:uid=1999,gid=1999
    - ./sample_data:/home/pipeline-server/videos
    - ./model_installer/models/public/ch_PP-OCRv4_rec_infer/FP32:/home/pipeline-server/models/ch_PP-OCRv4_rec_infer
    - ./model_installer/models/public/yolov8_license_plate_detector/FP32:/home/pipeline-server/models/yolov8_license_plate_detector
  secrets:
    - source: root-cert
      target: certs/scenescape-ca.pem
```

Add `maxlag` option to the scene controller command:
```yaml
command: controller --broker broker.scenescape.intel.com --ntp ntpserv --maxlag 25
```

### 6. Required Files Structure

Ensure your directory structure looks like this:

```
scenescape/
├── dlstreamer-pipeline-server/
│   ├── user_scripts/
│   │   ├── DeepScenario.py
│   │   ├── deepscenario_utils.py
│   │   ├── model.enc
│   │   ├── password.txt
│   │   ├── categories.json
│   │   └── intrinsics.json
│   └── deepscenario-config.json
├── model_installer/
│   └── models/
│       └── public/
│           ├── ch_PP-OCRv4_rec_infer/
│           │   └── FP32/
│           │       ├── ch_PP-OCRv4_rec_infer.xml
│           │       └── ch_PP-OCRv4_rec_infer.bin
│           └── yolov8_license_plate_detector/
│               └── FP32/
│                   ├── yolov8_license_plate_detector.xml
│                   └── yolov8_license_plate_detector.bin
└── sample_data/
    ├── docker-compose-dl-streamer-example.yml
    └── SampleVideo.mp4
```

### 7. Build and Run

```bash
DLS=1 make

DLS=1 make demo
```

### 8. Verification

Check that the services are running correctly:

```bash
# Check service status
docker-compose ps
```

### 9. Adding a new scene and a new camera

A new scene can now be created in UI. Camera ID that can be used to retrive the demo DeepScenario pipeline output is `lpr`.

For how to add a new scene please refer to [the docs](How-to-create-new-scene.md).


### Custom Pipeline Configuration

Modify the `deepscenario-config.json` file to customize:

- Input sources (camera, video files, RTSP streams)
- Processing parameters
- Output destinations
- Model-specific settings
- Camera intrinsics

### Camera Intrinsics: `intrinsics.json`

The `intrinsics.json` file contains the camera intrinsics parameters required for accurate geometric calibration and scene understanding. This file should be placed in the `scenescape/dlstreamer-pipeline-server/user_scripts/` directory alongside your other configuration files. Typical contents include the camera matrix and distortion coefficients.

This file should be updated after calibration. Refer to the [How-to-manually-calibrate-cameras](How-to-manually-calibrate-cameras.md) guide
on how to do that.
Each pipeline can have a seperate intrinsics file. The DeepScenario script accepts the path to `intrisics.json` file as the first argument.
