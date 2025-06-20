# Using Deep Learning Streamer Pipeline Server with Intel® SceneScape

- [Getting Started](#getting-started)
- [Enable Re-ID](#enable-reidentification)
- [Creating a New Pipeline](#creating-a-new-pipeline)
- [Using Authenticated MQTT Broker](#using-authenticated-mqtt-broker)

## Getting Started

Following are the step-by-step instructions for enabling the out-of-box scenes in SceneScape to leverage DLStreamer Pipeline Server for Video Analytics.

1. **Model Requirements:**
    Ensure the OMZ model `person-detection-retail-0013` is present in `<scenescape_dir>/model_installer/models/intel/`.

2. **Start SceneScape DLStreamer-based demo:**

   If this is the first time running SceneScape, run:
    ```sh
    make && DLS=1 make demo
    ```
    Alternatively, the script can be used:
    ```sh
    DLS=1 ./deploy.sh
    ```
    If you have already deployed SceneScape use:
    ```sh
    docker compose down --remove-orphans
    docker compose up -d
    ```

---
## Enable Reidentification

Following are the step-by-step instructions for enabling person reidentification for the out-of-box **Queuing** scene.

1. **Enable the ReID Database Container**\
   Uncomment the `vdms` container in `docker-compose.yml`:

   ```yaml
   vdms:
     image: intellabs/vdms:latest
     init: true
     networks:
       scenescape:
     restart: always
   ```

2. **Add Database Dependency to Scene Controller**\
   Add `vdms` to the `depends_on` list for the `scene` container:

   ```yaml
   scene:
     image: scenescape
     ...
     depends_on:
       - broker
       - web
       - ntpserv
       - vdms
   ```

3. Use the predefined [queuing-config-reid.json](./queuing-config-reid.json) to enable vector embedding metadata from the DLStreamer service:
    ```yaml
    services:
      queuing-video:
        volumes:
          - ./dlstreamer-pipeline-server/queuing-config-reid.json:/home/pipeline-server/config.json

    ```
    Ensure the OMZ model `person-reidentification-retail-0277` is available in `<scenescape_dir>/model_installer/models/intel/`.

    If this is the first time running SceneScape, run:
    ```sh
    ./deploy.sh
    ```
    If you have already deployed SceneScape use:
    ```sh
    docker compose down queuing-video
    docker compose up queuing-video -d
    ```
    Repeat the same steps but with [retail-config-reid.json](./retail-config-reid.json) to enable reid for the **Retail** scene.

## Creating a New Pipeline

To create a new pipeline, follow these steps:

1. **Create a New Config File:**
    Use the existing [config.json](./config.json) as a template to create your new pipeline configuration file (e.g., `my_pipeline_config.json`). Adjust the parameters as needed for your use case.

    > **Note:** The `detection_policy` parameter specifies the type of inference model used in the pipeline. For example, use `detection_policy` for detection models, `reid_policy` for re-identification models, and `classification_policy` for classification models. Currently, only these policies are supported. To add a custom policy, refer to the implementation in [sscape_adapter.py](./user_scripts/gvapython/sscape/sscape_adapter.py).

2. **Mount the Config File:**
    In your `docker-compose.yml`, update the DL Streamer Pipeline Server service to mount your new config file. For example:
    ```yaml
    services:
      dlstreamer-pipeline-server:
        volumes:
          - ./dlstreamer-pipeline-server/my_pipeline_config.json:/home/pipeline-server/config.json
    ```
    This ensures the container uses your custom configuration.

3. **Restart the Service:**
    After updating the compose file, restart the DL Streamer Pipeline Server service:
    ```sh
    docker-compose up -d dlstreamer-pipeline-server
    ```

Your new pipeline will now be used by the DL Streamer Pipeline Server on startup.

## Using Authenticated MQTT Broker
- The current DL Streamer Pipeline Server does not support Mosquitto connections with authentication by default. If authentication is required, configure a custom MQTT client with authentication support in [sscape_adapter.py](./user_scripts/gvapython/sscape/sscape_adapter.py).
