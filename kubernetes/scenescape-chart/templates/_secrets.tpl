# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

{{- define "secrets-py" -}}
SECRET_KEY='{{ randAlphaNum 50 }}'
DATABASE_PASSWORD='{{ .Values.pgserver.password }}'
{{- end -}}

{{- define "supass" -}}
{{ required "You must set supass (e.g. --set supass=...) for this chart to install." .Values.supass }}
{{- end -}}

{{- define "db-password" -}}
{{ required "You must set pgserver.password (e.g. --set pgserver.password=...) for this chart to install." .Values.pgserver.password }}
{{- end -}}

{{- define "positioning-auth" -}}
{{- $secret := lookup "v1" "Secret" .Release.Namespace (printf "%s-positioning.auth" .Release.Name) -}}
{{- if and $secret (hasKey $secret.data "positioning.auth") -}}
{{ index $secret.data "positioning.auth" | b64dec }}
{{- else -}}
{"user": "positioning", "password": "{{ randAlphaNum 32 }}"}
{{- end -}}
{{- end -}}
