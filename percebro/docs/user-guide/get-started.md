# Get Started with Percebro

## Prerequisites

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.

- [How to build Percebro from source](How-to-build-source.md)

## Running the service using Docker Compose

- **Navigate to the Directory**:

  ```bash
  cd scenescape
  ```

- **Generate secrets**:

  ```bash
  make build-secrets
  ```

- **Start the service**:
  Start the service using docker run:

  ```bash
  docker run --rm \
  --init \
  --network scenescape \
  --device /dev/dri:/dev/dri \
  -v $(pwd)/model_installer/models:/opt/intel/openvino/deployment_tools/intel_models \
  -v $(pwd)/sample_data:/home/scenescape/SceneScape/sample_data \
  -v $(pwd)/manager/secrets/percebro.auth:/run/secrets/percebro.auth:ro \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  --name retail-video \
  scenescape-percebro \
  percebro \
  --camera=sample_data/apriltag-cam1.mp4 \
  --cameraid=camera1 \
  --intrinsics='{"fov":70}' \
  --camera=sample_data/apriltag-cam2.mp4 \
  --cameraid=camera2 \
  --intrinsics='{"fov":70}' \
  --camerachain=retail \
  --ntp=ntpserv \
  --auth=/run/secrets/percebro.auth \
  broker.scenescape.intel.com
  ```

- **Note**:
  - The secrets folder contains auth files and certificates for connecting to a secure mosquitto broker with authentication enabled.
  - The `percebro` service **depends on** the `broker` and `ntpserv`services.
    Before starting this container, ensure that:
    - The **broker** service at `broker.scenescape.intel.com` is up and reachable.
    - The **ntpserv** service at `udp://<host-ip>:123` which maps to port `123/udp` inside the container.

- **Verify the service**:
  Check that the service is running:

  ```bash
  docker ps
  ```

- **Stop the service**:

  ```bash
  docker stop retail-video
  ```

## Percebro Options

To run Percebro directly and view its help documentation, first launch the Percebro Docker container.

    $ tools/scenescape-start --image scenescape-percebro:latest --shell
    scenescape@hostname:/home/user/SceneScape$ cd percebro/
    scenescape@hostname:/home/user/SceneScape/percebro$ ./percebro -h
    usage: percebro [-h] [--camerachain CAMERACHAIN] --camera CAMERA [--cameraid CAMERAID]
                    [--sensor SENSOR] [--sensorchain SENSORCHAIN] [--sensorattrib SENSORATTRIB]
                    [-e THRESHOLD] [--window] [--usetimestamps] [--ntp NTP] [--virtual VIRTUAL]
                    [--debug] [--aspect ASPECT] [--intrinsics INTRINSICS] [--distortion DISTORTION]
                    [--override-saved-intrinsics] [--frames FRAMES] [--stats] [--waitforstable]
                    [--preprocess] [--realtime] [--faketime] [--modelconfig MODELCONFIG]
                    [--rootcert ROOTCERT] [--cert CERT] [--auth AUTH] [--cvcores CVCORES]
                    [--ovcores OVCORES] [--unwarp] [--ovmshost OVMSHOST]
                    [--resolution RESOLUTION] [--framerate FRAMERATE]
                    [--cv_subsystem CV_SUBSYSTEM]
                    [--maxcache MAXCACHE] [--filter FILTER] [--disable_rotation]
                    [--maxdistance MAXDISTANCE] [--infrared]
                    [broker]

    positional arguments:
    broker                hostname or IP of MQTT broker

    options:
    -h, --help            show this help message and exit
    --camerachain CAMERACHAIN, -m CAMERACHAIN, --model CAMERACHAIN
                          model to use for camera
    --camera CAMERA, -i CAMERA, --input CAMERA
                          video source to be used. If using /dev/video0 the argument should be -i 0
    --cameraid CAMERAID, --mqttid CAMERAID
                          camera id to use instead of MAC+input
    --sensor SENSOR       name and optional bounding box to publish as sensor
    --sensorchain SENSORCHAIN
                          model chain to use for sensor
    --sensorattrib SENSORATTRIB
                          attribute/field name of data to use for sensor value
    -e THRESHOLD, --threshold THRESHOLD
                          Threshold to filter keypoints
    --window              Display inferencing results in a window
    --usetimestamps       Use file timestamps to synchronize videos
    --ntp NTP             NTP server, default is to use mqtt broker
    --virtual VIRTUAL     JSON list for virtual cameras
    --debug               Run in debug mode, don't connect to MQTT broker or NTP server
    --aspect ASPECT       aspect ratio to force
    --intrinsics INTRINSICS
                          camera intrinsics as diagonal_fov, "[horizontal_fov, vertical_fov]", or "[fx, fy, cx, cy]"
    --distortion DISTORTION
                          camera distortion coeffs, "[k1,k2,p1,p2[,k3[,k4,k5,k6[,s1,s2,s3,s4[,taux,tauy]]]]]"
    --override-saved-intrinsics
                          Override camera intrinsics in database with command line values
    --frames FRAMES       process this many frames and then exit
    --stats               Print FPS/latency stats
    --waitforstable       Print FPS/latency stats
    --preprocess          Preprocess video files into json files and exit
    --realtime            Drop frames to keep video at original speed during processing <preprocess only>
    --faketime            Write timestamps as fast as they occur <preprocess only>
    --modelconfig MODELCONFIG
                          JSON file with model configuration
    --rootcert ROOTCERT   path to ca certificate
    --cert CERT           path to client certificate
    --auth AUTH           user:password or JSON file for MQTT authentication
    --cvcores CVCORES     Number of threads to request for OpenCV
    --ovcores OVCORES     Number of threads to request for OpenVINO
    --unwarp              Unwarp image before inference
    --ovmshost OVMSHOST   OVMS host
    --resolution RESOLUTION
                          Requested frame resolution (WxH)
    --framerate FRAMERATE
                          Requested framerate
    --cv_subsystem CV_SUBSYSTEM
                          Hardware device requested for decoding. Options are 'CPU' (default), 'ANY', 'GPU', or 'GPU.X' where X refers to the card available at /dev/dri/cardX
    --maxcache MAXCACHE   Max video cache size in frames. Specify the desired max number of frames to process in parallel.
    --filter FILTER       Bounding box filtering for sub-detections. Options are 'bottom', 'top', or 'none'. This will allow only the bottom-most, top-most, or all detections through. Default is 'none'
    --disable_rotation    Disable closest face transform algorithm for 3d object detection
    --maxdistance MAXDISTANCE
                          Max distance from camera for object detection. Objects beyond this threshold will be dropped.
    --infrared            Use infrared channel, for RealSense cameras or ROSBAG files. Note this will affect all cameras for this instance.

### Note on passing intrinsics for multiple streams.

To configure inferencing for multiple streams, follow one of the two best practices:

- Use a percebro instance per stream and provide intrinsics as needed.
- When using the same percebro instance to configure multiple streams, provide intrinsics for each and every stream, to avoid any association issues.

## Next Steps

- [How to connect to different input sources](How-to-connect-to-different-input-sources.md)
- [How to enable different models for inferencing](How-to-enable-different-models-for-inferencing.md)
- [How to improve performance](How-to-improve-performance.md)
- [How to chain models and sensors](How-to-chain-models-and-sensors.md)
- [How to run OVMS inferencing](How-to-run-OVMS-inferencing.md)
- [How to add custom models](How-to-add-custom-models.md)
