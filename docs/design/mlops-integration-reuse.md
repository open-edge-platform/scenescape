# Design Document: Open-Edge-Platform MLOps Integration and Reuse of Pipeline Building and Model Management

- **Author(s)**: [Tomasz Dorau](https://github.com/tdorau)
- **Date**: 2026-06-11
- **Status**: `Proposed`
- **Related ADRs**: [ADR-12 — MLOps Integration and Reuse](../adr/0012-mlops-integration-reuse.md)

---

## 1. Overview

This document specifies the design for implementing [ADR-12](../adr/0012-mlops-integration-reuse.md), which delegates SceneScape's model management, pipeline building, and video acquisition to OEP components. It details the technical contracts, service-level changes, and rollout plan for this integration.

Some cross-service integration details depend on other components' designs (notably ViPPET, the DLSPS runtime pipeline API, and Stream Manager). Those dependencies are called out explicitly throughout the document, and the affected design decisions are deferred to subsequent phases when the dependent designs are ready.

## 2. Goals

The design goals follow directly from [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision):

- Delegate model management, pipeline building, and video acquisition to OEP components.
- Evolve the DLSPS integration to use a runtime API.
- Unify pipeline management across Docker and Kubernetes deployments.
- Preserve SceneScape's ability to run without ViPPET and Stream Manager.
- Keep SceneScape focused on its core spatial-awareness value.
- Preserve backwards compatibility throughout the phased transition.

## 3. Non-Goals

The following are explicitly out of scope of this design document:

- Direct SceneScape↔Geti integration (per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision); Geti is reached indirectly via Model Downloader for models and via Stream Manager for training data).
- The internal API design of Stream Manager (owned by the Stream Manager team).
- ViPPET's internal pipeline templates and verification tooling.
- DLSPS's internal architecture and the design of its runtime pipeline API.
- Concrete UX flows in the SceneScape Manager UI (separate UX/feature work).
- Geti-side integration timelines with ViPPET, Model Downloader, and Stream Manager.
- The exact set of public models that will replace OpenVINO Model Zoo (OMZ) models in default SceneScape pipelines

## 4. Background / Context

This section adds the engineering-level detail that [ADR-12](../adr/0012-mlops-integration-reuse.md) intentionally omits, focusing on specific code paths and implementation details relevant to the integration.

### 4.1 SceneScape Current Implementation

Two capabilities in SceneScape are being **delegated** to new OEP components, and the existing **DLSPS integration is being evolved**.

**Capabilities being delegated:**

1. **Model download** is handled by [`model_installer/`](../../model_installer/), which downloads a basic set of models from the OpenVINO Model Zoo. Model management (listing, uploading, and removing models) is supported only on Kubernetes and is managed through the Manager UI, principally via [`manager/src/manager/model_directory_view.py`](../../manager/src/manager/model_directory_view.py). Using custom models requires manually updating a [model configuration file](../user-guide/other-topics/model-configuration-file-format.md).
2. **Visual pipeline building.** Today handled differently per deployment target:
   - **Docker Compose**: manually authored static JSON files under [`dlstreamer-pipeline-server/`](../../dlstreamer-pipeline-server/) (one per pipeline variant), bind-mounted into DLSPS.
   - **Kubernetes**: A custom generator ([`manager/src/manager/ppl_generator/`](../../manager/src/manager/ppl_generator/)) creates pipelines from high-level settings in the UI. These are materialized as ConfigMaps and applied via [`manager/src/manager/kubeclient.py`](../../manager/src/manager/kubeclient.py).

**Existing DLSPS integration being evolved:**

DLSPS is **already integrated** with SceneScape as the pipeline runtime; this integration is being evolved, not introduced. Two limitations of today's integration drive the evolution:

- DLSPS does not (today) expose a runtime API for arbitrary pipeline reconfiguration, and runs a statically configured number of pipelines. As a consequence, the Kubernetes flow above **recreates DLSPS pods on every pipeline update**. Once DLSPS exposes a runtime pipeline API, SceneScape will use it for true dynamic pipeline lifecycle in both Docker Compose and Kubernetes deployments.
- SceneScape injects custom Python logic — the _SceneScape adapter_ — into DLSPS pipelines via `gvapython` elements. The adapter code lives under [`dlstreamer-pipeline-server/user_scripts/gvapython/sscape/`](../../dlstreamer-pipeline-server/user_scripts/gvapython/sscape/) in the SceneScape repository (not in the DLSPS repository); it is statically injected into DLSPS pipeline configurations and executed by DLSPS at runtime. The `gvapython` element is itself being deprecated upstream in favour of the Gst Analytics Python API. The adapter is monolithic today; refactoring it into smaller, reusable units is a multi-phase activity discussed in the _Open Questions_ section.

### 4.2 SceneScape Component Reference

This subsection defines the SceneScape-internal vocabulary used in the rest of the document. SceneScape is a set of microservices; different sections of this design refer to specific SceneScape services rather than to "SceneScape" as a whole.

#### SceneScape components in scope of (or possibly in scope of) MLOps integration

- **Manager** — today a single Django service ([`manager/`](../../manager/)) combining multiple responsibilities. In subsequent phases, it is recommended (but not required) to split it into three distinct services (or at least containers):

  - **Manager (UI)** — A thin front-end that consumes the backend REST APIs.
  - **Manager (Backend)** — Manages the **scene configuration**, including cameras, scene maps, and persistence. It handles scene import/export, provides the primary REST API for the UI, and is responsible for fetching pipeline definitions from ViPPET to store within the scene configuration.
  - **Pipeline Orchestrator** — A dedicated service responsible for the pipeline lifecycle and interaction with DLSPS. It monitors the database for changes to scene and pipeline configurations and orchestrates the runtime state accordingly (e.g., starting, stopping, or updating pipelines in DLSPS).

  Wherever any of these three entities is referenced in this document, the reference denotes the corresponding part of today's Manager service.

- **Auto Camera Calibration** ([`autocalibration/`](../../autocalibration/)) — computes camera intrinsics and extrinsics from sensor feeds. May consume images from Stream Manager in future phases (decision deferred).

