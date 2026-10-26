# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

MANAGERIMAGE=intel/scenescape-manager
CAMCALIBIMAGE=intel/scenescape-autocalibration
CONTROLLERIMAGE=intel/scenescape-controller
CLUSTERANALYTICSIMAGE=intel/scenescape-cluster-analytics
MAPPINGIMAGE=intel/scenescape-mapping
ANALYTICSIMAGE=intel/scenescape-analytics
TRACKERIMAGE=intel/scenescape-tracker

# Image groupings for flexible builds
CORE_IMAGES=$(MANAGERIMAGE) $(CAMCALIBIMAGE) $(CONTROLLERIMAGE) $(ANALYTICSIMAGE)
ALL_IMAGES=$(CORE_IMAGES) $(CLUSTERANALYTICSIMAGE) $(MAPPINGIMAGE) $(TRACKERIMAGE)

VERSION:=$(shell cat ../version.txt)
NAMESPACE=scenescape
WORKINGDIR=$(shell dirname $(shell pwd))
DEPLOYMENT_TEST=
TEST_FLAGS=
# it may need to be increased if all models are being downloaded (see values.yaml)
INSTALL_TIMEOUT?=1800s

ifeq ($(DEPLOYMENT_TEST), 1)
	TEST_FLAGS=--debug
endif

KINDREG=kind-registry
KINDREGPORT=5001
# Uncomment and set HOSTDIR if you want to access the persistent volumes on the host (root ownership)
# HOSTDIR=$(WORKINGDIR)/kind-storage

CERTPASS=$(shell openssl rand -base64 33)
REGISTRY=localhost:$(KINDREGPORT)

RELEASE=scenescape-release-1
FORCE_VAAPI?=0

# Compose-profile-style selector shared with the root Makefile's DEPLOY_PROFILES:
# space-separated list of controller|tracker|mapping|cluster-analytics|reid
DEPLOY_PROFILES?=controller
# ReID vector database backend used when "reid" is in DEPLOY_PROFILES: vdms (default) or qdrant
REID_BACKEND?=vdms

TRACKER_ARG := $(if $(filter tracker,$(DEPLOY_PROFILES)),--set tracker.enabled=true,)
MAPPING_ARG := $(if $(filter mapping,$(DEPLOY_PROFILES)),--set mapping.enabled=true,)
CLUSTER_ANALYTICS_ARG := $(if $(filter cluster-analytics,$(DEPLOY_PROFILES)),--set clusterAnalytics.enabled=true,)
REID_ARG := $(if $(filter reid,$(DEPLOY_PROFILES)),--set reid.enabled=true --set reid.backend=$(REID_BACKEND),--set reid.enabled=false)
MODE_ARG := $(strip $(TRACKER_ARG) $(MAPPING_ARG) $(CLUSTER_ANALYTICS_ARG) $(REID_ARG))

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

# start kind, then install Scenescape with helm
# Tracker/mapping/cluster-analytics need their own image (load-all); tracker
# also has no use for the bundled demo cameras, since it replaces the Scene
# Controller entirely.
default: check-deploy-profiles install-deps clean-kind kind $(if $(filter tracker mapping cluster-analytics,$(DEPLOY_PROFILES)),load-all,load-core) $(if $(filter tracker,$(DEPLOY_PROFILES)),,video-source-up) install

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
	@CID=$$(docker ps -aq --filter "label=io.x-k8s.kind.cluster=kind"); \
	if [ -n "$$CID" ]; then \
	    docker update --restart=always $$CID; \
	else \
	    echo "WARNING: no kind container found, skipping --restart=always"; \
	fi

# remove the kind container
clean-kind: video-source-down
	kind delete cluster
	docker network rm kind || true

install-cert-manager:
	kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.18.2/cert-manager.yaml

