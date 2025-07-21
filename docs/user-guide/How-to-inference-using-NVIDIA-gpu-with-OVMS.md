# Using NVIDIA® GPU with OVMS in Scenescape

## Pre-requisite

Follow instructions for enabling NVIDIA GPU Support from this Blog post:

[Deploying AI workloads with OpenVINO Model Server across CPUs and GPUs](https://blog.openvino.ai/blog-posts/deploy-ai-workloads-with-openvino-tm-model-server-across-cpus-and-gpus)

## Setup Docker Build Environment

Pull docker cuda runtime.

```
docker pull docker.io/nvidia/cuda:11.8.0-runtime-ubuntu20.04
```

or for Ubuntu 24.04:

```
docker pull docker.io/nvidia/cuda:11.8.0-runtime-ubuntu22.04
```

Follow instructions in the blog for installation the NVIDIA Container Toolkit. Generally, the steps are:

- download NVIDIA keyring
- install experimental packages
- apt update

```
sudo apt-get install -y nvidia-container-toolkit
```

## Fetch and Build OVMS

Fetch all of the model server sources from github.

```
mkdir ovms_nvidia
cd ovms_nvidia
git clone https://github.com/openvinotoolkit/model_server.git
cd model_server
```

Build the model server docker container.

```
NVIDIA=1 OV_USE_BINARY=0 OV_SOURCE_BRANCH=master OV_CONTRIB_BRANCH=master make docker_build
```

_Note: The build and test process will take anywhere from 20 - 45 minutes to complete._

Results displayed at the end of build/test:

```
=> => writing image sha256:6664132b5bf15b0afe53e4acfc3829d712810500ad5a64e5a3511c599fd65b9b                                                 0.0s
=> => naming to docker.io/openvino/model_server-gpu:latest-cuda
```

View built containers via the "docker images" command.

```
tom@adlgraphics:~/develop/ovms_nvidia/model_server$ docker images
REPOSITORY                    TAG                          IMAGE ID       CREATED          SIZE
openvino/model_server-gpu     latest-cuda                  6664132b5bf1   18 minutes ago   5.3GB
openvino/model_server         latest-gpu-cuda              6664132b5bf1   18 minutes ago   5.3GB
nvidia/cuda                   11.8.0-runtime-ubuntu20.04   87fde1234010   6 months ago     2.66GB
nvidia/cuda                   11.8.0-runtime-ubuntu22.04   d8fb74ecc8b2   6 months ago     2.65GB
hello-world                   latest                       d2c94e258dcb   13 months ago    13.3kB
```

## Run NVIDIA Enabled OVMS Container

Follow the directions in OVMS documentation for setting-up the directory structure for video content. Where the directory
structure looks similair to:

```
workspace/
    person-detection-retail-0013
        1/
           person-detection-retail-0013.bin
           person-detection-retail-0013.xml

```

Set the model directory environment variable:

```
MODEL_DIR=/home/tom/develop/openvino
echo $MODEL_DIR
```

Run the model server docker container.

```
docker run -p 30001:30001 -p 30002:30002 -it --gpus all \
-v ${MODEL_DIR}/workspace:/workspace openvino/model_server:latest-cuda \
--model_path /workspace/person-detection-retail-0013 \
--model_name person-detection-retail-0013 --port 30001 \
--rest_port 30002 --target_device NVIDIA
```

When the OVMS server is running, output should be similar to:

```
[2024-05-31 11:36:28.233][1][modelmanager][info][modelinstance.cpp:1321] Number of OpenVINO streams: 1
[2024-05-31 11:36:28.233][1][modelmanager][info][modelinstance.cpp:757] Plugin config for device: NVIDIA
[2024-05-31 11:36:28.233][1][modelmanager][info][modelinstance.cpp:761] OVMS set plugin settings key: PERFORMANCE_HINT; value: LATENCY;
[2024-05-31 11:36:28.235][1][serving][info][modelinstance.cpp:824] Loaded model person-detection-retail-0013; version: 1; batch size: 1; No of InferRequests: 1
[2024-05-31 11:36:28.235][1][serving][info][modelversionstatus.cpp:109] STATUS CHANGE: Version 1 of model person-detection-retail-0013 status change. New status: ( "state": "AVAILABLE", "error_code": "OK" )
[2024-05-31 11:36:28.235][1][serving][info][model.cpp:88] Updating default version for model: person-detection-retail-0013, from: 0
[2024-05-31 11:36:28.235][1][serving][info][model.cpp:98] Updated default version for model: person-detection-retail-0013, to: 1
[2024-05-31 11:36:28.235][1][serving][info][servablemanagermodule.cpp:55] ServableManagerModule started
[2024-05-31 11:36:28.235][268][modelmanager][info][modelmanager.cpp:1086] Started cleaner thread
[2024-05-31 11:36:28.235][267][modelmanager][info][modelmanager.cpp:1067] Started model manager thread
```

## Testing OVMS Using Benchmark Client

Build the model server benchmark client following directions in "Deploy AI Workloads with OpenVINO™ Model Server across CPUs and GPUs" Blog.

When docker build completes, benchmark_client displays with "docker images" command

```
tom@adlgraphics:~/develop/ovms_nvidia/model_server/demos/benchmark/python$ docker images
REPOSITORY                    TAG                          IMAGE ID       CREATED          SIZE
benchmark_client              latest                       0aeba9dc0462   32 seconds ago   2.36GB
```

Run benchmark client.

```
docker run --network host benchmark_client -a localhost -r 30002 -m person-detection-retail-0013 -p 30001 -n 8 --report_warmup --print_all
```

The output of benchmark client shows latencies and frame rates.

```
XI worker: window_first_latency: 0.044996039000125165
XI worker: window_pass_max_latency: 0.044996039000125165
XI worker: window_fail_max_latency: 0.0
XI worker: window_brutto_batch_rate: 31.29846114349164
XI worker: window_brutto_frame_rate: 31.29846114349164
XI worker: window_netto_batch_rate: 26.631751020653166
XI worker: window_netto_frame_rate: 26.631751020653166
XI worker: window_frame_passrate: 1.0
XI worker: window_batch_passrate: 1.0
XI worker: window_mean_latency: 0.03754916450009205
XI worker: window_mean_latency2: 0.0014308553988021302
XI worker: window_stdev_latency: 0.004573362455257325
XI worker: window_cv_latency: 0.12179665023561613
XI worker: window_pass_mean_latency: 0.03754916450009205
XI worker: window_pass_mean_latency2: 0.0014308553988021302
XI worker: window_pass_stdev_latency: 0.004573362455257325
XI worker: window_pass_cv_latency: 0.12179665023561613
```

## Scenescape docker_compose.yml file configuration

The OVMS configuration section of docker_compose.yml should look similiar to the configuration below. Refer to
docker help for information under the "devices" section to use a selected GPU if multiple GPUs are installed.

```
ovms:
     image: openvino/model_server:latest-cuda
     user: "${UID}:${GID}"
     networks:
       scenescape:
     command: --config_path /models/ovms-config.json --port 30001 --rest_port 30002 --cache_dir /models/ovms/cache
     volumes:
      - ./model_installer/models:/models
     restart: always
     deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

For completeness, an example retail video section is shown below. There are four changes to
the scene section: depends_on, camerachain, ovmshost and the "volumes" section pointing to the directory
containing the models.

```
retail-video:
    image: scenescape:<version>
    init: true
    networks:
      scenescape:
    depends_on:
     - broker
     - ntpserv
     - ovms
    command:
     - "percebro"
     - "--camera=sample_data/apriltag-cam1.mp4"
     - "--cameraid=camera1"
     - "--intrinsics={\"fov\":70}"
     - "--camera=sample_data/apriltag-cam2.mp4"
     - "--cameraid=camera2"
     - "--intrinsics={\"fov\":70}"
     - "--camerachain=retail=ovms"
     - "--ovmshost=ovms:30001"
     - "--ntp=ntpserv"
     - "--auth=/run/secrets/percebro.auth"
     - "broker.scenescape.intel.com"
    privileged: true
    volumes:
     - ./model_installer/models:/opt/intel/openvino/deployment_tools/intel_models
     - ./model_installer/models/ovms-config.json:/opt/ml/ovms-config.json
     - ./model_installer/models:/models
    secrets:
     - certs
     - percebro.auth
    restart: always
```

## Verifying that NVIDIA hardware is being utilized

Use nvtop to view GPU utilization while Scenescape is running.

```
sudo apt install nvtop
```

## Troubleshooting Tips

### Build Issues

- When building OVMS with NVIDIA support, using `OV_SOURCE_BRANCH=master` may be more reliable than specific version branches like 2024.0 or 2024.1
- If build failures occur with specific versions, try the master branch as demonstrated in the build command above

### NVIDIA Driver Issues

If you encounter "device not found" errors when running `nvidia-smi` despite having drivers installed:

1. Consider switching from NVIDIA proprietary drivers to the open source version
2. Add the following configuration to enable support for your GPU in `/etc/modprobe.d/nvidia.conf`:

```
options nvidia NVreg_OpenRmEnableUnsupportedGpus=1
```

3. Reboot your system after making these changes
4. Verify GPU detection with `nvidia-smi` command

### Verifying GPU Utilization

Monitor GPU usage during inference to confirm NVIDIA acceleration is working properly:

```
nvtop
```

or

```
nvidia-smi -l 1
```

to refresh GPU statistics every second

```
tom@adlgraphics:~$ nvidia-smi
Fri May 31 07:25:12 2024
+---------------------------------------------------------------------------------------+
| NVIDIA-SMI 535.171.04             Driver Version: 535.171.04   CUDA Version: 12.2     |
|-----------------------------------------+----------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |         Memory-Usage | GPU-Util  Compute M. |
|                                         |                      |               MIG M. |
|=========================================+======================+======================|
|   0  NVIDIA GeForce RTX 3050        Off | 00000000:01:00.0 Off |                  N/A |
| 34%   34C    P2              20W /  70W |    185MiB /  6144MiB |      3%      Default |
|                                         |                      |                  N/A |
+-----------------------------------------+----------------------+----------------------+

+---------------------------------------------------------------------------------------+
| Processes:                                                                            |
|  GPU   GI   CI        PID   Type   Process name                            GPU Memory |
|        ID   ID                                                             Usage      |
|=======================================================================================|
|    0   N/A  N/A      1611      G   /usr/lib/xorg/Xorg                            4MiB |
|    0   N/A  N/A      1859      C   ...libexec/gnome-remote-desktop-daemon      157MiB |
|    0   N/A  N/A      2310      G   ...libexec/gnome-remote-desktop-daemon        0MiB |
+---------------------------------------------------------------------------------------+
tom@adlgraphics:~$
```
