# Design Document: Open-Edge-Platform MLOps Integration and Reuse of Pipeline Building and Model Management

- **Author(s)**: [Tomasz Dorau](https://github.com/tdorau)
- **Date**: 2026-06-11
- **Status**: `Proposed`
- **Related ADRs**: [ADR-12 — MLOps Integration and Reuse](../adr/0012-mlops-integration-reuse.md)

---

## 1. Overview

This document specifies the design for implementing [ADR-12](../adr/0012-mlops-integration-reuse.md), which delegates Scenescape's model management, pipeline building, and video acquisition to OEP components. It details the technical contracts, service-level changes, and rollout plan for this integration.

Some cross-service integration details depend on other components' designs (notably ViPPET, the DLSPS runtime pipeline API, and Stream Manager). Those dependencies are called out explicitly throughout the document, and the affected design decisions are deferred to subsequent phases when the dependent designs are ready.

## 2. Goals

The design goals follow directly from [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision):

- Delegate model management, pipeline building, and video acquisition to OEP components.
- Evolve the DLSPS integration to use a runtime API.
- Unify pipeline management across Docker and Kubernetes deployments.
- Preserve Scenescape's ability to run without ViPPET and Stream Manager.
- Keep Scenescape focused on its core spatial-awareness value.
- Preserve backwards compatibility throughout the phased transition.

## 3. Non-Goals

The following are explicitly out of scope of this design document:

- Direct SceneScape↔Geti integration (per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision); Geti is reached indirectly via Model Downloader for models and via Stream Manager for training data).
- The internal API design of Stream Manager (owned by the Stream Manager team).
- ViPPET's internal pipeline templates and verification tooling.
- DLSPS's internal architecture and the design of its runtime pipeline API.
- Concrete UX flows in the Scenescape Manager UI (separate UX/feature work).
- Geti-side integration timelines with ViPPET, Model Downloader, and Stream Manager.
- The exact set of public models that will replace OpenVINO Model Zoo (OMZ) models in default Scenescape pipelines

## 4. Background / Context

This section adds the engineering-level detail that [ADR-12](../adr/0012-mlops-integration-reuse.md) intentionally omits, focusing on specific code paths and implementation details relevant to the integration.

### 4.1 Scenescape Current Implementation

Two capabilities in Scenescape are being **delegated** to new OEP components, and the existing **DLSPS integration is being evolved**.

**Capabilities being delegated:**

1. **Model download** is handled by [`model_installer/`](../../model_installer/), which downloads a basic set of models from the OpenVINO Model Zoo. Model management (listing, uploading, and removing models) is supported only on Kubernetes and is managed through the Manager UI, principally via [`manager/src/manager/model_directory_view.py`](../../manager/src/manager/model_directory_view.py). Using custom models requires manually updating a [model configuration file](../user-guide/other-topics/model-configuration-file-format.md).
2. **Visual pipeline building.** Today handled differently per deployment target:
   - **Docker Compose**: manually authored static JSON files under [`dlstreamer-pipeline-server/`](../../dlstreamer-pipeline-server/) (one per pipeline variant), bind-mounted into DLSPS.
   - **Kubernetes**: A custom generator ([`manager/src/manager/ppl_generator/`](../../manager/src/manager/ppl_generator/)) creates pipelines from high-level settings in the UI. These are materialized as ConfigMaps and applied via [`manager/src/manager/kubeclient.py`](../../manager/src/manager/kubeclient.py).

**Existing DLSPS integration being evolved:**

DLSPS is **already integrated** with Scenescape as the pipeline runtime; this integration is being evolved, not introduced. Two limitations of today's integration drive the evolution:

- DLSPS does not (today) expose a runtime API for arbitrary pipeline reconfiguration, and runs a statically configured number of pipelines. As a consequence, the Kubernetes flow above **recreates DLSPS pods on every pipeline update**. Once DLSPS exposes a runtime pipeline API, Scenescape will use it for true dynamic pipeline lifecycle in both Docker Compose and Kubernetes deployments.
- Scenescape injects custom Python logic — the _SceneScape adapter_ — into DLSPS pipelines via `gvapython` elements. The adapter code lives under [`dlstreamer-pipeline-server/user_scripts/gvapython/sscape/`](../../dlstreamer-pipeline-server/user_scripts/gvapython/sscape/) in the Scenescape repository (not in the DLSPS repository); it is statically injected into DLSPS pipeline configurations and executed by DLSPS at runtime. The `gvapython` element is itself being deprecated upstream in favour of the Gst Analytics Python API. The adapter is monolithic today; refactoring it into smaller, reusable units is a multi-phase activity discussed in the _Open Questions_ section.

### 4.2 Scenescape Component Reference

This subsection defines the Scenescape-internal vocabulary used in the rest of the document. Scenescape is a set of microservices; different sections of this design refer to specific Scenescape services rather than to "Scenescape" as a whole.

#### Scenescape components in scope of (or possibly in scope of) MLOps integration

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
- **Self-contained exported scenes.** Per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision), exported scenes embed pipeline definitions by value (deployment does not require ViPPET) and reference models by identifier (no model files in the scene artifact). Populating the shared model volume is the deployment operator's responsibility; the two supported deployment paths are described in the _Scene export / import format_ section.
- **Optional Stream Manager.** Scenescape must continue to operate without Stream Manager; direct camera/file sources remain supported.
- **No direct Model Downloader download calls from Scenescape at runtime.** For standalone Scenescape deployments model download is performed out-of-band (e.g., by a deployment-time job or the ViPPET UI).
- **Cross-component design dependencies.** Several design choices (ViPPET pipeline-definition format details, DLSPS runtime API shape, Stream Manager API shape) depend on the corresponding teams' designs and are deferred to the relevant phase.

---

## 5. Proposed Design

### 5.1 Component-level architecture

The component view below shows the runtime relationships between Scenescape and the OEP MLOps components. Only the interactions relevant to MLOps integration are shown; intra-Scenescape interactions (Manager ↔ Scene Controller MQTT, Auto Camera Calibration outputs, etc.) are omitted.

![Component Interaction](./assets/Scenescape_MLOps-Component_Interaction.drawio.svg)

> Each "Scenescape →" arrow in this diagram is realized inside Scenescape by the corresponding **client library** described later in this section (one per OEP component). The diagram is component-level only — protocols, transport, and auth are specified in the per-contract specifications below.

**Component roles** (consolidated from [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision) and the _SceneScape today_ subsection above):