# generate yaml pointing the "mediaserver" Service at the external video-source stack
VIDEOSOURCE_PORT?=8554
generate-mediaserver-yaml:
	mkdir -p setup
	cp template/mediaserver.template setup/mediaserver.yaml
	sed -e "s|{VIDEOSOURCE_IP}|$(VIDEOSOURCE_IP)|g" -e "s|{VIDEOSOURCE_PORT}|$(VIDEOSOURCE_PORT)|g" setup/mediaserver.yaml > setup/mediaserver.yaml.tmp && mv setup/mediaserver.yaml.tmp setup/mediaserver.yaml

# Deploys the "mediaserver" Service+EndpointSlice alongside the scenescape-chart,
# pointing it at the host running the per-scene video-source compose file(s)
# (sample_data/demo_scenes/<Scene>/compose.<scene>-video.yml).
.PHONY: mediaserver-up
mediaserver-up:
	@if [ -z "$(VIDEOSOURCE_IP)" ]; then \
	    echo "Set VIDEOSOURCE_IP=<ip of the host running sample_data/demo_scenes/<Scene>/compose.<scene>-video.yml>"; \
	    exit 1; \
	fi
	$(MAKE) generate-mediaserver-yaml
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -n $(NAMESPACE) -f setup/mediaserver.yaml

.PHONY: mediaserver-down
mediaserver-down:
	-kubectl delete -n $(NAMESPACE) -f setup/mediaserver.yaml

# Video source (mediamtx + per-scene ffmpeg loopers) for the kind all-in-one
# demo; not used by the "Scenescape Only" BYO-cluster flow (see
# kubernetes/README.md to point at a remote video-source host instead).
# Joins the kind cluster's own Docker network directly so its IP is reachable
# from cluster pods; dlsps pods are created dynamically in-cluster by
# kubeclient, so retail-video/queuing-video are not started here.
# Each scene owns its own private mediamtx (same "mediaserver" service name in
# both files); Compose merges them into one shared instance across -f flags.
VIDEO_SOURCE_COMPOSE_FILES := -f ../sample_data/demo_scenes/Retail/compose.retail-video.yml -f ../sample_data/demo_scenes/Queuing/compose.queuing-video.yml

.PHONY: video-source-up
video-source-up:
	$(MAKE) -C .. convert-dls-videos
	SECRETSDIR=$(WORKINGDIR)/manager/secrets SCENESCAPE_NETWORK=kind \
		docker compose --project-directory .. $(VIDEO_SOURCE_COMPOSE_FILES) up -d mediaserver retail-cams queuing-cams
	@CID=$$(docker compose --project-directory .. $(VIDEO_SOURCE_COMPOSE_FILES) ps -q mediaserver); \
	IP=$$(docker inspect -f '{{.NetworkSettings.Networks.kind.IPAddress}}' $$CID); \
	$(MAKE) mediaserver-up VIDEOSOURCE_IP=$$IP

