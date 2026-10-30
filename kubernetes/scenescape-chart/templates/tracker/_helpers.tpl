# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

{{/*
True ("true") when the Tracker consumes PTZ PoseContexts in either mode.
Fails rendering on configurations the Tracker would reject at startup.
*/}}
{{- define "tracker.ptzActive" -}}
{{- $ptz := .Values.tracker.ptz | default dict -}}
{{- if and $ptz.enabled $ptz.shadowMode -}}
{{- fail "tracker.ptz.enabled and tracker.ptz.shadowMode are mutually exclusive" -}}
{{- end -}}
{{- if or $ptz.enabled $ptz.shadowMode -}}
{{- $config := $ptz.config | default dict -}}
{{- range $setting := list "max_pose_age_s" "max_clock_offset_s" "max_detection_pipeline_latency_s" "max_detection_timestamp_uncertainty_s" -}}
{{- if not (hasKey $config $setting) -}}
{{- fail (printf "tracker.ptz.config.%s is required when tracker.ptz.enabled or tracker.ptz.shadowMode is set" $setting) -}}
{{- end -}}
{{- end -}}
true
{{- end -}}
{{- end -}}