| Component            | Status                                    | Owned data                              | Scenescape's relationship                                                                                       |
| -------------------- | ----------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Model Downloader** | Existing OEP component (new requirements) | Installed models                        | No runtime download calls                                                                                       |
| **ViPPET**           | Existing OEP component (new requirements) | Pipeline templates and definitions      | REST pull of pipeline definitions (Manager back-end); embedded by value into scene exports                      |
| **DLSPS**            | Already integrated; integration evolving  | Running pipelines; inference output     | Runtime pipeline lifecycle via DLSPS REST API (Pipeline Orchestrator); MQTT inference output (Scene Controller) |
| **Stream Manager**   | New OEP component (optional)              | Camera devices, live and captured video | Livestream/replay APIs (Manager Backend and, deferred, Auto Camera Calibration / Mapping)                       |
| **Geti**             | Existing OEP component (no changes)       | Datasets, trained models                | **No direct integration** — mediated via Model Downloader and Stream Manager                                    |

**Data flow at runtime:**

- Models are loaded from a **shared model volume** populated by the deployment operator before pipeline start. Scenescape never reads model files directly.
- Pipeline definitions are pulled from ViPPET by Manager back-end, persisted in Scenescape's scene configuration (embedded by value), and pushed to DLSPS via its runtime API.
- Video sources are either consumed from Stream Manager (restreaming or video playback) or accessed directly (RTSP/file).
- DLSPS publishes inference results to MQTT, consumed unchanged by Scene Controller (no MLOps-integration changes to Scene Controller).

### 5.2 End-to-end process model

The process model shows the user-facing workflow for building, packaging, and deploying a Scenescape-based solution that integrates Geti (training), ViPPET (pipeline building), DLSPS (pipeline execution), Stream Manager (video acquisition), Model Downloader (model lifecycle), and Scenescape (scene management and runtime).

![Process Model](./assets/Scenescape_MLOps-Process_Model.drawio.svg)

> **One representative flow.** The diagram presents one representative end-to-end flow. The order of phases is not fixed: stages may be reordered, repeated, skipped, or run in parallel depending on the user's workflow. The stages below describe the canonical happy path used to derive Scenescape's design requirements; they are not a mandatory execution order.

**Stages** (top-to-bottom, summarized):

1. **Camera Setup** — Stream Manager detects and configures camera devices.
2. **Data Acquisition** — Stream Manager captures videos and uploads them to a Geti instance for annotation.
3. **Geti Training** — Geti annotates, trains, and validates the model.
4. **DLS Pipeline Development** — ViPPET downloads the Geti-trained model (via Model Downloader), authors and verifies the DLSPS pipeline.
5. **Scene Development** — Scenescape sets up scenes and cameras, consumes the ViPPET pipeline definition, maps pipelines to sources, starts pipelines. AI-task performance is evaluated.
6. **Package Preparation** — Scenescape exports the scene (self-contained per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision)).
7. **Deployment** — at the production site, the deployment operator populates the shared model volume, Scenescape imports the scene and starts pipelines, Stream Manager runs alongside (when deployed) for video acquisition.

**Properties of the workflow relevant to this design:**

- **No direct Scenescape ↔ Geti arrow.** Confirms the corresponding non-goal stated above.
- **Scene-evaluation feedback loop** (dashed in the diagram) returns to _Annotate_, _Build Pipeline_, or _Capture_ depending on the root cause of poor AI-task performance — the design must keep this loop short, which is why pipeline-to-source mapping is owned scene-side (see _Responsibility matrix_ below) and pipeline updates are dynamic via DLSPS runtime API (see the DLSPS runtime API delta).
- **Development and production deployments are independent.** Each component can be deployed standalone for iterative development; production composition is reconstructed from the exported scene plus the required OEP components.

### 5.3 Responsibility matrix and cross-cutting concerns

This section is the source of truth for _who does what_ in the integrated system. It collapses the per-component breakdown in _SceneScape today_ and the ADR-12 component assignments into a single Scenescape-perspective view, refined to the specific Scenescape services that own each responsibility (per the _SceneScape Component Reference_).

> **Note on Manager service:** Responsibilities are assigned to _Manager (UI)_, _Manager (Backend)_, and _Pipeline Orchestrator_ to guide future development. Until the service is formally split, all three sets of responsibilities reside within the current monolithic Manager service.

**Per-component responsibility matrix:**

_Scene_

| Concern                                                  | Owner             | Notes                                                                          |
| -------------------------------------------------------- | ----------------- | ------------------------------------------------------------------------------ |
| Scene model and persistence                              | Manager (Backend) | Scene map, cameras, ROIs, pipeline-to-source mapping.                          |
| Pipeline-to-source mapping (scene-level)                 | Manager (Backend) | Persisted Scenescape-side only; ViPPET's internal mapping is not synchronized. |
| Multimodal fusion, tracking, dynamic scene state updates | Scene Controller  | Unchanged.                                                                     |
| Scene export / import                                    | Manager (Backend) | Extends today's `manager/src/manager/scene_import.py`.                         |

_Pipeline_

| Concern                                           | Owner                                  | Notes                                                                                                                                 |
| ------------------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Pipeline authoring                                | ViPPET                                 | Scenescape never authors pipelines.                                                                                                   |
| Pipeline definition consumption                   | Manager (Backend)                      | REST pull from ViPPET; embedded by value into scene exports.                                                                          |
| Pipeline lifecycle (start/stop, dynamic reconfig) | Pipeline Orchestrator → DLSPS REST API | Replaces both the static-JSON Docker Compose flow and the pod-recreation Kubernetes flow at parity (see the DLSPS runtime API delta). |
| Pipeline execution                                | DLSPS                                  | Reads models from shared model volume; publishes inference output to MQTT.                                                            |
| Inference output consumption                      | Scene Controller                       | Existing MQTT contract; **no MLOps-integration changes**.                                                                             |

_Model_

| Concern                                            | Owner                                     | Notes                                                                                                                                           |
| -------------------------------------------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Model lifecycle (install, list)                    | Model Downloader / ViPPET UI              | No Scenescape involvement.                                                                                                                      |
| Model volume population at deployment time         | Deployment operator                       | Via a download job or script (standard path) or a model volume extraction job or script (air-gap path). Scenescape has no runtime interaction with Model Downloader. See the _Scene export / import format_ section.                       |
| Model storage at runtime                           | Shared volume (operator-populated); DLSPS (reads) | Scenescape services do not access the volume directly.                                                                                                                                                 |
| Model training, dataset management                 | Geti                                      | No Scenescape involvement.                                                                                                                      |

