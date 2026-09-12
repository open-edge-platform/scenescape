# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

MANAGERIMAGE=intel/scenescape-manager
CAMCALIBIMAGE=intel/scenescape-autocalibration
CONTROLLERIMAGE=intel/scenescape-controller
CLUSTERANALYTICSIMAGE=intel/scenescape-cluster-analytics
MAPPINGIMAGE=intel/scenescape-mapping
ANALYTICSIMAGE=intel/scenescape-analytics

# Image groupings for flexible builds
CORE_IMAGES=$(MANAGERIMAGE) $(CAMCALIBIMAGE) $(CONTROLLERIMAGE) $(ANALYTICSIMAGE)
ALL_IMAGES=$(CORE_IMAGES) $(CLUSTERANALYTICSIMAGE) $(MAPPINGIMAGE)

VERSION:=$(shell cat ../version.txt)
NAMESPACE=scenescape
WORKINGDIR=$(shell dirname $(shell pwd))
DEPLOYMENT_TEST=
TEST_FLAGS=
# it may need to be increased if all models are being downloaded (see values.yaml)
INSTALL_TIMEOUT?=1800s

ifeq ($(DEPLOYMENT_TEST), 1)
    TEST_FLAGS=--wait --timeout $(INSTALL_TIMEOUT) --debug
endif

KINDREG=kind-registry
KINDREGPORT=5001
# Uncomment and set HOSTDIR if you want to access the persistent volumes on the host (root ownership)
# HOSTDIR=$(WORKINGDIR)/kind-storage

CERTPASS=$(shell openssl rand -base64 33)
REGISTRY=localhost:$(KINDREGPORT)

RELEASE=scenescape-release-1
FORCE_VAAPI?=0
CHART_DEBUG?=0

# Demo mode variable for Kubernetes deployments (core, reid or all)
DEMO_K8S_MODE?=core
# ReID vector database backend used when ReID is deployed: vdms (default) or qdrant
REID_BACKEND?=vdms

# Directory with one subdirectory per demo scene (each holding a <name>.zip),
# and the client that uploads them
DEMO_SCENES_DIR?=../sample_data/demo_scenes
DEMO_SCENES_URL?=https://localhost/api/v1
# The demo certificate is issued for web.scenescape.intel.com, not for localhost.
# Override with --rootcert <ca.pem> when uploading to a properly named host.
DEMO_SCENES_TLS?=--insecure
DEMO_SCENES_WAIT?=300
UPLOAD_SCENES:=../tools/upload_scenes/upload-scenes

# Proxy settings: if http_proxy, https_proxy, or no_proxy environment variables are set,
# they will be automatically passed to the Helm chart during installation
# Chart debug: set CHART_DEBUG=1 to enable chartdebug=true in Helm deployment

# start kind, then install Scenescape with helm
default: install-deps clean-kind kind load-core install

# publish to ITEP by building, packaging, then pushing
build-and-package: build-core package

# build scenescape images and load everything to kind cluster, then generate Chart.yaml
build: build-core

build-core: docker-build-core load-core

build-all: docker-build-all load-all

kind: generate-kind-yaml start-kind install-cert-manager

# remove everything Kubernetes related from your machine
clean-all: clean-kind

