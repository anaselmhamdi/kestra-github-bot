{{/*
Expand the name of the chart.
*/}}
{{- define "kestra-github-bot.name" -}}
{{- default .Chart.Name .Values.appName | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "kestra-github-bot.fullname" -}}
{{- $name := default .Chart.Name .Values.appName }}
{{- if contains $name .Release.Name -}}
{{- printf "%s-%s" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "kestra-github-bot.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "kestra-github-bot.labels" -}}
helm.sh/chart: {{ include "kestra-github-bot.chart" . }}
{{ include "kestra-github-bot.selectorLabels" . }}

{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selectors labels
*/}}
{{- define "kestra-github-bot.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kestra-github-bot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