_Source_

| Concern                                   | Owner                                                | Notes                                                                                                         |
| ----------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Camera discovery and device configuration | Stream Manager                                       | Scenescape consumes the resulting stream list only; ownership of camera discovery is **not** with Scenescape. |
| Video acquisition (livestream / replay)   | Stream Manager                                       | Optional dependency; direct RTSP/file sources remain supported when Stream Manager is not deployed.           |
| Video capture and retrieval by timestamp  | Stream Manager                                       | Optional dependency; out of scope for this document.                                                          |
| Calibration-time image acquisition        | Auto Camera Calibration; _(deferred)_ Stream Manager | Decision deferred per phase (see the Stream Manager consumption delta).                                       |
| Mapping-time image / stream acquisition   | Mapping; _(deferred)_ Stream Manager                 | Decision deferred per phase (see the Stream Manager consumption delta).                                       |

**Cross-cutting concerns** (applied uniformly across all OEP integrations; mechanisms implemented inside the client libraries described later in this section):

| Concern                             | Approach                                                                                                                                                                                                                             |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Authentication and certificates** | Per-component credentials configured at deployment; client libraries handle injection and rotation.                                                                                                                                  |
| **Retries and backoff**             | Built into each client library with bounded retry counts; Scenescape services treat client-library calls as best-effort and fail visibly when retries are exhausted.                                                                 |
| **Schema validation**               | Inbound payloads (pipeline definitions from ViPPET) validated against versioned schemas inside the corresponding client library.                                                                                                     |
| **Versioning**                      | Each client library encodes the supported OEP-component API version range; mismatches surface as a single configuration error rather than scattered runtime failures.                                                                |
| **Telemetry and tracing**           | OpenTelemetry spans named per OEP component (e.g., `vippet.get_pipeline_definition`); per-component metrics for latency, error rate, retry count. Aligns with the existing observability conventions in `controller/observability/`. |
| **Test doubles**                    | Each client library ships fakes / mocks usable by all Scenescape-side unit tests; integration tests run against component fakes (see the _Testing & Monitoring_ section).                                                            |

### 5.4 Integration layer

This section describes how Scenescape integrates with OEP components. Two distinct integration patterns are used:

- **Client libraries** — Python packages consumed by Scenescape services; one per OEP component.
- **Out-of-service integration components** — components that run outside the Scenescape service boundary: an external model download job and a Custom DLSPS Pipeline Element exposing a timestamped video stream.

#### 5.4.1 Client-library integration layer

To avoid each Scenescape service implementing its own HTTP/MQTT plumbing, schema validation, retries, and telemetry against every OEP component, all OEP-component integrations are encapsulated in **client libraries**: small Python packages on the Scenescape side, one per OEP component, consumed by the Scenescape services that interact with that component.

**Rationale.**

- **Reduce the integration surface.** Each OEP component's wire-level details (auth, retries, schemas, version negotiation, telemetry) live in exactly one place. Scenescape services consume a typed Python API.
- **Avoid tight coupling.** When an OEP component evolves (new endpoints, new payload fields, breaking-change versions), the change is absorbed inside its client library; Scenescape services see a stable Python API or a single deliberate API-evolution change.
- **Enable parallel Scenescape work.** Multiple Scenescape services (Manager back-end, Manager UI, Auto Camera Calibration, Mapping) can adopt the same OEP component without duplicating integration code.
- **Make testing tractable.** Each client library ships fakes / mocks; Scenescape-service tests run against those fakes without standing up an OEP component.

**Naming convention.** _<Component> client library_ (e.g., _ViPPET client library_, _DLSPS client library_). The term "client" deliberately does **not** mean "thin HTTP wrapper" — a client library owns the full set of cross-cutting concerns listed in the matrix above, not just transport. The name _adapter_ is reserved for the existing Scenescape-authored DLSPS extensions (`gvapython` code injected into DLSPS); the two concepts are distinct.

**Client libraries.**

| Client library                | OEP component  | Scenescape consumers                                                                               | Status |
| ----------------------------- | -------------- | -------------------------------------------------------------------------------------------------- | ------ |
| ViPPET client library         | ViPPET         | Manager (Backend) (REST pull of pipeline definitions)                                              | New    |
| DLSPS client library          | DLSPS          | Pipeline Orchestrator (runtime pipeline lifecycle)                                                 | New    |
| Stream Manager client library | Stream Manager | Manager (Backend) (livestream / replay consumption); _(deferred)_ Auto Camera Calibration, Mapping | New    |

There is **no Model Downloader client library** — Scenescape has no runtime integration with Model Downloader; the shared model volume is the only coupling.
There is **no Geti client library** — Scenescape has no direct integration with Geti.

**Concerns each client library owns** (these are realizations of the cross-cutting concerns listed above):

- Transport (HTTP / MQTT / etc.), authentication, certificate handling, timeouts.
- Typed Python API surface (request/response data classes) consumed by Scenescape services.
- Schema validation of inbound payloads against versioned schemas.
- Bounded retries with backoff; deterministic failure modes.
- OpenTelemetry instrumentation (spans, metrics) named per OEP component.
- API-version negotiation and version-mismatch reporting.
- Test doubles (fakes / mocks) for downstream Scenescape-service tests.

**Open questions for this layer:**

- **Repository location.** Three candidate placements are possible: (A) extend [`scene_common/`](../../scene_common/) with an `integration/` subpackage (one module per OEP component); (B) introduce a new top-level shared library (e.g., `integration_clients/`); (C) decide per component. This decision is **deferred** and tracked in the _Open Questions_ section.

#### 5.4.2 Out-of-service integration components

Two integration components participate in the overall architecture but run outside the Scenescape service boundary.

**Model volume population job or script.** Out-of-band job or script that populates the shared model volume. Two modes: (a) standard path — calls Model Downloader's download endpoint to materialize the model set from a model list (static, predefined in the deployment configuration, or dynamic, extracted from the scene artifact at import time); (b) air-gap path — extracts the compressed model volume archive from the package. The job is not a Scenescape service; Scenescape may provide reference implementations.

During the backwards-compatibility window (while dynamic pipeline configuration is still supported), the job is also responsible for generating the [model configuration file](../user-guide/other-topics/model-configuration-file-format.md) containing the parameters and paths of the downloaded models, to be consumed by the pipeline generator in dynamic pipeline configuration.

