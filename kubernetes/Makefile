# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

IMAGE=scenescape-manager
BROKERIMAGE=scenescape-broker
CAMCALIBIMAGE=scenescape-camcalibration
CAMERAIMAGE=scenescape-percebro
CONTROLLERIMAGE=scenescape-controller
VERSION:=$(shell cat ../version.txt)
NAMESPACE=scenescape
WORKINGDIR=$(shell dirname $(shell pwd))
ORGANIZATION?=
VALIDATION=
VALIDATION_FLAG=

ifeq ($(VALIDATION), 1)
    VALIDATION_FLAG=--set tests.enabled=true
endif

KINDREG=kind-registry
KINDREGPORT=5001
# Uncomment and set HOSTDIR if you want to access the persistent volumes on the host (root ownership)
# HOSTDIR=$(WORKINGDIR)/kind-storage

CERTPASS=$(shell openssl rand -base64 33)
REGISTRY=localhost:$(KINDREGPORT)

RELEASE=scenescape-release-1
FORCE_VAAPI?=0

# ITEP constants
# REGISTRY=registry.test-public-maestro.edgeorch.net/scenescape
CHARTREPO=registry.test-public-maestro.edgeorch.net/chartrepo/scenescape
# HELM_REPO_USERNAME=<harbor_username>
# HELM_REPO_PASSWORD=<harbor_cli_secret>

# start kind, then install SceneScape with helm
default: install-deps clean-kind kind build-all-tests install

# publish to ITEP by building, packaging, then pushing
# must set appropriate REGISTRY, CHARTREPO, HELM_REPO_USERNAME and HELM_REPO_PASSWORD constants
build-and-package-all: build-all install-package-deps package

# build init-images, scenescape images and push everything to a registry, then generate Chart.yaml
build-all-tests: build-all push-test-images
build-all: build build-init-images push-init-images push chart.yaml

kind: generate-kind-yaml start-kind

# remove everything Kubernetes related from your machine
clean-all: clean-kind clean-kind-registry

# dependency installation (requires sudo) for kind, kubectl, k9s (optional), helm
# NO SUDO: alternatively, if your user does not have sudo access:
# 1. comment out the sudo commands for kind, kubectl, k9s and helm
# 2. move the kind, kubectl, k9s and helm binaries to your PATH manually from /tmp, e.g. to ~/.local/bin, like so:
# mv /tmp/kind /tmp/kubectl /tmp/k9s /tmp/helm ~/.local/bin
install-deps:
	@if [ -z "$(shell which kind)" ] ; then \
	    curl -Lo /tmp/kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64 ; \
	    chmod +x /tmp/kind ; \
	    sudo mv /tmp/kind /usr/local/bin/kind ; \
	    echo "kind installed" ; \
	fi
	@if [ -z "$(shell which kubectl)" ] ; then \
	    curl -Lo /tmp/kubectl https://dl.k8s.io/release/v1.28.1/bin/linux/amd64/kubectl ; \
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
	sed -e "s|{KINDREGPORT}|$(KINDREGPORT)|g" template/kind.template > setup/kind.yaml
	sed -e "s|{KINDREG}|$(KINDREG)|g" -e "s|{KINDREGPORT}|$(KINDREGPORT)|g" \
	template/kind-config.template > setup/kind-config.yaml
	@if [ -z "$(HOSTDIR)" ] ; then \
	    sed -n -i '/{HOSTDIR}/q;p' setup/kind-config.yaml; \
	else \
	    sed -e "s|{HOSTDIR}|$(HOSTDIR)|g" -i setup/kind-config.yaml; \
	    echo "HOSTDIR is set. Kind will mount $(HOSTDIR) into container for persistent volumes."; \
	fi

# run a test cluster in a kind container. Requires the kind binary
start-kind:
	if [ "$(shell docker inspect -f '{{.State.Running}}' "$(KINDREG)" 2>/dev/null || true)" != 'true' ]; then \
	    docker run -d --restart=always -p "127.0.0.1:$(KINDREGPORT):5000" --name "$(KINDREG)" registry:2; \
	fi
	NO_PROXY=$(NO_PROXY),$(KINDREG) kind create cluster --config ./setup/kind-config.yaml || true
	docker network connect "kind" "$(KINDREG)" || true
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

# remove the kind container
clean-kind:
	kind delete cluster
	docker network disconnect kind $(KINDREG) || true
	docker network rm kind || true

