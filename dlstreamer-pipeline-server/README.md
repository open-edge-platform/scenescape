# Using Deep Learning Streamer Pipeline Server with Intel® SceneScape

- [Getting Started](#getting-started)
- [Running on GPU](#running-on-gpu)
- [Running on NPU](#running-on-npu)
- [Enable Re-ID](#enable-reidentification)
- [Creating a New Pipeline](#creating-a-new-pipeline)
- [Using Authenticated MQTT Broker](#using-authenticated-mqtt-broker)
- [Additional Resources](#additional-resources)

## Getting Started

Below are step-by-step instructions for enabling out-of-the-box scenes in Intel® SceneScape to leverage DL Streamer Pipeline Server for Video Analytics.

1. **Model Requirements:**
   Ensure the OMZ model `person-detection-retail-0013` is present in the Models Volume in the `models/intel/` subfolder. Refer to the instructions in [How to Manage Files in Volumes](../docs/user-guide/other-topics/how-to-manage-files-in-volumes.md) on how to access the Models Volume.

2. **Start Intel® SceneScape DL Streamer-based demo:**

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

Running the pipelines on GPU is highly recommended when available on the system. This approach efficiently utilizes available CPU cores for other SceneScape services and provides optimal performance for the visual analytics service. Only Intel GPU devices are supported.

To facilitate GPU acceleration, sample configuration files are provided for the out-of-box **Queuing** and **Retail** scenes with the following pipeline optimizations:

- Video decode offloaded to GPU
- Inference offloaded to GPU
- Cross-stream batching enabled

### Automatic GPU Device Selection

The following steps enable the above-mentioned optimizations for:

- platforms with multiple GPU devices: a GPU device will be chosen automatically.
- systems with only one GPU device.

1. Expose Direct Rendering Infrastructure device directory to the docker containers running visual pipelines. In your `docker-compose.yml`, uncomment the following lines:

   ```yaml
   retail-video:
     devices:
       - "/dev/dri:/dev/dri"
   ```

   ```yaml
   queuing-video:
     devices:
       - "/dev/dri:/dev/dri"
   ```

2. Use the predefined configuration files in your `docker-compose.yml` to enable GPU acceleration for out-of-box scenes:
   - [queuing-config-gpu.json](./queuing-config-gpu.json) - GPU configuration for Queuing scene
   - [retail-config-gpu.json](./retail-config-gpu.json) - GPU configuration for Retail scene

   ```yaml
   configs:
     retail-config:
       file: ./dlstreamer-pipeline-server/retail-config-gpu.json
     queuing-config:
       file: ./dlstreamer-pipeline-server/queuing-config-gpu.json
   ```

### Manual GPU Device Selection (by exposing device to container)

To enable SceneScape pipelines to run on a specific GPU device of your choice (e.g., on a discrete GPU, in case an integrated GPU also exists), follow these steps. These instructions are similar to the "Automatic GPU Device Selection" section, with the key difference being the selection of a specific device (e.g., `renderD129`).

1. **List Available GPU Devices:**
   Use the following command to list available GPU devices on your system:

   ```sh
   ls /dev/dri
   ```

   Look for entries like `renderD128`, `renderD129`, etc. The specific device to use depends on your hardware configuration.

2. **Verify Device Functionality:**
   To ensure the selected device is functional, you can use tools like `vainfo` (for VA-API support) or `intel_gpu_top` (for Intel GPUs).

3. **Update the `docker-compose.yml` file:**
   - Uncomment the `devices` section and specify the appropriate GPU device. Make sure only your device of choice is listed; otherwise, it is not guaranteed that the proper GPU will be chosen. For example, if you expose the whole folder `/dev/dri/` or keep both `renderD128` and `renderD129`, it is likely that the first choice will be `renderD128`, which may not be what you expect.
     Example:
     ```yaml
     devices:
       - "/dev/dri/renderD129:/dev/dri/renderD129"
     ```

4. **Use GPU-specific configuration files:**
   - Replace the default configuration files with GPU-optimized versions:
     ```yaml
     configs:
       retail-config:
         file: ./dlstreamer-pipeline-server/retail-config-gpu.json
       queuing-config:
         file: ./dlstreamer-pipeline-server/queuing-config-gpu.json
     ```

By following these steps, only the selected GPU device will be available in the container. As a result, all DL Streamer Pipeline Server pipelines running in the container will use the GPU device of your choice.

> **Note**: This setup cannot run two pipelines in the same container on different GPU devices. To work around that limitation, configure each pipeline as described in the [DL Streamer documentation](https://docs.openedgeplatform.intel.com/2026.0/edge-ai-libraries/dl-streamer/dev_guide/gpu_device_selection.html), but be aware that doing so disables cross-stream batching and may deliver lower throughput.

## Running on NPU

Running inference on NPU is recommended when an Intel® NPU is available on the system. This offloads the inference workload to the NPU, freeing up CPU and GPU resources for other SceneScape services.

To facilitate NPU acceleration, sample configuration files are provided for the out-of-box **Queuing** and **Retail** scenes with the following pipeline optimizations:

- Inference offloaded to NPU

NPU performance metrics can be monitored using [NPU System Monitoring Tool](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/tools/npu-monitor-tool)

### Configuration

1. Expose the NPU accelerator device directory to the docker containers running visual pipelines. In your `docker-compose.yml` uncomment the following lines:

   ```yaml
   retail-video:
     devices:
       - "/dev/accel:/dev/accel"
   ```

   ```yaml
   queuing-video:
     devices:
       - "/dev/accel:/dev/accel"
   ```

2. Use the predefined configuration files in your `docker-compose.yml` to enable NPU acceleration for out-of-box scenes:
   - [queuing-config-npu.json](./queuing-config-npu.json) - NPU configuration for Queuing scene
   - [retail-config-npu.json](./retail-config-npu.json) - NPU configuration for Retail scene

   ```yaml
   configs:
   retail-config:
     file: ./dlstreamer-pipeline-server/retail-config-npu.json
   queuing-config:
     file: ./dlstreamer-pipeline-server/queuing-config-npu.json
   ```

## Enable Reidentification

Following are the step-by-step instructions for enabling person reidentification for the out-of-box **Queuing** scene.

1. **Enable the ReID Database Container**\
   Launch scenescape using vdms profile

   ```bash
   docker compose -f docker-compose.yml -f sample_data/docker-compose.vdms-override.yml --profile vdms up -d
   ```

2. Use the predefined [queuing-config-reid.json](./queuing-config-reid.json) to enable vector embedding metadata from the DL Streamer service:

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
   docker compose -f docker-compose.yml -f sample_data/docker-compose.vdms-override.yml --profile vdms up queuing-video retail-video vdms scene -d
   ```

   Ensure the OMZ model `person-reidentification-retail-0277` is available in `intel/` subfolder of models volume: `docker run --rm -v scenescape_vol-models:/models alpine ls /models/intel`.

## Creating a New Pipeline

To create a new pipeline, follow these steps:

1. **Create a New Config File:**
   Use the existing `config.json` as a template to create your new pipeline configuration file (e.g., `my_pipeline_config.json`). Adjust the parameters as needed for your use case.

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

## Additional Resources

For detailed instructions on further configuring DL Streamer pipelines, refer to:

- [How to Configure DL Streamer Video Pipeline](../docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md) - Step-by-step guide for configuring DL Streamer video pipelines in SceneScape.
- [DL Streamer Pipeline Server documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer-pipeline-server/how-to-guides/use-gpu-npu-for-decode-and-inference.html) - How to configure video pipeline to use GPU or NPU.
