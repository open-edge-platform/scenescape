#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Nokia
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# ==============================================================================
# K3s + NVIDIA GPU Bootstrap
# Ubuntu 22.04 & 24.04 | NVIDIA Driver 580
# DeepStream + Triton + SceneScape ready
# ==============================================================================

TARGET_DRIVER_SERIES="${NVIDIA_DRIVER_SERIES:-580}"
K3S_VERSION="${K3S_VERSION:-v1.32.9+k3s1}"
DEVICE_PLUGIN_VERSION="${DEVICE_PLUGIN_VERSION:-v0.14.5}"

INFO='\033[0;34m[INFO]\033[0m'
OK='\033[0;32m[OK]\033[0m'
ACTION='\033[0;33m[ACTION]\033[0m'
ERROR='\033[0;31m[ERROR]\033[0m'
log() { echo -e "$1 $2"; }

# ---------------- ROOT CHECK ----------------
if [[ $EUID -ne 0 ]]; then
  log "$ERROR" "Run as root: sudo bash install.sh"
  exit 1
fi

# ---------------- OS CHECK ------------------
. /etc/os-release
if [[ "$ID" != "ubuntu" || ( "$VERSION_ID" != "22.04" && "$VERSION_ID" != "24.04" ) ]]; then
  log "$ERROR" "Ubuntu 22.04 or 24.04 required"
  exit 1
fi
log "$INFO" "OS verified: Ubuntu $VERSION_ID"

# ---------------- HELPERS -------------------
wait_for_apt() {
  while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
    sleep 2
  done
}

apt_install_retry() {
  local max_attempts=3
  local attempt=1
  while [ $attempt -le $max_attempts ]; do
    if apt-get install -y --fix-missing --allow-downgrades "$@" 2>&1 | tee /tmp/apt-install.log; then
      return 0
    fi
    log "$ACTION" "Retry $attempt/$max_attempts failed, waiting and trying again..."
    apt-get clean
    sleep 10
    apt-get update -y --fix-missing || true
    attempt=$((attempt + 1))
  done
  log "$ERROR" "Failed to install packages after $max_attempts attempts"
  return 1
}

