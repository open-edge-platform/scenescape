# Using Deep Learning Streamer Pipeline Server with Intel® SceneScape

- [Getting Started](#getting-started)
- [Running on GPU](#running-on-gpu)
- [Enable Re-ID](#enable-reidentification)
- [Creating a New Pipeline](#creating-a-new-pipeline)
- [Using Authenticated MQTT Broker](#using-authenticated-mqtt-broker)

## Getting Started

Following are the step-by-step instructions for enabling the out-of-box scenes in Intel® SceneScape to leverage DLStreamer Pipeline Server for Video Analytics.

1. **Model Requirements:**
   Ensure the OMZ model `person-detection-retail-0013` is present in `<scenescape_dir>/model_installer/models/intel/`.

2. **Start Intel® SceneScape DLStreamer-based demo:**

   If this is the first time running SceneScape, run:

   ```sh
   make && make demo
   ```

   Alternatively, the script can be used:

   ```sh
   ./deploy.sh
   ```

   If you have already deployed Intel® SceneScape, use:

   ```sh
   docker compose down --remove-orphans
   docker compose up -d
   ```

## Running on GPU

Running the pipelines on GPU is highly recommended when available on the system. This approach efficiently utilizes available CPU cores for other SceneScape services and provides optimal performance for the visual analytics service.

To facilitate GPU acceleration, sample configuration files are provided for the out-of-box **Queuing** and **Retail** scenes with the following pipeline optimizations:

- Video decode offloaded to GPU
- Inference offloaded to GPU
- Cross-stream batching enabled

### Configuration

Use the predefined configuration files in your `docker-compose.yml` to enable GPU acceleration for out-of-box scenes:

- [queuing-config-gpu.json](./queuing-config-gpu.json) - GPU configuration for Queuing scene
- [retail-config-gpu.json](./retail-config-gpu.json) - GPU configuration for Retail scene

```yaml
configs:
  retail-config:
    file: ./dlstreamer-pipeline-server/retail-config-gpu.json
  queuing-config:
    file: ./dlstreamer-pipeline-server/queuing-config-gpu.json
```

### Additional Resources

For detailed instructions on further configuring DLStreamer pipelines to use GPU, refer to the [DLStreamer Pipeline Server documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer-pipeline-server/how-to-use-gpu-for-decode-and-inference.html).

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
     #...
     depends_on:
       - broker
       - web
       - ntpserv
       - vdms
   ```

3. Use the predefined [queuing-config-reid.json](./queuing-config-reid.json) to enable vector embedding metadata from the DLStreamer service:

   ```yaml
   configs:
     queuing-config:
       file: ./dlstreamer-pipeline-server/queuing-config-reid.json
   ```

   Repeat the same step but with [retail-config-reid.json](./retail-config-reid.json) to enable reid for the **Retail** scene.

   If this is the first time running SceneScape, run:

   ```sh
   ./deploy.sh
   ```

   If you have already deployed Intel® SceneScape, use:

   ```sh
   docker compose down queuing-video retail-video scene
   docker compose up queuing-video retail-video vdms scene -d
   ```

   Ensure the OMZ model `person-reidentification-retail-0277` is available in `intel/` subfolder of models volume: `docker run --rm -v scenescape_vol-models:/models alpine ls /models/intel`.

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
