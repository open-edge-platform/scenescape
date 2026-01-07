# Model Configuration File Format

## Overview

Model configuration files (JSON) define the AI models available for use in camera pipelines within Intel® SceneScape, specifying model short names, model parameters, element types, and adapter configurations needed to generate proper GStreamer pipelines with DL Streamer elements.

> **Note**: Model configuration files described in this document are used for dynamic camera configuration in Kubernetes deployments. They are not used in Docker Compose deployments, where camera pipelines are configured statically in configuration files. Therefore, this document refers specifically to Kubernetes deployments unless stated otherwise.

## Location and Access

Model configuration files are JSON documents stored in the `<Models Volume>/models/model_configs` folder and are managed:

- Through the Intel® SceneScape Models page, accessible via the link in the top menu. Each file contains model definitions with unique identifiers that can be referenced in the Camera Chain field.
- By accessing the models volume directly using `kubectl` tool (see the [How to Manage Files in Volumes](./how-to-manage-files-in-volumes.md) guide for detailed instructions).

### Usage

The Intel® SceneScape model installer automatically generates the default model configuration file at the location `<Models Volume>/models/model_configs/model_config.json` for the set of models being downloaded.

The user needs to update the model configuration file in the following cases:

- They need to use their own custom models.
- They need to do custom configurations of the installed models (e.g., non-default values of DLStreamer parameters like threshold).
- They need to modify the precisions of the installed models that are used in the generated pipelines.

For basic usage of the models downloaded by the model installer, no changes are required in the automatically generated model configuration file.

### Basic File Structure

```json
{
  "model_identifier": {
    "type": "detect|classify",
    "params": {
      "model": "path/to/model.xml",
      "model_proc": "path/to/model-proc.json"
      // other DLStreamer element parameters
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
      "model_proc": "intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json",
      "scheduling-policy": "latency",
      "threshold": "0.75"
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
- **`inference`**: maps to `gvainference` element for other inference models.

### Parameters Section

Contains the model-specific parameters passed to the DLStreamer element.

#### Path Resolution

- **`model`**: Path to the model file (typically `.xml` for OpenVINO models).
- **`model_proc`**: Path to the model processing configuration file (`.json`).

> **Note**: The model proc file is deprecated. Avoid using it to prevent dealing with a legacy solution. It will be maintained for some time to ensure backward compatibility, but you should not use it in modern applications. The new method of model preparation is described in the Model Info Section. See the Model proc file [documentation page](https://dlstreamer.github.io/dev_guide/model_proc_file.html) for more details on the deprecated functionality.

**Important**: Paths are automatically resolved relative to the `/home/pipeline-server/models` directory in the DLStreamer container. Use relative paths from this base directory.

#### Additional Parameters

Any additional parameters specified in the `params` section are passed directly to the DLStreamer element with proper formatting and quoting for GStreamer pipeline syntax.

### Adapter Parameters

Configuration for the Python adapter that transforms DLStreamer metadata to the Intel® SceneScape format:

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
3. The `type` field determines which DLStreamer element to use.
4. The `params` section provides the element parameters with resolved paths.
5. The `adapter-params` configure the metadata transformation adapter.

## Best Practices

- **Descriptive Identifiers**: use meaningful names for model identifiers.
- **Relative Paths**: always use paths relative to the models directory.
- **Consistent Naming**: follow consistent naming conventions across configurations.
- **Validation**: test model configurations before deployment.

## Troubleshooting

When adding a new model or model config file through the Models page UI, if you encounter any errors, use the cluster PVC mount that holds Intel® SceneScape models (Models Volume) to view the current configuration or make a new configuration and models available at runtime.

Refer to instructions in [How to manage files in volumes](how-to-manage-files-in-volumes.md) on how to access Models Volume and copy files from local file system to the volume.

Refer to the instructions in [`model_installer` documentation](../../../model_installer/src/README.md) on the Models Volume folder structure.

## Related Documentation

- [How to Configure DLStreamer Video Pipeline](how-to-configure-dlstreamer-video-pipeline.md)
- [Deep Learning Streamer Elements Documentation](https://dlstreamer.github.io/elements/elements.html)
- [How to manage files in volumes](how-to-manage-files-in-volumes.md)
- [`model_installer` documentation](../../../model_installer/src/README.md)
