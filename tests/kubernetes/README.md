# Tests for SceneScape on Kubernetes
Run Kubernetes tests on a Docker test host against our local Kind testing setup or a remote Kubernetes cluster.

# Usage
## Local Kubernetes cluster tests
```bash
# make sure SS docker isn't running
make -C kubernetes VALIDATION=1 # this starts kubernetes with tests.enabled = true in the helm chart
# wait until containers are ready, check with k9s
# run tests with the SUPASS in values.yaml and KUBERNETES=1
make -C tests out-of-box SUPASS=change_me KUBERNETES=1
# containers won't be stopped after a test, you can go ahead and execute the next test.
make -C kubernetes clean-all # to clear all kubernetes infra after you are done
```

## Remote Kubernetes cluster tests
```bash
# install SS on Kubernetes with tests.enabled: true in values.yaml, wait until all pods are ready
# prepare docker test host on the same network
# copy kubeconfig to docker test host
# execute the test cases on a remote cluster with scenescape installed with tests enabled
KUBECONFIG=/home/ubuntu/config make -C tests out-of-box SUPASS=change_me KUBERNETES=1 KUB_CLUSTER_FRP_ADDRESS=192.168.122.42 KUB_CLUSTER_FRP_PORT=7000
# Variables to set
KUBECONFIG=<absolute-path-to-remote-cluster-kubeconfig>
KUB_CLUSTER_FRP_ADDRESS=<ip-of-frps-service>
KUB_CLUSTER_FRP_PORT=<port-of-frps-service>
KUB_CLUSTER_FRP_SECRET_KEY=<frps-secret-key>
CERT_KUB_BROKER_URL=<broker-cert-url> # in the format broker.<namespace> where ns is the ns in where scenescape is installed
CERT_KUB_WEB_URL=<web-cert-url> # in the format web.<namespace> where ns is the ns in where scenescape is installed
```

# How it works
The kubernetes `runtest`, which will be run when `make -C tests` is started with `KUBERNETES=1` does the following:
- expects SceneScape to be running in validation mode on a Kubernetes cluster with `tests.enabled: true`
  - this will start one FRP server (frps) and multiple FRP client (frpc) containers to proxy pod ports
  - require an additional `init-tests` image to copy our test database into our pgserver pod to run tests against
- uses `kubectl` which uses the kubeconfig defined by the `KUBECONFIG` environment variable to connect to a cluster (local or remote) to manage PVCs and deployments
- starts multiple [FRP](https://github.com/fatedier/frp) clients as docker containers which proxy most of the useful ports out from Kubernetes back into the docker environment, through one frps server port. These containers proxy the ports from the Kubernetes pods back into the docker test host so our existing test infrastructure does not need to be modified.

Additional loadbalancer, service or nodeport values can be changed in the chart's values.yaml depending on the cluster.
