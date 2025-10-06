# How to Configure DLStreamer Video Pipeline

SceneScape uses DLStreamer Pipeline Server as the Video Analytics microservice. The file [docker-compose-dl-streamer-example.yml](/sample_data/docker-compose-dl-streamer-example.yml) shows how a DLStreamer Pipeline Server docker container is configured to stream video analytics data for consumption by SceneScape. It leverages DLStreamer pipelines definitions in [queuing-config.json](/dlstreamer-pipeline-server/queuing-config.json) and [retail-config.json](/dlstreamer-pipeline-server/retail-config.json)

## Video Pipeline Configuration

The following is the GStreamer command that defines the video processing pipeline. It specifies how video frames are read, processed, and analyzed using various GStreamer elements and plugins. Each element in the pipeline performs a specific task, such as decoding, object detection, metadata conversion, and publishing, to enable video analytics in the SceneScape platform.

```
"pipeline": "multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json ! gvametaconvert add-tensor-data=true name=metaconvert ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
```

### Breakdown of gstreamer command

`multifilesrc` is a GStreamer element that reads video files from disk. The `loop=TRUE` parameter ensures the video will loop continuously. The `location` parameter specifies the path to the video file to be used as input. In this example, the video file is located at `/home/pipeline-server/videos/qcam1.ts`.
`decodebin` is a GStreamer element that automatically detects and decodes the input video stream. It simplifies the pipeline by handling various video formats without manual configuration.

`videoconvert` converts the video stream into a raw format suitable for further processing. In this case, it ensures the video is in the BGR format required by downstream elements.

`gvapython` is a GStreamer element that allows custom Python scripts to process video frames. In this pipeline, it is used twice:

- The first instance, `PostDecodeTimestampCapture`, captures timestamps and processes frames after decoding.
- The second instance, `PostInferenceDataPublish`, processes frames after inference and publishes metadata in SceneScape detection format as described in [metadata.schema.json](/controller/src/schema/metadata.schema.json)

`gvadetect` performs object detection using a pre-trained deep learning model. The `model` parameter specifies the path to the model file, and the `model-proc` parameter points to the model's preprocessing configuration.

`gvametaconvert` converts inference metadata into a format suitable for publishing. The `add-tensor-data=true` parameter ensures tensor data is included in the metadata.

`gvametapublish` publishes the metadata to a specified destination. In this pipeline, it sends the data to an `appsink` element for further processing or storage.

`appsink` is the final element in the pipeline, which consumes the processed video and metadata. The `sync=true` parameter ensures the pipeline operates in sync with the video stream.

Read the instructions here for details on how to further configure DLStreamer pipeline [DLStreamer Pipeline Server documentation](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/dlstreamer-pipeline-server/docs/user-guide) to customize:

- Input sources (video files, USB, RTSP streams)
- Processing parameters
- Output destinations
- Model-specific settings
- Camera intrinsics

### Parameters

This section describes the metadata schema and the format that the payload needs to align to.

```
"parameters": {
    "type": "object",
    "properties": {
        "ntp_config": {
            "element": {
                "name": "timesync",
                "property": "kwarg",
                "format": "json"
            },
            "type": "object",
            "properties": {
                "ntpServer": {
                    "type": "string"
                }
            }
        },
        "camera_config": {
            "element": {
                "name": "datapublisher",
                "property": "kwarg",
                "format": "json"
            },
            "type": "object",
            "properties": {
                "cameraid": {
                    "type": "string"
                },
                "metadatagenpolicy": {
                    "type": "string",
                    "description": "Meta data generation policy, one of detectionPolicy(default),reidPolicy,classificationPolicy"
                },
                "publish_frame": {
                    "type": "boolean",
                    "description": "Publish frame to mqtt"
                }
            }
        }
    }
},
```

#### Breakdown of parameters

- **ntp_config**: Configuration for time synchronization.
  - **ntpServer** (string): Specifies the NTP server to synchronize time with.
- **camera_config**: Configuration for the camera and its metadata publishing.
  - **intrinsics** (array of numbers): Defines the camera intrinsics. This can be specified as:
    - `[diagonal_fov]` (diagonal field of view),
    - `[horizontal_fov, vertical_fov]` (horizontal and vertical field of view), or
    - `[fx, fy, cx, cy]` (focal lengths and principal point coordinates).
  - **cameraid** (string): Unique identifier for the camera.
  - **metadatagenpolicy** (string): Policy for generating metadata. Possible values:
    - `detectionPolicy` (default): Metadata for object detection.
    - `reidPolicy`: Metadata for re-identification.
    - `classificationPolicy`: Metadata for classification.
  - **publish_frame** (boolean): Indicates whether to publish the video frame to MQTT.

The payload section is the actual values for the specific pipeline being configured:

```
"payload": {
    "destination": {
        "frame": {
            "type": "rtsp",
            "path": "atag-qcam1"
        }
    },
    "parameters": {
        "ntp_config": {
            "ntpServer": "ntpserv"
        },
        "camera_config": {
            "cameraid": "atag-qcam1",
            "metadatagenpolicy": "detectionPolicy"
        }
    }
}
```