- **Mapping** ([`mapping/`](../../mapping/)) — generates scene 3D models and camera intrinsics and extrinsics based on camera feeds. May consume streams or images from Stream Manager in future phases (decision deferred).

- **`model_installer`** ([`model_installer/`](../../model_installer/)) — the current model-download tool. **Removed** once Model Downloader populates the shared model volume (see the _Proposed Design_ section).

#### Services not in scope of MLOps integration (listed for completeness)

- **Scene Controller** ([`controller/`](../../controller/)) — runtime scene state updates, multimodal sensor fusion, multi-object tracking. Consumes DLSPS inference output via MQTT. **No MLOps-integration changes are planned.**

- **Cluster Analytics** ([`cluster_analytics/`](../../cluster_analytics/)) — not part of the MLOps integration scope.

### 4.3 Constraints driving the design

- **Backwards compatibility window.** Existing deployments using static JSON pipeline configurations (Docker Compose bind-mount) and the custom dynamic pipeline configuration on Kubernetes must remain supported until feature parity with the ViPPET-based flow is achieved.
- **Self-contained exported scenes.** Per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision), exported scenes embed pipeline definitions by value (so deployment does not require ViPPET) and reference models by identifier (so Model Downloader is required at deployment time to materialize the models).
- **Optional Stream Manager.** SceneScape must continue to operate without Stream Manager; direct camera/file sources remain supported.
- **No direct Model Downloader download calls from SceneScape at runtime.** For standalone Scenescape deployments model download is performed out-of-band (e.g., by a deployment-time job or the ViPPET UI).
- **Cross-component design dependencies.** Several design choices (ViPPET pipeline-definition format details, DLSPS runtime API shape, Stream Manager API shape) depend on the corresponding teams' designs and are deferred to the relevant phase.

---

## 5. Proposed Design

### 5.1 Component-level architecture

The component view below shows the runtime relationships between SceneScape and the OEP MLOps components. Only the interactions relevant to MLOps integration are shown; intra-SceneScape interactions (Manager ↔ Scene Controller MQTT, Auto Camera Calibration outputs, etc.) are omitted.

![Component Interaction](./assets/SceneScape_MLOps-Component_Interaction.drawio.svg)

> Each "SceneScape →" arrow in this diagram is realized inside SceneScape by the corresponding **client library** described later in this section (one per OEP component). The diagram is component-level only — protocols, transport, and auth are specified in the per-contract specifications below.

**Component roles** (consolidated from [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision) and the _SceneScape today_ subsection above):

| Component            | Status                                    | Owned data                              | SceneScape's relationship                                                                                       |
| -------------------- | ----------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Model Downloader** | Existing OEP component (new requirements) | Installed models                        | No runtime download calls                                                |
| **ViPPET**           | Existing OEP component (new requirements) | Pipeline templates and definitions      | REST pull of pipeline definitions (Manager back-end); embedded by value into scene exports                      |
| **DLSPS**            | Already integrated; integration evolving  | Running pipelines; inference output     | Runtime pipeline lifecycle via DLSPS REST API (Pipeline Orchestrator); MQTT inference output (Scene Controller) |
| **Stream Manager**   | New OEP component (optional)              | Camera devices, live and captured video | Livestream/replay APIs (Manager Backend and, deferred, Auto Camera Calibration / Mapping)                       |
| **Geti**             | Existing OEP component (no changes)       | Datasets, trained models                | **No direct integration** — mediated via Model Downloader and Stream Manager                                    |

**Data flow at runtime:**

- Models are downloaded by an out-of-band job into a **shared model volume** populated by Model Downloader and read by DLSPS. SceneScape never reads model files directly.
- Pipeline definitions are pulled from ViPPET by Manager back-end, persisted in SceneScape's scene configuration (embedded by value), and pushed to DLSPS via its runtime API.
- Video sources are either consumed from Stream Manager (when deployed) or accessed directly (RTSP/file) when Stream Manager is not deployed.
- DLSPS publishes inference results to MQTT, consumed unchanged by Scene Controller (no MLOps-integration changes to Scene Controller).

### 5.2 End-to-end process model

The process model shows the user-facing workflow for building, packaging, and deploying a SceneScape-based solution that integrates Geti (training), ViPPET (pipeline building), DLSPS (pipeline execution), Stream Manager (video acquisition), Model Downloader (model lifecycle), and SceneScape (scene management and runtime).

![Process Model](./assets/SceneScape_MLOps-Process_Model.drawio.svg)

> **One representative flow.** The diagram presents one representative end-to-end flow. The order of phases is not fixed: stages may be reordered, repeated, skipped, or run in parallel depending on the user's workflow. The stages below describe the canonical happy path used to derive SceneScape's design requirements; they are not a mandatory execution order.

**Stages** (top-to-bottom, summarized):

1. **Camera Setup** — Stream Manager detects and configures camera devices.
2. **Data Acquisition** — Stream Manager captures videos and uploads them to a Geti instance for annotation.
3. **Geti Training** — Geti annotates, trains, and validates the model.
4. **DLS Pipeline Development** — ViPPET downloads the Geti-trained model (via Model Downloader), authors and verifies the DLSPS pipeline.
5. **Scene Development** — SceneScape sets up scenes and cameras, consumes the ViPPET pipeline definition, maps pipelines to sources, starts pipelines. AI-task performance is evaluated.
6. **Package Preparation** — SceneScape exports the scene (self-contained per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision)).
7. **Deployment** — at the production site, Model Downloader materializes the referenced models, SceneScape imports the scene and starts pipelines, Stream Manager runs alongside (when deployed) for video acquisition.

**Properties of the workflow relevant to this design:**

- **No direct SceneScape ↔ Geti arrow.** Confirms the corresponding non-goal stated above.
- **Scene-evaluation feedback loop** (dashed in the diagram) returns to _Annotate_, _Build Pipeline_, or _Capture_ depending on the root cause of poor AI-task performance — the design must keep this loop short, which is why pipeline-to-source mapping is owned scene-side (see _Responsibility matrix_ below) and pipeline updates are dynamic via DLSPS runtime API (see the DLSPS runtime API delta).
- **Development and production deployments are independent.** Each component can be deployed standalone for iterative development; production composition is reconstructed from the exported scene plus the required OEP components.

