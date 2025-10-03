# Model Configuration File Format

## Overview

Model configuration files (JSON) define the AI models available for use in camera pipelines within SceneScape, specifying model parameters, element types, and adapter configurations needed to generate proper GStreamer pipelines with DLStreamer elements.

## File Structure

Model configuration files are JSON documents stored in the `Models/models/model_configs` folder and managed through the SceneScape Models page, which is accessible in the top menu of the SceneScape UI. Each file contains model definitions with unique identifiers that can be referenced in the Camera Chain field.

### Basic Structure

```json
{
  "model_identifier": {
    "type": "detect|classify",
    "params": {
      "model": "path/to/model.xml",
      "model_proc": "path/to/model-proc.json"
      // other DLStreamer element parameters
    },
    "input-format": {
      "color-space": "BGR|RGB"
    },
    "adapter-params": {
      "metadatagenpolicy": "detectionPolicy|reidPolicy|classificationPolicy"
    }
  }
}
```

### Example Configuration

```json
{
  "retail": {
    "type": "detect",
    "params": {
      "model": "intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml",
      "model_proc": "object_detection/person/person-detection-retail-0013.json",
      "scheduling-policy": "latency",
      "threshold": "0.75"
    },
    "input-format": {
      "color-space": "BGR"
    },
    "adapter-params": {
      "metadatagenpolicy": "detectionPolicy"
    }
  }
}
```

## Field Descriptions

### Model Identifier

The top-level key (e.g., "retail") serves as the short identifier referenced in the Camera Chain field.
It should be unique within the configuration file, descriptive of the model's purpose, and easy to reference in the camera configuration page.

### Type Field

Specifies the DLStreamer element type for the model:

- **`detect`**: maps to `gvadetect` element for object detection models.
- **`classify`**: maps to `gvaclassify` element for classification models.

### Parameters Section

Contains the model-specific parameters passed to the DLStreamer element.

#### Path Resolution

- **`model`**: path to the model file (typically `.xml` for OpenVINO models).
- **`model_proc`**: path to the model processing configuration file (`.json`).

> **Note**: Model proc file is deprecated. Avoid using it to prevent dealing with a legacy solution. It will be maintained for some time to ensure backwards compatibility, but you should not use it in modern applications. The new method of model preparation is described in Model Info Section. See the Model proc file [documentation page](https://dlstreamer.github.io/dev_guide/model_proc_file.html) for more details.

**Important**: Paths are automatically resolved relative to the `/home/pipeline-server/models` directory in the DLStreamer container. Use relative paths from this base directory.

#### Additional Parameters

Any additional parameters specified in the `params` section are passed directly to the DLStreamer element with proper formatting and quoting for GStreamer pipeline syntax.

### Input Format

Defines the expected input format for the model:

- **`color-space`**: Specifies the color space format (BGR, RGB) required by the model

### Adapter Parameters

Configuration for the Python adapter that transforms DLStreamer metadata to the SceneScape format:

- **`metadatagenpolicy`**: defines how metadata is generated and formatted.
  - `detectionPolicy`: for standard object detection results with 2D bounding boxes.
  - `detection3DPolicy`: for 3D object detection results with spatial coordinates, rotation, and dimensions.
  - `reidPolicy`: for re-identification tracking with detection data plus encoded feature vectors.
  - `classificationPolicy`: for classification results combined with detection bounding boxes.
  - `ocrPolicy`: for optical character recognition results with 3D detection data plus extracted text.

## Usage in Pipeline Generation

When generating a camera pipeline:

1. The Camera Chain field references a model by its identifier (e.g., "retail").
2. The pipeline generator looks up the model configuration.
3. The `type` field determines which DLStreamer element to use (`gvadetect` or `gvaclassify`).
4. The `params` section provides the element parameters with resolved paths.
5. The `adapter-params` configure the metadata transformation adapter.

## Best Practices

- **Descriptive Identifiers**: use meaningful names for model identifiers.
- **Relative Paths**: always use paths relative to the models directory.
- **Consistent Naming**: follow consistent naming conventions across configurations.
- **Validation**: test model configurations before deployment.

## Troubleshooting

When adding a new model config file through the Models page UI, if you encounter the following error:

`Error uploading file: [Errno 13] Permission denied`

use below instructions as a workaround.

### Copying a model config into models PVC

Use the cluster PVC mount that holds SceneScape models to make a config available at runtime.

1. **Find the models PVC and pod:**

```bash
kubectl get pvc -n <namespace> | grep models
kubectl get pods -n <namespace>
```

2. **Identify mount path of the models PVC**

```bash
kubectl describe pod scenescape-release-1-web-dep-584dbc6c5d-vtcwl -n scenescape | grep -A 10 -B 10 models
```

3. **Copy the config file:**
   The default mount path is `/home/scenescape/SceneScape/models`.

```bash
kubectl cp /path/to/local/config.json <namespace>/<pod>:/home/scenescape/SceneScape/models/models/model_configs/config.json
```

4. **Verify and restart (if needed):**

```bash
kubectl exec -n <namespace> <pod> -- ls -la /home/scenescape/SceneScape/models/models/model_configs/
kubectl rollout restart deployment/<deployment-name> -n <namespace>
```

If you encounter the same permissions error uploading model files, copy the files using above instructions into the models folder such that they can be referenced from the new model config file.

## Related Documentation

- [How to Configure DLStreamer Video Pipeline](How-to-configure-dlstreamer-video-pipeline.md)
- [Deep Learning Streamer Elements Documentation](https://dlstreamer.github.io/elements/elements.html)
