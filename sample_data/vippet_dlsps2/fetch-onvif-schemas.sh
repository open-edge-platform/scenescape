#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Downloads, unmodified, the ONVIF device/media WSDLs and the XML schemas they
# import, for the virtual ONVIF cameras (compose.onvif-cams.yml). onvif-server
# loads them at startup; its HTTP client cannot reach them through proxies
# that only allow CONNECT tunnels, so they are served from this cache instead.
#
# Usage: fetch-onvif-schemas.sh <output directory>
# Files are stored as <output directory>/<host>/<path>. Existing files are kept.

set -euo pipefail

OUT_DIR=${1:?usage: $0 <output directory>}

SCHEMA_URLS=(
  https://www.onvif.org/ver10/device/wsdl/devicemgmt.wsdl
  https://www.onvif.org/ver10/media/wsdl/media.wsdl
  https://www.onvif.org/ver10/schema/onvif.xsd
  https://www.onvif.org/ver10/schema/common.xsd
  https://www.w3.org/2003/05/soap-envelope
  https://www.w3.org/2004/08/xop/include
  https://www.w3.org/2005/05/xmlmime
  http://www.w3.org/2001/xml.xsd
  http://www.w3.org/2009/01/xml.xsd
  http://www.w3.org/2005/08/addressing/ws-addr.xsd
  http://docs.oasis-open.org/wsn/b-2.xsd
  http://docs.oasis-open.org/wsn/t-1.xsd
  http://docs.oasis-open.org/wsrf/bf-2.xsd
)

for url in "${SCHEMA_URLS[@]}"; do
  target="${OUT_DIR}/${url#*://}"
  if [[ -s "${target}" ]]; then
    continue
  fi
  mkdir -p "$(dirname "${target}")"
  echo "Downloading ${url}"
  if ! curl --fail --silent --show-error --location --max-time 60 \
      --output "${target}.tmp" "${url}"; then
    rm -f "${target}.tmp"
    echo "Error: failed to download ${url} (check network / proxy settings)." >&2
    exit 1
  fi
  mv "${target}.tmp" "${target}"
done
