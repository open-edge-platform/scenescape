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
    - secret:
        name: {{ .Release.Name }}-vdms-s-tls
        items:
        - key: tls.key
          path: scenescape-vdms-s.key
        - key: tls.crt
          path: scenescape-vdms-s.crt
    - secret:
        name: {{ .Release.Name }}-vdms-c-tls
        items:
        - key: tls.key
          path: scenescape-vdms-c.key
        - key: tls.crt
          path: scenescape-vdms-c.crt
    - secret:
        name: {{ .Release.Name }}-camcalibration-tls
        items:
        - key: tls.key
          path: scenescape-camcalibration.key
        - key: tls.crt
          path: scenescape-camcalibration.crt
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