**Custom DLSPS Pipeline Element exposing timestamped video stream.** A custom DLSPS pipeline element that runs inside the DLSPS pipeline process — not inside a Scenescape service. It streams camera video and absolute timestamps to Stream Manager to enable event-driven or on-demand frame retrieval by timestamp. The absolute timestamps are aligned with objects and events in Scenescape output. This element is the post-`gvapython` successor to the adapter code currently under [`dlstreamer-pipeline-server/user_scripts/gvapython/sscape/`](../../dlstreamer-pipeline-server/user_scripts/gvapython/sscape/). The full specification of its Stream Manager integration is out of scope for this document.

### 5.5 Per-contract specifications

This section specifies the integration contracts between Scenescape and each OEP component.

Contracts are presented at the level of detail required for Scenescape-side design. Wire-level specifications (exact URL paths, request/response JSON schemas, authentication mechanisms) are owned by the corresponding OEP-component teams and referenced from the _References_ section once published; where a Scenescape-side decision depends on a not-yet-finalized OEP-component design, this is called out explicitly.

> **Manager service split.** As noted in the _Responsibility matrix_, "Manager back-end", "Manager UI", and "Pipeline Orchestrator" labels are recommendations; the decision to split today's monolithic Manager is deferred. Until the split is decided, all contracts assigned to any of these three are implemented inside the current Manager service.

#### 5.5.1 Scenescape ↔ Model Downloader

**No runtime contract.** Scenescape has no runtime interaction with Model Downloader. The integration point is the shared model volume: DLSPS reads model files from it at pipeline runtime; model identity is embedded in pipeline definitions and scene exports. Populating the model volume before deployment is the deployment operator's responsibility — see the _Scene export / import format_ section for the two supported paths.

**Backward compatibility (dynamic pipeline configuration).** The dynamic pipeline configuration feature remains supported until feature parity with ViPPET-based pipeline authoring is achieved. During this transition, the job or script that downloads models via Model Downloader is also responsible for generating the [model configuration file](../user-guide/other-topics/model-configuration-file-format.md) containing the parameters and paths of the downloaded models.

#### 5.5.2 Scenescape ↔ ViPPET

**Purpose.** Consume pipeline definitions authored in ViPPET and persist them in Scenescape's scene configuration.

| Aspect                    | Specification                                                                                                                                                                       |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Scenescape consumer       | Manager back-end                                                                                                                                                                    |
| Client library            | ViPPET client library                                                                                                                                                               |
| Endpoint consumed         | ViPPET pipeline-definition REST endpoint (exact URL/shape owned by the ViPPET team; client library absorbs the wire detail).                                                        |
| Direction                 | Scenescape → ViPPET (REST pull, per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision))                                                                            |
| Payload                   | A pipeline definition containing: a DLSPS-consumable pipeline definition body (parametrized), and pipeline metadata. **Models are referenced by identifier (path) — not embedded.** |
| Frequency                 | On-demand at scene-development time (user selects/updates a pipeline definition for a scene).                                                                                       |
| Persistence in Scenescape | The fetched pipeline definition is **persisted by value** in Scenescape's scene configuration so the scene is self-contained (deployable without ViPPET).                           |
| Failure mode              | Fetch failures surface as a UI error at the time of selection; once a pipeline definition is persisted in a scene, no further ViPPET call is required.                              |

**Pipeline definition requirements.** For successful integration, ViPPET pipeline definitions must meet the following requirements:

- Support embedding custom Scenescape pipeline elements (the DLSPS adapter functionality, once broken down and migrated from `gvapython` to the Gst Analytics Python API).
- Be parametrizable per camera instance, exposing at minimum the following per-instance parameters: video source address, source ID used in MQTT output, model confidence threshold, and NTP usage.

The exact pipeline-definition format (parametrization syntax, version envelope) depends on ViPPET's design and is tracked in _Open Questions_.

#### 5.5.3 Scenescape ↔ DLSPS

**Purpose.** Drive the runtime lifecycle of DLSPS pipelines (start, stop, reconfigure) and consume inference output. This integration is evolving from the static-JSON + pod-recreation mechanisms toward a runtime REST API.

| Aspect                                           | Specification                                                                                                                                                                                              |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Scenescape consumer (runtime pipeline lifecycle) | Pipeline Orchestrator                                                                                                                                                                                      |
| Client library                                   | DLSPS client library (for the runtime pipeline API)                                                                                                                                                        |
| Pipeline-lifecycle endpoint                      | DLSPS runtime REST API for start / stop / reconfigure (exact shape owned by the DLSPS team)                                                                                                                |
| Direction                                        | Scenescape → DLSPS (REST control)                                                                                                                                                                          |
| Payload                                          | A pipeline-instance descriptor including: the (already-resolved) pipeline definition from ViPPET, the source binding (Stream Manager URL, direct RTSP/file, etc.), and any per-instance parameters.        |
| Frequency                                        | At scene start/stop and on any pipeline-to-source mapping change.                                                                                                                                          |
| Failure mode                                     | Lifecycle-call failures surface to Pipeline Orchestrator; the legacy pod-recreation (Kubernetes) and static-JSON (Docker Compose) mechanisms remain available until parity, per the _Constraints_ section. |

**Scenescape-authored DLSPS extensions.** The `gvapython`-based extension code under [`dlstreamer-pipeline-server/user_scripts/gvapython/sscape/`](../../dlstreamer-pipeline-server/user_scripts/gvapython/sscape/) is statically injected into DLSPS pipeline configurations and runs inside the DLSPS pipeline process. It is **not** part of the DLSPS client library (the client library is a Scenescape-side Python API; the extensions run inside DLSPS). Its migration from `gvapython` to the Gst Analytics Python API and its breakdown into smaller units are tracked in _Open Questions_.

#### 5.5.4 Scenescape ↔ Stream Manager

**Purpose.** Consume live video sources and replays from Stream Manager when Stream Manager is deployed. Stream Manager is an **optional** dependency; Scenescape continues to support direct RTSP/file sources when Stream Manager is not deployed.

| Aspect              | Specification                                                                                                                                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Scenescape consumer | Manager back-end (livestream / replay URLs for pipeline source binding); _(deferred)_ Auto Camera Calibration, Mapping                                                                                                                  |
| Client library      | Stream Manager client library                                                                                                                                                                                                           |
| Endpoints consumed  | Stream Manager livestream / replay APIs (exact shape owned by the Stream Manager team; per the _SceneScape team: livestreams/replays API_ line item in the Stream Manager proposal).                                                    |
| Direction           | Scenescape → Stream Manager (REST control + stream consumption)                                                                                                                                                                         |
| Payload             | Stream URLs / handles for livestream and replay; camera metadata used to populate scene-configuration camera entries.                                                                                                                   |
| Frequency           | At scene-configuration time (camera enumeration) and at runtime (stream URL resolution at pipeline start).                                                                                                                              |
| Failure mode        | When Stream Manager is not deployed, the client library is not loaded and source-binding falls back to direct RTSP/file sources. When Stream Manager is deployed but unreachable, errors surface to Manager back-end at pipeline start. |

