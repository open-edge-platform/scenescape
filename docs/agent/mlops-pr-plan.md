# Plan for AI-assisted creation of documents for Open-Edge-Platform MLOps Integration and reuse

## Goal

Submit two separate PRs based on existing inputs (JIRA items, PowerPoint presentation and DrawIO diagrams, GitHub issue etc.): one for ADR and one for design doc. Prepare pull request descriptions for both using built-in GitHub template.

## Role of AI coding-agent in the process

Driving rule:

```
AI coding-agent, I want you to be facilitator, coach and consultant in the process. If there are any inconsistencies in the architecture or design, or if some design choices and assumptions are not explicitely stated, help me identify it, flag it and support me in resolution or clarification. Do not make assuptions or design choices on your own. Help me in better analyzing, structuring and phrasing the document.
```

## Scope and components involved

All components belong to Intel [Open-Edge-Platform](https://github.com/open-edge-platform) (OEP).

The scope of the documents created includes integration of [SceneScape](https://github.com/open-edge-platform/scenescape) with other components, namely:
- [Model Download](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/model-download) service, aka Model Manager
- [VIPPET](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/tools/visual-pipeline-and-platform-evaluation-tool) tool
- [DLSPS](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/dlstreamer-pipeline-server) service
- [Geti](https://github.com/open-edge-platform/geti)
- Stream Manager (aka Intel VST), a new service that is going to be introduced.

Integration of other components than SceneScape among themselves is part of the whole solution but is not the subject of the design decisions.

The documents created are deliverable for OEP 2026.1 release. The feature is planned to be delivered in phases in next releases (2026.2+).
JIRA item created for 2026.2 release define the exact scope.
Important: Use the release numbers mostly for your reference and refrain from using it in the documents. Just focus on the technical aspect and refer to them as phases.

## SceneScape context

SceneScape currently provides custom solutions for:
- model download (model_installer/src/README.md) and management (docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md, docs/user-guide/other-topics/model-configuration-file-format.md)
- visual pipeline building (manager/src/manager/ppl_generator, docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md)

The goal is to delegate those functionalities and reuse existing or future components in OEP.

SceneScape supports dynamic pipeline configuration (currently supported only in Kubernetes - see docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md) using DLSPS. This is caused by the fact that DLSPS lacks run-time API for arbitrary dynamic pipeline configuration and static configuration must be generated as a config map. DLSPS pods are recreated on each pipeline update (see `manager/src/manager/kubeclient.py`) because DLSPS number of pipelines is also statically configured. Improvements in DLSPS are needed but once pipeline building is delegated and DLSPS supports true dynamic pipeline configuration via REST API, the dynamic pipeline configuration in SceneScape will be possible in Docker Compose deployment as well, since no custom orchestration will be needed by SceneScape and everything will be managed via REST API calls - such universal solution with clear division of responsibilities is the ultimate goal.

DLStreamer pipeline is customized with a dedicated, monolithic scripts (dlstreamer-pipeline-server/user_scripts/gvapython/sscape) running in SceneScape pipelines using `gvapython` element that is going to be deprecated in favour of Gst Analytics Python approach. This makes it difficult to integrate SceneScape pipelines with other components and delegate pipeline building.

## Inputs

1. [PowerPoint presentation](docs/agent/presentation-extract.md)
2. [DrawIO diagrams](docs/agent/diagrams/SceneScape_MLOps.drawio)
  - Process Model Page
  - Component Interaction Page
2. [JIRA tickets](docs/agent/jira)
3. [NOKIA feature request](https://github.com/open-edge-platform/scenescape/issues/782)

## Outputs

1. PR descriptions in MarkDown format: `docs/agent/` folder
2. ADR: `docs/adr/0012-mlops-integration-reuse.md`
3. Design doc: `docs/design/mlops-integration-reuse.md`

## Steps

Follow steps below one by one. Ask for clarification if needed.

1. Verify all inputs, extract information. Stop immediately and flag any issues if inputs are not clear or information is not accessible.
2. Treat original NOKIA feature request as a reference of WHAT we are aiming in terms of UX, not a must have requirements
3. Treat JIRA tickets, presentation and diagrams as a definition of WHAT and HOW we are going to deliver

### Create ADR

- Help me adopt this knowledge into template docs/adr/template.md step-by-step.
- If any parts of template are not clear or covered, do not invent on your own, but ask for input and clarification.

### Create design doc

- Help me adopt this knowledge into template docs/design/template.md step-by-step.
- If any parts of template are not clear or covered, do not invent on your own, but ask for input and clarification.
