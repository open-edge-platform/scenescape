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

{{- define "reid.backend" -}}
{{- $backend := .Values.reid.backend | default "vdms" -}}
{{- if not (has $backend (list "vdms" "qdrant")) -}}
{{- fail (printf "reid.backend must be 'vdms' or 'qdrant', got '%s'" $backend) -}}
{{- end -}}
{{- $backend -}}
{{- end -}}

{{- define "certs_volume" }}
- name: certs
  projected:
    sources:
    - secret:
        name: {{ .Release.Name }}-web-tls
        items:
        - key: tls.crt
          path: scenescape-web.crt
        - key: tls.key
          path: scenescape-web.key
    - secret:
        name: {{ .Release.Name }}-broker-tls
        items:
        - key: tls.crt
          path: scenescape-broker.crt
        - key: tls.key
          path: scenescape-broker.key
    {{- if .Values.reid.enabled }}
    - secret:
        name: {{ .Release.Name }}-reid-s-tls
        items:
        - key: tls.key
          path: scenescape-reid-s.key
        - key: tls.crt
          path: scenescape-reid-s.crt
    - secret:
        name: {{ .Release.Name }}-reid-c-tls
        items:
        - key: tls.key
          path: scenescape-reid.key
        - key: tls.crt
          path: scenescape-reid.crt
    {{- end }}
    - secret:
        name: {{ .Release.Name }}-autocalibration-tls
        items:
        - key: tls.key
          path: scenescape-autocalibration.key
        - key: tls.crt
          path: scenescape-autocalibration.crt
    - secret:
        name: {{ .Release.Name }}-mapping-tls
        items:
        - key: tls.key
          path: scenescape-mapping.key
        - key: tls.crt
          path: scenescape-mapping.crt
    - secret:
        name: {{ .Release.Name }}-scenescape-ca.pem
        items:
        - key: tls.crt
          path: scenescape-ca.pem
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

{{- define "releaseLabels" }}
meta.helm.sh/release-name: {{ .Release.Name }}
meta.helm.sh/release-namespace: {{ .Release.Namespace }}
{{- end }}
