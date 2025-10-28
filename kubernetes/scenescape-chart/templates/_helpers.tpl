# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

{{- define "proxy_envs" }}
- name: HTTP_PROXY
  value: {{ .Values.httpProxy }}
- name: HTTPS_PROXY
  value: {{ .Values.httpsProxy }}
- name: NO_PROXY
  value: {{ .Values.noProxy }}
- name: http_proxy
  value: {{ .Values.httpProxy }}
- name: https_proxy
  value: {{ .Values.httpsProxy }}
- name: no_proxy
  value: {{ .Values.noProxy }}
{{- end }}

{{- define "defaultPodSecurityContext" }}
runAsUser: 1000
runAsGroup: 1000
{{- end }}

{{- define "defaultContainerSecurityContext" }}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop:
    - ALL
{{- end }}
