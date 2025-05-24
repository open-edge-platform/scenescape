# Using Deep Learning Streamer Pipeline Server with Intel® SceneScape

- [Getting Started](#getting-started)
- [Enable Re-ID](#enable-reidentification)
- [Creating a New Pipeline](#creating-a-new-pipeline)
- [Using Authenticated MQTT Broker](#using-authenticated-mqtt-broker)

## Getting Started

This guide provides step-by-step instructions for enabling the DL Streamer Pipeline Server with Intel® SceneScape. The following steps demonstrate usage with the out-of-the-box Retail scene, utilizing the pipeline defined in [config.json](./config.json).

1. **Use Predefined Compose File:**
    Copy the provided [docker-compose-dl-streamer-example.yml](../sample_data/docker-compose-dl-streamer-example.yml) into your current directory as `docker-compose.yml`:
    ```sh
    cp docker-compose-dl-streamer-example.yml docker-compose.yml
    ```

2. **Set Environment Variables in `docker-compose.yml`:**
    Obtain your user and group IDs by running:
    ```sh
    id -u
    id -g
    ```
    Then, specify these values as the `UID` and `GID` environment variables in the relevant services within your `docker-compose.yml`:
    ```yaml
    services:
        broker:
        environment:
            - UID=<your-uid>
            - GID=<your-gid>
    ```

3. **Model Requirements:**
    Ensure the OMZ model `person-detection-retail-0013` is present in `<scenescape_dir>/models/intel/`.

4. **Convert Video Files:**
    For enabling infite looping of input video files run:
    ```sh
    ./dlstreamer-pipeline-server/convert_video_to_ts.sh
    ```
    It will convert `.mp4` files in `sample_data` to `.ts` format.

5. **Start SceneScape:**
    If this is the first time running SceneScape, run:
    ```sh
    ./deploy.sh
    ```
    If you have already deployed SceneScape use:
    ```sh
    docker compose down --remove-orphans
    docker compose up -d
    ```

---
## Enable Reidentification

- On startup, the DL Streamer Pipeline Server container runs pipelines defined in [config.json](./config.json). This file specifies the pipeline and parameters (video file/camera, NTP server, camera ID, FOV, etc.).

- To run the reidentification pipeline, use [config_reid.json](./config_reid.json) as your pipeline configuration. In your `docker-compose.yml`, mount it as follows:
    ```yaml
    services:
      dlstreamer-pipeline-server:
        volumes:
          - ./dlstreamer-pipeline-server/config_reid.json:/home/pipeline-server/config.json

    ```
    Ensure the OMZ model `person-reidentification-retail-0277` is available in `<scenescape_dir>/models/intel/`.

    Restart the service:
    ```sh
    docker-compose up -d dlstreamer-pipeline-server
    ```
    For more details about reidentification refer to [How to Enable Re-identification Using Visual Similarity Search](../docs/user-guide/How-to-enable-reidentification.md).

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