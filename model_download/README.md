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
- `MODEL_DOWNLOAD_PATH` (default: `models`)
- `MODEL_LIST` (JSON array override; supports the format required by model_downloader REST API)
- `MODEL_DOWNLOAD_PLUGIN` (list of plugins describing available sources of models, default: `omz`)
- `MODEL_CONFIG_OUTPUT_FILE` (default: `model_config.json`)
- `MODEL_CONFIG_PREFER_PRECISION` (default: `FP16`)
- `MODEL_CONFIG_SUBFOLDERS` (default: `omz,intel,public`)

The downloader submits model download jobs, then polls `/api/v1/jobs` until every returned job reaches a terminal state.

- Exit code `0`: all tracked download jobs completed successfully.
- Exit code `1`: at least one tracked job failed, no job IDs were returned, polling timed out, or the status API returned an invalid response.

After downloads finish, `make -C model_download install-models` also generates `model_config.json` in `/models/model_configs/` by calling the shared Scenescape generator through the wrapper script.

Example `MODEL_LIST`:

```bash
MODEL_LIST_JSON='[{"name":"person-detection-retail-0013","hub":"omz"},{"name":"person-attributes-recognition-crossroad-0230","hub":"omz"}]'
```

## Downloading Models from Different Sources

To add another model source one has to:
- add new model with its source to `MODEL_LIST` (for example `MODEL_LIST='[{"name":"person-detection-retail-0013","hub":"omz"},{"name":"my-custom-model","hub":"huggingface"}]'`)
- extend list of plugins installed in the `model_downloader` container - by modifying the following line in the `Makefile`:

```makefile
MODEL_DOWNLOADER_CMD ?= --plugins omz,huggingface
```

- if, except of just downloading, the model needs some postprocessing - like generating model-config file for omz models - add this step in 
  the `Makefile` - in similar way to the `generate-model-config` or `copy-config-files` targets.

> [!NOTE] list of available plugins and their configuration can be found in the `model_downloader` [documentation](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/model-download/README.md).