wait_for_k3s() {
  for i in {1..30}; do
    if KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl get nodes &>/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

unset KUBECONFIG

# ---------------- BASE PACKAGES -------------
log "$ACTION" "Installing base dependencies..."
wait_for_apt
apt-get clean
apt-get update -y --fix-missing || log "$ERROR" "apt-get update failed, continuing..."
apt_install_retry \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  software-properties-common \
  apt-transport-https || {
  log "$ERROR" "Critical base packages failed to install"
  exit 1
}

# Install snapd separately (optional)
log "$ACTION" "Installing snapd..."
apt_install_retry snapd || log "$ERROR" "snapd installation failed, continuing without it..."

# ---------------- NOKIA CA CERTIFICATES -----
# Nokia internal registries (registry-central-reg.ndac.dyn.nesc.nokia.net) use
# Nokia's internal PKI. Both Docker and k3s containerd must trust these CAs.
# Bundled certs are in installer/certs/ (preferred). Falls back to downloading
# from Nokia PKI if bundled certs are not found.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLED_CERTS_DIR="${SCRIPT_DIR}/certs"
NOKIA_ROOT_CA="/usr/local/share/ca-certificates/nokia-internal-root-ca.crt"
NOKIA_SUB_CA="/usr/local/share/ca-certificates/nokia-internal-subca07.crt"
NOKIA_REGISTRY="registry-central-reg.ndac.dyn.nesc.nokia.net"

anyCertCopied="false"

if [ -f "$NOKIA_ROOT_CA" ] && [ -f "$NOKIA_SUB_CA" ]; then
  log "$OK" "Nokia CA certificates already installed."
else
  log "$ACTION" "Installing Nokia CA certificates..."

  if [ -f "${BUNDLED_CERTS_DIR}/NokiaInternalRootCA.crt" ] && \
     [ -f "${BUNDLED_CERTS_DIR}/NokiaInternalSubCA07.crt" ]; then
    # Use bundled certs (works in air-gapped environments)
    log "$INFO" "Using bundled certificates from ${BUNDLED_CERTS_DIR}"
    cp "${BUNDLED_CERTS_DIR}/NokiaInternalRootCA.crt" "$NOKIA_ROOT_CA"
    cp "${BUNDLED_CERTS_DIR}/NokiaInternalSubCA07.crt" "$NOKIA_SUB_CA"
    anyCertCopied="true"
  elif curl -sf --connect-timeout 10 "http://pki.net.nokia.com/PKI/NokiaInternalRootCA.crt" \
       -o /tmp/nokia-rootca.der 2>/dev/null; then
    # Fallback: download from Nokia PKI
    log "$INFO" "Bundled certs not found, downloading from Nokia PKI..."
    openssl x509 -in /tmp/nokia-rootca.der -inform DER -out "$NOKIA_ROOT_CA" 2>/dev/null
    curl -sf "http://pki.net.nokia.com/PKI/NokiaInternalSubCA07(1).crt" -o /tmp/nokia-subca.der
    openssl x509 -in /tmp/nokia-subca.der -inform DER -out "$NOKIA_SUB_CA" 2>/dev/null
    rm -f /tmp/nokia-rootca.der /tmp/nokia-subca.der
    anyCertCopied="true"
  else
    log "$ACTION" "Nokia PKI unreachable and no bundled certs — skipping CA install."
  fi

  if [ "${anyCertCopied}" = "true" ]; then
    update-ca-certificates

    # Docker trust for Nokia registry
    mkdir -p "/etc/docker/certs.d/${NOKIA_REGISTRY}"
    cp "$NOKIA_ROOT_CA" "/etc/docker/certs.d/${NOKIA_REGISTRY}/ca.crt"
    cp "$NOKIA_SUB_CA" "/etc/docker/certs.d/${NOKIA_REGISTRY}/subca.crt"

    # Combined CA bundle for k3s containerd (used in registries.yaml)
    mkdir -p /etc/rancher/k3s
    cat "$NOKIA_ROOT_CA" "$NOKIA_SUB_CA" > /etc/rancher/k3s/nokia-ca.pem

    log "$OK" "Nokia CA certificates installed."
  fi
fi

# ---------------- DOCKER --------------------
if ! command -v docker &>/dev/null; then
  log "$ACTION" "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker --now
else
  log "$OK" "Docker already installed."
fi

# ---------------- DOCKER BUILDX -------------
if ! docker buildx version &>/dev/null; then
  log "$ACTION" "Installing Docker Buildx..."
  mkdir -p /usr/libexec/docker/cli-plugins
  curl -SL https://github.com/docker/buildx/releases/latest/download/buildx-linux-amd64 \
    -o /usr/libexec/docker/cli-plugins/docker-buildx
  chmod +x /usr/libexec/docker/cli-plugins/docker-buildx
fi

# Fix Docker buildx/build directory ownership for non-root builds.
# install.sh runs as root, which creates root-owned files in ~/.docker/
# and build/. Subsequent non-root `make deploy-all-mxcp` fails with
# "permission denied" on these files.
TARGET_USER_DOCKER="${SUDO_USER:-$(whoami)}"
TARGET_HOME_DOCKER="$(getent passwd "$TARGET_USER_DOCKER" | cut -d: -f6)"
if [ -d "$TARGET_HOME_DOCKER/.docker" ]; then
  chown -R "$TARGET_USER_DOCKER:$TARGET_USER_DOCKER" "$TARGET_HOME_DOCKER/.docker"
  log "$OK" "Fixed .docker ownership for $TARGET_USER_DOCKER"
fi
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_BUILD_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/build"
if [ -d "$REPO_BUILD_DIR" ]; then
  chown -R "$TARGET_USER_DOCKER:$TARGET_USER_DOCKER" "$REPO_BUILD_DIR"
  log "$OK" "Fixed build/ ownership for $TARGET_USER_DOCKER"
fi

# ---------------- K3s -----------------------
if ! command -v k3s &>/dev/null; then
  log "$ACTION" "Installing K3s..."
  export INSTALL_K3S_VERSION="$K3S_VERSION"
  curl -sfL https://get.k3s.io | sh -s - server \
    --write-kubeconfig-mode 600 \
    --disable traefik \
    --disable servicelb
  systemctl enable k3s --now
else
  log "$OK" "K3s already installed."
fi

# ---------------- K3S NOKIA REGISTRY ---------
# Configure k3s containerd to trust Nokia registry (requires Nokia CA from above)
if [ -f /etc/rancher/k3s/nokia-ca.pem ] && [ ! -f /etc/rancher/k3s/registries.yaml ]; then
  log "$ACTION" "Configuring k3s containerd for Nokia registry..."
  cat > /etc/rancher/k3s/registries.yaml << REGEOF
mirrors:
  "${NOKIA_REGISTRY}":
    endpoint:
      - "https://${NOKIA_REGISTRY}"

configs:
  "${NOKIA_REGISTRY}":
    tls:
      ca_file: /etc/rancher/k3s/nokia-ca.pem
REGEOF
  log "$OK" "k3s registry config created."
  systemctl restart k3s || log "$ERROR" "k3s restart failed after registry config"
  sleep 5
elif [ -f /etc/rancher/k3s/registries.yaml ]; then
  log "$OK" "k3s registry config already exists."
fi

# ---------------- FIX KUBECTL ---------------
if [[ -L /usr/local/bin/kubectl ]]; then
  rm -f /usr/local/bin/kubectl
fi

if ! command -v kubectl &>/dev/null; then
  log "$ACTION" "Installing kubectl..."
  if command -v snap &>/dev/null; then
    snap install kubectl --classic || {
      log "$ACTION" "snap install failed, trying direct download..."
      curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
      chmod +x kubectl
      mv kubectl /usr/local/bin/
    }
  else
    log "$ACTION" "snap not available, using direct download..."
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    chmod +x kubectl
    mv kubectl /usr/local/bin/
  fi
else
  log "$OK" "kubectl already installed."
fi

# ---------------- HELM ----------------------
if ! command -v helm &>/dev/null; then
  log "$ACTION" "Installing Helm..."
  curl -sfL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
else
  log "$OK" "Helm already installed."
fi

# ---------------- YQ -------------------------
if ! command -v yq &>/dev/null; then
  log "$ACTION" "Installing yq..."
  YQ_VERSION=$(curl -s https://api.github.com/repos/mikefarah/yq/releases/latest 2>/dev/null | grep tag_name | cut -d'"' -f4 || echo "v4.44.1")
  curl -fsSL "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_amd64" -o /usr/local/bin/yq
  chmod +x /usr/local/bin/yq
  log "$OK" "yq ${YQ_VERSION} installed."
else
  log "$OK" "yq already installed."
fi

# ---------------- NVIDIA DRIVER -------------
if ! nvidia-smi &>/dev/null; then
  log "$ACTION" "Installing NVIDIA driver $TARGET_DRIVER_SERIES..."
  add-apt-repository -y ppa:graphics-drivers/ppa
  wait_for_apt
  apt-get update -y || log "$ERROR" "apt-get update failed, continuing..."
  apt_install_retry nvidia-driver-$TARGET_DRIVER_SERIES || {
    log "$ERROR" "Failed to install NVIDIA driver"
    exit 1
  }
  log "$ERROR" "REBOOT REQUIRED after script completes"
else
  log "$OK" "NVIDIA driver already installed."
fi

# ---------------- NVIDIA CONTAINER TOOLKIT --
log "$ACTION" "Installing NVIDIA Container Toolkit..."

rm -f /etc/apt/sources.list.d/nvidia*
rm -f /usr/share/keyrings/nvidia*

# Get distribution - use ubuntu22.04 repo for ubuntu24.04 (compatible)
distribution=$(. /etc/os-release; echo ${ID}${VERSION_ID})
if [[ "$distribution" == "ubuntu24.04" ]]; then
  distribution="ubuntu22.04"
  log "$INFO" "Using ubuntu22.04 repository for Ubuntu 24.04 compatibility"
fi

# Download GPG key with retry
for i in {1..3}; do
  if curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit.gpg; then
    break
  fi
  log "$ACTION" "GPG key download attempt $i failed, retrying..."
  sleep 5
done

# Setup repository with retry
for i in {1..3}; do
  if curl -fsSL https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit.gpg] https://#g' \
    | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list; then
    log "$OK" "NVIDIA repository configured successfully"
    break
  fi
  log "$ACTION" "Repository setup attempt $i failed, retrying..."
  sleep 5
done

wait_for_apt
apt-get clean
rm -rf /var/lib/apt/lists/*
apt-get update -y --fix-missing || log "$ERROR" "apt-get update failed, continuing..."
apt_install_retry nvidia-container-toolkit || {
  log "$ERROR" "Failed to install nvidia-container-toolkit - may need manual installation"
  log "$ERROR" "You can try: sudo apt-get install -y --fix-missing nvidia-container-toolkit"
  # Don't exit here - continue with what we have
}

# ---------------- CONTAINERD CONFIG ---------
if command -v nvidia-ctk &>/dev/null; then
  log "$ACTION" "Configuring NVIDIA runtime..."
  nvidia-ctk runtime configure --runtime=containerd || log "$ERROR" "nvidia-ctk configure failed, continuing..."
  systemctl restart containerd || log "$ERROR" "containerd restart failed, continuing..."
  
  # Configure K3s containerd for NVIDIA runtime
  log "$ACTION" "Configuring K3s NVIDIA runtime..."
  mkdir -p /var/lib/rancher/k3s/agent/etc/containerd/config.toml.d/
  cat > /var/lib/rancher/k3s/agent/etc/containerd/config.toml.d/nvidia.toml << 'EOF'
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]
  privileged_without_host_devices = false
  runtime_engine = ""
  runtime_root = ""
  runtime_type = "io.containerd.runc.v2"
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia.options]
    BinaryName = "/usr/bin/nvidia-container-runtime"
EOF
  
  systemctl restart k3s || log "$ERROR" "k3s restart failed, continuing..."
  sleep 5
else
  log "$ERROR" "nvidia-ctk not found - skipping runtime configuration"
fi

# ---------------- KUBECONFIG SETUP ----------
log "$ACTION" "Configuring kubeconfig..."
TARGET_USER="${SUDO_USER:-root}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"

mkdir -p "$TARGET_HOME/.kube"
cp /etc/rancher/k3s/k3s.yaml "$TARGET_HOME/.kube/config"
chown -R "$TARGET_USER:$TARGET_USER" "$TARGET_HOME/.kube"

grep -q 'KUBECONFIG=.*/.kube/config' "$TARGET_HOME/.bashrc" 2>/dev/null || \
  echo 'export KUBECONFIG=$HOME/.kube/config' >> "$TARGET_HOME/.bashrc"

# ---------------- NVIDIA DEVICE PLUGIN ------
log "$ACTION" "Waiting for Kubernetes API..."
sleep 10

# Create NVIDIA RuntimeClass
log "$ACTION" "Creating NVIDIA RuntimeClass..."
cat <<'EOF' | k3s kubectl apply -f - || log "$ERROR" "Failed to create RuntimeClass"
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: nvidia
handler: nvidia
EOF

# GPU_REPLICAS determines how many virtual GPUs are created via NVIDIA time-slicing.
# Override: sudo GPU_REPLICAS=30 bash install.sh
GPU_REPLICAS="${GPU_REPLICAS:-20}"

log "$ACTION" "Configuring GPU time-slicing (${GPU_REPLICAS} replicas)..."
cat <<EOF | k3s kubectl apply -f - || log "$ERROR" "Failed to create time-slicing config"
apiVersion: v1
kind: ConfigMap
metadata:
  name: nvidia-device-plugin-config
  namespace: kube-system
data:
  config: |
    version: v1
    sharing:
      timeSlicing:
        resources:
          - name: nvidia.com/gpu
            replicas: ${GPU_REPLICAS}
EOF

# Deploy NVIDIA Device Plugin with RuntimeClass and Time-Slicing
if ! k3s kubectl get ds -n kube-system nvidia-device-plugin-daemonset 2>/dev/null | grep -q nvidia-device-plugin; then
  log "$ACTION" "Deploying NVIDIA Device Plugin with GPU time-slicing..."
  cat <<EOF | k3s kubectl apply -f - || log "$ERROR" "Failed to deploy device plugin"
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-device-plugin-daemonset
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: nvidia-device-plugin-ds
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        name: nvidia-device-plugin-ds
    spec:
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      priorityClassName: "system-node-critical"
      runtimeClassName: nvidia
      containers:
      - image: nvcr.io/nvidia/k8s-device-plugin:${DEVICE_PLUGIN_VERSION}
        name: nvidia-device-plugin-ctr
        args:
          - "--config-file=/etc/nvidia/config.yaml"
        env:
          - name: FAIL_ON_INIT_ERROR
            value: "false"
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
        volumeMounts:
        - name: device-plugin
          mountPath: /var/lib/kubelet/device-plugins
        - name: config
          mountPath: /etc/nvidia
      volumes:
      - name: device-plugin
        hostPath:
          path: /var/lib/kubelet/device-plugins
      - name: config
        configMap:
          name: nvidia-device-plugin-config
          items:
          - key: config
            path: config.yaml
EOF
  log "$OK" "NVIDIA Device Plugin deployed"
else
  log "$OK" "NVIDIA Device Plugin already running."
fi

# Wait for device plugin to register
sleep 10

# ---------------- FINAL VERIFICATION --------
echo
log "$INFO" "===== FINAL VERIFICATION ====="

if command -v nvidia-smi &>/dev/null; then
  if nvidia-smi &>/dev/null; then
    log "$OK" "NVIDIA Driver operational"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
  else
    log "$ERROR" "nvidia-smi failed - driver may need reboot"
  fi
else
  log "$ERROR" "nvidia-smi not available - NVIDIA driver installation pending or needs reboot"
fi

log "$ACTION" "Waiting for Kubernetes API..."
if wait_for_k3s; then
  log "$OK" "Kubernetes API ready"
  KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl get nodes || log "$ERROR" "kubectl get nodes failed"
  
  echo
  log "$ACTION" "Checking GPU resources in Kubernetes..."
  GPU_COUNT=$(KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl get nodes -o jsonpath='{.items[0].status.capacity.nvidia\.com/gpu}' 2>/dev/null || echo "0")
  
  if [ "$GPU_COUNT" != "0" ] && [ -n "$GPU_COUNT" ]; then
    log "$OK" "GPU detected in Kubernetes: $GPU_COUNT GPU(s) available"
    if [ "$GPU_COUNT" = "24" ]; then
      log "$OK" "GPU time-slicing enabled: 1 physical GPU → $GPU_COUNT virtual GPUs"
    fi
    KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl get nodes -o custom-columns=NODE:.metadata.name,GPU:.status.capacity."nvidia\.com/gpu" || true
  else
    log "$ERROR" "No GPU resources detected in Kubernetes"
    log "$INFO" "Checking device plugin status..."
    KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl get pods -n kube-system -l name=nvidia-device-plugin-ds || true
    log "$INFO" "If device plugin is running but GPU not detected, reboot may be required"
  fi
else
  log "$ERROR" "Kubernetes API not ready yet (retry: kubectl get nodes)"
fi

echo
log "$OK" "Installation complete! 🚀"
if ! nvidia-smi &>/dev/null; then
  echo
  log "$ERROR" "⚠️  REBOOT REQUIRED to activate NVIDIA driver"
  log "$INFO" "After reboot, run this script again to verify GPU detection"
  log "$INFO" "Verify with: nvidia-smi && kubectl get nodes -o custom-columns=NODE:.metadata.name,GPU:.status.capacity.\"nvidia\\.com/gpu\""
fi