**Deferred Scenescape consumers.** Whether Auto Camera Calibration and Mapping consume from Stream Manager (in addition to or instead of their current direct-source paths) is a per-phase decision tracked under the Stream Manager consumption delta in the _Rollout / Migration Plan_ section.

#### 5.5.5 Custom DLSPS Pipeline Element exposing timestamped video stream ↔ Stream Manager

**Purpose.** Stream camera video and timestamps to Stream Manager for event-driven or on-demand frame retrieval by timestamp. Stream Manager is an **optional** dependency; Scenescape continues to operate when Stream Manager is not deployed.

**Out of scope for this document.** This integration will be specified in a separate ADR and/or design document.

#### 5.5.6 Scenescape ↔ Geti

**No direct contract.** Per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision), Scenescape does not integrate with Geti directly. Geti is reached only indirectly:

- **Models** flow from Geti to Scenescape via Model Downloader (which populates the shared model volume read by DLSPS).
- **Training videos** flow from cameras to Geti via Stream Manager.

There is therefore no Scenescape-side client library for Geti and no row in the contracts above.

### 5.6 Per-service Scenescape deltas

This section enumerates the concrete changes Scenescape must absorb to participate in the target architecture. Each delta names the Scenescape services touched, the client library involved, the affected Scenescape modules, the parity criterion that gates removal of any legacy mechanism, and a **decision-timing** note (_decided now_ — the service-ownership assignment is established in this design; _deferred per phase_ — the assignment is left to the phase that delivers the delta).

> **Manager service split.** As elsewhere in this document, _Manager back-end_, _Manager UI_, and _Pipeline Orchestrator_ labels in the deltas below are recommendations; the Manager split decision is deferred. Until that decision is taken, all changes assigned to any of these three are implemented inside the current monolithic Manager service.

The deltas are organized by area of work, and the rollout plan in the _Rollout / Migration Plan_ section maps them to deployment phases.

#### 5.6.1 Stream Manager consumption

| Aspect                      | Specification                                                                                                                                                                                                                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Consume Stream Manager APIs for video sources (livestream, replay) in addition to today's direct RTSP / file sources.                                                                                                                                                                 |
| Scenescape consumers        | Manager back-end (camera enumeration, stream URL resolution for pipeline source binding); _(deferred)_ Auto Camera Calibration (calibration-time images); _(deferred)_ Mapping (streams / images); _(deferred)_ a path for DLSPS to consume streams directly.                         |
| Client library              | Stream Manager client library.                                                                                                                                                                                                                                                        |
| Affected Scenescape modules | Camera-source binding inside Manager back-end (camera-source persistence, pipeline-source resolution). When deferred consumers are activated: corresponding source-acquisition code paths in Auto Camera Calibration and Mapping.                                                     |
| Parity criterion            | Feature parity is **per consumer**: each Scenescape service that adopts Stream Manager retains its direct-source path until its Stream Manager consumption is validated end-to-end. Stream Manager remains an optional dependency overall — there is no "remove direct sources" gate. |
| Decision timing             | **Deferred per phase.** Manager back-end's Stream Manager consumption is the anchor consumer (Phase 3 in the rollout plan). The other consumers (Auto Camera Calibration, Mapping, the DLSPS-side path) are decided in their respective phases as the corresponding designs solidify. |
| Cross-component dependency  | Stream Manager API design (livestream / replay endpoints), owned by the Stream Manager team.                                                                                                                                                                                          |

#### 5.6.2 ViPPET pipeline-definition consumption

| Aspect                      | Specification                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Consume ViPPET pipeline definitions as a first-class source of pipeline configuration, replacing both the manually authored static JSON files (Docker Compose) and the custom pipeline generation (Kubernetes).                                                                                                                                                                                                                                                                                                                                                       |
| Scenescape consumers        | Manager back-end.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Client library              | ViPPET client library.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Affected Scenescape modules | New consumer in Manager back-end for pulling pipeline definitions and persisting them by value in the scene model. Legacy mechanisms scoped for removal at parity: the static JSON files under [`dlstreamer-pipeline-server/`](../../dlstreamer-pipeline-server/) and the custom pipeline generator at [`manager/src/manager/ppl_generator/`](../../manager/src/manager/ppl_generator/). The Kubernetes config-map writer in [`manager/src/manager/kubeclient.py`](../../manager/src/manager/kubeclient.py) is affected by the DLSPS runtime API delta, not this one. |
| Parity criterion            | A scene configured exclusively via ViPPET-supplied pipeline definitions reproduces the AI-task behavior of the equivalent scene configured via today's static JSON / custom pipeline generation, for the supported set of pipelines. Each of the two legacy mechanisms (Docker Compose static JSON; Kubernetes custom pipeline generation) has its **own** parity gate per the _Constraints_ section.                                                                                                                                                                 |
| Decision timing             | **Decided now** — Manager back-end is the consumer.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| Cross-component dependency  | ViPPET pipeline-definition format (parametrization syntax, version envelope), owned by the ViPPET team. The exact format is tracked in _Open Questions_.                                                                                                                                                                                                                                                                                                                                                                                                              |

#### 5.6.3 Model Downloader adoption

| Aspect                      | Specification                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Replace Scenescape's custom model download with the shared-model-volume model populated by Model Downloader.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Scenescape consumers        | None at runtime. Model identity is embedded in pipeline definitions sourced from ViPPET; no Scenescape service calls Model Downloader at runtime.                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Client library              | None — no Scenescape service integrates with Model Downloader at runtime.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Affected Scenescape modules | [`model_installer/`](../../model_installer/) **removed** in favor of the shared model volume populated by Model Downloader (download is out-of-band per [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision)). [`manager/src/manager/model_directory_view.py`](../../manager/src/manager/model_directory_view.py) **removed** — model identity is embedded in pipeline definitions from ViPPET; no separate model-listing step is required. Scenescape-specific model-configuration conventions ([model-configuration-file-format](../user-guide/other-topics/model-configuration-file-format.md)) retired. |
| Parity criterion            | (a) An equivalent set of models can be installed via Model Downloader and consumed by DLSPS for the supported set of pipelines; (b) the OMZ-to-public-models migration does not regress the default Scenescape pipelines.                                                                                                                                                                                                                                                                                                                                                                                                  |
| Decision timing             | **Decided now** — `model_installer` is removed; Scenescape has no runtime interaction with Model Downloader.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Cross-component dependency  | Shared-volume model-storage convention.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