### 5.3 Responsibility matrix and cross-cutting concerns

This section is the source of truth for _who does what_ in the integrated system. It collapses the per-component breakdown in _SceneScape today_ and the ADR-12 component assignments into a single SceneScape-perspective view, refined to the specific SceneScape services that own each responsibility (per the _SceneScape Component Reference_).

> **Note on Manager service:** Responsibilities are assigned to _Manager (UI)_, _Manager (Backend)_, and _Pipeline Orchestrator_ to guide future development. Until the service is formally split, all three sets of responsibilities reside within the current monolithic Manager service.

**Per-component responsibility matrix:**

_Scene_

| Concern                                  | Owner             | Notes                                                                                             |
| ---------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------- |
| Scene model and persistence              | Manager (Backend) | Scene map, cameras, ROIs, pipeline-to-source mapping.                                             |
| Pipeline-to-source mapping (scene-level) | Manager (Backend) | Persisted SceneScape-side only; ViPPET's internal mapping is not synchronized.                    |
| Multimodal fusion, tracking, dynamic scene state updates | Scene Controller  | Unchanged.                                                                                        |
| Scene export / import                    | Manager (Backend) | Extends today's `manager/src/manager/scene_import.py`; new format defined later in this section. |

_Pipeline_

| Concern                                           | Owner                                  | Notes                                                                                                                                 |
| ------------------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Pipeline authoring                                | ViPPET                                 | SceneScape never authors pipelines.                                                                                                   |
| Pipeline definition consumption                   | Manager (Backend)                      | REST pull from ViPPET; embedded by value into scene exports.                                                                          |
| Pipeline lifecycle (start/stop, dynamic reconfig) | Pipeline Orchestrator → DLSPS REST API | Replaces both the static-JSON Docker Compose flow and the pod-recreation Kubernetes flow at parity (see the DLSPS runtime API delta). |
| Pipeline execution                                | DLSPS                                  | Reads models from shared model volume; publishes inference output to MQTT.                                                            |
| Inference output consumption                      | Scene Controller                       | Existing MQTT contract; **no MLOps-integration changes**.                                                                             |

_Model_

| Concern                          | Owner                                     | Notes                                                                                                                                           |
| -------------------------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Model lifecycle (install, list)  | Model Downloader / ViPPET UI              | No SceneScape involvement.                                                                                                                      |
| Model download (standalone Scenescape deployments)      | External job                  | SceneScape does not call Model Downloader's download endpoint at runtime ([ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision)). |
| Model storage at runtime         | Model Downloader (writes) + DLSPS (reads) | Shared model volume; no direct runtime call from DLSPS to Model Downloader.                                                                     |
| Model training, dataset management | Geti                                    | No SceneScape involvement.                                                                                                                      |

_Source_

| Concern                                   | Owner                                                | Notes                                                                                               |
| ----------------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Camera discovery and device configuration | Stream Manager                                       | SceneScape consumes the resulting stream list only; ownership of camera discovery is **not** with SceneScape. |
| Video acquisition (livestream / replay)   | Stream Manager                                       | Optional dependency; direct RTSP/file sources remain supported when Stream Manager is not deployed. |
| Calibration-time image acquisition        | Auto Camera Calibration; _(deferred)_ Stream Manager | Decision deferred per phase (see the Stream Manager consumption delta).                             |
| Mapping-time image / stream acquisition   | Mapping; _(deferred)_ Stream Manager                 | Decision deferred per phase (see the Stream Manager consumption delta).                             |

**Cross-cutting concerns** (applied uniformly across all OEP integrations; mechanisms implemented inside the client libraries described later in this section):

| Concern                             | Approach                                                                                                                                                                                                                                                             |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Authentication and certificates** | Per-component credentials configured at deployment; client libraries handle injection and rotation.                                                                                                                                                                  |
| **Retries and backoff**             | Built into each client library with bounded retry counts; SceneScape services treat client-library calls as best-effort and fail visibly when retries are exhausted.                                                                                                 |
| **Schema validation**               | Inbound payloads (pipeline definitions from ViPPET) validated against versioned schemas inside the corresponding client library.                                                                                                                                     |
| **Versioning**                      | Each client library encodes the supported OEP-component API version range; mismatches surface as a single configuration error rather than scattered runtime failures.                                                                                                |
| **Telemetry and tracing**           | OpenTelemetry spans named per OEP component (e.g., `vippet.get_pipeline_definition`); per-component metrics for latency, error rate, retry count. Aligns with the existing observability conventions in `controller/observability/`.                                 |
| **Test doubles**                    | Each client library ships fakes / mocks usable by all SceneScape-side unit tests; integration tests run against component fakes (see the _Testing & Monitoring_ section).                                                                                            |
| **Backwards compatibility**         | Two distinct legacy mechanisms (static JSON pipeline configs; custom dynamic K8s pipeline configuration) retain separate parity gates per the _Constraints_ and _Rollout / Migration Plan_ sections.                                                                 |

### 5.4 Client-library integration layer

To avoid each SceneScape service implementing its own HTTP/MQTT plumbing, schema validation, retries, and telemetry against every OEP component, all OEP-component integrations are encapsulated in **client libraries**: small Python packages on the SceneScape side, one per OEP component, consumed by the SceneScape services that interact with that component.

**Rationale.**

- **Reduce the integration surface.** Each OEP component's wire-level details (auth, retries, schemas, version negotiation, telemetry) live in exactly one place. SceneScape services consume a typed Python API.
- **Avoid tight coupling.** When an OEP component evolves (new endpoints, new payload fields, breaking-change versions), the change is absorbed inside its client library; SceneScape services see a stable Python API or a single deliberate API-evolution change.
- **Enable parallel SceneScape work.** Multiple SceneScape services (Manager back-end, Manager UI, Auto Camera Calibration, Mapping) can adopt the same OEP component without duplicating integration code.
- **Make testing tractable.** Each client library ships fakes / mocks; SceneScape-service tests run against those fakes without standing up an OEP component.