# dependency installation (requires sudo) for kind, kubectl, k9s (optional), helm
# NO SUDO: alternatively, if your user does not have sudo access:
# 1. comment out the sudo commands for kind, kubectl, k9s and helm
# 2. move the kind, kubectl, k9s and helm binaries to your PATH manually from /tmp, e.g. to ~/.local/bin, like so:
# mv /tmp/kind /tmp/kubectl /tmp/k9s /tmp/helm ~/.local/bin
install-deps:
	@if [ -z "$(shell which kind)" ] ; then \
	    curl -Lo /tmp/kind https://kind.sigs.k8s.io/dl/v0.32.0/kind-linux-amd64 ; \
	    chmod +x /tmp/kind ; \
	    sudo mv /tmp/kind /usr/local/bin/kind ; \
	    echo "kind installed" ; \
	fi
	@if [ -z "$(shell which kubectl)" ] ; then \
	    curl -Lo /tmp/kubectl https://dl.k8s.io/release/v1.35.0/bin/linux/amd64/kubectl ; \
	    chmod +x /tmp/kubectl ; \
	    sudo install -o root -g root -m 0755 /tmp/kubectl /usr/local/bin/kubectl ; \
	    echo "kubectl installed" ; \
	fi
	@if [ -z "$(shell which k9s)" ] ; then \
	    wget https://github.com/derailed/k9s/releases/download/v0.27.4/k9s_Linux_amd64.tar.gz -P /tmp ; \
	    tar -C /tmp -zxvf /tmp/k9s_Linux_amd64.tar.gz k9s ; \
	    sudo mv /tmp/k9s /usr/local/bin/k9s ; \
	    echo "k9s installed" ; \
	fi
	@if [ -z "$(shell which helm)" ] ; then \
	    wget https://get.helm.sh/helm-v3.13.0-linux-amd64.tar.gz -P /tmp ; \
	    tar -C /tmp -zxvf /tmp/helm-v3.13.0-linux-amd64.tar.gz --strip-components=1 linux-amd64/helm ; \
	    sudo mv /tmp/helm /usr/local/bin/helm ; \
	    echo "helm installed" ; \
	fi

# generate yaml for kind setup
generate-kind-yaml:
	mkdir -p setup
	cp template/kind.template setup/kind.yaml
	cp template/kind-config.template setup/kind-config.yaml
	@if [ -z "$(HOSTDIR)" ] ; then \
	    sed -n -i '/{HOSTDIR}/q;p' setup/kind-config.yaml; \
	else \
	    sed -e "s|{HOSTDIR}|$(HOSTDIR)|g" -i setup/kind-config.yaml; \
	    echo "HOSTDIR is set. Kind will mount $(HOSTDIR) into container for persistent volumes."; \
	fi

# run a test cluster in a kind container. Requires the kind binary
start-kind:
	NO_PROXY=$(NO_PROXY),$(KINDREG) kind create cluster --config ./setup/kind-config.yaml || true
	kubectl apply -f ./setup/kind.yaml
	@until kubectl get svc kubernetes -o go-template='{{.spec.clusterIP}}' | grep -qv '<none>'; do \
	    sleep 1; \
	done
	kubectl patch service kubernetes --type=merge -p '{"spec": {"ports": [{"name": "https", "port": 6443, "targetPort": 6443}]}}'
	kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
	@until kubectl get pod -n ingress-nginx --selector=app.kubernetes.io/component=controller -o go-template='{{.items | len}}' | grep -qxF 1; do \
	    sleep 1; \
	done
# kubectl -n ingress-nginx patch deployment ingress-nginx-controller --type=json -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--enable-ssl-passthrough"}]'
	kubectl wait -n ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=300s
# Enable automatic restart for the kind container so when host is rebooted, the kind cluster will be available
	docker update --restart=always $(docker ps -aq --filter "label=io.x-k8s.kind.cluster=kind")

# remove the kind container
clean-kind:
	kind delete cluster
	docker network rm kind || true

install-cert-manager:
	kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.18.2/cert-manager.yaml

# build scenescape docker images, download models for init-models
# note, will make unneeded secrets in secrets/ as well
docker-build-core:
	$(MAKE) -C .. CERTPASS=$(CERTPASS) FORCE_VAAPI=$(FORCE_VAAPI)

docker-build-all:
	$(MAKE) -C .. build-all CERTPASS=$(CERTPASS) FORCE_VAAPI=$(FORCE_VAAPI)

load-image:
	docker tag $(IMAGE):$(VERSION) $(REGISTRY)/$(IMAGE):$(VERSION)
	kind load docker-image $(REGISTRY)/$(IMAGE):$(VERSION)

load-core:
	$(MAKE) load-image IMAGE=$(MANAGERIMAGE)
	$(MAKE) load-image IMAGE=$(CAMCALIBIMAGE)
	$(MAKE) load-image IMAGE=$(CONTROLLERIMAGE)
	$(MAKE) load-image IMAGE=$(ANALYTICSIMAGE)

