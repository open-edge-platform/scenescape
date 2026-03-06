# Generation of all dependencies lists per component

Prerequisite (run in the top level folder):

```bash
make build-all
make list-dependencies
```

# Generation of SBOM from Dockerfiles using Docker buildkit

Generate additional licence information that can be associated with dependencies per Dockerfile
Scripts are provided that generate SBOMS in Json format

```sh
docker buildx create --use --name=scenescape-buildkit-container --driver=docker-container --driver-opt=env.http_proxy=$http_proxy,env.https_proxy=$https_proxy,env.HTTP_PROXY=$HTTP_PROXY,env.HTTPS_PROXY=$HTTPS_PROXY,default-load=true

make generate-sboms

docker buildx rm scenescape-buildkit-container
```

Docs: https://www.docker.com/blog/generate-sboms-with-buildkit/
