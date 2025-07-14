{{ range .Results }}
Trivy Misconfiguration Scan Results ({{- .Target -}})
MisconfigurationID,Severity,Title,Description,Resolution,PrimaryURL
{{ range .Misconfigurations }}
    {{- .ID }},
    {{- .Severity }},
    {{- quote .Title }},
    {{- quote .Description }},
    {{- quote .Resolution }},
    {{- .PrimaryURL }}
{{ else -}}
    No misconfigurations found at this time.
{{ end }}
{{ end }}
