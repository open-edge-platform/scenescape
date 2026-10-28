# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

{{/*
True ("true") when the Scene Controller consumes PTZ PoseContexts in either mode.
Fails rendering on configurations the Controller would reject at startup.
*/}}
{{- define "scene.ptzActive" -}}
{{- $ptz := .Values.scene.ptz | default dict -}}
{{- if and $ptz.enabled $ptz.shadowMode -}}
{{- fail "scene.ptz.enabled and scene.ptz.shadowMode are mutually exclusive" -}}
{{- end -}}
{{- if or $ptz.enabled $ptz.shadowMode -}}
{{- $config := $ptz.config | default dict -}}
{{- range $setting := list "max_pose_age_s" "max_clock_offset_s" "max_detection_pipeline_latency_s" "max_detection_timestamp_uncertainty_s" -}}
{{- if not (hasKey $config $setting) -}}
{{- fail (printf "scene.ptz.config.%s is required when scene.ptz.enabled or scene.ptz.shadowMode is set" $setting) -}}
{{- end -}}
{{- end -}}
true
{{- end -}}
{{- end -}}
