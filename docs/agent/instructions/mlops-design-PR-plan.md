# Plan for AI-assisted creation of Design Document for Open-Edge-Platform MLOps Integration and reuse (WIP)

## Goal

Submit PR based on existing inputs with design document for "Open-Edge-Platform MLOps Integration and reuse" feature as specified below. Prepare pull request description using built-in GitHub template.

## Role of AI coding-agent in the process

Driving rule:

```
AI coding-agent, I want you to be facilitator, coach and consultant in the process. If there are any inconsistencies in the architecture or design, or if some design choices and assumptions are not explicitely stated, help me identify it, flag it and support me in resolution or clarification. Do not make assuptions or design choices on your own. Help me in better analyzing, structuring and phrasing the document.
```

## Scope and components involved

The design document specifies high level design and will be detailed in next phases where needed. Some of the cross-service integration details have dependency on other components' design and are going to be decided when the design is ready. Explicitely state this limitation in the design document.

All components belong to Intel [Open-Edge-Platform](https://github.com/open-edge-platform) (OEP).

The scope of the documents created includes integration of [SceneScape](https://github.com/open-edge-platform/scenescape) with other components, namely:
- [Model Download](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/model-download) service, aka Model Manager
- [VIPPET](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/tools/visual-pipeline-and-platform-evaluation-tool) tool
- [DLSPS](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/dlstreamer-pipeline-server) service
- [Geti](https://github.com/open-edge-platform/geti)
- Stream Manager (aka Intel VST), a new service that is going to be introduced.

## Context

SceneScape currently provides custom solutions for:
- model download (model_installer/src/README.md) and management (docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md, docs/user-guide/other-topics/model-configuration-file-format.md)
- visual pipeline building (manager/src/manager/ppl_generator, docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md)

The goal is to delegate those functionalities and reuse existing or future components in OEP.

SceneScape supports dynamic pipeline configuration (currently supported only in Kubernetes - see docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md) using DLSPS. This is caused by the fact that DLSPS lacks run-time API for arbitrary dynamic pipeline configuration and static configuration must be generated as a config map. DLSPS pods are recreated on each pipeline update (see `manager/src/manager/kubeclient.py`) because DLSPS number of pipelines is also statically configured. Improvements in DLSPS are needed but once pipeline building is delegated and DLSPS supports true dynamic pipeline configuration via REST API, the dynamic pipeline configuration in SceneScape will be possible in Docker Compose deployment as well, since no custom orchestration will be needed by SceneScape and everything will be managed via REST API calls - such universal solution with clear division of responsibilities is the ultimate goal.

DLStreamer pipeline is customized with a dedicated, monolithic scripts (dlstreamer-pipeline-server/user_scripts/gvapython/sscape) running in SceneScape pipelines using `gvapython` element that is going to be deprecated in favour of Gst Analytics Python approach. This makes it difficult to integrate SceneScape pipelines with other components and delegate pipeline building. We want to address it but it will be investigated in next phase, how the custom logic can broken down.

## Base Inputs

Use these documents as a primary high-level source. All of these were created in the process of generating ADR document.

1. ADR: `docs/adr/0012-mlops-integration-reuse.md`
2. All MarkDown files in `docs/agent/intermediate` folder.

## Source Inputs

Use these documents as a secondary lower-level source or fall back if anything is ambiguous in base inputs. These are the primary sources of knowledge that were used in ADR document generation.

Embed both the SVG diagrams in the right place in the design document.

1. [presentation extract](docs/agent/presentation-extract.md)
2. [presentation extract](docs/agent/stream-manager.md)
3. [DrawIO diagrams](docs/agent/diagrams/SceneScape_MLOps.drawio)
  - Process Model Page (exported as `docs/agent/diagrams/SceneScape_MLOps-Process Model.drawio.svg`)
  - Component Interaction Page (exported as `docs/agent/diagrams/SceneScape_MLOps-Process Model.drawio.svg`)

## Outputs

1. Design doc: `docs/design/mlops-integration-reuse.md`
2. PR description in MarkDown format: `docs/agent/` folder

## Steps

Follow steps below one by one. Ask for clarification if needed. Each time ask for approval before proceeding to next step.

1. Verify all base inputs. Stop immediately and flag any issues if inputs are not clear or information is not accessible.
2. Analyze `docs/agent/intermediate/adr-vs-design-split.md` document and compare with ADR document for consistency.
3. Check whether you have everything needed to generate the design document. Verify all sources for consistency and flag any issues or inconsistencies.

### Create Design Document

- Help me adopt this knowledge into template docs/design/template.md step-by-step.
- If any parts of template are not clear or covered, do not invent on your own, but ask for input and clarification.
- Include diagrams exported as SVG where appropriate.
- Iteratively, step-by-step improve, clarify or fill in placeholders and ask for feedback.
- As stated in the scope section, it is OK if some parts of the design are not decided at this stage. In such cases, explicitely state that those will be addressed in next phases.