load-all: load-core
	$(MAKE) load-image IMAGE=$(CLUSTERANALYTICSIMAGE)
	$(MAKE) load-image IMAGE=$(MAPPINGIMAGE)

SERVICES := $(patsubst scenescape-%,%,$(ALL_IMAGES))
.PHONY: $(SERVICES)
$(SERVICES):
	$(MAKE) -C ../$@
	$(MAKE) load-image IMAGE=scenescape-$@
	$(MAKE) restart-service IMAGE=scenescape-$@

restart-service:
	kubectl get pods -n scenescape -o json | jq -r '.items[] | select(.spec.containers[].image | contains("$(IMAGE)")) | .metadata.name' | xargs -I {} kubectl delete pod {} -n scenescape

# generate Chart.yaml with appropriate version.txt
chart.yaml:
	sed -e "s|{VERSION}|$(VERSION)|g" template/Chart.template > scenescape-chart/Chart.yaml

# packages and pushes the helm chart
package: copy-files chart.yaml
	helm package scenescape-chart/

copy-files:
	mkdir -p scenescape-chart/files/dlsps
	mkdir -p scenescape-chart/files/broker
	mkdir -p scenescape-chart/files/model-download
	mkdir -p scenescape-chart/files/sample-data
	mkdir -p scenescape-chart/files/scene-controller
	cp -r ../dlstreamer-pipeline-server/user_scripts/gstplugins/* scenescape-chart/files/dlsps/
	cp ../dlstreamer-pipeline-server/mosquitto/mosquitto-secure.conf scenescape-chart/files/broker/mosquitto-secure.conf
	cp ../controller/config/tracker-config.json scenescape-chart/files/scene-controller/tracker-config.json
	cp ../controller/config/reid-config.json scenescape-chart/files/scene-controller/reid-config.json
	cp ../model_download/src/download_models.py scenescape-chart/files/model-download/download_models.py
	cp ../model_download/src/generate_model_config.py scenescape-chart/files/model-download/generate_model_config.py
	cp ../model_download/src/entrypoint-k8s.sh scenescape-chart/files/model-download/entrypoint-k8s.sh
	cp ../model_download/models.json scenescape-chart/files/model-download/models.json
	cp ../sample_data/scripts/download-sample-data-k8s.sh scenescape-chart/files/sample-data/download-sample-data-k8s.sh
	cp ../sample_data/scripts/convert-videos-k8s.sh scenescape-chart/files/sample-data/convert-videos-k8s.sh


check-demo-k8s-mode:
	@case "$(DEMO_K8S_MODE)" in \
	  core|reid|all) ;; \
	  *) echo "Invalid DEMO_K8S_MODE '$(DEMO_K8S_MODE)'. Use core, reid or all."; exit 1 ;; \
	esac
	@case "$(REID_BACKEND)" in \
	  vdms|qdrant) ;; \
	  *) echo "Invalid REID_BACKEND '$(REID_BACKEND)'. Use vdms or qdrant."; exit 1 ;; \
	esac

# Uploads sample_data/demo_scenes/*.zip through the REST API, same client the root Makefile uses.
.PHONY: demo-scenes
demo-scenes:
	@VENV="../tools/upload_scenes/.venv"; \
	if [ ! -d "$$VENV" ]; then \
		python3 -m venv "$$VENV"; \
		"$$VENV/bin/pip" install -q -r ../tools/upload_scenes/requirements.txt; \
	fi
	@echo "Waiting for kubeclient to be ready (so it doesn't miss camera-creation events)..."
	kubectl rollout status deployment/$(RELEASE)-kubeclient-dep -n $(NAMESPACE) --timeout=300s
	@echo "Uploading demo scenes from $(DEMO_SCENES_DIR) to $(DEMO_SCENES_URL)..."
	@AUTH_FILE=$$(mktemp); \
	VENV="../tools/upload_scenes/.venv"; \
	trap 'rm -f $$AUTH_FILE' EXIT; \
	kubectl get secret $(RELEASE)-controller.auth -n $(NAMESPACE) -o jsonpath='{.data.controller\.auth}' | base64 -d > $$AUTH_FILE; \
	"$$VENV/bin/python3" $(UPLOAD_SCENES) --restauth $$AUTH_FILE $(DEMO_SCENES_TLS) --wait $(DEMO_SCENES_WAIT) \
		$(DEMO_SCENES_URL) $(DEMO_SCENES_DIR)

# to test template rendering
# helm template -s templates/ingress.yaml kubernetes/scenescape-chart/
# helm install scenescape-release-1 kubernetes/scenescape-chart/ --dry-run --debug
install: check-demo-k8s-mode copy-files chart.yaml
	@VALUES_FILE=""; \
	if [ -n "$(http_proxy)" ] || [ -n "$(https_proxy)" ]; then \
		VALUES_FILE="/tmp/scenescape-proxy-values.yaml"; \
		if [ -n "$(http_proxy)" ]; then \
			echo "httpProxy: \"$(http_proxy)\"" >> $$VALUES_FILE; \
		fi; \
		if [ -n "$(https_proxy)" ]; then \
			echo "httpsProxy: \"$(https_proxy)\"" >> $$VALUES_FILE; \
		fi; \
		if [ -n "$(no_proxy)" ]; then \
			echo "noProxy: \"$(no_proxy)\"" >> $$VALUES_FILE; \
		fi; \
		VALUES_FILE="-f $$VALUES_FILE"; \
	fi; \
	DEBUG_ARGS=""; \
	if [ "$(CHART_DEBUG)" = "1" ]; then \
		DEBUG_ARGS="--set chartdebug=true"; \
	fi; \
	SUPASS_ARG=""; \
	if [ -n "$${SUPASS}" ]; then \
		SUPASS_ARG="--set supass=$${SUPASS}"; \
	fi; \
	PGPASS_ARG=""; \
	if [ -n "$${PGPASS}" ]; then \
		PGPASS_ARG="--set pgserver.password=$${PGPASS}"; \
	fi; \
	MODE_ARG="--set reid.enabled=false"; \
	if [ "$(DEMO_K8S_MODE)" = "reid" ]; then \
		MODE_ARG="--set reid.enabled=true --set reid.backend=$(REID_BACKEND)"; \
	elif [ "$(DEMO_K8S_MODE)" = "all" ]; then \
		MODE_ARG="--set reid.enabled=true --set reid.backend=$(REID_BACKEND) --set mapping.enabled=true --set clusterAnalytics.enabled=true"; \
	fi; \
	REPOSITORY_ARG="--set repository=$(REGISTRY)"; \
	helm upgrade $(RELEASE) --install scenescape-chart/ -n $(NAMESPACE) --create-namespace --timeout $(INSTALL_TIMEOUT) $${DEBUG_ARGS} $${REPOSITORY_ARG} $${SUPASS_ARG} $${PGPASS_ARG} $${MODE_ARG} $${VALUES_FILE} $(TEST_FLAGS);
	@if [ -f "/tmp/scenescape-proxy-values.yaml" ]; then \
		rm -f /tmp/scenescape-proxy-values.yaml; \
	fi
	$(MAKE) demo-scenes

uninstall:
	helm uninstall $(RELEASE) -n $(NAMESPACE) || true

delete-namespace:
	kubectl delete ns $(NAMESPACE) || true

# development targets
# wait for scenescape to be ready
wait-for-ready:
	@until kubectl get pod -n $(NAMESPACE) --selector="app=$(RELEASE)-scene" -o go-template='{{.items | len}}' | grep -qxF 1; do \
	    sleep 1; \
	done
	kubectl wait -n $(NAMESPACE) --for=condition=ready pod --selector="app=$(RELEASE)-scene" --timeout=240s

# below targets work if registry and kind are already running
# building and reinstalling (during development)
rebuild: rebuild-demo

rebuild-demo:
	@if [ "$(DEMO_K8S_MODE)" = "all" ]; then \
		$(MAKE) rebuild-all; \
	else \
		$(MAKE) rebuild-core; \
	fi

rebuild-core: uninstall delete-namespace build-core install

rebuild-all: uninstall delete-namespace build-all install

test:
	@helm test $(RELEASE) -n $(NAMESPACE) --timeout 240s