**Naming convention.** _<Component> client library_ (e.g., _Model Downloader client library_, _ViPPET client library_). The term "client" deliberately does **not** mean "thin HTTP wrapper" — a client library owns the full set of cross-cutting concerns listed in the matrix above, not just transport. The name _adapter_ is reserved for the existing SceneScape-authored DLSPS extensions (`gvapython` code injected into DLSPS); the two concepts are distinct.

**Client libraries.**

| Client library                  | OEP component    | SceneScape consumers                                                                                             | Status                                                                                       |
| ------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Model Downloader client library | Model Downloader | Deployment job / scripts (out-of-band download)                                                                  | New                                                                                          |
| ViPPET client library           | ViPPET           | Manager (Backend) (REST pull of pipeline definitions)                                                            | New                                                                                          |
| DLSPS client library            | DLSPS            | Pipeline Orchestrator (runtime pipeline lifecycle); Scene Controller (MQTT inference output — existing contract) | New for the runtime pipeline API; existing for MQTT (already encapsulated in `scene_common`) |
| Stream Manager client library   | Stream Manager   | Manager (Backend) (livestream / replay consumption); _(deferred)_ Auto Camera Calibration, Mapping               | New                                                                                          |

There is **no Geti client library** — SceneScape has no direct integration with Geti.

**Concerns each client library owns** (these are realizations of the cross-cutting concerns listed above):

- Transport (HTTP / MQTT / etc.), authentication, certificate handling, timeouts.
- Typed Python API surface (request/response data classes) consumed by SceneScape services.
- Schema validation of inbound payloads against versioned schemas.
- Bounded retries with backoff; deterministic failure modes.
- OpenTelemetry instrumentation (spans, metrics) named per OEP component.
- API-version negotiation and version-mismatch reporting.
- Test doubles (fakes / mocks) for downstream SceneScape-service tests.

**Open questions for this layer:**

- **Repository location.** Three candidate placements are possible: (A) extend [`scene_common/`](../../scene_common/) with an `integration/` subpackage (one module per OEP component); (B) introduce a new top-level shared library (e.g., `integration_clients/`); (C) decide per component. This decision is **deferred** and tracked in the _Open Questions_ section.
- **Distribution and versioning model** (single shared library vs. independently versioned per-component packages) follows from the repository-location choice and is deferred with it.

### 5.5 Per-contract specifications

This section specifies the integration contracts between SceneScape and each OEP component: the endpoints SceneScape consumes, the data SceneScape exchanges, and the SceneScape service that owns the call. Each contract is implemented inside the corresponding client library described above; the table rows therefore double as the public Python-API surface of each library.

Contracts are presented at the level of detail required for SceneScape-side design (endpoint identity, payload shape, ownership, frequency, failure mode). Wire-level specifications (exact URL paths, request/response JSON schemas, authentication mechanisms) are owned by the corresponding OEP-component teams and referenced from the _References_ section once published; where a SceneScape-side decision depends on a not-yet-finalized OEP-component design, this is called out explicitly.

> **Manager service split.** As noted in the _Responsibility matrix_, "Manager back-end" and "Manager UI" labels are recommendations; the decision to split today's monolithic Manager is deferred. Until the split is decided, all contracts assigned to Manager back-end or Manager UI are implemented inside the current Manager service.

#### 5.5.1 SceneScape ↔ Model Downloader

**No runtime contract.** SceneScape does not call Model Downloader at runtime. The integration point is the shared model volume: Model Downloader writes model files to the volume at deployment time; DLSPS reads from it during pipeline execution. Model identity (name, hub, precision) is embedded in pipeline definitions sourced from ViPPET and recorded in scene exports — no runtime enumeration call from any SceneScape service is required.

**SceneScape does not call Model Downloader's download or listing endpoints at runtime.** Both are performed out-of-band: download by an external job or via the ViPPET UI; listing (if needed) by deployment tooling only.

#### 5.5.2 SceneScape ↔ ViPPET

**Purpose.** Consume pipeline definitions authored in ViPPET and persist them in SceneScape's scene configuration.

| Aspect                    | Specification                                                                                                                                                                                                                                                  |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SceneScape consumer       | Manager back-end                                                                                                                                                                                                                                               |
| Client library            | ViPPET client library                                                                                                                                                                                                                                          |
| Endpoint consumed         | ViPPET pipeline-definition REST endpoint (exact URL/shape owned by the ViPPET team; client library absorbs the wire detail).                                                                                                                                   |
| Direction                 | SceneScape → ViPPET (REST pull, per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision))                                                                                                                                                       |
| Payload                   | A pipeline definition containing: a DLSPS-consumable pipeline definition body, parametrized model reference(s) by ID + version, and pipeline metadata. **Models are parameters of the pipeline definition; they are referenced by identifier — not embedded.** |
| Frequency                 | On-demand at scene-development time (user selects/updates a pipeline definition for a scene). Cached by the client library; retrieved-once-then-embedded into the scene config.                                                                                |
| Persistence in SceneScape | The fetched pipeline definition is **persisted by value** in SceneScape's scene configuration so the scene is self-contained (deployable without ViPPET).                                                                                                      |
| Failure mode              | Fetch failures surface as a UI error at the time of selection; once a pipeline definition is persisted in a scene, no further ViPPET call is required.                                                                                                         |

**Open dependency.** The exact pipeline-definition format (parametrization syntax, version envelope) depends on ViPPET's design and is tracked in _Open Questions_.

#### 5.5.3 SceneScape ↔ DLSPS

**Purpose.** Drive the runtime lifecycle of DLSPS pipelines (start, stop, reconfigure) and consume inference output. This integration is evolving from the static-JSON + pod-recreation mechanisms toward a runtime REST API.