#### 5.6.4 Scene-level pipeline-to-source mapping

| Aspect                      | Specification                                                                                                                                                                                                                                                           |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Persist and manage the binding between pipeline definitions and the camera sources they run against, scene-side. Different cameras in the same scene serve different spatial-awareness tasks; a pipeline definition can be mapped to one or more sources (one-to-many). |
| Scenescape consumers        | Manager back-end (scene configuration owner).                                                                                                                                                                                                                           |
| Client library              | None — internal to Scenescape. The mapping is consumed by the caller of DLSPS client library (when starting pipeline instances) and embedded in scene exports by the export/import code; it is not itself an OEP integration.                                           |
| Affected Scenescape modules | Scene model in Manager back-end (new persistent field set for the pipeline-definition-to-source mapping).                                                                                                                                                               |
| Parity criterion            | Every pipeline-to-source binding expressible via today's mechanisms (static JSON pipeline configurations for Docker Compose; custom pipeline generation for Kubernetes) is expressible via the scene-side mapping.                                                      |
| Decision timing             | **Decided now** — Manager back-end owns the scene model.                                                                                                                                                                                                                |
| Cross-component dependency  | None directly; depends on the ViPPET-pipeline-definition delta for the identity of pipeline definitions that the mapping references.                                                                                                                                    |

#### 5.6.5 DLSPS runtime pipeline API

| Aspect                      | Specification                                                                                                                                                                                                                                                                                                                                                  |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Drive DLSPS pipeline lifecycle (start, stop, reconfigure) via DLSPS's runtime REST API once available, replacing today's static-JSON bind-mount mechanism (Docker Compose) and pod-recreation mechanism (Kubernetes).                                                                                                                                          |
| Scenescape consumers        | Pipeline Orchestrator (lifecycle calls).                                                                                                                                                                                                                                                                                                                       |
| Client library              | DLSPS client library (new for the runtime pipeline API).                                                                                                                                                                                                                                                                                                       |
| Affected Scenescape modules | New lifecycle-management code in Pipeline Orchestrator. Legacy mechanisms scoped for removal at parity: the Kubernetes config-map writer + pod-recreation logic in [`manager/src/manager/kubeclient.py`](../../manager/src/manager/kubeclient.py); the static-JSON bind-mount wiring under [`dlstreamer-pipeline-server/`](../../dlstreamer-pipeline-server/). |
| Parity criterion            | Both legacy reconfiguration mechanisms are retired and replaced by the DLSPS runtime API across both deployment targets (Docker Compose and Kubernetes). This is the exit criterion of the final rollout phase.                                                                                                                                                |
| Decision timing             | **Decided now** — Pipeline Orchestrator is the runtime-API consumer. The legacy pod-recreation behavior remains available as a fall-back until the parity gate is met.                                                                                                                                                                                         |
| Cross-component dependency  | DLSPS runtime REST API design, owned by the DLSPS team. The migration of the existing Scenescape-authored DLSPS extensions from `gvapython` to the Gst Analytics Python API is a related but separately tracked activity — it does not block this delta but proceeds in parallel.                                                                              |

#### 5.6.6 Scene export / import

| Aspect                      | Specification                                                                                                                                                                                                                                                                                                                              |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Purpose                     | Extend Scenescape's scene export/import to produce a **self-contained** scene artifact suitable for production deployment: pipeline definitions are embedded by value (deployment does not require ViPPET); models are either referenced by identifier (standard path: download job materializes them at deployment time) or embedded as a compressed volume in the package (air-gap / offline path: no Model Downloader required). |
| Scenescape consumers        | Manager back-end.                                                                                                                                                                                                                                                                                                                          |
| Client library              | None — internal to Scenescape. The exported artifact references identities consumed by the Model Downloader and ViPPET client libraries at runtime, but the export/import flow itself is internal.                                                                                                                                         |
| Affected Scenescape modules | Extends today's [`manager/src/manager/scene_import.py`](../../manager/src/manager/scene_import.py). New fields: embedded pipeline definitions; model references by identifier with model ID and version metadata (hashes for verification); the scene-level pipeline-definition-to-source mapping from the corresponding delta.            |
| Parity criterion            | A scene exported under the new format can be imported on a fresh deployment and produces the same runtime behavior as the source deployment, regardless of which deployment path is used to populate the model volume. Existing scenes (legacy format) remain importable for the duration of the backwards-compatibility window.                                                |
| Decision timing             | **Decided now** — Manager back-end owns scene export/import.                                                                                                                                                                                                                                                                               |
| Cross-component dependency  | None directly; depends on Model Downloader's identifier scheme (for the model references in the artifact) and on ViPPET's pipeline-definition format (for the embedded pipeline definitions).                                                                                                                                              |

#### 5.6.7 DLSPS adapter breakdown and migration to Gst Analytics Python API

| Aspect                      | Specification                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                     | Replace the monolithic `gvapython`-based Scenescape adapter with new pipeline elements using the Gst Analytics Python API. The `gvapython` element is deprecated upstream in favor of the Gst Analytics Python API. The adapter is also broken down into smaller, reusable elements as part of this migration (breakdown plan tracked in _Open Questions_).                                                                                         |
| Scenescape consumers        | None — the adapter runs inside the DLSPS pipeline process, not inside a Scenescape service.                                                                                                                                                                                                                                                                                                                                                         |
| Client library              | None — the adapter is a DLSPS pipeline element, not a Scenescape service-side library.                                                                                                                                                                                                                                                                                                                                                              |
| Affected Scenescape modules | [`dlstreamer-pipeline-server/user_scripts/gvapython/sscape/`](../../dlstreamer-pipeline-server/user_scripts/gvapython/sscape/) **replaced** by new pipeline element code using the Gst Analytics Python API. Pipeline configurations referencing `gvapython` adapter elements are updated accordingly. The Custom DLSPS Pipeline Element (per the _Out-of-service integration components_ subsection) is the post-`gvapython` form of this adapter. |
| Parity criterion            | All adapter responsibilities (MQTT inference output: payload construction, camera ID, timestamp, NTP alignment) are reproduced by the new implementation. Scene Controller requires no changes: MQTT output format and topic conventions are preserved.                                                                                                                                                                                             |
| Decision timing             | **Decided now** — migration to Gst Analytics Python API is a committed activity that proceeds in parallel with other deltas. The adapter breakdown plan is tracked in _Open Questions_.                                                                                                                                                                                                                                                             |
| Cross-component dependency  | Requires DLSPS support for the Gst Analytics Python API and upstream availability of the Gst Analytics Python API as the `gvapython` replacement.                                                                                                                                                                                                                                                                                                   |

