# Diagram Summaries — SceneScape MLOps Integration

> **Source:** [SceneScape_MLOps.drawio](../diagrams/SceneScape_MLOps.drawio)
> **Pages covered:** *Process Model*, *Component Interaction* only. Pages *Objects Logical Model* and *Assets (WIP)* are intentionally out of scope for this intermediate.
>
> **Terminology note:** The drawio file uses the labels "VIPPET", "Stream Manager (Intel VST)", "Model Downloader / Manager", and "DLStreamer Pipeline Server". This summary uses the standardized canonical names: **ViPPET**, **Stream Manager**, **Model Downloader**, **DL Streamer Pipeline Server (DLSPS)**.

---

## 1. Process Model

> Exported SVG: [SceneScape_MLOps-Process Model.drawio.svg](../diagrams/SceneScape_MLOps-Process%20Model.drawio.svg)

### Purpose

Describes the end-to-end user workflow for building a SceneScape-based solution that integrates Geti (training), ViPPET (pipeline building), DLSPS (pipeline execution), Stream Manager (camera/video acquisition), Model Downloader (model lifecycle), and SceneScape (scene management & runtime). It is organized as horizontal **stages** crossed by vertical **component swimlanes**.

### Swimlanes (vertical)

| Swimlane | Role in the workflow |
|---|---|
| **SceneScape** | Scene & camera setup, scene development, packaging, deployment |
| **Geti** | Annotate, train, validate model |
| **Stream Manager** | Detect & configure camera devices; capture videos; retrieve frames/captures at runtime |
| **ViPPET** | Download Geti-trained model, build and verify DLS pipeline |

### Stages (horizontal, top-to-bottom)

1. **Camera Setup** — Stream Manager: *Detect Camera Devices* → *Configure Camera Devices*. Output: camera IPs.
2. **Data Acquisition** — Stream Manager: *Capture Videos* → *Upload Videos to Geti Instance*. Output: synchronized video files.
3. **Geti Training** — Geti: *Annotate Videos* → *Train Model* → *Validate Model* → *Deploy (Development Setup)*. Output: Geti-trained model.
4. **DLS Pipeline Development** — ViPPET: *Download Geti-Trained Model* → *Build DLS Pipeline* → *Verify DLS Pipeline Output*. Output: pipeline definition + model artifacts.
5. **Scene Development** — SceneScape: *Deploy (Development Setup)* → *Setup Scene & Cameras* → *Use Pipeline Definition* → *Map Pipeline to Sources* → *Start Pipelines* → *Evaluate AI Task Performance*. Output: scene map & config, camera poses, pipeline definitions, models list.
6. **Package Preparation** — SceneScape: *Export Scene*.
7. **Deployment** — SceneScape (production): *Deploy (Production Setup with Model Downloader)* → *Download Models* → *Import Scene* → *Start Pipelines* → *Connect Business Logic*. Stream Manager (production): *Deploy* → *Video Capture / Retrieve*. Outputs: tracked objects, events sent to business logic, retrieved video frames for online/offline analysis.

### Key cross-component interactions

- **Stream Manager → Geti**: video upload feeds Geti datasets.
- **Geti → ViPPET**: trained model is downloaded by ViPPET to assemble the pipeline.
- **ViPPET → SceneScape**: pipeline definition and model metadata are reused by SceneScape (no manual conversion or copying).
- **SceneScape ↔ Stream Manager** (runtime): SceneScape consumes video sources and retrievals.
- **Model Downloader** is used at production deployment time by SceneScape to fetch models (model storage shared with DLSPS).
- **Scene Evaluation feedback loop** (dashed): poor AI task performance loops back to *Annotate Videos*, *Build DLS Pipeline*, or *Capture Videos* depending on root cause.

### Observations relevant to the ADR

- SceneScape has **no direct arrow to Geti**. Geti integration is mediated by Stream Manager (data) and ViPPET (model). Consistent with the agreed scope: no direct SceneScape↔Geti integration.
- The "Deploy (Development Setup)" step appears in three swimlanes (SceneScape, Geti, Stream Manager) — implies each component is independently deployable for iterative development.
- The production deployment stage cleanly separates SceneScape's responsibilities (scene/pipeline orchestration) from Stream Manager's (video ingestion) and Model Downloader's (model lifecycle).

---

## 2. Component Interaction

> Exported SVG: [SceneScape_MLOps-Component Interaction.drawio.svg](../diagrams/SceneScape_MLOps-Component%20Interaction.drawio.svg)

### Purpose

High-level component view showing how SceneScape interacts with the other components at runtime, with each component's primary data ownership, and a legend distinguishing new, existing, and existing-with-new-requirements components.

### Components & ownership

| Component | Legend status | Owned data |
|---|---|---|
| **SceneScape** | Existing (new requirements) | Scene Map & Config, Camera Poses, Video Sources (Camera/File), Pipeline Definitions |
| **Stream Manager** | **NEW** component | Video sources (cameras), Captured Video Files |
| **ViPPET Backend** | Existing (new requirements) | Pipeline Templates, Pipeline Definitions |
| **Geti** | Existing (no changes) | Projects, Datasets, Trained Models |
| **Model Downloader** | Existing (new requirements) | Models |
| **DL Streamer Pipeline Server (DLSPS)** | Existing (new requirements) | Pipeline Definition, Video Source (runtime) |

### Interactions (directed, dashed = use/consume)

- **SceneScape → Stream Manager**: *Use / Download Video Sources*
- **SceneScape → ViPPET**: *Use Pipeline Definitions*
- **SceneScape → Model Downloader**: *Use Models*
- **SceneScape → DLSPS**: *Run Pipelines*
- **ViPPET → DLSPS**: *Run Pipelines* (for ViPPET's own pipeline verification)
- **ViPPET → Stream Manager**: *Use Video Sources*
- **ViPPET → Model Downloader**: *Use Models*
- **DLSPS → Model Downloader**: *Use Models* (shared model storage)
- **Model Downloader → Geti**: *Download Models*
- **Stream Manager → Geti**: *Upload Videos*

### Observations relevant to the ADR

- **Stream Manager is the only new component.** Everything else exists but most need new requirements to support this integration; only Geti is unchanged.
- **SceneScape consumes APIs but exposes none** to the other components in this diagram — confirming that Stream Manager API ownership stays with the Stream Manager team (SceneScape only uses livestream/replay APIs).
- **Models flow through Model Downloader** for all consumers (SceneScape, ViPPET, DLSPS). Geti is the upstream model producer, accessed via Model Downloader rather than directly.
- **No direct SceneScape ↔ Geti edge.** Geti integration is fully mediated by Model Downloader (models) and Stream Manager (training videos).
- The diagram is component-level only — it does not specify protocols, transport, or auth. Those are decisions to be captured in the ADR.

---

## Clarifications resolved

1. **Camera discovery**: SceneScape does **not** perform camera discovery. It consumes streams that have been discovered and exposed by Stream Manager.
2. **Pipeline-to-source mapping**: Persisted on the **SceneScape side only**. ViPPET may maintain its own mapping for its own purposes; that mapping is not relevant to SceneScape and is not synchronized.
3. **Exported-scene pipeline reference**: Deferred to the ADR.
4. **Runtime model access**: DLSPS reads models from a **shared volume** that Model Downloader populates. DLSPS does not call Model Downloader directly at runtime.