| Aspect                                           | Specification                                                                                                                                                                                         |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SceneScape consumer (runtime pipeline lifecycle) | Manager back-end                                                                                                                                                                                      |
| SceneScape consumer (inference output)           | Scene Controller                                                                                                                                                                                      |
| Client library                                   | DLSPS client library (new for the runtime pipeline API); existing MQTT-consumption code in `scene_common` for inference output                                                                        |
| Pipeline-lifecycle endpoint                      | DLSPS runtime REST API for start / stop / reconfigure (exact shape owned by the DLSPS team).                                                                                                          |
| Direction                                        | SceneScape → DLSPS (REST control); DLSPS → Scene Controller (MQTT inference output, **existing contract, unchanged**).                                                                                |
| Payload (lifecycle)                              | A pipeline-instance descriptor including: the (already-resolved) pipeline definition from ViPPET, the source binding (Stream Manager URL, direct RTSP/file, etc.), and any per-instance parameters.   |
| Payload (inference output)                       | Per-frame inference results published to MQTT topics consumed by Scene Controller — **schema unchanged from today**.                                                                                  |
| Frequency (lifecycle)                            | At scene start/stop and on any pipeline-to-source mapping change.                                                                                                                                     |
| Frequency (inference output)                     | Per inference (continuous, high rate).                                                                                                                                                                |
| Failure mode                                     | Lifecycle-call failures surface to Manager back-end; the legacy pod-recreation (Kubernetes) and static-JSON (Docker Compose) mechanisms remain available until parity, per the _Constraints_ section. |

**SceneScape-authored DLSPS extensions.** The `gvapython`-based extension code under [`dlstreamer-pipeline-server/user_scripts/gvapython/sscape/`](../../dlstreamer-pipeline-server/user_scripts/gvapython/sscape/) is statically injected into DLSPS pipeline configurations and runs inside the DLSPS pipeline process. It is **not** part of the DLSPS client library (the client library is a SceneScape-side Python API; the extensions run inside DLSPS). Its migration from `gvapython` to the Gst Analytics Python API and its breakdown into smaller units are tracked in _Open Questions_.

#### 5.5.4 SceneScape ↔ Stream Manager

**Purpose.** Consume live video sources and replays from Stream Manager when Stream Manager is deployed. Stream Manager is an **optional** dependency; SceneScape continues to support direct RTSP/file sources when Stream Manager is not deployed.

| Aspect              | Specification                                                                                                                                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SceneScape consumer | Manager back-end (livestream / replay URLs for pipeline source binding); _(deferred)_ Auto Camera Calibration, Mapping                                                                                                                  |
| Client library      | Stream Manager client library                                                                                                                                                                                                           |
| Endpoints consumed  | Stream Manager livestream / replay APIs (exact shape owned by the Stream Manager team; per the _SceneScape team: livestreams/replays API_ line item in the Stream Manager proposal).                                                    |
| Direction           | SceneScape → Stream Manager (REST control + stream consumption)                                                                                                                                                                         |
| Payload             | Stream URLs / handles for livestream and replay; camera metadata used to populate scene-configuration camera entries.                                                                                                                   |
| Frequency           | At scene-configuration time (camera enumeration) and at runtime (stream URL resolution at pipeline start).                                                                                                                              |
| Failure mode        | When Stream Manager is not deployed, the client library is not loaded and source-binding falls back to direct RTSP/file sources. When Stream Manager is deployed but unreachable, errors surface to Manager back-end at pipeline start. |

**Deferred SceneScape consumers.** Whether Auto Camera Calibration and Mapping consume from Stream Manager (in addition to or instead of their current direct-source paths) is a per-phase decision tracked under the Stream Manager consumption delta in the _Rollout / Migration Plan_ section.

#### 5.5.5 SceneScape ↔ Geti

**No direct contract.** Per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision), SceneScape does not integrate with Geti directly. Geti is reached only indirectly:

- **Models** flow from Geti to SceneScape via Model Downloader (which populates the shared model volume read by DLSPS).
- **Training videos** flow from cameras to Geti via Stream Manager.

There is therefore no SceneScape-side client library for Geti and no row in the contracts above.

### 5.6 Per-service SceneScape deltas

This section enumerates the concrete changes SceneScape must absorb to participate in the target architecture. Each delta names the SceneScape services touched, the client library involved, the affected SceneScape modules, the parity criterion that gates removal of any legacy mechanism, and a **decision-timing** note (_decided now_ — the service-ownership assignment is established in this design; _deferred per phase_ — the assignment is left to the phase that delivers the delta).

> **Manager service split.** As elsewhere in this document, _Manager back-end_ and _Manager UI_ labels in the deltas below are recommendations; the Manager split decision is deferred. Until that decision is taken, all changes assigned to Manager back-end or Manager UI are implemented inside the current monolithic Manager service.

The deltas are organized by area of work, and the rollout plan in the _Rollout / Migration Plan_ section maps them to deployment phases.

#### 5.6.1 Stream Manager consumption

| Aspect                      | Specification                                                                                                                                                                                                                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Consume Stream Manager APIs for video sources (livestream, replay) in addition to today's direct RTSP / file sources.                                                                                                                                                                 |
| SceneScape consumers        | Manager back-end (camera enumeration, stream URL resolution for pipeline source binding); _(deferred)_ Auto Camera Calibration (calibration-time images); _(deferred)_ Mapping (streams / images); _(deferred)_ a path for DLSPS to consume streams directly.                         |
| Client library              | Stream Manager client library.                                                                                                                                                                                                                                                        |
| Affected SceneScape modules | Camera-source binding inside Manager back-end (camera-source persistence, pipeline-source resolution). When deferred consumers are activated: corresponding source-acquisition code paths in Auto Camera Calibration and Mapping.                                                     |
| Parity criterion            | Feature parity is **per consumer**: each SceneScape service that adopts Stream Manager retains its direct-source path until its Stream Manager consumption is validated end-to-end. Stream Manager remains an optional dependency overall — there is no "remove direct sources" gate. |
| Decision timing             | **Deferred per phase.** Manager back-end's Stream Manager consumption is the anchor consumer (Phase 3 in the rollout plan). The other consumers (Auto Camera Calibration, Mapping, the DLSPS-side path) are decided in their respective phases as the corresponding designs solidify. |
| Cross-component dependency  | Stream Manager API design (livestream / replay endpoints), owned by the Stream Manager team.                                                                                                                                                                                          |

