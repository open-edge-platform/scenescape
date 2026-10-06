#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Download Smart Intersection sample videos for the map-autocalib spike.
# Reads proxy from GNOME system settings (or APT conf) when env proxies are
# unset / point at a broken local sandbox forwarder.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
OUT_DIR="${1:-${SCRIPT_DIR}/fixtures/videos}"
VIDEO_BRANCH="${VIDEO_BRANCH:-main}"
VIDEO_URL="https://github.com/open-edge-platform/edge-ai-resources/raw/refs/heads/${VIDEO_BRANCH}/videos"
VIDEOS=(1122east_h264.ts 1122west_h264.ts 1122north_h264.ts 1122south_h264.ts)

_is_local_forwarder() {
  case "${1:-}" in
    *127.0.0.1*|*localhost*) return 0 ;;
    *) return 1 ;;
  esac
}

_apply_system_proxy() {
  local mode host_http port_http host_https port_https
  if command -v gsettings >/dev/null 2>&1; then
    mode=$(gsettings get org.gnome.system.proxy mode 2>/dev/null || true)
    mode=${mode//\'/}
    if [[ "${mode}" == "manual" || "${mode}" == "auto" ]]; then
      host_http=$(gsettings get org.gnome.system.proxy.http host 2>/dev/null | tr -d "'")
      port_http=$(gsettings get org.gnome.system.proxy.http port 2>/dev/null | tr -d "'")
      host_https=$(gsettings get org.gnome.system.proxy.https host 2>/dev/null | tr -d "'")
      port_https=$(gsettings get org.gnome.system.proxy.https port 2>/dev/null | tr -d "'")
      if [[ -n "${host_http}" && "${host_http}" != "''" && -n "${port_http}" ]]; then
        export http_proxy="http://${host_http}:${port_http}"
        export HTTP_PROXY="${http_proxy}"
      fi
      if [[ -n "${host_https}" && "${host_https}" != "''" && -n "${port_https}" ]]; then
        export https_proxy="http://${host_https}:${port_https}"
        export HTTPS_PROXY="${https_proxy}"
      elif [[ -n "${http_proxy:-}" ]]; then
        export https_proxy="${http_proxy}"
        export HTTPS_PROXY="${https_proxy}"
      fi
    fi
  fi

  # Fallback: APT proxy lines (Intel DMZ layout uses 911/912).
  if [[ -z "${http_proxy:-}" ]] && [[ -f /etc/apt/apt.conf ]]; then
    local apt_http apt_https
    apt_http=$(grep -oE 'Acquire::http::Proxy[[:space:]]+"[^"]+"' /etc/apt/apt.conf 2>/dev/null \
      | head -1 | sed -E 's/.*"([^"]+)".*/\1/') || true
    apt_https=$(grep -oE 'Acquire::https::Proxy[[:space:]]+"[^"]+"' /etc/apt/apt.conf 2>/dev/null \
      | head -1 | sed -E 's/.*"([^"]+)".*/\1/') || true
    [[ -n "${apt_http}" ]] && export http_proxy="${apt_http}" HTTP_PROXY="${apt_http}"
    [[ -n "${apt_https}" ]] && export https_proxy="${apt_https}" HTTPS_PROXY="${apt_https}"
  fi

  export NO_PROXY="${NO_PROXY:-127.0.0.1,::1,localhost}"
  export no_proxy="${NO_PROXY}"
}

# Prefer real corporate proxy over Cursor sandbox local forwarders when those fail.
if [[ -z "${http_proxy:-}${HTTP_PROXY:-}" ]] \
  || _is_local_forwarder "${http_proxy:-${HTTP_PROXY:-}}"; then
  _apply_system_proxy
fi

echo "Using http_proxy=${http_proxy:-<none>} https_proxy=${https_proxy:-<none>}"
mkdir -p "${OUT_DIR}"

for video in "${VIDEOS[@]}"; do
  dest="${OUT_DIR}/${video}"
  if [[ -s "${dest}" ]]; then
    echo "Already present: ${dest}"
    continue
  fi
  echo "Downloading ${video} ..."
  curl -L --fail --connect-timeout 30 --max-time 600 \
    -o "${dest}.partial" "${VIDEO_URL}/${video}"
  mv "${dest}.partial" "${dest}"
done

echo "Done. Videos in ${OUT_DIR}"
