# MLOps Integration Geti/DLS-PS/SceneScape: Phase 2

| Field | Value |
|---|---|
| **Project** | ITEP (EdgeSW) |
| **Issue Type** | Feature |
| **Summary** | MLOps Integration Geti/DLS-PS/SceneScape: Phase 2 |
| **Priority** | P2-High |
| **Fix Version/s** | EAL-2026.2 |
| **Component/s** | Metro AI Suite |
| **Reporter** | Gorecki, Jan |
| **Assignee** | Klimaszewski, Marcin |
| **Engineering Contact/Owner** | Klimaszewski, Marcin; Gorecki, Jan |
| **Primary Owner** | Watts, Robert A |
| **Security Level** | Public |
| **Customer Company** | Nokia |
| **Customer Priority** | Undecided |
| **Business Unit** | Health and Cities |

## Description (JIRA wiki markup)

```
This is Phase 2 of the MLOps Integration feature, building on the design and architecture work completed in Phase 1 (ITEP-87215, EAL-2026.1).

Phase 1 (2026.1) delivered:
* Identification and documentation of use cases, workflows and highlighting of gaps in API endpoints of Model Downloader / DLSPS / VIPPET and Geti.
* Identification and documentation of feature gaps or architecture reworks in SceneScape.
* Architecture work with Model Downloader / DL Streamer / VIPPET teams on a clear division of responsibilities between SceneScape and Model Downloader/DLSPS/VIPPET with respect to model and pipeline management.
* Documenting the feature high level architecture design / decisions in ADR (Architecture Decision Record) and / or the design document in SceneScape repository.

Phase 2 (2026.2) scope:

# *Integration with Model Downloader (Manager) service* — Integrate SceneScape with the Model Downloader (Manager) microservice to enable automated model retrieval, storage, and lifecycle management.
# *Switch from gvapython to Gst Analytics Python* — Replace the legacy gvapython-based inference post-processing with the Gst Analytics Python API for improved maintainability and alignment with upstream GStreamer conventions.
# *Simplify / break down Python adapter (phase 1)* — Begin refactoring the monolithic Python adapter into smaller, well-defined modules to improve testability, readability, and extensibility.
# *VIPPET integration design* — Design the integration between SceneScape and VIPPET (Video Ingestion Pipeline for Pre-processing, Evaluation and Training). This has a dependency on VIPPET and DLSPS design readiness.
# *Switch to a new set of public models (discard OMZ models)* — Migrate from OpenVINO Model Zoo (OMZ) models to a new set of publicly available models, removing the dependency on the deprecated OMZ repository.

||Target Platform||All||
```

## Acceptance Criteria (JIRA wiki markup)

```
# SceneScape can discover, download, and use models via the Model Downloader (Manager) service without manual file transfer or model conversion.
# Inference post-processing uses Gst Analytics Python API instead of gvapython; no regression in detection accuracy or performance.
# Python adapter codebase is refactored into at least two separate, independently testable modules (phase 1 of simplification).
# A design document for VIPPET integration is published in the SceneScape repository (ADR or design doc), covering API contracts, data flow, and division of responsibilities.
# All default pipelines use the new public model set; no OMZ model dependencies remain in the default configuration.
# No measurable impact to performance or accuracy compared to the pre-Phase 2 baseline when using the new model set and Gst Analytics Python API.
```
