<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Model Download

This folder contains Scenescape model download orchestration that uses Intel `model_downloader` REST API to download
models from various sources for purpose of demonstration.

## Main command

```bash
make -C model_download install-models
```

For Kubernetes deployments, the same flow can be selected in the Helm chart with
`--set modelDownload.enabled=true`. The chart runs the model downloader service and this folder's Python orchestration
inside a pre-install hook, writing outputs to the models PVC.

## Key variables

- `COMPOSE_PROJECT_NAME` (default: `scenescape`)
- `MODEL_DOWNLOADER_IMAGE` (default: `intel/model-download:latest`)
- `MODEL_DOWNLOADER_URL` (default: `http://127.0.0.1:8200`)
- `MODEL_CONFIG_FILE` (default: `models.json`; shared model download and Scenescape config metadata)
- `MODEL_DOWNLOADER_CMD` (model_downloader startup arguments; default: `--plugins omz`)

The downloader submits model download jobs, then polls `/api/v1/jobs` until every returned job reaches a terminal state.

- Exit code `0`: all tracked download jobs completed successfully.
- Exit code `1`: at least one tracked job failed, no job IDs were returned, polling timed out, or the status API returned an invalid response.

After downloads finish, `make -C model_download install-models` also generates `model_config.json` in `/models/model_configs/` from `MODEL_CONFIG_FILE`. If a model entry contains `scenescape.model_proc`, the same generation step writes that DL Streamer model-proc JSON file into the models volume and references it from generated `model_config.json`.

## Shared model configuration

The default configuration lives in `model_download/models.json`. Its top-level `models` array is the single source for downloads and generated DL Streamer configuration. Each model entry has separate namespaces so downloader fields cannot collide with Scenescape fields:

- `model_downloader`: passed to the `model_downloader` REST API as-is.
- `scenescape`: optional Scenescape metadata used only to generate `model_config.json`.

```json
{
  "models": [
    {
      "model_downloader": {
        "name": "person-detection-retail-0013",
        "hub": "omz"
      },
      "scenescape": {
        "name": "retail",
        "config": {
          "type": "detect",
          "params": {
            "model": "omz/person-detection-retail-0013/FP16/person-detection-retail-0013.xml"
          },
          "adapter-params": {
            "metadatagenpolicy": "detectionPolicy"
          }
        },
        "model_proc": {
          "path": "object_detection/person/person-detection-retail-0013.json",
          "content": {
            "json_schema_version": "2.0.0",
            "input_preproc": [],
            "output_postproc": [
              {
                "labels": ["", "person"],
                "converter": "tensor_to_bbox_ssd"
              }
            ]
          }
        }
      }
    }
  ],
  "model_config": {
    "output_file": "model_config.json",
    "prefer_precision": "FP16"
  }
}
```

`scenescape.name` is the convenient key written to generated `model_config.json`. `scenescape.config` is copied into the generated entry. `scenescape.config.params.model` must point to the model XML path relative to the models volume.

`scenescape.model_proc` is optional. When present:
- `path` is the model-proc JSON path relative to the models volume. It must be a relative `.json` path inside the models directory.
- `content` is the DL Streamer model-proc JSON object to write at that path.
- the generator adds `params.model_proc` with the same relative path to generated `model_config.json`.

Models without the `scenescape` section are downloaded but skipped when generating `model_config.json`.

Use a different configuration file with:

```bash
make -C model_download install-models MODEL_CONFIG_FILE=/path/to/models.json
```

## Downloading Models from Different Sources

To add another model source one has to:
- add the new model with its source to `models[].model_downloader` in `MODEL_CONFIG_FILE` (for example `{"name":"my-custom-model","hub":"huggingface"}`)
- add `scenescape.name` and `scenescape.config` to that model object when it should appear in generated `model_config.json`
- extend list of plugins installed in the `model_downloader` container - by modifying the following line in the `Makefile`:

```makefile
MODEL_DOWNLOADER_CMD ?= --plugins omz,huggingface
```

- if the model needs DL Streamer post-processing metadata, add `scenescape.model_proc` to the model entry so the generator creates the model-proc file in the models volume.

> [!NOTE] list of available plugins and their configuration can be found in the `model_downloader` [documentation](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/model-download/README.md).
