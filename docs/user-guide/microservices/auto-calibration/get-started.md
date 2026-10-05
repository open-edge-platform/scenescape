# Get Started

## Prerequisites

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.
- [Build Auto Camera Calibration from source](./get-started/build-from-source.md).

## Run the service using Docker Compose

- **Navigate to the Directory**:

  ```bash
  cd scenescape
  ```

- **Generate secrets**:

  ```bash
  make build-secrets
  ```

- **Start the service**:
  Start the service using docker run:

  ```bash
  docker run --rm \
  --init \
  --network scenescape \
  -e EGL_PLATFORM=surfaceless \
  -e DBROOT \
  -v scenescape_vol-media:/workspace/media \
  -v scenescape_vol-datasets:/workspace/datasets \
  -v scenescape_vol-netvlad_models:/usr/local/lib/python3.11/site-packages/third_party/netvlad \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/calibration.auth:/run/secrets/calibration.auth:ro \
  --name autocalibration \
  intel/scenescape-autocalibration \
  autocalibration \
  --resturl https://web.scenescape.intel.com:443/api/v1
  ```

- **Note**:
  The `autocalibration` service **depends on** the `web` service.
  The application image does not download NetVLAD at startup, and it does not wait for the
  download to finish: AprilTag calibration works immediately. For Compose deployments, the
  `autocalibration-model-init` service downloads the model in parallel with the application
  starting; markerless calibration becomes available once that download completes. For a
  standalone `docker run`, run the downloader against the same named volume so markerless
  calibration works once it finishes:

  ```bash
  docker run --rm \
    --user 1000:1000 \
    --entrypoint python3 \
    -e NETVLAD_MODEL_DIR=/usr/local/lib/python3.11/site-packages/third_party/netvlad \
    -v scenescape_vol-netvlad_models:/usr/local/lib/python3.11/site-packages/third_party/netvlad \
    intel/scenescape-autocalibration \
    /usr/local/bin/download_models.py
  ```

  The downloader verifies the model checksum and exits nonzero if preparation fails.
  Before starting this container, ensure that:
  - The **web** service at `https://web.scenescape.intel.com:443` is accessible.

- **Verify the service**:
  Check that the service is running:

  ```bash
  docker ps
  ```

- **Stop the service**:

  ```bash
  docker stop autocalibration
  ```

- **Access autocalibration output through MQTT**:
  - Refer to [autocalibration-api.yaml](./_assets/autocalibration-api.yaml) on how to access
    auto calibration output.
  - Refer to [Auto Calibration Sequence Diagram](./auto-calibration.md#sequence-diagram-auto-camera-calibration-workflow)

<!--hide_directive
:::{toctree}
:hidden:

get-started/build-from-source

:::
hide_directive-->
