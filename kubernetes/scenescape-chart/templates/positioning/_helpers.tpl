# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

{{- define "positioning.onvifCredentialsDir" -}}
/run/secrets/onvif
{{- end -}}

{{/*
Rendered positioning.json: positioning.config plus resolver_id from positioning.resolverId.
Sources without credentials_file default to the chart-mounted ONVIF secret file
<onvifCredentialsDir>/<source_id>.json. Fails rendering on configurations the service
would reject at startup.
*/}}
{{- define "positioning.configJson" -}}
{{- $values := .Values.positioning -}}
{{- $config := deepCopy ($values.config | default dict) -}}
{{- if hasKey $config "resolver_id" -}}
{{- fail "positioning.config.resolver_id is not supported; set positioning.resolverId" -}}
{{- end -}}
{{- $_ := set $config "resolver_id" $values.resolverId -}}
{{- $assignments := $values.assignments | default dict -}}
{{- $credentials := $values.onvifCredentials | default dict -}}
{{- $sources := dict -}}
{{- range $sourceId, $source := ($config.sources | default dict) -}}
{{- if not (kindIs "map" $source) -}}
{{- fail (printf "positioning.config.sources.%s must be an object" $sourceId) -}}
{{- end -}}
{{- $source = deepCopy $source -}}
{{- if not $source.credentials_file -}}
{{- $_ := set $source "credentials_file" (printf "%s/%s.json" (include "positioning.onvifCredentialsDir" $) $sourceId) -}}
{{- end -}}
{{- if ne (toString (get $assignments $sourceId)) (toString $values.resolverId) -}}
{{- fail (printf "positioning.config.sources.%s must be assigned to %q in positioning.assignments" $sourceId (toString $values.resolverId)) -}}
{{- end -}}
{{- $_ := set $sources $sourceId $source -}}
{{- end -}}
{{- range $sourceId, $resolverId := $assignments -}}
{{- if and (eq (toString $resolverId) (toString $values.resolverId)) (not (hasKey $sources $sourceId)) -}}
{{- fail (printf "positioning.assignments.%s is assigned to %q but has no entry in positioning.config.sources" $sourceId (toString $values.resolverId)) -}}
{{- end -}}
{{- end -}}
{{- if $sources -}}
{{- range $setting := list "max_pose_age_s" "max_timestamp_uncertainty_s" "max_clock_offset_s" "target_reprojection_rms_px" -}}
{{- if not (hasKey $config $setting) -}}
{{- fail (printf "positioning.config.%s is required when positioning.config.sources is not empty" $setting) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if and $credentials.existingSecret $credentials.sources -}}
{{- fail "Set only one of positioning.onvifCredentials.existingSecret and positioning.onvifCredentials.sources" -}}
{{- end -}}
{{- $_ := set $config "sources" $sources -}}
{{- toJson $config -}}
{{- end -}}

{{- define "positioning.onvifCredentialsSecretName" -}}
{{- $credentials := .Values.positioning.onvifCredentials | default dict -}}
{{- if $credentials.existingSecret -}}
{{- $credentials.existingSecret -}}
{{- else if $credentials.sources -}}
{{- printf "%s-positioning-onvif" .Release.Name -}}
{{- end -}}
{{- end -}}