### 5.7 Scene export / import format — delta vs. today

This section captures **only the delta** between today's scene export/import (extended from [`manager/src/manager/scene_import.py`](../../manager/src/manager/scene_import.py)) and the new format required by this design. It does not re-specify the existing format.

**Package structure.** The deployment package consists of two components with separate ownership:

- **Scene artifact** — assembled and consumed by Scenescape Manager back-end. A self-contained archive containing pipeline definitions (models referenced by path identifier), scene and camera configuration, and the pipeline-to-source mapping. Does not contain model files.
- **Model artifact** — assembled and consumed by the deployment operator via a job or script. Either a model list (standard path: used by the download job to populate the model volume via Model Downloader) or a compressed model volume archive (air-gap path: extracted by the extraction job or script).

**Delta** (driven by [ADR-12 §Decision](../adr/0012-mlops-integration-reuse.md#decision) and the scene-export/import delta):

1. **Camera configuration stored separately from pipeline definitions.** Each camera entry carries its source identity (Stream Manager handle, direct RTSP URL, or file path) and calibration (intrinsics, extrinsics, pose). Cameras are no longer co-located with pipeline-specific fields.
2. **Model metadata is part of the pipeline definition**, supplied as a template-parameter value (models are parameters of pipeline definitions, referenced by ID + version). Pipeline definitions are embedded by value in the scene artifact so deployment does not require ViPPET. Model files are not part of the scene artifact; they are provided separately by the deployment operator via the model artifact.
3. **Pipeline-to-camera mapping** is a first-class section of the artifact, serializing the scene-side mapping owned by Manager back-end (per the scene-level pipeline-to-source mapping delta). A pipeline definition can map to one or more cameras (one-to-many). Camera-specific parameter values (for example, camera ID, confidence threshold) are part of the mapping to enable per-camera parametrization of the pipeline template. Proposed structure: `{ { <Pipeline definition template>: [key-value list of common parameter values] } : [ { <Source ID>: [key-value list of camera-specific parameter values] }, ... ] }`.
4. **Model artifact support.** The deployment package format supports both model artifact variants described in the _Package structure_: model list (standard path) and compressed model volume archive (air-gap / offline path). When the archive is present, the deployment operator's extraction job or script extracts it at deployment time, without requiring Model Downloader or network access.

Existing scenes exported under the legacy format remain importable for the duration of the backwards-compatibility window defined in the _Constraints_ section.

> The deployment operator is responsible for populating the shared model volume before Scenescape starts. Standard path: an external job reads model identifiers from the scene artifact and downloads models to the shared volume via Model Downloader. Air-gap path: an external job or script extracts the compressed model volume archive from the package. Scenescape may provide reference implementations for both paths.

### 5.8 Deployment topology

This section specifies the deployment-time arrangement of Scenescape and the OEP components it integrates with, for both supported targets: Docker Compose and Kubernetes. The topology is the same shape on both targets — only the orchestration mechanism differs.

**Components in the Scenescape deployment.**

| Component                                                                                         | Required                                     | Notes                                                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------------------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Scenescape services (Manager, Scene Controller, Auto Camera Calibration; _experimental_: Mapping) | Yes                                          | The current set of microservices, less `model_installer` after the Model Downloader delta.                                                                                                                                                                                                   |
| DL Streamer Pipeline Server (DLSPS)                                                               | Yes                                          | Runtime pipeline executor; reads models from the shared model volume; publishes MQTT inference output.                                                                                                                                                                                       |
| Shared model volume                                                                               | Yes                                          | Populated by the deployment operator (via download job or volume extraction); read by DLSPS. Scenescape does not read model files directly.                                                                                                                                                   |
| Model Downloader                                                                                  | Required on the standard deployment path     | Populates the shared model volume when models are referenced by identifier. Not required on the air-gap path. Scenescape has no runtime interaction with Model Downloader.                                                                   |
| Model volume population job or script                                                             | Required at deployment and scene-import time | Populates the shared model volume. Two modes: (a) standard — downloads models from a model list via Model Downloader (static list predefined in deployment configuration, or dynamic list extracted from the scene artifact); (b) air-gap — extracts the compressed model volume archive from the package. Scenescape may provide reference implementations.                                                                                                   |
| Stream Manager                                                                                    | Optional                                     | When deployed, provides livestream / replay; when absent, Scenescape uses direct RTSP / file sources.                                                                                                                                                                                        |
| ViPPET                                                                                            | Required only at development time            | Pipeline definitions are embedded by value in the scene artifact per the scene export/import format above. ViPPET is used during scene development, not in production.                                                                                                                       |
| Geti                                                                                              | Not at the Scenescape deployment site        | Geti is reached only indirectly during the upstream training stages of the workflow.                                                                                                                                                                                                         |

**Shared model volume.**

The shared model volume is populated by the deployment operator (via download job on the standard path, or by direct extraction on the air-gap path) and read by DLSPS at pipeline runtime. It is materialized differently per target:

- **Docker Compose.** A named Docker volume mounted into the DLSPS container and into the deployment-time population job/container.
- **Kubernetes.** A PersistentVolumeClaim mounted into the DLSPS pod(s) and into the population job/pod. Scenescape services do not mount this volume.

Scenescape services do not access the volume or enumerate its contents.

**Model volume population.**

The deployment operator is responsible for populating the shared model volume before Scenescape starts, using the standard path (download job via Model Downloader) or the air-gap path (extraction job or script from the package). Both paths are described in the _Scene export / import format_ section.

**DLSPS container / Pod creation and scaling.**

DLSPS instance creation and scaling is the responsibility of the deployment operator, not Scenescape. The current DLSPS orchestration logic in [`manager/src/manager/kubeclient.py`](../../manager/src/manager/kubeclient.py) is removed in favor of a static manual setup. Dynamic auto-scaling capabilities of Kubernetes may be used if needed in the future.

**Multi–Model-Downloader topology (open).**

ViPPET may be deployed with its own embedded Model Downloader instance or a single instance shared with Scenescape during development. Two options are under consideration:

- **(O1) Single shared Model Downloader instance, shared volume** across ViPPET and Scenescape; no model duplication; requires reachability between the two deployments. Volume sharing is not straightforward when Scenescape runs on Kubernetes and ViPPET on Docker Compose.
- **(O2) Separate Model Downloader instances, separate volumes** — clean separation; models must be re-downloaded into the Scenescape-side volume after pipeline update. This may require manually invoking a model download script during the development process. Results in model duplication and additional manual effort.

The choice is tracked in _Open Questions_ and is independent of the Scenescape-side deltas: Scenescape behavior is identical across O1 and O2 — Scenescape has no runtime calls to Model Downloader; the shared model volume boundary is the only coupling between the two deployments.

**Stream Manager opt-in.**

Stream Manager is added to the topology only when source acquisition through Stream Manager is required. The Stream Manager client library is the only point where its presence or absence matters to Scenescape services: when Stream Manager is not deployed, source bindings in the scene artifact resolve to direct RTSP / file sources without any code path through the client library.

**Network and authentication.**

Service URLs and credentials for new components (ViPPET pipeline-definition endpoint when used during development, Stream Manager livestream / replay) are configured at deployment time (for example, via environment variables) or at runtime via the Manager UI, and passed to the corresponding client libraries. The detailed list of credentials per component follows from the corresponding teams' API specifications.

---

## 6. Alternatives Considered

The architectural alternatives for the integration as a whole are evaluated in [ADR-12 §Alternatives Considered](../adr/0012-mlops-integration-reuse.md#alternatives-considered) and not repeated here.

This section records design-level alternatives that arose specifically while drafting _how_ the integration is implemented.

| Alternative                                                                                                                                                              | Considered for                    | Outcome                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Per-service direct integration** with each OEP component (no shared client libraries; each Scenescape service implements its own transport, auth, retries, telemetry). | Client-library integration layer. | **Rejected** in favor of one client library per OEP component, to reduce the integration surface, absorb OEP-component API churn in one place, and enable parallel adoption across Scenescape services. |

## 7. Rollout / Migration Plan

The integration is rolled out in four phases, with each phase delivering a subset of the seven deltas defined in the _Per-service Scenescape deltas_ section. The mapping of deltas to phases is chosen to deliver end-to-end value at each step and to manage cross-component dependencies.

| Phase       | Deltas delivered                                                                                                 | Key outcome                                                                                                                                                  |
| ----------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Phase 1** | **(3) Model Downloader adoption.**<br>**(7) DLSPS adapter breakdown and migration to Gst Analytics Python API**. | `model_installer` is removed. DLSPS adapter breakdown and migration to Gst Analytics Python API is underway.                                                 |
| **Phase 2** | **(2) ViPPET pipeline-definition consumption.**<br>**4) Scene-level pipeline-to-source mapping.**                | Scenescape can consume ViPPET pipeline definitions and map them to sources. Legacy pipeline mechanisms (static JSON, custom K8s generation) remain in place. |
| **Phase 3** | **(1) Stream Manager consumption** (Manager back-end only).<br>**(6) Scene export/import.**                      | Scenescape can consume from Stream Manager and can export/import self-contained scenes.                                                                      |
| **Phase 4** | **(5) DLSPS runtime pipeline API.**                                                                              | Legacy pipeline mechanisms are removed. DLSPS pipeline lifecycle is fully dynamic.                                                                           |

**Parity gates.** Each legacy mechanism (static JSON pipeline configurations for Docker Compose; custom dynamic pipeline configuration on Kubernetes) has its own parity gate per the _Constraints_ section. A legacy mechanism is removed only when its full capability is reproduced by the new flow. The DLSPS runtime API delta in Phase 4 is the final gate for removing both.

**Phase scope.** The phase boundaries above are high-level guidance, not hard constraints. Deltas **(1) Stream Manager consumption**, **(2) ViPPET pipeline-definition consumption**, and **(7) DLSPS adapter migration** may each span more than one phase: work begins in the phase listed and continues into subsequent phases depending on the pace of OEP-component design availability and the Scenescape team's priorities.

## 8. Testing & Monitoring

**Testing.**

- **Client libraries.** Each client library is tested in isolation with unit tests against its test doubles (fakes/mocks).
- **Scenescape services.** Service-level unit tests consume the client-library test doubles.
- **Integration tests.** A new suite of functional tests (`tests/functional/mlops/`) is added, one test per delta. These tests run against OEP-component fakes or stubs, not live components.
- **End-to-end tests.** The existing basic acceptance tests (`tests/functional/test_basic_acceptance.py`) are extended to cover one end-to-end happy path for each phase's key outcome.

**Monitoring.**

- **Telemetry.** Per the _Cross-cutting concerns_ matrix, each client library emits OpenTelemetry spans and metrics (latency, error rate, retry count) for its downstream OEP component. These are scraped and visualized using the existing observability stack.
- **Health checks.** The existing health-check mechanisms are extended to include the reachability of each required OEP component's API endpoint.

## 9. Open Questions

This section consolidates all deferred decisions and open questions called out in the sections above.

- **Client-library repository location.** Three candidate placements are possible: (A) extend [`scene_common/`](../../scene_common/) with an `integration/` subpackage; (B) introduce a new top-level shared library (e.g., `integration_clients/`); (C) decide per component. The distribution and versioning model follows from this choice.
- **ViPPET pipeline-definition format.** The exact format for pipeline definitions consumed from ViPPET, especially the model-parametrization syntax and the version envelope, depends on the ViPPET team's design.
- **Multi–Model-Downloader topology.** The choice between a single shared Model Downloader instance (O1) and separate instances with separate volumes (O2) for development deployments.
- **`gvapython` to Gst Analytics Python migration and adapter breakdown.** The detailed plan for refactoring the monolithic adapter into smaller, reusable units. This proceeds in parallel with the DLSPS runtime API delta.
- **Stream Manager consumption by deferred consumers.** The decision on whether (and when) Auto Camera Calibration and Mapping will consume from Stream Manager.
- **Manager service split.** The decision on whether (and when) to split today's monolithic Manager service into separate back-end and UI services.

## 10. References

- [ADR-12 — MLOps Integration and Reuse](../adr/0012-mlops-integration-reuse.md)
- Diagrams:
  - [Component Interaction](./assets/Scenescape_MLOps-Component_Interaction.drawio.svg)
  - [Process Model](./assets/Scenescape_MLOps-Process_Model.drawio.svg)
