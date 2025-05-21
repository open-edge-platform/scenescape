# Using Deep Learning Streamer Pipeline Server with Intel® SceneScape


- [Getting Started](#getting-started)
- [Additional Information and Troubleshooting](#additional-information-and-troubleshooting)
- [Creating a New Pipeline](#creating-a-new-pipeline)

## Getting Started

This guide provides step-by-step instructions for enabling the DL Streamer Pipeline Server with Intel® SceneScape. The following steps demonstrate usage with the out-of-the-box Retail scene, utilizing the pipeline defined in [config.json](./config.json).

1. **Enable Services:**
    In your `docker-compose.yml`, enable the DL Streamer Pipeline Server and its dependent services. Disable the corresponding Percebro service to avoid conflicts.

2. **Alternative Compose File:**
    Alternatively, copy the provided [docker-compose-dl-streamer-example.yml](../sample_data/docker-compose-dl-streamer-example.yml) into your current directory as `docker-compose.yml`:
    ```sh
    cp docker-compose-dl-streamer-example.yml docker-compose.yml
    ```

3. **Set Environment Variables in `docker-compose.yml`:**
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

4. **Model Requirements:**
    Ensure the OMZ model `person-detection-retail-0013` is present in `<scenescape_dir>/models/intel/`.

5. **Convert Video Files:**
    From `<scenescape_dir>`, run:
    ```sh
    ./dlstreamer-pipeline-server/convert_video_to_ts.sh
    ```
    This [script](./convert_video_to_ts.sh) converts `.mp4` files in `<scenescape_dir>/sample_data` to `.ts` format.

---
## Additional Information and Troubleshooting

- The DL Streamer Pipeline Server does not support Mosquitto connections with authorization by default. If authorization is required, configure a custom MQTT client with authorization support in [sscape_adapter.py](./user_scripts/gvapython/sscape/sscape_adapter.py).

- If you encounter the following Docker error:
  ```
  Error response from daemon: Get "https://amr-registry.caas.intel.com/v2/": tls: failed to verify certificate: x509: certificate signed by unknown authority
  ```
  Refer to [this wiki article](https://wiki.ith.intel.com/display/SceneScape/How+to+setup+computing+systems+to+pull+docker+images+from+Intel+harbor+registry) for solutions.

- To enable infinite looping playback of a video file with the GStreamer `multifilesrc` element, first convert your `.mp4` file to MPEG-TS format:
  ```sh
  ffmpeg -i <infile.mp4> -c copy <outfile.ts>
  ```
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
