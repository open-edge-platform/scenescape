# Intel® SceneScape on Kubernetes

Intel® SceneScape Kubernetes helm chart

## Overview

This folder contains the helm chart to run Intel® SceneScape on Kubernetes.

This readme goes through a minimal setup for running this on your local development machine with only 3 extra binaries needed. The default Makefile target starts a Kubernetes cluster in a Docker container using kind, then deploys Intel® SceneScape to that cluster using helm.

Advanced users intending to deploy this in production will have to change the default chart values or modify the templates.

### Prerequisites:

Intel® SceneScape needs the necessary dependencies installed first.
From the project directory, run `deploy.sh`, with parameters to skip container bringup and FPS check.
```console
$ SKIP_BRINGUP=1 REQUIRED_FPS=0 ./deploy.sh
```

## Installation and First Run

Run from the project directory (e.g. ~/scenescape)
1. `default` target starts a kind cluster, then builds and installs Intel® SceneScape on it.
**Note**: requires sudo to install binaries if not available, check additional notes below if user doesn't have sudo access
    ```console
    $ make -C kubernetes
    ```
2. When the webUI is up, log in with `admin:change_me`, on `https://localhost`.\
Note that the default admin password is defined by the `supass` value in scenescape-chart/values.yaml.
3. To stop Intel® SceneScape, run:
    ```console
    $ make -C kubernetes uninstall
    ```
4. To start Intel Scenescape again:
    ```console
    $ make -C kubernetes install
    ```
5. To remove all the Kubernetes related containers (kind, kind-registry):
    ```console
    $ make -C kubernetes clean-all
    ```

## Detailed steps and explanation

Run from the project directory (e.g. ~/scenescape)
1. Start up a kind cluster and a local registry.
    ```console
    $ make -C kubernetes kind
    ```
    This uses the template files in kubernetes/template and generates yaml files for kind cluster configuration. It then starts up a registry container, a kind cluster container and adds them to the same Docker network so they can communicate. Run `generate-kind-yaml` and `start-kind` targets separately if you want to keep your edited yaml files.
    Leave the kind cluster running or omit this step if you have your own cluster and registry ready.
2. Build Intel® SceneScape init-images and scenescape images, then push everything to the local registry.
    ```console
    $ make -C kubernetes build-all
    ```
3. Install the Intel® SceneScape release with helm.
    ```console
    $ make -C kubernetes install
    ```
11. Verify that Intel Scenescape is running.
    ```console
    kubectl get pods -n scenescape -w
    # alternative TUI
    k9s
    ```
12. Uninstall the Intel® SceneScape release.
    ```console
    $ make -C kubernetes uninstall
    ```

### Additional notes

* Additionally, to remove the kind cluster, use the `clean-kind` target. The kind registry isn't removed so the images are cached if you wish to pull from it again. To also remove the kind registry, use the `clean-kind-registry` target.
* Use the `clean-all` target to remove all containers.
* **WARNING: Intel® SceneScape data isn't persisted, uninstalling the release will lead to data loss.**
* **NON-SUDO USERS**: The `default` target will run the `install-deps` target to ensure that the `kind`, `kubectl`, `k9s` and `helm` binaries are available and install them to /usr/local/bin with sudo. If your user does not have sudo access, check the comments for the `install-deps` target and edit the Makefile accordingly.

## FAQ

* How do I verify that everything is working properly?
Run `k9s` and check that the Intel® SceneScape pods are `Ready` and in the `Running` status. If they're stuck in an error status, refer to the steps in Troubleshooting.

## Troubleshooting

* If the scene controller does not seem to be running (no dots moving in the scene), restart the scene deployment.
* If your pods can't pull the images, check to see whether the registry container is on the same docker network as the kind cluster container.
Troubleshoot by running `docker inspect kind`. If they are not, run `docker network connect "kind" "kind-registry"`.
* If you can't access the Intel® SceneScape webUI, make sure Intel® SceneScape on Docker isn't running.
