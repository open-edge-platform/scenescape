# Design Document: Open-Edge-Platform MLOps Integration and Reuse

- **Author(s)**: [Tomasz Dorau](https://github.com/tdorau)
- **Date**: 2026-06-09
- **Status**: `Proposed`
- **Related ADRs**: [ADR-12 — MLOps Integration and Reuse](../adr/0012-mlops-integration-reuse.md)

---

## 1. Overview

This document specifies the high-level design for integrating SceneScape with new Intel® [Open-Edge-Platform](https://github.com/open-edge-platform) (OEP) components — **Model Downloader**, **ViPPET**, and **Stream Manager** — and for evolving the existing integration with the **DL Streamer Pipeline Server (DLSPS)**. Geti participates in the end-to-end workflow but is reached only indirectly (via Model Downloader for models and via Stream Manager for training videos).

The architectural decision and its rationale are recorded in [ADR-12](../adr/0012-mlops-integration-reuse.md). This document focuses on *how* SceneScape implements that decision: per-component contracts, the per-service changes inside SceneScape, the scene export/import format, the deployment topology, and the phased rollout plan.

Some cross-service integration details depend on other components' designs (notably ViPPET, the DLSPS runtime pipeline API, and Stream Manager). Those dependencies are called out explicitly throughout the document, and the affected design decisions are deferred to subsequent phases when the dependent designs are ready.

## 2. Goals

The design goals follow directly from [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision):

- **Delegate** model management, visual pipeline building, and video-source acquisition to OEP components (Model Downloader, ViPPET, Stream Manager) and reuse them in place of SceneScape-specific implementations.
- **Evolve the existing SceneScape↔DLSPS integration** toward a fully runtime API-based pipeline lifecycle, retiring the static-JSON and pod-recreation mechanisms.
- Adopt a uniform, dynamic, API-based approach to pipeline configuration and management for both Docker Compose and Kubernetes SceneScape deployments.
- Preserve SceneScape's ability to deploy and run **without ViPPET** (self-contained exported scenes) and **without Stream Manager** (Stream Manager is an optional dependency).
- Keep SceneScape focused on its core spatial-awareness value (sensor fusion, multi-object tracking, scene state), reducing the maintenance burden of redundant capabilities.
- Preserve existing SceneScape deployments throughout the phased transition (backwards compatibility until feature parity is achieved).

## 3. Non-Goals

The following are explicitly out of scope of this design document:

- Direct SceneScape↔Geti integration (per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision); Geti is reached indirectly via Model Downloader for models and via Stream Manager for training data).
- The internal API design of Stream Manager (owned by the Stream Manager team).
- ViPPET's internal pipeline templates and verification tooling.
- DLSPS's internal architecture and the design of its runtime pipeline API.
- Concrete UX flows in the SceneScape Manager UI (separate UX/feature work).
- Geti-side integration timelines with ViPPET, Model Downloader, and Stream Manager.
- The exact set of public models that will replace OpenVINO Model Zoo (OMZ) models in default SceneScape pipelines (an open question captured later in this document).

## 4. Background / Context

For motivation and the high-level decision narrative, see [ADR-12 §Context](../adr/0012-mlops-integration-reuse.md#context) and [§Decision](../adr/0012-mlops-integration-reuse.md#decision). This section adds the engineering-level detail that the ADR intentionally omits.

### 4.1 SceneScape today

Two capabilities in SceneScape are being **delegated** to new OEP components, and the existing **DLSPS integration is being evolved**.

**Capabilities being delegated:**

1. **Model download** is today handled by [`model_installer/`](../../model_installer/), which downloads models from the OpenVINO Model Zoo into a shared volume (`vol-models`) consumed by DLSPS pipelines, governed by SceneScape-specific model-configuration conventions. **Model management** (listing installed models, surfacing them in the UI for pipeline configuration) is handled by Manager's UI, principally [`manager/src/manager/model_directory_view.py`](../../manager/src/manager/model_directory_view.py). See [model-configuration-file-format](../user-guide/other-topics/model-configuration-file-format.md).
2. **Visual pipeline building.** Today handled differently per deployment target:
   - **Docker Compose**: manually authored static JSON files under [`dlstreamer-pipeline-server/`](../../dlstreamer-pipeline-server/) (one per pipeline variant), bind-mounted into DLSPS.
   - **Kubernetes**: custom pipeline generation by [`manager/src/manager/ppl_generator/`](../../manager/src/manager/ppl_generator/), materialized as Kubernetes ConfigMaps and applied by [`manager/src/manager/kubeclient.py`](../../manager/src/manager/kubeclient.py).

**Existing DLSPS integration being evolved:**

DLSPS is **already integrated** with SceneScape as the pipeline runtime; this integration is being evolved, not introduced. Two limitations of today's integration drive the evolution:

- DLSPS does not (today) expose a runtime API for arbitrary pipeline reconfiguration, and runs a statically configured number of pipelines. As a consequence, the Kubernetes flow above **recreates DLSPS pods on every pipeline update**. Once DLSPS exposes a runtime pipeline API, SceneScape will use it for true dynamic pipeline lifecycle in both Docker Compose and Kubernetes deployments.
- SceneScape injects custom Python logic — the *SceneScape adapter* — into DLSPS pipelines via `gvapython` elements. The adapter code lives under [`dlstreamer-pipeline-server/user_scripts/gvapython/sscape/`](../../dlstreamer-pipeline-server/user_scripts/gvapython/sscape/) in the SceneScape repository (not in the DLSPS repository); it is statically injected into DLSPS pipeline configurations and executed by DLSPS at runtime. The `gvapython` element is itself being deprecated upstream in favour of the Gst Analytics Python API. The adapter is monolithic today; refactoring it into smaller, reusable units is a multi-phase activity discussed in the *Open Questions* section.

### 4.2 SceneScape Component Reference

This subsection defines the SceneScape-internal vocabulary used in the rest of the document. SceneScape is a set of microservices; different sections of this design refer to specific SceneScape services rather than to "SceneScape" as a whole.

#### Services in scope of (or possibly in scope of) MLOps integration

**Manager** — today a single Django service ([`manager/`](../../manager/)) combining the web UI, REST API, scene model, PostgreSQL persistence, scene import/export, and pipeline orchestration against DLSPS (both the Kubernetes pipeline-generation flow and direct interactions). In subsequent phases, Manager is expected to split into two services:

- **Manager (back-end)** — REST API, scene model, scene import/export, and DLSPS pipeline lifecycle. The term *Manager back-end* in this document refers to this responsibility set whether implemented as the current monolith or as a future separate service.
- **Manager (UI)** — thin front-end consuming the Manager back-end's REST API. The term *Manager UI* in this document refers to this responsibility set independent of the split timeline.

**Auto Camera Calibration** ([`autocalibration/`](../../autocalibration/)) — computes camera intrinsics and extrinsics from sensor feeds. May consume images from Stream Manager in future phases (decision deferred).

**Mapping** ([`mapping/`](../../mapping/), *experimental*) — may consume streams or images from Stream Manager in future phases (decision deferred).

**`model_installer`** ([`model_installer/`](../../model_installer/)) — the current model-download service. **Removed** once Model Downloader populates the shared model volume (see the *Proposed Design* section).

#### Services not in scope of MLOps integration (listed for completeness)

**Scene Controller** ([`controller/`](../../controller/)) — runtime scene state, multimodal sensor fusion, multi-object tracking. Consumes DLSPS inference output via MQTT. **No MLOps-integration changes are planned.**

**Cluster Analytics** ([`cluster_analytics/`](../../cluster_analytics/), *experimental*) — not part of the MLOps integration scope.

### 4.3 Constraints driving the design

- **Backwards compatibility window.** Existing deployments using static JSON pipeline configurations (Docker Compose bind-mount) and the custom dynamic pipeline configuration on Kubernetes must remain supported until feature parity with the ViPPET-based flow is achieved. These are two distinct legacy mechanisms with separate parity gates.
- **Self-contained exported scenes.** Per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision), exported scenes embed pipeline definitions by value (so deployment does not require ViPPET) and reference models by identifier (so Model Downloader is required at deployment time to materialize the models).
- **Optional Stream Manager.** SceneScape must continue to operate without Stream Manager; direct camera/file sources remain supported.
- **No direct Model Downloader download calls from SceneScape at runtime.** Model download is performed out-of-band (deployment-time job or ViPPET UI); SceneScape's only runtime interaction with Model Downloader is the listing endpoint.
- **Cross-component design dependencies.** Several design choices (ViPPET pipeline-definition format details, DLSPS runtime API shape, Stream Manager API shape) depend on the corresponding teams' designs and are deferred to the relevant phase.

---

## 5. Proposed Design

### 5.1 Component-level architecture

The component view below shows the runtime relationships between SceneScape and the OEP MLOps components. Only the interactions relevant to MLOps integration are shown; intra-SceneScape interactions (Manager ↔ Scene Controller MQTT, Auto Camera Calibration outputs, etc.) are omitted.

![Component Interaction](../agent/diagrams/SceneScape_MLOps-Component%20Interaction.drawio.svg)

> Each "SceneScape →" arrow in this diagram is realized inside SceneScape by the corresponding **client library** described later in this section (one per OEP component). The diagram is component-level only — protocols, transport, and auth are specified in the per-contract specifications below.

**Component roles** (consolidated from [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision) and the *SceneScape today* subsection above):

| Component | Status | Owned data | SceneScape's relationship |
|---|---|---|---|
| **Model Downloader** | Existing OEP component (new requirements) | Installed models | Runtime listing endpoint (Manager UI); no runtime download calls |
| **ViPPET** | Existing OEP component (new requirements) | Pipeline templates and definitions | REST pull of pipeline definitions (Manager back-end); embedded by value into scene exports |
| **DLSPS** | Already integrated; integration evolving | Running pipelines; inference output | Runtime pipeline lifecycle via DLSPS REST API (Manager back-end); MQTT inference output (Scene Controller) |
| **Stream Manager** | New OEP component (optional) | Camera devices, live and captured video | Livestream/replay APIs (Manager back-end and, deferred, Auto Camera Calibration / Mapping) |
| **Geti** | Existing OEP component (no changes) | Datasets, trained models | **No direct integration** — mediated via Model Downloader and Stream Manager |

**Data flow at runtime:**

- Models are downloaded by an out-of-band job into a **shared model volume** populated by Model Downloader and read by DLSPS. SceneScape never reads model files directly.
- Pipeline definitions are pulled from ViPPET by Manager back-end, persisted in SceneScape's scene configuration (embedded by value), and pushed to DLSPS via its runtime API.
- Video sources are either consumed from Stream Manager (when deployed) or accessed directly (RTSP/file) when Stream Manager is not deployed.
- DLSPS publishes inference results to MQTT, consumed unchanged by Scene Controller (no MLOps-integration changes to Scene Controller).

### 5.2 End-to-end process model

The process model shows the user-facing workflow for building, packaging, and deploying a SceneScape-based solution that integrates Geti (training), ViPPET (pipeline building), DLSPS (pipeline execution), Stream Manager (video acquisition), Model Downloader (model lifecycle), and SceneScape (scene management and runtime).

![Process Model](../agent/diagrams/SceneScape_MLOps-Process%20Model.drawio.svg)

**Stages** (top-to-bottom, summarized):

1. **Camera Setup** — Stream Manager detects and configures camera devices.
2. **Data Acquisition** — Stream Manager captures videos and uploads them to a Geti instance for annotation.
3. **Geti Training** — Geti annotates, trains, and validates the model.
4. **DLS Pipeline Development** — ViPPET downloads the Geti-trained model (via Model Downloader), authors and verifies the DLSPS pipeline.
5. **Scene Development** — SceneScape sets up scenes and cameras, consumes the ViPPET pipeline definition, maps pipelines to sources, starts pipelines, and evaluates AI-task performance.
6. **Package Preparation** — SceneScape exports the scene (self-contained per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision)).
7. **Deployment** — at the production site, Model Downloader materializes the referenced models, SceneScape imports the scene and starts pipelines, Stream Manager runs alongside (when deployed) for video acquisition.

