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

*Sections 5–11 to be added.*
