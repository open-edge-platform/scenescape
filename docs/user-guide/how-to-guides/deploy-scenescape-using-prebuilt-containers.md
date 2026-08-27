# Deploy Scenescape (Prebuilt Containers)

This guide explains how to deploy Scenescape using prebuilt Docker images, primarily from Docker Hub.

## 1. Set Up Docker Environment

Ensure Docker is installed and running on your system. For help, refer to [Installing Docker on your system](../get-started/system-requirements.md#installing-docker-on-your-system).

## 2. Generate secrets and download OpenVINO Model Zoo models

```bash
make init-secrets install-models
```

## 3. Use Prebuilt Images for Scenescape Deployment

Prebuilt containers are published on Docker Hub:

- [Scenescape Manager](https://hub.docker.com/r/intel/scenescape-manager)
- [Scenescape Controller](https://hub.docker.com/r/intel/scenescape-controller)
- [Scenescape Analytics](https://hub.docker.com/r/intel/scenescape-analytics)
- [Scenescape Autocalibration](https://hub.docker.com/r/intel/scenescape-autocalibration)
- [Scenescape Tracker](https://hub.docker.com/r/intel/scenescape-tracker)
- [Scenescape Cluster Analytics](https://hub.docker.com/r/intel/scenescape-cluster-analytics)
- [Scenescape Mapping](https://hub.docker.com/r/intel/scenescape-mapping)

## 4. Configure preloaded scenes at deployment

Scenes are not preloaded while the database is initialized. They are uploaded
through the REST API once the deployment is running, from a directory that holds
one exported scene archive (`.zip`) per scene, as produced by the "Export Scene"
button of the web UI. The demo archives live in `sample_data/demo_scenes`.

- **Load the demo scenes:** `make demo` does this automatically; run it again at
  any time with `make demo-scenes`. Scenes that already exist are skipped.
- **Load your own scenes:** point the upload at a different directory of
  exported archives:

  ```bash
  make demo-scenes DEMO_SCENES_DIR=/home/scenescape/Scenescape/sample_data/my-scenes
  ```

- **Skip loading scenes:** do not run `make demo-scenes`.

## 5. Start Services

Start the demo without rebuilding local images (relies entirely on the prebuilt containers):

```bash
SUPASS=<password> DEMO_REBUILD_IMAGES=false make demo
```

> `DEMO_REBUILD_IMAGES=false` skips the re-building images locally from source.

Verify that all containers are running:

```bash
docker ps
```

## 6. Import Scenes

After the services are up, scenes can be imported either via API (`curl`) or the Web UI.

### 6.1 Using `curl`

1. Obtain an authentication token:

   ```bash
   curl --location --insecure -X POST -d "username=admin&password=<password>" https://<ip_address>/api/v1/auth
   ```

   > Note: `<password>` is the same as used in `SUPASS=<password> make demo`.

2. Upload the scene ZIP:

   ```bash
   curl -k -X POST \
     -H "Authorization: Token <token>" \
     -F "zipFile=@<path_to_zip>" \
     https://<ip_address>/api/v1/import-scene/
   ```

### 6.2 Using the Web UI

1. Log in with admin credentials.
2. Navigate to **Import Scene**.
3. Select and upload the scene ZIP.