**Properties of the workflow relevant to this design:**

- **No direct SceneScape ↔ Geti arrow.** Confirms the corresponding non-goal stated above.
- **Scene-evaluation feedback loop** (dashed in the diagram) returns to *Annotate*, *Build Pipeline*, or *Capture* depending on the root cause of poor AI-task performance — the design must keep this loop short, which is why pipeline-to-source mapping is owned scene-side (see *Responsibility matrix* below) and pipeline updates are dynamic via DLSPS runtime API (see the DLSPS runtime API delta).
- **Development and production deployments are independent.** Each component can be deployed standalone for iterative development; production composition is reconstructed from the exported scene plus the required OEP components.

### 5.3 Responsibility matrix and cross-cutting concerns

This section is the source of truth for *who does what* in the integrated system. It collapses the per-component breakdown in *SceneScape today* and the ADR-12 component assignments into a single SceneScape-perspective view, refined to the specific SceneScape services that own each responsibility (per the *SceneScape Component Reference*).

> **Note on Manager service split.** The matrix below assigns responsibilities to *Manager back-end* and *Manager UI* as a **recommendation**. The decision on whether (and when) to split today's monolithic Manager service into separate back-end and UI services is **deferred**. Until that decision is made, all rows assigned to *Manager back-end* or *Manager UI* are implemented inside the current Manager service; the BE/UI labels capture the intended responsibility boundary, not a current service boundary.

