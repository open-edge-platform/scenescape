# How to Configure Deep Learning Streamer Video Pipeline

## Video Pipeline Configuration in UI Camera Calibration Page (in Kubernetes Deployment)

When Intel® SceneScape is deployed in a Kubernetes environment, you can configure Deep Learning Streamer (DL Streamer) video pipelines directly through the camera calibration web interface. This provides a user-friendly way to generate and customize GStreamer pipelines for your cameras without manually editing configuration files.

### Accessing the Camera Calibration Page

1. Navigate to your Intel® SceneScape web interface.
2. Select a scene from the main dashboard.
3. Click an existing camera or create a new one.
4. Open the camera calibration page to access pipeline configuration options.

### Available Configuration Fields

In Kubernetes deployments, the camera calibration form provides access to a subset of camera configuration fields that are specifically relevant to pipeline generation:

#### Core Pipeline Fields

- **Camera (Video Source)**: Specifies the video source command. Supported formats:
  - RTSP streams: `rtsp://camera-ip:554/stream` (raw H.264).
  - HTTP/HTTPS streams: `http://camera-ip/mjpeg` (MJPEG).
  - File sources: `file://video.ts` (relative to video folder, which is mounted from Sample-Data Volume). Streaming-friendly formats as MPEG-TS (.ts) are recommended. MP4 inputs are not reliably supported - see the [Limitations](#limitations).
- **Camera Chain**: defines the sequence or combination of AI models to chain together in the pipeline using their short identifiers (e.g., "retail"). Models can be chained serially (one after another). For details on chaining syntax, available models, and usage examples, see the [Model Chaining](#model-chaining) section below.
- **Camera Pipeline**: The generated or custom GStreamer pipeline string

#### Model Chaining

Model chaining allows you to combine multiple AI models in a single pipeline to create more sophisticated video analytics workflows. For example, you can chain a person detection model with a re-identification model to first detect people in the video and then generate unique identifiers for tracking.

##### Prerequisites

By default, only a limited number of models is downloaded during helm chart installation, which limits the possibilities of model chaining. To enable the full set of models:

1. Set `initModels.modelType=all` in `kubernetes/scenescape-chart/values.yaml`.
2. Configure desired model precisions (e.g., `initModels.modelPrecisions=FP16`) in `kubernetes/scenescape-chart/values.yaml`.
3. (Re)deploy Intel® SceneScape to download the additional models.

##### Chaining Syntax

- **Serial chaining**: Use the `+` operator to chain models sequentially (e.g., `retail+reid`).
- **Device specification**: Optionally specify the inference device using `=` (e.g., `retail=GPU`). See [DLStreamer documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dl-streamer/dev_guide/gpu_device_selection.html) for GPU device selection convention.
- **Default device**: If no device is specified, CPU is used as the default.

> **Note**: On systems with Intel GPU (either integrated or discrete), it is highly recommended to run both the decoding and the inference on GPU, so that other Intel® SceneScape services can fully benefit from available CPU cores. GPU inference typically provides better performance for complex models.

**Example**: `retail=GPU+reid=GPU` runs person detection on GPU, then feeds the results to person re-identification also running on GPU.

##### Available Models

Use the following short names to refer to each model in the chain:

| Category              | Full Model Name                              | Short Name  | Description                               |
| --------------------- | -------------------------------------------- | ----------- | ----------------------------------------- |
| **Person Detection**  | person-detection-retail-0013                 | retail      | General person detection                  |
|                       | pedestrian-and-vehicle-detector-adas-0001    | pedveh      | Pedestrian and vehicle detection          |
| **Person Analysis**   | person-reidentification-retail-0277          | reid        | Person re-identification                  |
|                       | person-attributes-recognition-crossroad-0238 | personattr  | Person attributes (age, gender, clothing) |
|                       | age-gender-recognition-retail-0013           | agegender   | Age and gender classification             |
|                       | human-pose-estimation-0001                   | pose        | Human pose estimation                     |
| **Vehicle Detection** | vehicle-detection-0200                       | veh0200     | Vehicle detection (newer model)           |
|                       | vehicle-detection-0201                       | veh0201     | Vehicle detection (alternative)           |
|                       | vehicle-detection-0202                       | veh0202     | Vehicle detection (alternative)           |
|                       | vehicle-detection-adas-0002                  | vehadas     | ADAS vehicle detection                    |
|                       | person-vehicle-bike-detection-2000           | pvb2000     | Multi-class detection                     |
|                       | person-vehicle-bike-detection-2001           | pvb2001     | Multi-class detection (v2)                |
|                       | person-vehicle-bike-detection-2002           | pvb2002     | Multi-class detection (v3)                |
|                       | person-vehicle-bike-detection-crossroad-0078 | pvbcross78  | Crossroad detection                       |
|                       | person-vehicle-bike-detection-crossroad-1016 | pvbcross16  | Crossroad detection (v2)                  |
| **Vehicle Analysis**  | vehicle-attributes-recognition-barrier-0042  | vehattr     | Vehicle attributes (color, type)          |
|                       | vehicle-license-plate-detection-barrier-0106 | platedetect | License plate detection                   |
| **Text Analysis**     | horizontal-text-detection-0001               | textdetect  | Text detection                            |
|                       | text-recognition-0012                        | textrec     | Text recognition                          |
|                       | text-recognition-resnet-fc                   | textresnet  | ResNet-based text recognition             |

##### Common Chaining Patterns

**Person Analytics Workflows:**

```
# Basic person detection with re-identification
retail+reid

# Person detection with attributes analysis
retail+personattr

# Person detection with age/gender classification
retail=GPU+agegender=GPU

```

**Vehicle Analytics Workflows:**

```
# Vehicle detection with re-identification
veh0200=GPU+reid=GPU

# Vehicle detection with attributes
veh0200+vehattr

# Vehicle detection with license plate detection
veh0200+platedetect
```

**Multi-Class Detection:**

```
# Detect people, vehicles, and bikes
pvb2000=GPU

# Multi-class detection with re-identification
pvb2000=GPU+reid=GPU
```

#### Advanced Configuration

- **Decode Device**: video decoding device settings (`AUTO`, `GPU` or `CPU`). It is highly recommended to use the `AUTO` or `GPU` (only on systems with GPU) setting, as the `CPU` setting forces the pipeline to use software codecs that have significantly lower performance than hardware accelerators. When `AUTO` is set, the pipeline will automatically choose GPU as the decode device if it is available on the system and fall back to CPU otherwise. If the user sets `GPU` on the system without GPU, the pipeline will not work.
- **Model Config**: references a model configuration file. Model configuration files are managed in the Models page and stored in the folder `Models/models/model_configs`. You can upload custom model configuration files or modify existing ones using the Models page. The Models page is accessible in the top menu of the Intel® SceneScape UI.
- **Use Camera Pipeline**: when enabled, directly applies the Camera Pipeline string in the camera VA pipeline instead of generating it automatically from camera settings on saving the camera configuration. When disabled (default), the system automatically generates the pipeline from other form fields.

> **Note**: The `AUTO` setting for decode device does not assume the optimal setting in each possible case. There might be cases when the optimal configuration can be achieved by setting the decode device manually.

> **Note**: The Model Config field references configuration files that define AI model parameters and processing settings. The default configuration file `model_config.json` is auto-generated for the models downloaded by the Intel® SceneScape model installer. See [Model Configuration File Format](model-configuration-file-format.md) for more details on the file format and when/how it should be updated.

> **Note**: When the **Use Camera Pipeline** checkbox is enabled, the values of camera settings from other form fields ('Camera', 'Camera Chain', 'Decode Device', 'Undistort', 'Model Config') do not impact the effective Visual Analytics pipeline. Enable the checkbox only when you want to use a custom pipeline that should not be auto-generated and remember to update it manually when needed.

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
   - Metadata publishing for Intel® SceneScape integration.

### Customizing the Generated Pipeline

After generating a pipeline preview, you can make manual adjustments:

1. **Edit Pipeline String**: modify the generated pipeline in the Camera Pipeline text area.
   - Add or remove GStreamer elements as needed.
   - Adjust element parameters for specific requirements.
   - Ensure the pipeline maintains compatibility with Intel® SceneScape - do not modify `gvapython` or `cameraundistort` elements.

2. **Common Customizations**:
   - **Video Source**: change input source type (file, RTSP, HTTP).
   - **Model Parameters**: fine-tune AI model inference settings either in model config file or the **Camera Pipeline** field.

3. **Enable Use Camera Pipeline**: check the **Use Camera Pipeline** checkbox to apply your custom pipeline string directly instead of auto-generation from form fields.

4. **Validation**: when you save the configuration or generate the pipeline preview, the system performs preliminary checks of the pipeline and reports an error if pipeline generation is not possible. However, it does not validate pipeline correctness in terms of GStreamer pipeline syntax and its functionality. You need to verify that the pipeline performs as expected.

### Saving and Applying Configuration

1. **Save Camera Configuration**: click **"Save Camera"** to apply your pipeline configuration.
   - The system automatically generates the camera pipeline if the field is empty.
   - Configuration is stored and deployed to the Kubernetes cluster.
   - The camera deployment is updated with the new pipeline.

2. **Automatic Pipeline Generation**: if you save the form with **Use Camera Pipeline** checkbox disabled, the system automatically generates a pipeline based on other form fields, following best practices and standards for Intel® SceneScape. This ensures every camera has a valid pipeline configuration.

3. **Error Handling**: If pipeline generation fails, the form remains open for correction and error messages are displayed. Common issues include missing model configurations or invalid command syntax.

### Best Practices

- **Start with Generated Pipeline**: use the "Generate Pipeline Preview" button to create a baseline configuration.
- **Test Incrementally**: make small changes and test each modification.
- **Validate Model Config**: ensure your selected Model Config file exists and is properly formatted.
- **Monitor Performance**: check camera performance after applying pipeline changes.
- **Backup Configurations**: save working pipeline configurations for future reference.

### Adding custom models or input video files

You can upload custom models or input video files and use them in DLStreamer Video Pipeline. These are stored in the Models Volume and Sample-Data Volume respectively.

#### Uploading custom models

You can upload custom models to the Models Volume using the Models page. The Models page is accessible in the top menu of the Intel® SceneScape UI. Alternatively, use the instructions in the [How to Manage Files in Volumes](./how-to-manage-files-in-volumes.md) guide to do it from the command line.

1. Upload the model in OpenVINO IR format with desired precision(s). Refer to the instructions in the [`model_installer` documentation](../../../model_installer/src/README.md) on the Models Volume folder structure.
2. Update the model configuration file or upload a new one so that it includes the newly added model(s). See [Model Configuration File Format](model-configuration-file-format.md) for more details on the file format and when/how it should be updated.
3. Reference the model in the camera pipeline configuration: use the short model name in the **Camera Chain** and the custom model configuration file name in the **Model Config** field.

#### Uploading custom video files

You can upload custom input video files to the Sample-Data Volume using the command line. Use the instructions in the [How to Manage Files in Volumes](./how-to-manage-files-in-volumes.md) guide.

1. Upload the video file to the Sample-Data Volume.
2. Reference the file in the camera pipeline configuration: set the **Camera (Video Source)** field using the relative path to the Sample-Data Volume, e.g.: `file://new-video.ts`.

### Limitations

- Only serial chaining of detectors with classification or re-identification models is supported in the **Camera Chain** field, where the ROI from the detection model serves as input to the classification or re-identification model in the chain. Serial chaining of two or more detectors is not supported (e.g. vehicle detector → license plate detector → OCR). Parallel inference on multiple models is not yet supported.
- Distortion correction is temporarily disabled due to a bug in DLStreamer-Pipeline-Server.
- Explicit frame rate and resolution configuration is not available yet.
- Network instability and camera disconnects are not handled gracefully for network-based streams (RTSP/HTTP/HTTPS) and may cause the pipeline to fail.
- Cross-stream batching is not supported since in Intel® SceneScape Kubernetes deployment each camera pipeline is running in a separate Pod.
- Direct selection of a specific GPU as decode device on systems with multiple GPUs is not supported. As a workaround, use specific GStreamer elements in the **Camera Pipeline** field according to [DLStreamer documentation](https://docs.openedgeplatform.intel.com/2025.2/edge-ai-libraries/dl-streamer/dev_guide/gpu_device_selection.html).
- MP4 input files are not reliably supported. This is due to a GStreamer limitation: the combination of `multifilesrc` and `decodebin3` elements may fail because MP4 container metadata is unavailable when data is provided as discrete file fragments. As a workaround, convert MP4 files to a streaming-friendly format such as MPEG-TS (.ts).

### Troubleshooting

- **Pipeline Generation Errors**: check that all required fields are filled correctly.
- **Model Config Issues**: verify the model configuration file exists in the Models page and model(s) used in the **Camera Chain** field are defined in the model config file.
- **Video Source Problems**: ensure the Camera (Video Source) field contains a valid video source URL or a device path.
- **Deployment Failures**: if the camera goes offline after an update or creation, check the Kubernetes logs of the corresponding video pipeline Pod for detailed error information. Video pipeline Pod names follow the format `<release-name>-videoppl-<sensor_id>-<sensor-id-hash>-<replicaset-hash>-<pod-hash>`. Look for log entries containing `ERROR`, for example: `kubectl logs -n scenescape scenescape-release-1-videoppl-atag-qcam1-de57f-bdc45859c-mfjpn | grep ERROR`.

## Manual Video Pipeline Configuration (in Docker Compose deployment)

Intel® SceneScape uses DLStreamer Pipeline Server as the Video Analytics microservice. The file [docker-compose-dl-streamer-example.yml](/sample_data/docker-compose-dl-streamer-example.yml) shows how a DLStreamer Pipeline Server docker container is configured to stream video analytics data for consumption by Intel® SceneScape. It leverages DLStreamer pipelines definitions in [queuing-config.json](/dlstreamer-pipeline-server/queuing-config.json) and [retail-config.json](/dlstreamer-pipeline-server/retail-config.json)

### Video Pipeline Configuration

The following is the GStreamer command that defines the video processing pipeline. It specifies how video frames are read, processed, and analyzed using various GStreamer elements and plugins. Each element in the pipeline performs a specific task, such as decoding, object detection, metadata conversion, and publishing, to enable video analytics in the Intel® SceneScape platform.

```
"pipeline": "multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json ! gvametaconvert add-tensor-data=true name=metaconvert ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
```

#### Breakdown of gstreamer command

`multifilesrc` is a GStreamer element that reads video files from disk. The `loop=TRUE` parameter ensures the video will loop continuously. The `location` parameter specifies the path to the video file to be used as input. In this example, the video file is located at `/home/pipeline-server/videos/qcam1.ts`.
`decodebin` is a GStreamer element that automatically detects and decodes the input video stream. It simplifies the pipeline by handling various video formats without manual configuration.

`videoconvert` converts the video stream into a raw format suitable for further processing. In this case, it ensures the video is in the BGR format required by downstream elements.

`gvapython` is a GStreamer element that allows custom Python scripts to process video frames. In this pipeline, it is used twice:

- The first instance, `PostDecodeTimestampCapture`, captures timestamps and processes frames after decoding.
- The second instance, `PostInferenceDataPublish`, processes frames after inference and publishes metadata in Intel® SceneScape detection format as described in [metadata.schema.json](/controller/src/schema/metadata.schema.json)

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

### Adding custom models or input video files to Docker volumes

You can upload custom models or input video files and use them in DLStreamer Video Pipeline. These are stored in the Models Volume and Sample-Data Volume respectively.

#### Uploading custom models to Docker volumes

You can upload custom models to the Models Volume using the command line. Use the instructions in the [How to Manage Files in Volumes](./how-to-manage-files-in-volumes.md) guide.

1. Upload the model in OpenVINO IR format with desired precision(s). Refer to the instructions in the [`model_installer` documentation](../../../model_installer/src/README.md) for the Models Volume folder structure.
2. Reference the model in the video pipeline inference element (e.g. `gvadetect`).

#### Uploading custom video files to Docker volumes

You can upload custom input video files to the Sample-Data Volume using the command line. Use the instructions in the [How to Manage Files in Volumes](./how-to-manage-files-in-volumes.md) guide.

1. Upload the video file to the Sample-Data Volume.
2. Reference the file in the video pipeline source element `multifilesrc`.