#### 5.6.2 ViPPET pipeline-definition consumption

| Aspect                      | Specification                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Consume ViPPET pipeline definitions as a first-class source of pipeline configuration, replacing both the manually authored static JSON files (Docker Compose) and the custom pipeline generation (Kubernetes).                                                                                                                                                                                                                                                                                                                                                       |
| SceneScape consumers        | Manager back-end.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Client library              | ViPPET client library.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Affected SceneScape modules | New consumer in Manager back-end for pulling pipeline definitions and persisting them by value in the scene model. Legacy mechanisms scoped for removal at parity: the static JSON files under [`dlstreamer-pipeline-server/`](../../dlstreamer-pipeline-server/) and the custom pipeline generator at [`manager/src/manager/ppl_generator/`](../../manager/src/manager/ppl_generator/). The Kubernetes config-map writer in [`manager/src/manager/kubeclient.py`](../../manager/src/manager/kubeclient.py) is affected by the DLSPS runtime API delta, not this one. |
| Parity criterion            | A scene configured exclusively via ViPPET-supplied pipeline definitions reproduces the AI-task behavior of the equivalent scene configured via today's static JSON / custom pipeline generation, for the supported set of pipelines. Each of the two legacy mechanisms (Docker Compose static JSON; Kubernetes custom pipeline generation) has its **own** parity gate per the _Constraints_ section.                                                                                                                                                                 |
| Decision timing             | **Decided now** — Manager back-end is the consumer.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| Cross-component dependency  | ViPPET pipeline-definition format (parametrization syntax, version envelope), owned by the ViPPET team. The exact format is tracked in _Open Questions_.                                                                                                                                                                                                                                                                                                                                                                                                              |

#### 5.6.3 Model Downloader adoption

| Aspect                      | Specification                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Replace SceneScape's custom model download with the shared-model-volume model populated by Model Downloader.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| SceneScape consumers        | None at runtime. Model identity is embedded in pipeline definitions sourced from ViPPET; no SceneScape service calls Model Downloader at runtime.                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| Client library              | Model Downloader client library.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Affected SceneScape modules | [`model_installer/`](../../model_installer/) **removed** in favor of the shared model volume populated by Model Downloader (download is out-of-band per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision)). [`manager/src/manager/model_directory_view.py`](../../manager/src/manager/model_directory_view.py) **removed** — model identity is embedded in pipeline definitions from ViPPET; no separate model-listing step is required. SceneScape-specific model-configuration conventions ([model-configuration-file-format](../user-guide/other-topics/model-configuration-file-format.md)) retired.  |
| Parity criterion            | (a) An equivalent set of models can be installed via Model Downloader and consumed by DLSPS for the supported set of pipelines; (b) the OMZ-to-public-models migration (tracked in _Open Questions_) does not regress the default SceneScape pipelines.                                                                                                                                                                                                                                                                                                                                                                      |
| Decision timing             | **Decided now** — `model_installer` is removed; SceneScape has no runtime interaction with Model Downloader.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Cross-component dependency  | Shared-volume model-storage convention.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

#### 5.6.4 Scene-level pipeline-to-source mapping

| Aspect                      | Specification                                                                                                                                                                                                                                                           |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Persist and manage the binding between pipeline definitions and the camera sources they run against, scene-side. Different cameras in the same scene serve different spatial-awareness tasks; a pipeline definition can be mapped to one or more sources (one-to-many). |
| SceneScape consumers        | Manager back-end (scene-model owner).                                                                                                                                                                                                                                   |
| Client library              | None — internal to SceneScape. The mapping is consumed by the DLSPS client library (when starting pipeline instances) and embedded in scene exports by the export/import code; it is not itself an OEP integration.                                                     |
| Affected SceneScape modules | Scene model in Manager back-end (new persistent field set for the pipeline-definition-to-source mapping). Scene Controller is **not** affected: it continues to consume the existing per-camera MQTT inference output.                                                  |
| Parity criterion            | Every pipeline-to-source binding expressible via today's mechanisms (static JSON pipeline configurations for Docker Compose; custom pipeline generation for Kubernetes) is expressible via the scene-side mapping.                                                      |
| Decision timing             | **Decided now** — Manager back-end owns the scene model.                                                                                                                                                                                                                |
| Cross-component dependency  | None directly; depends on the ViPPET-pipeline-definition delta for the identity of pipeline definitions that the mapping references.                                                                                                                                    |

#### 5.6.5 DLSPS runtime pipeline API

| Aspect                      | Specification                                                                                                                                                                                                                                                                                                                                             |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Drive DLSPS pipeline lifecycle (start, stop, reconfigure) via DLSPS's runtime REST API once available, replacing today's static-JSON bind-mount mechanism (Docker Compose) and pod-recreation mechanism (Kubernetes).                                                                                                                                     |
| SceneScape consumers        | Manager back-end (lifecycle calls). Scene Controller (MQTT inference output) — **unchanged**.                                                                                                                                                                                                                                                             |
| Client library              | DLSPS client library (new for the runtime pipeline API). The existing MQTT-consumption code in `scene_common` covers inference output and does not change.                                                                                                                                                                                                |
| Affected SceneScape modules | New lifecycle-management code in Manager back-end. Legacy mechanisms scoped for removal at parity: the Kubernetes config-map writer + pod-recreation logic in [`manager/src/manager/kubeclient.py`](../../manager/src/manager/kubeclient.py); the static-JSON bind-mount wiring under [`dlstreamer-pipeline-server/`](../../dlstreamer-pipeline-server/). |
| Parity criterion            | Both legacy reconfiguration mechanisms are retired and replaced by the DLSPS runtime API across both deployment targets (Docker Compose and Kubernetes). This is the exit criterion of the final rollout phase.                                                                                                                                           |
| Decision timing             | **Decided now** — Manager back-end is the runtime-API consumer. The legacy pod-recreation behavior remains available as a fall-back until the parity gate is met.                                                                                                                                                                                         |
| Cross-component dependency  | DLSPS runtime REST API design, owned by the DLSPS team. The migration of the existing SceneScape-authored DLSPS extensions from `gvapython` to the Gst Analytics Python API is a related but separately tracked activity in _Open Questions_ — it does not block this delta but proceeds in parallel.                                                     |

