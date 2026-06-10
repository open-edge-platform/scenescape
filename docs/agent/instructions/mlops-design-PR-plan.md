# Plan for AI-assisted creation of Design Document for Open-Edge-Platform MLOps Integration and reuse

## Goal

Prepare artifacts for a PR introducing the design document for the "Open-Edge-Platform MLOps Integration and reuse" feature, based on the existing inputs specified below. The agent's responsibility ends at producing the artifacts (design document and PR-description markdown). The user commits, pushes, and opens the pull request.

Prepare the pull request description using the built-in GitHub template at [.github/pull_request_template.md](../../../.github/pull_request_template.md).

## Role of AI coding-agent in the process

Driving rule:

```
AI coding-agent, I want you to be facilitator, coach and consultant in the process. If there are any inconsistencies in the architecture or design, or if some design choices and assumptions are not explicitly stated, help me identify it, flag it and support me in resolution or clarification. Do not make assumptions or design choices on your own. Help me in better analyzing, structuring and phrasing the document.
```

## Scope and components involved

The design document specifies high level design and will be detailed in next phases where needed. Some of the cross-service integration details have dependency on other components' design and are going to be decided when the design is ready. Explicitly state this limitation in the design document.

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

DLStreamer pipeline is customized with a dedicated, monolithic scripts (dlstreamer-pipeline-server/user_scripts/gvapython/sscape) running in SceneScape pipelines using `gvapython` element that is going to be deprecated in favour of Gst Analytics Python approach. This makes it difficult to integrate SceneScape pipelines with other components and delegate pipeline building. We want to address it but it will be investigated in next phase, how the custom logic can be broken down.

## Base Inputs

Use these documents as a primary high-level source. All of these were created in the process of generating ADR document.

1. ADR: `docs/adr/0012-mlops-integration-reuse.md`
2. All MarkDown files in `docs/agent/intermediate` folder.

## Source Inputs

Use these documents as a secondary lower-level source or fall back if anything is ambiguous in base inputs. These are the primary sources of knowledge that were used in ADR document generation.

Embed both the SVG diagrams in the right place in the design document.

1. [presentation extract](docs/agent/presentation-extract.md)
2. [Stream Manager presentation extract](docs/agent/stream-manager.md)
3. [DrawIO diagrams](docs/agent/diagrams/SceneScape_MLOps.drawio)
  - Process Model Page (exported as `docs/agent/diagrams/SceneScape_MLOps-Process Model.drawio.svg`)
  - Component Interaction Page (exported as `docs/agent/diagrams/SceneScape_MLOps-Component Interaction.drawio.svg`)
4. [JIRA tickets](docs/agent/jira)
5. [NOKIA feature request](https://github.com/open-edge-platform/scenescape/issues/782)

Important: Release numbers, JIRA IDs and GitHub issue numbers must NOT appear in the design document body. Refer to phases instead. This rule is carried forward from the ADR-PR plan.

## Authoring conventions

- **Reference the ADR rather than duplicate its content.** Where the ADR ([docs/adr/0012-mlops-integration-reuse.md](docs/adr/0012-mlops-integration-reuse.md)) already states the decision, motivation, or constraint, the design document should link to the ADR section instead of repeating the text. This applies to the Context, Goals, Non-Goals, and Alternatives Considered sections in particular. The design document focuses on the *how* (implementation, contracts, deltas, rollout); the ADR remains the source of truth for *what* and *why*.

## Outputs

1. Design doc: `docs/design/mlops-integration-reuse.md`
2. PR description in MarkDown format: `docs/agent/design-pull-request-description.md`
3. Design-doc decision log: `docs/agent/intermediate/design-doc-decisions.md` — living record of drafting status, decisions taken while authoring the design doc that supplement (not override) the ADR, wording disciplines, and the service-ownership matrix. Updated continuously as the design doc is drafted.

## Steps

Follow steps below one by one. Ask for clarification if needed. Each time ask for approval before proceeding to next step.

1. Verify all base inputs. Stop immediately and flag any issues if inputs are not clear or information is not accessible.
2. Use `docs/agent/intermediate/adr-vs-design-split.md` as the structural backbone for the design document — its *Design-Doc scope* subsections seed §5 (Proposed Design) of [docs/design/template.md](docs/design/template.md). Perform a quick consistency check between this intermediate and the ADR ([docs/adr/0012-mlops-integration-reuse.md](docs/adr/0012-mlops-integration-reuse.md)) and flag any drift before proceeding.
3. Check whether you have everything needed to generate the design document. Verify all sources for consistency and flag any issues or inconsistencies.
4. **SceneScape granularity analysis** — Before drafting, analyze whether the term "SceneScape" in the existing inputs (ADR, intermediates, source docs) is used at the right level of abstraction. SceneScape is itself a set of microservices (Manager, Scene Controller, Auto Camera Calibration, model_installer, etc.). Determine:
   - For each occurrence of "SceneScape" in scope of the design doc, whether it should remain as the umbrella name or be refined to a specific service.
   - Which level of detail is appropriate for the design doc vs. the ADR (the ADR treats SceneScape as a whole; the design doc may need to be more specific in some sections).
   - Which SceneScape services will be extended or become clients of other OEP components, and **when** that mapping is decided (now, or per phase).
   Capture the conclusions and apply them consistently when drafting. This step exists to avoid drift between the umbrella term and concrete service-level integration responsibilities.

### Create Design Document

- Help me adopt this knowledge into template docs/design/template.md step-by-step.
- If any parts of template are not clear or covered, do not invent on your own, but ask for input and clarification.
- Include diagrams exported as SVG where appropriate.
- Iteratively, step-by-step improve, clarify or fill in placeholders and ask for feedback.
- As stated in the scope section, it is OK if some parts of the design are not decided at this stage. In such cases, explicitly state that those will be addressed in next phases.
- Apply the *Reference the ADR rather than duplicate* rule from the *Authoring conventions* section.
- **Keep the design-doc decision log up to date.** After each drafting iteration (new subsection drafted, comment applied, or decision taken), update [docs/agent/intermediate/design-doc-decisions.md](../intermediate/design-doc-decisions.md) so its *Drafting status*, decision entries, and wording disciplines reflect the current state of the design doc. Read this file before starting any new subsection.

### Create PR Description

- Create a PR description aligned with [.github/pull_request_template.md](../../../.github/pull_request_template.md), saved to `docs/agent/design-pull-request-description.md`.
- Use [docs/agent/adr-pull-request-description.md](../adr-pull-request-description.md) as a structural reference (this is a documentation-only PR).
- Iterate until I approve.
