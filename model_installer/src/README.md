# Model Installer

Model installer provides users with AI models for SceneScape by:

- downloading the configured set of models from OpenVINO Model Zoo
- downloading/generating necessary configuration files to integrate them with SceneScape services

The models and configuration files are downloaded into a models volume that is attached to SceneScape services for both Docker and Kubernetes deployments.

## Configuration

Model installer can be configured to download a specific set of models using the following parameters:

| Parameter    | Allowed Values          | Format               | Description                                                                                                                                                                                                                       |
| ------------ | ----------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `models`     | `default`, `ocr`, `all` | Single value         | Specifies which set of models to download. `default` includes person detection, re-identification, and pose estimation models. `ocr` includes text detection and recognition models. `all` downloads both default and OCR models. |
| `precisions` | `FP32`, `FP16`, `INT8`  | Comma-separated list | Model precision formats to download. Multiple precisions can be specified for the same model (e.g., `FP16,FP32`). The first one will be used as preferred when generating `model-config.json`                                     |

For Kubernetes deployment refer to the `initModels` section in [Helm chart values](../../kubernetes/scenescape-chart/values.yaml), for example use `--set initModels.modelType=all --set initModels.modelPrecisions=FP16,FP32` when installing the Helm chart.

For Docker deployment use `MODELS` and `PRECISIONS` environment variables when building, e.g.: `make install-models MODELS=all` or `make install-models MODELS=all PRECISIONS="FP16,FP8"`.

## Models Volume Folder Structure

```
models/
├── intel/
│   ├── model-name-1/
│   │   ├── FP16/
│   │   │   ├── model-name-1.xml (OpenVINO model)
│   │   │   ├── model-name-1.bin (OpenVINO model)
│   │   │   └── model-name-1.json (model-proc file - required only for selected models)
│   │   └── FP32/
│   │       └── ...
│   └── model-name-2/
│       └── ...
├── public/
│   └── model-name-3/
│       └── ...
└── model_configs/
    └── model_config.json (auto-generated default model configuration file)
```

## Auto-Generation of `model-config.json` File

For detailed information about the file format and its usage, refer to the [Model Configuration File Format documentation](../../docs/user-guide/other-topics/model-configuration-file-format.md).

#### Model Classification

The function automatically assigns metadata policies and element types based on model names:

| Model Pattern                                 | Metadata Policy        | Type      | Description                              |
| --------------------------------------------- | ---------------------- | --------- | ---------------------------------------- |
| _detection_, _detector_, _detect_             | `detectionPolicy`      | detect    | Object detection models                  |
| _text_ + _detection_                          | `ocrPolicy`            | detect    | Text detection models                    |
| _reidentification_, _reid_                    | `reidPolicy`           | inference | Person/object re-identification          |
| _recognition_, _attributes_, _classification_ | `classificationPolicy` | classify  | Classification and attribute recognition |
| _text_ + _recognition_                        | `ocrPolicy`            | classify  | Text recognition models                  |
| _pose_                                        | `detection3DPolicy`    | inference | Human pose estimation                    |

#### Model Name Mapping

The `generate_model_config.py` file includes a predefined mapping for shorter, more convenient model names. The mapping is defined in the `_MODEL_NAME_MAP` variable.

If a model name exists in this mapping, the shortened name will be used as the key in the configuration. Otherwise, the original behavior (replacing hyphens with underscores) is used.