#### 5.6.6 Scene export / import

| Aspect                      | Specification                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Extend SceneScape's scene export/import to produce a **self-contained** scene artifact suitable for production deployment: pipeline definitions are embedded by value (deployment does not require ViPPET); models are referenced by identifier (Model Downloader required at deployment time to materialize the models).                                                                                                                                                                                            |
| SceneScape consumers        | Manager back-end.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Client library              | None — internal to SceneScape. The exported artifact references identities consumed by the Model Downloader and ViPPET client libraries at runtime, but the export/import flow itself is internal.                                                                                                                                                                                                                                                                                                                   |
| Affected SceneScape modules | Extends today's [`manager/src/manager/scene_import.py`](../../manager/src/manager/scene_import.py). New fields (per the cross-references in the _Background_ section and the canonical wording above): embedded pipeline definitions; model references by identifier with model ID and version recorded in both camera and scene metadata (hashes for verification); the scene-level pipeline-definition-to-source mapping from the corresponding delta. The exact on-disk format is defined in the next subsection. |
| Parity criterion            | A scene exported under the new format can be imported on a fresh deployment that has Model Downloader available, and produces the same runtime behavior as the source deployment. Existing scenes (legacy format) remain importable for the duration of the backwards-compatibility window.                                                                                                                                                                                                                          |
| Decision timing             | **Decided now** — Manager back-end owns scene export/import.                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Cross-component dependency  | None directly; depends on Model Downloader's identifier scheme (for the model references in the artifact) and on ViPPET's pipeline-definition format (for the embedded pipeline definitions).                                                                                                                                                                                                                                                                                                                        |

### 5.7 Scene export / import format — delta vs. today

This section captures **only the delta** between today's scene export/import (extended from [`manager/src/manager/scene_import.py`](../../manager/src/manager/scene_import.py)) and the new format required by this design. It does not re-specify the existing format. The concrete container shape (single JSON document, multi-file bundle, or archive) is deferred to implementation (tracked in _Open Questions_).

**Delta** (driven by [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision) and the scene-export/import delta):

1. **Camera configuration stored separately from pipeline definitions.** Each camera entry carries its source identity (Stream Manager handle, direct RTSP URL, or file path) and calibration (intrinsics, extrinsics, pose). Cameras are no longer co-located with pipeline-specific fields.
2. **Model metadata is part of the pipeline definition**, supplied as a template-parameter value (per the ViPPET-pipeline-definition delta: models are parameters of pipeline definitions, referenced by ID + version). Pipeline definitions are embedded by value in the artifact so deployment does not require ViPPET. Models themselves are referenced by identifier only — no model files are embedded; Model Downloader materializes them at deployment time.
3. **Pipeline-to-camera mapping** is a first-class section of the artifact, serializing the scene-side mapping owned by Manager back-end (per the scene-level pipeline-to-source mapping delta). A pipeline definition can map to one or more cameras (one-to-many).

Existing scenes exported under the legacy format remain importable for the duration of the backwards-compatibility window defined in the _Constraints_ section.

### 5.8 Deployment topology

This section specifies the deployment-time arrangement of SceneScape and the OEP components it integrates with, for both supported targets: Docker Compose and Kubernetes. The topology is the same shape on both targets — only the orchestration mechanism differs.

**Components in the SceneScape deployment.**

| Component                                                                                         | Required                              | Notes                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SceneScape services (Manager, Scene Controller, Auto Camera Calibration; _experimental_: Mapping) | Yes                                   | The current set of microservices, less `model_installer` after the Model Downloader delta.                                                                             |
| DL Streamer Pipeline Server (DLSPS)                                                               | Yes                                   | Runtime pipeline executor; reads models from the shared model volume; publishes MQTT inference output.                                                                 |
| Shared model volume                                                                               | Yes                                   | Written by Model Downloader, read by DLSPS. SceneScape does not read model files directly.                                                                             |
| Model Downloader                                                                                  | Required at deployment time           | Populates the shared model volume. SceneScape has no runtime interaction with Model Downloader.                                                                        |
| Stream Manager                                                                                    | Optional                              | When deployed, provides livestream / replay; when absent, SceneScape uses direct RTSP / file sources.                                                                  |
| ViPPET                                                                                            | **Not required at deployment time**   | Pipeline definitions are embedded by value in the scene artifact per the scene export/import format above. ViPPET is used during scene development, not in production. |
| Geti                                                                                              | Not at the SceneScape deployment site | Geti is reached only indirectly during the upstream training stages of the workflow.                                                                                   |

**Shared model volume.**

The shared model volume is the integration point between Model Downloader (writer) and DLSPS (reader). It is materialized differently per target:

- **Docker Compose.** A named Docker volume mounted into the DLSPS container and into the deployment-time Model Downloader job/container.
- **Kubernetes.** A PersistentVolumeClaim mounted into the DLSPS pod(s) and into the Model Downloader job/pod. SceneScape services do not mount this volume.

The volume holds model files written by Model Downloader and read by DLSPS at pipeline runtime. SceneScape services do not access the volume or enumerate its contents.

**Multi–Model-Downloader topology (open).**

ViPPET may be deployed with its own embedded Model Downloader instance during development. If the development setup and the SceneScape deployment use separate Model Downloader instances writing to separate model volumes, the deployment design must disambiguate which Model Downloader instance owns which model volume. Two options are under consideration:

- **(O1) Single shared Model Downloader instance** across ViPPET and SceneScape — simplest; no model duplication; requires reachability between the two deployments.
- **(O2) Separate Model Downloader instances, separate volumes** — clean separation; models must be re-downloaded into the SceneScape-side volume at production-deployment time using the IDs recorded in the exported scene.

