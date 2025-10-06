# How to Configure DLStreamer Video Pipeline

## Video Pipeline Configuration in UI camera calibration page (in Kubernetes deployment)

When SceneScape is deployed in a Kubernetes environment, you can configure DLStreamer video pipelines directly through the camera calibration web interface. This provides a user-friendly way to generate and customize GStreamer pipelines for your cameras without manually editing configuration files.

### Accessing the Camera Calibration Page

1. Navigate to your SceneScape web interface.
2. Select a scene from the main dashboard.
3. Click an existing camera or create a new one.
4. Open the camera calibration page to access pipeline configuration options.

### Available Configuration Fields

In Kubernetes deployments, the camera calibration form provides access to a subset of camera configuration fields that are specifically relevant to pipeline generation:

#### Core Pipeline Fields

- **Camera (Video Source)**: specifies the video source command. Supported formats:
  - RTSP streams: `rtsp://camera-ip:554/stream` (raw H.264).
  - HTTP/HTTPS streams: `http://camera-ip/mjpeg` (MJPEG).
  - File sources: `file://video.ts` (relative to video folder).
- **Camera Chain**: defines the sequence or combination of AI models to chain together in the pipeline using their short identifiers (e.g., "retail"). Models can be chained serially (one after another) or in parallel arrangements. These identifiers are defined in the model configuration file with their detailed parameters needed for pipeline generation.

> **Note**: Currently, only limited model chaining is supported. See the limitations section below.

- **Camera Pipeline**: The generated or custom GStreamer pipeline string

#### Advanced Configuration

- **Decode Device**: video decoding device settings (CPU or GPU).
- **Model Config**: references a model configuration file. Model configuration files are managed in the Models page and stored in the folder `Models/models/model_configs`. You can upload custom model configuration files or modify existing ones using the Models page. The Models page is accessible in the top menu of the SceneScape UI.

> **Note**: The Model Config field references configuration files that define AI model parameters and processing settings. See [Model Configuration File Format](Model-configuration-file-format.md) for more details.

#### Camera Intrinsics and Distortion

- **Intrinsics**: camera focal lengths (fx, fy) and principal point coordinates (cx, cy).
- **Distortion Coefficients**: k1, k2, k3, p1, p2 for lens distortion correction.

### Generating a Pipeline Preview

The camera calibration page provides an automated pipeline generation feature:

1. **Fill in Required Fields**: enter the necessary camera configuration parameters:
   - Set the **Camera (Video Source)** (e.g., `rtsp://camera-ip:554/stream`).
   - Configure **Camera Chain** settings, if needed.
   - Select the appropriate **Model Config**.

2. **Generate Pipeline Preview**: click the **"Generate Pipeline Preview"** button.
   - The system will automatically generate a GStreamer pipeline based on your configuration.
   - The generated pipeline appears in the **Camera Pipeline** text area.
   - You can review the pipeline structure and elements.

3. **Review Generated Pipeline**: the generated pipeline will include:
   - Video source configuration based on your Camera (Video Source) field.
   - AI model integration using the selected Model Config.
   - Camera intrinsics and distortion correction, if configured.
   - Metadata publishing for SceneScape integration.

### Customizing the Generated Pipeline

After generating a pipeline preview, you can make manual adjustments:

1. **Edit Pipeline String**: modify the generated pipeline in the Camera Pipeline text area.
   - Add or remove GStreamer elements as needed.
   - Adjust element parameters for specific requirements.
   - Ensure the pipeline maintains compatibility with SceneScape - do not modify `gvapython` or `cameraundistort` elements.

2. **Common Customizations**:
   - **Video Source**: change input source type (file, RTSP, USB).
   - **Model Parameters**: fine-tune AI model inference settings either in model config file or the **Camera Pipeline** field.

3. **Validation**: when you save the configuration or generate the pipeline preview, the system performs preliminary checks of the pipeline and reports an error if pipeline generation is not possible. However, it does not validate pipeline correctness in terms of GStreamer pipeline syntax and its functionality. You need to verify that the pipeline performs as expected.

> **Note**: Directly editing the **Camera Pipeline** preview will leave the component fields and GStreamer pipeline string out of sync. If any subsequent changes are made to component fields, they will not impact the GStreamer pipeline string unless the pipeline string is regenerated. Remember to adjust the GStreamer pipeline string manually or regenerate it from the updated fields in such cases.

### Saving and Applying Configuration

1. **Save Camera Configuration**: click **"Save Camera"** to apply your pipeline configuration.
   - The system automatically generates the camera pipeline if the field is empty.
   - Configuration is stored and deployed to the Kubernetes cluster.
   - The camera deployment is updated with the new pipeline.

2. **Automatic Pipeline Generation**: if you save the form with an empty Camera Pipeline field, the system automatically generates a pipeline based on other form fields, following best practices and standards for SceneScape. This ensures every camera has a valid pipeline configuration.

3. **Error Handling**: If pipeline generation fails, the form remains open for correction and error messages are displayed. Common issues include missing model configurations or invalid command syntax.

### Best Practices

- **Start with Generated Pipeline**: use the "Generate Pipeline Preview" button to create a baseline configuration.
- **Test Incrementally**: make small changes and test each modification.
- **Validate Model Config**: ensure your selected Model Config file exists and is properly formatted.
- **Monitor Performance**: check camera performance after applying pipeline changes.
- **Backup Configurations**: save working pipeline configurations for future reference.

### Limitations

- The pipeline generation errors are not shown correctly in the UI when **Save Camera** button is clicked in the Camera Calibration page with **Camera Pipeline** field empty. As a work-around, check the `kubeclient` Pod logs for errors.
- Multiple model chaining is not supported yet. Only a single detection model can be used as **Camera Chain**.
- The only **Decode Device** supported for now is `CPU`.
- Distortion correction is temporarily disabled due to a bug in DLStreamer-Pipeline-Server.
- Explicit frame rate and resolution configuration is not available yet.
- Network instability and camera disconnects are not handled gracefully for network-based streams (RTSP/HTTP/HTTPS) and may cause the pipeline to fail.
- Cross-stream batching is not supported since in SceneScape Kubernetes deployment each camera pipeline is running in a separate Pod.

### Troubleshooting

- **Pipeline Generation Errors**: check that all required fields are filled correctly.
- **Model Config Issues**: verify the model configuration file exists in the Models page and model(s) used in the **Camera Chain** field are defined in the model config file.
- **Video Source Problems**: ensure the Camera (Video Source) field contains a valid video source URL or a device path.
- **Deployment Failures**: check Kubernetes logs for detailed error information.

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
