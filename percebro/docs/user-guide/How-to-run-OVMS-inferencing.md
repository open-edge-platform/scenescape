# How to run OVMS Inferencing

Please follow the steps below to run OpenVINO™ pre-trained models using OpenVINO™ Model Server (OVMS):
1. Add model config in `model-config.json` and use 'external_id' key to provide the full name of the model (same as xml file name without file extension) so that install-omz-model script can use the ID to generate `ovms-config.json` file. [Skip this step to run an existing model.]
2. Uncomment ovms container section in `docker-compose-example.yml` file and copy it to `docker-compose.yml`. Also, uncomment `depends_on` item for ovms in video container.
3. Add `=ovms` after Percebro model name in `docker-compose.yml`. Example: `retail=ovms`

Please follow the steps below to run Geti models in OVMS:
1. Put the Geti model in directory `[PROJECT_DIR]/model_installer/models/ovms`. Make sure the directory structure matches with the [directory structure mentioned here](https://docs.openvino.ai/2024/ovms_docs_models_repository.html)
2. Add config in `model-config.json` or use a config file that contains config similar to this:
```
{"model": "geti", "engine": "GetiDetector", "keep_aspect": 0, "categories" : ["person"], "external_id": "geti"}
```
3. Add model config in `ovms-config.json` similar to the example below. Please make sure the `name` is same as the `external_id` in `model-config.json`.
```
{
        "config": {
                "name": "geti",
                "base_path": "/models/ovms/geti",
                "shape": "auto",
                "batch_size": "1",
                "plugin_config": {
                        "PERFORMANCE_HINT": "LATENCY"
                },
                "allow_cache": true
        }
}
```

Known issues:
1. OVMS throws "model not found" exception when percebro asks for an output while OVMS container is still loading the model config. It only happens when there are a bunch of models listed in `ovms-config.json` and the model that is in use is listed at the bottom. To avoid the issue, it is better to add the desired model at the top of the config in `ovms-config.json`.
