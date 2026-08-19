{{/*
Fullname helper — used for service names & labels.
*/}}
{{- define "oran-dashboard.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Backend service name (frontend proxies to this DNS name).
*/}}
{{- define "oran-dashboard.backend" -}}
{{ include "oran-dashboard.fullname" . }}-backend
{{- end -}}

{{/*
Common labels
*/}}
{{- define "oran-dashboard.labels" -}}
app.kubernetes.io/name: {{ include "oran-dashboard.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}
