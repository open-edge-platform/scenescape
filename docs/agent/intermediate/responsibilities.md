# Division of Responsibilities — SceneScape MLOps Integration

> **Inputs:** [presentation-extract.md](../presentation-extract.md), [stream-manager.md](../stream-manager.md), [diagrams-summary.md](./diagrams-summary.md), JIRA features under [../jira/](../jira/).
>
> **Scope:** Responsibilities that are *relevant to SceneScape's integration with the MLOps stack*. Internal responsibilities of external components are described only when they are touched by an integration contract that SceneScape relies on.
>
> **Terminology:** ViPPET, Stream Manager, Model Downloader, DL Streamer Pipeline Server (DLSPS), Geti, SceneScape.

---

## 1. Responsibility matrix (per component)

### 1.1 SceneScape

**Owns / does:**

- Scene definition: scene map, regions of interest, sensor/camera placement (poses, intrinsics/extrinsics).
- Persistence of **pipeline-to-source mapping** (which ViPPET pipeline runs against which Stream Manager source on which camera in which scene).
- Orchestration of pipeline runs against DLSPS (start/stop, lifecycle).
- Multimodal sensor fusion, object tracking, scene state, event publication to business logic.
- Scene **export/import** for production packaging.
- Consumption of:
  - Video sources from **Stream Manager** (live + replay).
  - Pipeline definitions from **ViPPET**.
  - Models via **Model Downloader** (shared volume; populated at deployment).
- Runtime execution of pipelines via **DLSPS** (existing integration, evolving).

**Does NOT own / does NOT do:**

- Camera discovery / device configuration (Stream Manager).
- Video capture / storage / replay (Stream Manager).
- Pipeline authoring / verification tooling (ViPPET).
- Model training, dataset management (Geti).
- Model storage, download, lifecycle (Model Downloader).
- Direct integration with Geti (mediated by Model Downloader for models and Stream Manager for training data).

### 1.2 Stream Manager *(NEW component)*

**Owns / does:**

- Camera device discovery and configuration.
- Live video acquisition; captured-video storage.
- Exposes APIs for:
  - **Livestream** access (consumed by SceneScape at runtime).
  - **Replay** access (consumed by SceneScape at runtime).
  - **Video upload** to Geti instances (for training data).
- Independently deployable in development and production setups.

**Does NOT own:**

- Scene model, pipeline orchestration, or any SceneScape-side state.
- The API surface itself is owned by the Stream Manager team; SceneScape is a **consumer only**.

**SceneScape's contract with Stream Manager:**

- SceneScape consumes Stream Manager's livestream/replay APIs as defined by the Stream Manager team.
- No reverse dependency from Stream Manager into SceneScape.

### 1.3 ViPPET (Pipeline Builder Backend)

**Owns / does:**

- Pipeline **templates** and authored **pipeline definitions** for DLStreamer/DLSPS.
- Downloads Geti-trained models via Model Downloader; assembles DLS pipelines around them.
- Pipeline verification (runs pipelines through DLSPS during authoring).
- Exposes pipeline definitions for consumption by SceneScape.
- May maintain its own pipeline-to-source mapping for internal verification — **not** synchronized with SceneScape.

**Does NOT own:**

- Scene-level mapping of which pipeline runs on which scene's camera (SceneScape).
- Production pipeline orchestration (DLSPS, driven by SceneScape).
- Model storage (Model Downloader).

**SceneScape's contract with ViPPET:**

- SceneScape consumes pipeline definitions produced by ViPPET. The exact transport (REST pull, file export, registry lookup, embedded reference in scene) is a decision to capture in the ADR.

### 1.4 DL Streamer Pipeline Server (DLSPS)

**Owns / does:**

- Executes DLStreamer pipelines.
- Reads models from a **shared volume populated by Model Downloader** (no direct runtime call to Model Downloader).
- Receives pipeline definitions (today: static JSON configs; target: dynamic per the JIRA roadmap).
- Publishes inference results to MQTT for consumption by SceneScape.

**Does NOT own:**

- Pipeline authoring (ViPPET).
- Model download / lifecycle (Model Downloader).
- Scene state / fusion / tracking (SceneScape).

**SceneScape's contract with DLSPS:**

- SceneScape triggers pipeline lifecycle and consumes MQTT inference outputs.
- The mechanism for dynamic pipeline configuration (today via pod recreation in K8s; target via runtime API) is a decision to capture in the ADR roadmap.