The choice is tracked in _Open Questions_ and is independent of the SceneScape-side deltas: SceneScape behavior is identical across O1 and O2 — SceneScape has no runtime calls to Model Downloader; the shared model volume boundary is the only coupling between the two deployments.

**Stream Manager opt-in.**

Stream Manager is added to the topology only when source acquisition through Stream Manager is required. The Stream Manager client library is the only point where its presence or absence matters to SceneScape services: when Stream Manager is not deployed, source bindings in the scene artifact resolve to direct RTSP / file sources without any code path through the client library.

**Network and authentication.**

Per-component credentials (ViPPET pipeline-definition endpoint when used during development, DLSPS runtime API, Stream Manager livestream / replay) are configured at deployment time and injected into the corresponding client libraries. Existing SceneScape secret-management mechanisms (under [`manager/secrets/`](../../manager/secrets/) and propagated via Docker Compose secrets or Kubernetes Secrets) are extended to cover the new credentials. The detailed list of credentials per component follows from the corresponding teams' API specifications.

---

## 6. Alternatives Considered

The architectural alternatives for the integration as a whole are evaluated in [ADR-12 §Alternatives Considered](../adr/0012-mlops-integration-reuse.md#alternatives-considered) and not repeated here.

This section records design-level alternatives that arose specifically while drafting _how_ the integration is implemented.

| Alternative                                                                                                                                                              | Considered for                    | Outcome                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Per-service direct integration** with each OEP component (no shared client libraries; each SceneScape service implements its own transport, auth, retries, telemetry). | Client-library integration layer. | **Rejected** in favor of one client library per OEP component, to reduce the integration surface, absorb OEP-component API churn in one place, and enable parallel adoption across SceneScape services. |

## 7. Rollout / Migration Plan

The integration is rolled out in four phases, with each phase delivering a subset of the six deltas defined in the _Per-service SceneScape deltas_ section. The mapping of deltas to phases is chosen to deliver end-to-end value at each step and to manage cross-component dependencies.

| Phase       | Deltas delivered                                                                                  | Key outcome                                                                                                                                                  |
| ----------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Phase 1** | **(3) Model Downloader adoption.**                                                                | `model_installer` is removed. SceneScape UI lists models from Model Downloader.                                                                              |
| **Phase 2** | **(2) ViPPET pipeline-definition consumption.**<br>**4) Scene-level pipeline-to-source mapping.** | SceneScape can consume ViPPET pipeline definitions and map them to sources. Legacy pipeline mechanisms (static JSON, custom K8s generation) remain in place. |
| **Phase 3** | **(1) Stream Manager consumption** (Manager back-end only).<br>**(6) Scene export/import.**       | SceneScape can consume from Stream Manager and can export/import self-contained scenes.                                                                      |
| **Phase 4** | **(5) DLSPS runtime pipeline API.**                                                               | Legacy pipeline mechanisms are removed. DLSPS pipeline lifecycle is fully dynamic.                                                                           |

**Parity gates.** Each legacy mechanism (static JSON pipeline configurations for Docker Compose; custom dynamic pipeline configuration on Kubernetes) has its own parity gate per the _Constraints_ section. A legacy mechanism is removed only when its full capability is reproduced by the new flow. The DLSPS runtime API delta in Phase 4 is the final gate for removing both.

## 8. Testing & Monitoring

**Testing.**

- **Client libraries.** Each client library is tested in isolation with unit tests against its test doubles (fakes/mocks).
- **SceneScape services.** Service-level unit tests consume the client-library test doubles.
- **Integration tests.** A new suite of functional tests (`tests/functional/mlops/`) is added, one test per delta. These tests run against OEP-component fakes or stubs, not live components.
- **End-to-end tests.** The existing basic acceptance tests (`tests/functional/test_basic_acceptance.py`) are extended to cover one end-to-end happy path for each phase's key outcome.

**Monitoring.**

- **Telemetry.** Per the _Cross-cutting concerns_ matrix, each client library emits OpenTelemetry spans and metrics (latency, error rate, retry count) for its downstream OEP component. These are scraped and visualized using the existing observability stack.
- **Health checks.** The existing health-check mechanisms are extended to include the reachability of each required OEP component's API endpoint.

## 9. Open Questions

This section consolidates all deferred decisions and open questions called out in the sections above.

- **Client-library repository location.** Three candidate placements are possible: (A) extend [`scene_common/`](../../scene_common/) with an `integration/` subpackage; (B) introduce a new top-level shared library (e.g., `integration_clients/`); (C) decide per component. The distribution and versioning model follows from this choice.
- **ViPPET pipeline-definition format.** The exact format for pipeline definitions consumed from ViPPET, especially the model-parametrization syntax and the version envelope, depends on the ViPPET team's design.
- **Multi–Model-Downloader topology.** The choice between a single shared Model Downloader instance (O1) and separate instances with separate volumes (O2) for development vs. production deployments.
- **`gvapython` to Gst Analytics Python migration.** The detailed plan for migrating the SceneScape-authored DLSPS extensions from the deprecated `gvapython` element to the Gst Analytics Python API, and for refactoring the monolithic adapter into smaller, reusable units. This proceeds in parallel with the DLSPS runtime API delta.
- **Stream Manager consumption by deferred consumers.** The decision on whether (and when) Auto Camera Calibration and Mapping will consume from Stream Manager.
- **Manager service split.** The decision on whether (and when) to split today's monolithic Manager service into separate back-end and UI services.
- **Scene-artifact container shape.** The concrete on-disk format for exported scenes (single JSON document, multi-file bundle, or archive).

## 10. References

- [ADR-12 — MLOps Integration and Reuse](../adr/0012-mlops-integration-reuse.md)
- Diagrams:
  - [Component Interaction](./assets/SceneScape_MLOps-Component_Interaction.drawio.svg)
  - [Process Model](./assets/SceneScape_MLOps-Process_Model.drawio.svg)