**Per-component responsibility matrix:**

| Concern | Owner | Notes |
|---|---|---|
| Scene model and persistence | Manager back-end | Scene map, cameras, ROIs, pipeline-to-source mapping. |
| Pipeline-to-source mapping (scene-level) | Manager back-end | Persisted SceneScape-side only; ViPPET's internal mapping is not synchronized. |
| Pipeline authoring | ViPPET | SceneScape never authors pipelines. |
| Pipeline definition consumption | Manager back-end | REST pull from ViPPET; embedded by value into scene exports. |
| Pipeline lifecycle (start/stop, dynamic reconfig) | Manager back-end → DLSPS REST API | Replaces both the static-JSON Docker Compose flow and the pod-recreation Kubernetes flow at parity (see the DLSPS runtime API delta). |
| Pipeline execution | DLSPS | Reads models from shared model volume; publishes inference output to MQTT. |
| Inference output consumption | Scene Controller | Existing MQTT contract; **no MLOps-integration changes**. |
| Multimodal fusion, tracking, scene state | Scene Controller | Unchanged. |
| Model lifecycle (install, list) | Model Downloader | SceneScape uses listing endpoint only at runtime. |
| Model listing for UI selection | Manager UI → Model Downloader | New runtime call; replaces filesystem-scan behavior of today's `model_directory_view.py`. |
| Model download (production) | External job / ViPPET UI | SceneScape does not call Model Downloader's download endpoint at runtime ([ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision)). |
| Model storage at runtime | Model Downloader (writes) + DLSPS (reads) | Shared model volume; no direct runtime call from DLSPS to Model Downloader. |
| Camera discovery and device configuration | Stream Manager | SceneScape consumes the resulting stream list only; ownership of camera discovery is **not** with SceneScape. |
| Video acquisition (livestream / replay) | Stream Manager | Optional dependency; direct RTSP/file sources remain supported when Stream Manager is not deployed. |
| Calibration-time image acquisition | Auto Camera Calibration; *(deferred)* Stream Manager | Decision deferred per phase (see the Stream Manager consumption delta). |
| Mapping-time image / stream acquisition | Mapping; *(deferred)* Stream Manager | Decision deferred per phase (see the Stream Manager consumption delta). |
| Scene export / import | Manager back-end | Extends today's `manager/src/manager/scene_import.py`; new format defined later in this section. |
| Model training, dataset management | Geti | No SceneScape involvement. |

