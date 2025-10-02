# How to Configure DLStreamer Video Pipeline

## Video Pipeline Configuration in UI camera calibration page (in Kubernetes deployment)

When SceneScape is deployed in a Kubernetes environment, you can configure DLStreamer video pipelines directly through the camera calibration web interface. This provides a user-friendly way to generate and customize GStreamer pipelines for your cameras without manually editing configuration files.

### Accessing the Camera Calibration Page

1. Navigate to your SceneScape web interface
2. Select a scene from the main dashboard
3. Click on an existing camera or create a new camera
4. Open the camera calibration page to access pipeline configuration options

### Available Configuration Fields

In Kubernetes deployments, the camera calibration form provides access to a subset of camera configuration fields that are specifically relevant for pipeline generation:

#### Core Pipeline Fields
- **Command**: Specifies the video source command (e.g., RTSP URL, USB device path)
- **Camera Chain**: Defines the camera processing chain configuration
- **Camera Pipeline**: The generated or custom GStreamer pipeline string

#### Advanced Configuration
- **CV Subsystem**: Computer vision subsystem settings
- **Model Config**: References a model configuration file (managed in the Models page)

#### Camera Intrinsics and Distortion
- **Intrinsics**: Camera focal lengths (fx, fy) and principal point coordinates (cx, cy)
- **Distortion Coefficients**: k1, k2, k3, p1, p2 for lens distortion correction

> **Note**: The Model Config field references configuration files that define AI model parameters and processing settings. For details on the model configuration file format, see [Model Configuration File Format](Model-configuration-file-format.md).

### Generating a Pipeline Preview

The camera calibration page provides an automated pipeline generation feature:

1. **Fill in Required Fields**: Enter the necessary camera configuration parameters:
   - Set the **Command** field with your video source (e.g., `rtsp://camera-ip:554/stream`)
   - Configure **Camera Chain** settings if needed
   - Select appropriate **Model Config** from available options

2. **Generate Pipeline Preview**: Click the **"Generate Pipeline Preview"** button
   - The system will automatically generate a GStreamer pipeline based on your configuration
   - The generated pipeline appears in the **Camera Pipeline** text area
   - You can review the pipeline structure and elements

3. **Review Generated Pipeline**: The generated pipeline will include:
   - Video source configuration based on your Command field
   - AI model integration using the selected Model Config
   - Camera intrinsics and distortion correction if configured
   - Metadata publishing for SceneScape integration

### Customizing the Generated Pipeline

After generating a pipeline preview, you can make manual adjustments:

1. **Edit Pipeline String**: Modify the generated pipeline in the Camera Pipeline text area
   - Add or remove GStreamer elements as needed
   - Adjust element parameters for specific requirements
   - Ensure the pipeline maintains compatibility with SceneScape

2. **Common Customizations**:
   - **Video Source**: Change input source type (file, RTSP, USB)
   - **Resolution**: Adjust video resolution and format conversion
   - **Frame Rate**: Modify frame rate limits or processing intervals
   - **Model Parameters**: Fine-tune AI model inference settings

3. **Validation**: The system validates the pipeline syntax when you save the configuration

### Saving and Applying Configuration

1. **Save Camera Configuration**: Click **"Save Camera"** to apply your pipeline configuration
   - The system automatically generates the camera pipeline if the field is empty
   - Configuration is stored and deployed to the Kubernetes cluster
   - The camera deployment is updated with the new pipeline

2. **Automatic Pipeline Generation**: If you save the form with an empty Camera Pipeline field:
   - The system automatically generates a pipeline based on other form fields
   - This ensures every camera has a valid pipeline configuration
   - The generated pipeline follows SceneScape best practices and standards

3. **Error Handling**: If pipeline generation fails:
   - Error messages are displayed in the form
   - The form remains open for corrections
   - Common issues include missing model configurations or invalid command syntax

### Best Practices

- **Start with Generated Pipeline**: Use the "Generate Pipeline Preview" button to create a baseline configuration
- **Test Incrementally**: Make small changes and test each modification
- **Validate Model Config**: Ensure your selected Model Config file exists and is properly formatted
- **Monitor Performance**: Check camera performance after applying pipeline changes
- **Backup Configurations**: Save working pipeline configurations for future reference

### Troubleshooting

- **Pipeline Generation Errors**: Check that all required fields are filled correctly
- **Model Config Issues**: Verify the model configuration file exists in the Models page
- **Video Source Problems**: Ensure the Command field contains a valid video source URL or device path
- **Deployment Failures**: Check Kubernetes logs for detailed error information

## Video Pipeline Configuration using Pipeline Generator tool

TBD

## Manual Video Pipeline Configuration (in Docker Compose deployment)

SceneScape uses DLStreamer Pipeline Server as the Video Analytics microservice. The file [docker-compose-dl-streamer-example.yml](/sample_data/docker-compose-dl-streamer-example.yml) shows how a DLStreamer Pipeline Server docker container is configured to stream video analytics data for consumption by SceneScape. It leverages DLStreamer pipelines definitions in [queuing-config.json](/dlstreamer-pipeline-server/queuing-config.json) and [retail-config.json](/dlstreamer-pipeline-server/retail-config.json)

### Video Pipeline Configuration

The following is the GStreamer command that defines the video processing pipeline. It specifies how video frames are read, processed, and analyzed using various GStreamer elements and plugins. Each element in the pipeline performs a specific task, such as decoding, object detection, metadata conversion, and publishing, to enable video analytics in the SceneScape platform.

```
"pipeline": "multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json ! gvametaconvert add-tensor-data=true name=metaconvert ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
```

#### Breakdown of gstreamer command

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

#### Parameters

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

##### Breakdown of parameters

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

#### Cross stream batching

DL Streamer Pipeline Server supports grouping multiple frames into a single batch submission during model processing. This can improve throughput when processing multiple video streams with the same pipeline configuration.

`batch-size` is an optional parameter which specifies the number of input frames grouped together in a single batch.

Read the instructions on how to configure cross stream batching in [DLStreamer Pipeline Server documentation](https://docs.openedgeplatform.intel.com/edge-ai-libraries/dlstreamer-pipeline-server/main/user-guide/advanced-guide/detailed_usage/how-to-advanced/cross-stream-batching.html)
