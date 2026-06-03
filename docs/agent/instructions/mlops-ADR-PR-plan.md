# Plan for AI-assisted creation of ADR document for Open-Edge-Platform MLOps Integration and reuse

## Goal

Submit PR with ADR (Architecture Decision Record) document for MLOps Integration and reuse, based on existing inputs (JIRA items, PowerPoint presentation and DrawIO diagrams, GitHub issue etc.).
Prepare pull request description using built-in GitHub template.

## Role of AI coding-agent in the process

Driving rule:

```
AI coding-agent, I want you to be facilitator, coach and consultant in the process. If there are any inconsistencies in the architecture or design, or if some design choices and assumptions are not explicitly stated, help me identify it, flag it and support me in resolution or clarification. Do not make assumptions or design choices on your own. Help me in better analyzing, structuring and phrasing the document.
```

## Scope and components involved

All components belong to Intel [Open-Edge-Platform](https://github.com/open-edge-platform) (OEP).

The scope of the documents created includes integration of [SceneScape](https://github.com/open-edge-platform/scenescape) with other components, namely:
- [Model Download](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/model-download) service, aka Model Manager
- [VIPPET](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/tools/visual-pipeline-and-platform-evaluation-tool) tool
- [DLSPS](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/dlstreamer-pipeline-server) service
- [Geti](https://github.com/open-edge-platform/geti)
- Stream Manager (aka Intel VST), a new service that is going to be introduced.

Integration of other components than SceneScape among themselves is part of the whole solution (division of responsibilities, interactions) but is not the subject of the design decisions.

Requirements are defined for the other components where needed to align them with SceneScape use cases.
High level requirements for the other components can be found in the presentation extract.
Some lower level requirements for Model Download service are available and can be found in ITEP-92375.xml JIRA item (feature defined for Model Download component for 2026.2 release).

Timeline: High-level plan can be found in the presentation extract `Slide 9: VA Platform Integration: Proposed Timeline`.
Mapping of phases to releases and JIRA items:
- Phase 1: OEP 2026.1 release (JIRA item ITEP-87215.xml). Deliverable: The ADR document and design document that will be created separately.
- Phase 2: OEP 2026.2 release (JIRA item ITEP-92811.xml). See the JIRA item for the exact scope.
- Phase 3: OEP 2026.3 release. JIRA item not defined yet.
- Phase 4: OEP 2027.0 release. JIRA item not defined yet.

Important: Use the release numbers mostly for your reference and refrain from using it in the documents. Just focus on the technical aspect and refer to them as phases.

## SceneScape context

SceneScape currently provides custom solutions for:
- model download (model_installer/src/README.md) and management (docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md, docs/user-guide/other-topics/model-configuration-file-format.md)
- visual pipeline building (manager/src/manager/ppl_generator, docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md)

The goal is to delegate those functionalities and reuse existing or future components in OEP.

SceneScape supports dynamic pipeline configuration (currently supported only in Kubernetes - see docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md) using DLSPS. This is caused by the fact that DLSPS lacks run-time API for arbitrary dynamic pipeline configuration and static configuration must be generated as a config map. DLSPS pods are recreated on each pipeline update (see `manager/src/manager/kubeclient.py`) because DLSPS number of pipelines is also statically configured. Improvements in DLSPS are needed but once pipeline building is delegated and DLSPS supports true dynamic pipeline configuration via REST API, the dynamic pipeline configuration in SceneScape will be possible in Docker Compose deployment as well, since no custom orchestration will be needed by SceneScape and everything will be managed via REST API calls - such universal solution with clear division of responsibilities is the ultimate goal.

DLStreamer pipeline is customized with a dedicated, monolithic scripts (dlstreamer-pipeline-server/user_scripts/gvapython/sscape) running in SceneScape pipelines using `gvapython` element that is going to be deprecated in favour of Gst Analytics Python approach. This makes it difficult to integrate SceneScape pipelines with other components and delegate pipeline building. We want to address it but it will be investigated in next phase, how the custom logic can be broken down.

## Inputs

1. [PowerPoint presentation](docs/agent/presentation-extract.md)
2. [DrawIO diagrams](docs/agent/diagrams/SceneScape_MLOps.drawio)
  - Process Model Page (exported as `docs/agent/diagrams/SceneScape_MLOps-Process Model.drawio.svg`)
  - Component Interaction Page (exported as `docs/agent/diagrams/SceneScape_MLOps-Component Interaction.drawio.svg`)
3. [JIRA tickets](docs/agent/jira)
4. [NOKIA feature request](https://github.com/open-edge-platform/scenescape/issues/782)
5. [Stream Manager presentation extract](docs/agent/stream-manager.md)

## Outputs

1. PR descriptions in MarkDown format: `docs/agent/` folder
2. ADR: `docs/adr/0012-mlops-integration-reuse.md`
3. Intermediate files as needed: `docs/agent/intermediate`

## What is and what is not relevant

Focus on technical aspects, design decisions and architecture.
Do not include specific release numbers, JIRA items or GitHub issues.
Improving UX is definitely one of main motivations but not the only one: engineering efficiency, focusing on core SceneScape functionalities, reducing redundant efforts are equally important.
UX KPIs like mouse-clicks are not relevant in the context of documents created. We shouldn't over-optimize the solution for UX only.

## Process description

Follow steps below one by one. Ask for clarification if needed. After each step wait for approval before proceeding to another one.

How to treat the inputs:
- Treat original NOKIA feature request as approximation of WHAT we are aiming in terms of UX, not a must have requirements.
- Treat JIRA tickets, presentation and diagrams as a definition of WHAT and HOW we are going to deliver

### Create ADR

1. Verify all inputs, extract information. Stop immediately and flag any issues if inputs are not clear or information is not accessible.
2. Explain each diagram and create intermediate .md files in `docs/agent/intermediate` folder with a summary. Ask for feedback, iterate and wait for approval.
3. Create an intermediate file with a division of responsibilites between involved components. Ask for feedback, iterate and wait for approval.
4. Help me adopt whole knowledge into template docs/adr/template.md step-by-step.
5. If any parts of template are not clear or covered, do not invent on your own, but ask for input and clarification.
6. Iterate and update the document and PR description until I approve them.
7. Create PR description aligned with `.github/pull_request_template.md` file.