**Cross-cutting concerns** (applied uniformly across all OEP integrations; mechanisms implemented inside the client libraries described later in this section):

| Concern | Approach |
|---|---|
| **Authentication and certificates** | Per-component credentials configured at deployment; client libraries handle injection and rotation. |
| **Retries and backoff** | Built into each client library with bounded retry counts; SceneScape services treat client-library calls as best-effort and fail visibly when retries are exhausted. |
| **Schema validation** | Inbound payloads (pipeline definitions from ViPPET, model listings from Model Downloader) validated against versioned schemas inside the corresponding client library. |
| **Versioning** | Each client library encodes the supported OEP-component API version range; mismatches surface as a single configuration error rather than scattered runtime failures. |
| **Telemetry and tracing** | OpenTelemetry spans named per OEP component (e.g., `model_downloader.list_models`, `vippet.get_pipeline_definition`); per-component metrics for latency, error rate, retry count. Aligns with the existing observability conventions in `controller/observability/`. |
| **Test doubles** | Each client library ships fakes / mocks usable by all SceneScape-side unit tests; integration tests run against component fakes (see the *Testing & Monitoring* section). |
| **Backwards compatibility** | Two distinct legacy mechanisms (static JSON pipeline configs; custom dynamic K8s pipeline configuration) retain separate parity gates per the *Constraints* and *Rollout / Migration Plan* sections. |

---

*The client-library integration layer, per-contract specifications, per-service deltas, scene export/import format, deployment topology, and the remaining top-level sections (Alternatives, Risks, Rollout, Testing & Monitoring, Open Questions, References) are to be added.*