.PHONY: video-source-down
video-source-down:
	-$(MAKE) mediaserver-down
	-SECRETSDIR=$(WORKINGDIR)/manager/secrets SCENESCAPE_NETWORK=kind \
		docker compose --project-directory .. $(VIDEO_SOURCE_COMPOSE_FILES) down

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
	$(MAKE) load-image IMAGE=$(TRACKERIMAGE)

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
	mkdir -p scenescape-chart/files/scene-controller
	cp -r ../dlstreamer-pipeline-server/user_scripts/gstplugins/* scenescape-chart/files/dlsps/
	cp ../dlstreamer-pipeline-server/mosquitto/mosquitto-secure.conf scenescape-chart/files/broker/mosquitto-secure.conf
	cp ../controller/config/tracker-config.json scenescape-chart/files/scene-controller/tracker-config.json
	cp ../controller/config/reid-config.json scenescape-chart/files/scene-controller/reid-config.json
	cp ../model_download/src/download_models.py scenescape-chart/files/model-download/download_models.py
	cp ../model_download/src/generate_model_config.py scenescape-chart/files/model-download/generate_model_config.py
	cp ../model_download/src/entrypoint-k8s.sh scenescape-chart/files/model-download/entrypoint-k8s.sh
	cp ../model_download/models.json scenescape-chart/files/model-download/models.json


.PHONY: check-deploy-profiles
check-deploy-profiles:
	@for profile in $(DEPLOY_PROFILES); do \
		case "$$profile" in \
		  controller|tracker|mapping|cluster-analytics|reid) ;; \
		  *) echo "Invalid DEPLOY_PROFILES token '$$profile'. Use any of: controller tracker mapping cluster-analytics reid."; exit 1 ;; \
		esac; \
	done
	@if [ -n "$(filter tracker,$(DEPLOY_PROFILES))" ] && [ -n "$(filter reid,$(DEPLOY_PROFILES))" ]; then \
		echo "DEPLOY_PROFILES cannot include both tracker and reid: ReID requires the Scene Controller, which Tracker replaces."; \
		exit 1; \
	fi

.PHONY: check-reid-backend
check-reid-backend:
	@case "$(REID_BACKEND)" in \
	  vdms|qdrant) ;; \
	  *) echo "Invalid REID_BACKEND '$(REID_BACKEND)'. Use vdms or qdrant."; exit 1 ;; \
	esac

# Uploads sample_data/demo_scenes/*.zip through the REST API, same client the root Makefile uses.
.PHONY: demo-scenes
demo-scenes:
	@VENV="../tools/upload_scenes/.venv"; \
	if [ ! -x "$$VENV/bin/pip" ]; then \
		rm -rf "$$VENV"; \
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
install: check-deploy-profiles check-reid-backend copy-files chart.yaml
	@VALUES_FILE=$$(mktemp); \
	trap 'rm -f "$$VALUES_FILE"' EXIT; \
	if [ -n "$(http_proxy)" ]; then \
		echo "httpProxy: \"$(http_proxy)\"" >> $$VALUES_FILE; \
	fi; \
	if [ -n "$(https_proxy)" ]; then \
		echo "httpsProxy: \"$(https_proxy)\"" >> $$VALUES_FILE; \
	fi; \
	if [ -n "$(no_proxy)" ]; then \
		echo "noProxy: \"$(no_proxy)\"" >> $$VALUES_FILE; \
	fi; \
	if [ -n "$${SUPASS}" ]; then \
		printf "supass: '%s'\n" "$$(printf '%s' "$${SUPASS}" | sed "s/'/''/g")" >> $$VALUES_FILE; \
	fi; \
	if [ -n "$${PGPASS}" ]; then \
		printf "pgserver:\n  password: '%s'\n" "$$(printf '%s' "$${PGPASS}" | sed "s/'/''/g")" >> $$VALUES_FILE; \
	fi; \
	ALLOWED_HOSTS_ARG=""; \
	if [ -n "$${SCENESCAPE_ALLOWED_HOSTS}" ]; then \
		ALLOWED_HOSTS_ARG="--set web.allowedHosts=$${SCENESCAPE_ALLOWED_HOSTS}"; \
	fi; \
	REPOSITORY_ARG="--set repository=$(REGISTRY)"; \
	helm upgrade $(RELEASE) --install scenescape-chart/ -n $(NAMESPACE) --create-namespace --timeout $(INSTALL_TIMEOUT) $${REPOSITORY_ARG} $${ALLOWED_HOSTS_ARG} $(MODE_ARG) --values "$$VALUES_FILE" $(TEST_FLAGS);
	kubectl rollout status deployment/$(RELEASE)-web-dep -n $(NAMESPACE) --timeout=$(INSTALL_TIMEOUT)
	@if [ -z "$(strip $(filter tracker,$(DEPLOY_PROFILES)))" ]; then \
		$(MAKE) demo-scenes; \
	fi

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
	@if [ -n "$(strip $(filter tracker mapping cluster-analytics,$(DEPLOY_PROFILES)))" ]; then \
		$(MAKE) rebuild-all; \
	else \
		$(MAKE) rebuild-core; \
	fi

rebuild-core: uninstall delete-namespace build-core install

rebuild-all: uninstall delete-namespace build-all install
