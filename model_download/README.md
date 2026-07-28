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

## Key variables

- `COMPOSE_PROJECT_NAME` (default: `scenescape`)
- `MODEL_DOWNLOADER_IMAGE` (default: `intel/model-download:latest`)
- `MODEL_DOWNLOADER_URL` (default: `http://127.0.0.1:8200`)
- `MODEL_CONFIG_FILE` (default: `models.json`; shared model download and Scenescape config metadata)
- `MODEL_LIST` (optional JSON array override; supports the format required by model_downloader REST API)
- `MODEL_DOWNLOADER_CMD` (model_downloader startup arguments; default: `--plugins omz`)

The downloader submits model download jobs, then polls `/api/v1/jobs` until every returned job reaches a terminal state.

- Exit code `0`: all tracked download jobs completed successfully.
- Exit code `1`: at least one tracked job failed, no job IDs were returned, polling timed out, or the status API returned an invalid response.

After downloads finish, `make -C model_download install-models` also generates `model_config.json` in `/models/model_configs/` from `MODEL_CONFIG_FILE`.

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
            "model_proc": "object_detection/person/person-detection-retail-0013.json"
          },
          "adapter-params": {
            "metadatagenpolicy": "detectionPolicy"
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

`scenescape.name` is the convenient key written to generated `model_config.json`. If `scenescape.config.params.model` is omitted, the generator locates the downloaded `.xml` model under `/models/<hub>/<name>/` using the `model_downloader` section and prefers the precision configured by `model_config.prefer_precision`.

Models without the `scenescape` section are downloaded but skipped when generating `model_config.json`.

Use a different configuration file with:

```bash
make -C model_download install-models MODEL_CONFIG_FILE=/path/to/models.json
```

Example `MODEL_LIST` override for download-only experimentation:

```bash
MODEL_LIST='[{"name":"person-detection-retail-0013","hub":"omz"},{"name":"person-attributes-recognition-crossroad-0230","hub":"omz"}]' make -C model_download download-models
```

`MODEL_LIST` is a direct `model_downloader` payload override, so it does not use the nested `model_downloader` / `scenescape` structure.

## Downloading Models from Different Sources

To add another model source one has to:
- add the new model with its source to `models[].model_downloader` in `MODEL_CONFIG_FILE` (for example `{"name":"my-custom-model","hub":"huggingface"}`)
- add `scenescape.name` and `scenescape.config` to that model object when it should appear in generated `model_config.json`
- extend list of plugins installed in the `model_downloader` container - by modifying the following line in the `Makefile`:

```makefile
MODEL_DOWNLOADER_CMD ?= --plugins omz,huggingface
```

- if, except of just downloading, the model needs some postprocessing - add this step in
  the `Makefile` - in similar way to the `generate-model-config` or `copy-config-files` targets.

> [!NOTE] list of available plugins and their configuration can be found in the `model_downloader` [documentation](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/model-download/README.md).