# remove the kind registry and its volume
clean-kind-registry:
	docker stop $(KINDREG) || true
	docker rm --volumes $(KINDREG) || true

# build scenescape docker images, download models for init-models
# note, will make unneeded secrets in secrets/ as well
build:
	make -C .. CERTPASS=$(CERTPASS) FORCE_VAAPI=$(FORCE_VAAPI)

push:
	docker tag $(ORGANIZATION)$(IMAGE):$(VERSION) $(REGISTRY)/$(IMAGE):$(VERSION)
	docker push $(REGISTRY)/$(IMAGE):$(VERSION)
	docker tag $(ORGANIZATION)$(BROKERIMAGE):$(VERSION) $(REGISTRY)/$(BROKERIMAGE):$(VERSION)
	docker push $(REGISTRY)/$(BROKERIMAGE):$(VERSION)
	docker tag $(ORGANIZATION)$(CAMCALIBIMAGE):$(VERSION) $(REGISTRY)/$(CAMCALIBIMAGE):$(VERSION)
	docker push $(REGISTRY)/$(CAMCALIBIMAGE):$(VERSION)
	docker tag $(ORGANIZATION)$(CAMERAIMAGE):$(VERSION) $(REGISTRY)/$(CAMERAIMAGE):$(VERSION)
	docker push $(REGISTRY)/$(CAMERAIMAGE):$(VERSION)
	docker tag $(ORGANIZATION)$(CONTROLLERIMAGE):$(VERSION) $(REGISTRY)/$(CONTROLLERIMAGE):$(VERSION)
	docker push $(REGISTRY)/$(CONTROLLERIMAGE):$(VERSION)

# build init images
build-init-images:
	cp $(shell which kubectl) ../.
	cd .. && docker build -f kubernetes/init-images/Dockerfile-secrets . -t init-secrets:$(VERSION) \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy)
	rm ../kubectl
	cd .. && docker build -f kubernetes/init-images/Dockerfile-models . -t init-models:$(VERSION) \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy)
	cd .. && docker build -f kubernetes/init-images/Dockerfile-tests . -t init-tests:$(VERSION) \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy)

# build scenescape-sources image
build-sources-image:
	make -C .. build-sources-image

push-init-images:
	docker tag $(ORGANIZATION)init-secrets:$(VERSION) $(REGISTRY)/init-secrets:$(VERSION)
	docker tag $(ORGANIZATION)init-models:$(VERSION) $(REGISTRY)/init-models:$(VERSION)
	docker push $(REGISTRY)/init-secrets:$(VERSION)
	docker push $(REGISTRY)/init-models:$(VERSION)

push-test-images:
	docker tag init-tests:$(VERSION) $(REGISTRY)/init-tests:$(VERSION)
	docker push $(REGISTRY)/init-tests:$(VERSION)

push-sources-image:
	docker tag $(ORGANIZATION)scenescape-sources:$(VERSION) $(REGISTRY)/scenescape-sources:$(VERSION)
	docker push $(REGISTRY)/scenescape-sources:$(VERSION)

# generate Chart.yaml with appropriate version.txt
chart.yaml:
	sed -e "s|{VERSION}|$(VERSION)|g" template/Chart.template > scenescape-chart/Chart.yaml

# packaging dependencies
install-package-deps:
	helm plugin install https://github.com/chartmuseum/helm-push || true
	helm repo add itep_harbor https://$(CHARTREPO)

# packages and pushes the helm chart
# must set HELM_REPO_USERNAME and HELM_REPO_PASSWORD variables
package:
	PACKAGE=$$(helm package scenescape-chart/ | awk '{print $$NF}'); \
	helm cm-push $$PACKAGE itep_harbor -u=$(HELM_REPO_USERNAME) -p=$(HELM_REPO_PASSWORD); \
	rm $$PACKAGE

# Query what's in the registry (local)
list-registry:
	curl -X GET http://$(REGISTRY)/v2/_catalog

# to test template rendering
# helm template -s templates/ingress.yaml kubernetes/scenescape-chart/
# helm install scenescape-release-1 kubernetes/scenescape-chart/ --dry-run --debug
install:
	helm install $(RELEASE) scenescape-chart/ -n $(NAMESPACE) --create-namespace $(VALIDATION_FLAG)

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
rebuild: uninstall delete-namespace build-all-tests install

# validation build (blocks until scenescape is ready)
build-validation: delete-namespace build-all-tests install wait-for-ready