### 1.5 Model Downloader

**Owns / does:**

- Persistent model registry; tracking which models are installed.
- Model download from Geti (and other registered sources).
- Populates the shared model volume read by DLSPS (and by ViPPET during authoring).
- Exposes model query/delete endpoints for SceneScape (and other consumers).

**Does NOT own:**

- Model training (Geti).
- Pipeline runtime (DLSPS).
- Scene state (SceneScape).

**SceneScape's contract with Model Downloader:**

- SceneScape queries available models, requests downloads at deployment time, and references models in pipeline definitions by ID. SceneScape does not read model files directly.

### 1.6 Geti

**Owns / does:**

- Dataset management (receives uploaded videos from Stream Manager).
- Model training, validation, and publication.
- Existing component; no new requirements from this integration.

**Does NOT own:**

- Model distribution to runtime (Model Downloader).
- Anything inside SceneScape's runtime.

**SceneScape's contract with Geti:**

- **None — no direct integration.** Geti is reached only indirectly via Model Downloader (for models) and via Stream Manager (for training data upload). The exact Geti-side integration timeline with ViPPET / Model Downloader / Stream Manager is out of scope of this ADR.

---

## 2. Cross-cutting concerns

| Concern | Owner | Notes |
|---|---|---|
| Camera discovery & configuration | Stream Manager | SceneScape consumes the resulting stream list only. |
| Pipeline authoring | ViPPET | SceneScape never authors pipelines. |
| Pipeline-to-source mapping (scene-level) | SceneScape | Persisted SceneScape-side; ViPPET's own mapping is irrelevant here. |
| Pipeline execution | DLSPS | Driven by SceneScape at runtime, by ViPPET during authoring. |
| Model storage at runtime | Model Downloader (writes) + DLSPS (reads via shared volume) | No direct runtime call DLSPS→Model Downloader. |
| Model lifecycle (install / list / delete) | Model Downloader | SceneScape uses its API. |
| Training data acquisition | Stream Manager → Geti | SceneScape not involved. |
| Model training | Geti | No SceneScape involvement. |
| Scene export / production deployment | SceneScape | Exported artifact references pipelines + models; embedding strategy deferred to ADR. |

---

## 3. New / changed responsibilities for SceneScape (delta vs. today)

This is the set of changes SceneScape must absorb to participate in the target architecture. It is the practical scope of the ADR for the SceneScape team.

1. **Consume Stream Manager APIs** instead of (or alongside) direct RTSP/file sources for cameras.
2. **Consume ViPPET pipeline definitions** as a first-class source of pipeline configuration, replacing or augmenting today's static `dlstreamer-pipeline-server/*-config.json` files.
3. **Use Model Downloader as the single front door for models**, replacing today's `model_installer` direct-to-OpenVINO-Zoo flow where applicable, and aligning the production deployment to download models from a registry populated by Model Downloader.
4. **Persist and manage the scene-level pipeline-to-source mapping** so that an exported scene can be re-instantiated in production against the same logical sources.
5. **Evolve the DLSPS integration** from static JSON / pod-recreation reconfiguration toward the runtime pipeline API model that the JIRA roadmap targets — without breaking existing deployments during the transition.
6. **Export/Import scene packages** that reference (or embed) pipeline definitions and model identifiers in a form Model Downloader and DLSPS can satisfy at deployment time.

---

## 4. Open points to resolve in the ADR

These are not invented design choices — they are gaps in the inputs that the ADR must close (or explicitly defer):

1. **Pipeline-definition transport** between ViPPET and SceneScape: REST pull, push, file export, or registry?
2. **Exported-scene packaging** (deferred from diagrams summary): are pipeline definitions embedded by value or referenced by ID/version?
3. **Phased rollout boundaries**: which of the six SceneScape-side deltas above land in which Phase (Foundation; Model Management Delegation; Pipeline Building Delegation & Stream Manager Adoption; Pipeline Building & Stream Manager Adoption – Part 2)?
4. **Backwards compatibility**: do today's static JSON pipeline configs and direct camera sources remain supported during the transition, and if so for how long?
5. **DLSPS runtime configuration mechanism**: confirm the target (runtime pipeline API) and the interim (today's pod recreation in K8s) are both acceptable as a staged transition.
6. **Stream Manager dependency mode**: optional (SceneScape can run without it for backward compatibility) vs. required (SceneScape always goes through Stream Manager in the target state).
