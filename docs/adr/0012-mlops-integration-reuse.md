# ADR 12: MLOps Integration and Reuse

- **Author(s)**: [Tomasz Dorau](https://github.com/tdorau)
- **Date**: 2026-06-08
- **Status**: `Proposed`

## Context

SceneScape today owns custom solutions for two capabilities that are also provided — or will be provided — by other Intel® [Open-Edge-Platform](https://github.com/open-edge-platform) (OEP) components:

- **Model download and management**, currently handled by SceneScape's `model_installer` and a set of model-configuration conventions.
- **Visual pipeline building**, currently handled by manually authored JSON files for Docker Compose deployments and a custom pipeline generator for Kubernetes deployments.

In addition, SceneScape's **existing integration with DL Streamer Pipeline Server (DLSPS)** is constrained by the absence of a runtime pipeline API: pipelines are statically configured, and Kubernetes deployments recreate DLSPS pods on every pipeline update. This integration is being **evolved**, not introduced.

In parallel, OEP offers reusable components covering these capabilities and the evolving DLSPS integration:

- [**Model Downloader**](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/model-download) — model lifecycle and storage.
- [**ViPPET**](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/tools/visual-pipeline-and-platform-evaluation-tool) (Visual Pipeline and Platform Evaluation Tool) — pipeline authoring and verification.
- [**DL Streamer Pipeline Server (DLSPS)**](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/dlstreamer-pipeline-server) — pipeline execution (existing integration, evolving toward a runtime pipeline API).
- **Stream Manager** — a new component for camera discovery, video capture, livestream and replay.
- [**Geti**](https://github.com/open-edge-platform/geti) — model training (no direct SceneScape integration is intended).

Maintaining SceneScape-specific implementations of model management and pipeline building is redundant with the platform direction, increases ongoing maintenance, and limits interoperability with other OEP components. The motivation for change is broader than UX: engineering efficiency, focus on SceneScape's core spatial-awareness functionality (sensor fusion, tracking, scene state), and reduction of redundant effort across OEP.

## Decision

SceneScape **delegates** model management, visual pipeline building, and video-source acquisition to the corresponding OEP components and **reuses** them in place of SceneScape-specific implementations.

**Delegated capabilities and their target OEP components:**

- **Model Downloader** — model lifecycle.
- **ViPPET** — pipeline authoring. SceneScape consumes pipeline definitions via **REST pull**.
- **Stream Manager** — camera discovery, video capture, livestream and replay. Stream Manager is an **optional** dependency for SceneScape.
- **Geti** — model training. There is **no direct SceneScape↔Geti integration**; Geti is reached indirectly via Model Downloader (for models) and Stream Manager (for training videos).

**Existing DLSPS integration being evolved:**

- **DLSPS** — pipeline execution. The integration evolves from static JSON / pod recreation toward a runtime pipeline API, in stages.

**SceneScape retains ownership** of: the scene model, the scene-level pipeline-to-source mapping, runtime pipeline orchestration against DLSPS, multimodal fusion and tracking, and scene export/import.

**Key design choices:**

- Adopt a **uniform dynamic API-based approach** to pipeline configuration and management for both Docker Compose and Kubernetes deployments, replacing today's split implementation (manual static configuration for Docker Compose; custom pipeline generation with K8s config maps for Kubernetes).
- **Exported scenes embed pipeline definitions by value** so that deployment is possible without ViPPET.
- **Exported scenes reference models by identifier** (not by value). Model Downloader is therefore required at deployment time to materialize the referenced models on a model volume shared with DLSPS.
- **SceneScape does not call Model Downloader's download endpoint.** Model download is handled out-of-band:

  - at deployment time or scene import by an **external job or script**, or
  - during pipeline development by the user via the **ViPPET UI**, into a volume shared with SceneScape.

  SceneScape's own runtime call to Model Downloader is limited to the **listing endpoint**, used when the user needs to see available models to choose or update a model in a pipeline definition.

- **Backwards compatibility:** existing static JSON pipeline configurations (Docker bind-mount and Kubernetes config maps) and the custom dynamic pipeline configuration on Kubernetes remain supported until feature parity with the ViPPET-based flow is achieved.

**Phased rollout**:

- _Foundation_ (current) — ADR and design baseline.
- _Model Management Delegation_ — adopt the shared model volume populated by Model Downloader; add a deployment-time job for downloading models; use the Model Downloader listing endpoint to enumerate installed models in the existing Kubernetes dynamic pipeline configuration flow.
- _Pipeline Building Delegation & Stream Manager Adoption_ — Stream Manager consumption; scene-level pipeline-to-source mapping; extend scene export/import to support externally downloaded models and embedded pipeline definitions.
- _Pipeline Building Delegation & Stream Manager Adoption – Part 2_ — full ViPPET pipeline-definition consumption; evolved DLSPS runtime integration; deprecate the custom dynamic pipeline configuration in favor of the uniform API-based dynamic pipeline configuration.

## Alternatives Considered

- **Status quo: keep custom SceneScape implementations** (model installer, pipeline generator, direct camera sources). _Pros_: no integration work. _Cons_: redundant with the platform, ongoing maintenance burden, very limited interoperability with other OEP components.
- **Push pipeline-to-source mapping into ViPPET.** _Pros_: a single source of pipeline metadata. _Cons_: scene-level binding is a SceneScape domain concept — different cameras in the same scene serve different spatial-awareness tasks — and ViPPET would need scene awareness it does not own.
- **Direct SceneScape↔Geti integration for models.** _Pros_: fewer hops. _Cons_: duplicates Model Downloader, couples SceneScape to yet another API, and breaks the platform's intended separation of concerns (ViPPET owns pipeline creation and verification).
- **Push pipeline definitions by reference (ID/version) in exported scenes.** _Pros_: smaller artifact. _Cons_: deployment would require ViPPET to be reachable in production, but ViPPET is not intended to be deployed in production.
- **Make Stream Manager a hard dependency.** _Pros_: a uniform video acquisition path. _Cons_: regresses today's direct-source deployments and complicates usage in scenarios where Stream Manager is not desired or available.

## Consequences

### Positive

- Smaller SceneScape surface area: the custom model installer and pipeline generator are removed over time.
- Clear separation of concerns aligned with the OEP architecture.
- SceneScape team focus shifts to core spatial-awareness value (sensor fusion, tracking, scene state).
- Deployments remain operable without ViPPET (self-contained exported scenes) and without Stream Manager (optional dependency).
- A staged transition preserves existing deployments throughout the rollout.

### Negative

- Cross-component dependency on Model Downloader availability, ViPPET delivery, DLSPS evolution, and Stream Manager delivery timelines.
- Temporary duality: both the legacy flow (static JSON configurations plus custom dynamic pipeline configuration on Kubernetes) and the new ViPPET-based flow coexist until parity.
- A new runtime call from SceneScape to Model Downloader's listing endpoint adds a small new integration surface.
- When ViPPET is deployed with its own Model Downloader instance, providing efficient model sharing between the SceneScape and ViPPET deployments — without maintaining redundant downloads or copies — may be complex from a technical or UX perspective.

## References

- Follow-up Design Doc (to be written separately): `docs/design/mlops-integration-reuse.md` (placeholder)
