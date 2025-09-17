# SceneScape Deployment Guide (Prebuilt Containers)

This guide explains how to deploy SceneScape using prebuilt Docker images, primarily from Docker Hub.

---

## 1. Set Up Docker Environment

1. Ensure Docker is installed and running on your system.

---

## 2. Deploy SceneScape Using Prebuilt Images

Build and prepare the services:

```bash
make init-secrets install-models
```

### 2.1 Pull Images from Docker Hub

SceneScape prebuilt containers can be found here:

* [SceneScape Manager](https://hub.docker.com/r/intel/scenescape-manager)
* [SceneScape Controller](https://hub.docker.com/r/intel/scenescape-controller)
* [SceneScape Cam Calibration](https://hub.docker.com/r/intel/scenescape-camcalibration)

**Adjustments for prebuilt images:**

* Use prebuilt images instead of local builds.
* Decide whether to preload the database:

  * **Skip preloading:** Do not set the `EXAMPLEDB` environment variable.
  * **Preload database:** Set the `EXAMPLEDB` environment variable to the path of your database tar file and ensure the folder is mounted. Example:

```yaml
web:
  image: docker.io/intel/scenescape-manager:latest
  environment:
    - EXAMPLEDB=/home/scenescape/SceneScape/sample_data/exampledb.tar.bz2
    - SUPASS=<password>
  volumes:
    - vol-sample-data:/home/scenescape/SceneScape/sample_data
```

Update `sample_data/docker-compose-dl-streamer-example.yml` to point to the pulled images. Example:

```yaml
scene:
  image: docker.io/intel/scenescape-controller:latest
web:
  image: docker.io/intel/scenescape-manager:latest
camcalibration:
  image: docker.io/intel/scenescape-camcalibration:latest
```

### 2.2 Start Services

Start the demo services:

```bash
SUPASS=<password> make demo
```

Verify that all containers are running:

```bash
docker ps
```

---

## 3. Import Scenes

After the services are up, scenes can be imported either via API (`curl`) or the Web UI.

### 3.1 Using `curl`

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

### 3.2 Using the Web UI

1. Log in with admin credentials.
2. Navigate to **Import Scene**.
3. Select and upload the scene ZIP.
