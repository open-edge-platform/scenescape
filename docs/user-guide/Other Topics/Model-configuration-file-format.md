# Model Configuration File Format

## Overview

Model configuration files (JSON) define the AI models available for use in camera pipelines within SceneScape, specifying model parameters, element types, and adapter configurations needed to generate proper GStreamer pipelines with DLStreamer elements.

## File Structure

Model configuration files are JSON documents stored in the `Models/models/model_configs` folder and managed through the SceneScape Models page. Each file contains model definitions with unique identifiers that can be referenced in the Camera Chain field.

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

**Important**: Paths are automatically resolved relative to the `/home/pipeline-server/models` directory in the DLStreamer container. Use relative paths from this base directory.

#### Additional Parameters

Any additional parameters specified in the `params` section are passed directly to the DLStreamer element with proper formatting and quoting for GStreamer pipeline syntax.

### Input Format

Defines the expected input format for the model:

- **`color-space`**: Specifies the color space format (BGR, RGB) required by the model

### Adapter Parameters

Configuration for the Python adapter that transforms DLStreamer metadata to SceneScape format:

- **`metadatagenpolicy`**: Defines how metadata is generated and formatted
  - `detectionPolicy`: For standard object detection results with 2D bounding boxes
  - `detection3DPolicy`: For 3D object detection results with spatial coordinates, rotation, and dimensions
  - `reidPolicy`: For re-identification tracking with detection data plus encoded feature vectors
  - `classificationPolicy`: For classification results combined with detection bounding boxes
  - `ocrPolicy`: For optical character recognition results with 3D detection data plus extracted text

## Usage in Pipeline Generation

When generating a camera pipeline:

1. The Camera Chain field references a model by its identifier (e.g., "retail")
2. The pipeline generator looks up the model configuration
3. The `type` field determines which DLStreamer element to use (`gvadetect` or `gvaclassify`)
4. The `params` section provides the element parameters with resolved paths
5. The `adapter-params` configure the metadata transformation adapter

## Best Practices

- **Descriptive Identifiers**: Use meaningful names for model identifiers
- **Relative Paths**: Always use paths relative to the models directory
- **Consistent Naming**: Follow consistent naming conventions across configurations
- **Validation**: Test model configurations before deployment

## Related Documentation

- [How to Configure DLStreamer Video Pipeline](How-to-configure-dlstreamer-video-pipeline.md)
- [Deep Learning Streamer Elements Documentation](https://dlstreamer.github.io/elements/elements.html)
