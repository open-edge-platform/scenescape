# ADR 12: MLOps Integration and Reuse of Pipeline Building and Model Management

- **Author(s)**: [Tomasz Dorau](https://github.com/tdorau)
- **Date**: 2026-06-11
- **Status**: `Accepted`

## Context

Customers using Scenescape often build custom visual analytics pipelines with models trained using [**Geti**](https://github.com/open-edge-platform/geti). A streamlined user experience (UX) and better interoperability between Geti, Scenescape, and visual analytic pipeline tools would allow customers to iterate more quickly and achieve their goals faster.

Scenescape currently has custom solutions for:

- **Model download and management**: Handled by the `model_installer` service and a set of static configuration conventions for a limited number of models.
- **Visual pipeline building**: Relies on manually authored JSON files for Docker Compose deployments and a custom pipeline generator for Kubernetes.

Furthermore, Scenescape's integration with the [**DL Streamer Pipeline Server (DLSPS)**](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/dlstreamer-pipeline-server) for pipeline execution is constrained by the lack of a runtime API. Pipelines are configured statically, and Kubernetes deployments must recreate DLSPS pods for every pipeline update. These limitations in runtime model management and dynamic pipeline configuration negatively impact the user experience.

In parallel, the Intel® [Open-Edge-Platform](https://github.com/open-edge-platform) (OEP) provides reusable components that cover these functionalities and enable integration with Geti:

- [**Model Downloader**](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/microservices/model-download): Manages model lifecycle and storage.
- [**ViPPET**](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.0.0/tools/visual-pipeline-and-platform-evaluation-tool) (Visual Pipeline and Platform Evaluation Tool): Supports pipeline authoring and verification.
- **Stream Manager**: A new component for camera discovery, video capture, livestreaming, and replay.

There is currently no interoperability between Scenescape and the OEP components mentioned. Integrating these components and reusing their capabilities in place of Scenescape's custom solutions would provide a better user experience, including indirect integration with Geti, and offer multiple advantages. The motivation for this change extends beyond UX to include improved engineering efficiency, a sharper focus on Scenescape's core spatial-awareness functionality (such as sensor fusion, tracking, and scene state), and a reduction of redundant engineering efforts across OEP.

## Decision

Scenescape will **delegate** model management, visual pipeline building, and video source acquisition to their corresponding OEP components, **reusing** them instead of its own specific implementations.

**Delegated Capabilities and Target OEP Components:**

- **Model Downloader**: Manages the model lifecycle.
- **ViPPET**: Handles pipeline authoring. Scenescape will consume self-contained pipeline definitions from ViPPET via a **REST pull** mechanism.
- **Stream Manager**: Manages camera discovery, video capture, livestreaming, and replay. It is an **optional** dependency for Scenescape.
- **Geti**: Used for model training. There is **no direct integration** between Scenescape and Geti. Instead, Geti is accessed indirectly through the Model Downloader (for models) and Stream Manager (for training videos).

**Evolving DLSPS Integration:**

- **DLSPS**: Continues to handle pipeline execution. The integration will evolve in stages from a static JSON and pod recreation approach to a fully runtime API, dependent on planned updates to DLSPS. Scenescape will continue to provide pipeline definitions directly to DLSPS, but the responsibility for authoring those definitions will shift from Scenescape to ViPPET.

**Scenescape Retains Ownership** of the following: the scene model, scene-level pipeline-to-source mapping, runtime pipeline orchestration with DLSPS (create, update, start, stop, remove), multimodal fusion and tracking, and scene export/import.

**Key design choices:**

- Adopt a **uniform dynamic API-based approach** to pipeline configuration and management for both Docker Compose and Kubernetes deployments, replacing today's split implementation (manual static configuration for Docker Compose; custom pipeline generation with K8s config maps for Kubernetes).
- **Exported scenes embed pipeline definitions by value** so that deployment is possible without ViPPET.
- **Exported scenes support two model deployment paths**, selectable by the deployment operator based on the scenario:
  - **Models referenced by identifier** (standard path): a job or script downloads them via Model Downloader at deployment time; Model Downloader is required.
  - **Models embedded as a compressed volume** (air-gap / offline path): the operator extracts the embedded volume; Model Downloader is not required.

  In both cases, populating the shared model volume before Scenescape starts is the deployment operator's responsibility.
- **Scenescape does not call Model Downloader's download or listing endpoints at runtime.** Model volume population is out-of-band:
  - via an **external job or script** that downloads models through Model Downloader (standard path), or
  - by the **deployment operator** extracting the embedded model volume from the exported package (air-gap path), or
  - during pipeline development, by the user via the **ViPPET UI** into a volume shared with Scenescape.

- **Backwards compatibility:** existing static JSON pipeline configurations (Docker bind-mount and Kubernetes config maps) and the custom dynamic pipeline configuration on Kubernetes remain supported until feature parity with the ViPPET-based flow is achieved.

**Phased rollout**:

- _Foundation_ (current) — ADR and design baseline.
- _Model Management Delegation_ — adopt the shared model volume populated by Model Downloader; add a deployment-time model volume population job (download path); optionally include a compressed model volume in the exported package (air-gap / offline path).
- _Pipeline Building Delegation & Stream Manager Adoption_ — Stream Manager consumption; scene-level pipeline-to-source mapping; extend scene export/import to support externally downloaded models and embedded pipeline definitions.
- _Pipeline Building Delegation & Stream Manager Adoption – Part 2_ — full ViPPET pipeline-definition consumption; evolved DLSPS runtime integration; deprecate the custom dynamic pipeline configuration in favor of the uniform API-based dynamic pipeline configuration.

## Alternatives Considered

- **Status quo: keep custom Scenescape implementations** (model installer, pipeline generator, direct camera sources). _Pros_: no integration work. _Cons_: redundant with the platform, ongoing maintenance burden, very limited interoperability with other OEP components.
- **Push pipeline-to-source mapping into ViPPET.** _Pros_: a single source of pipeline metadata. _Cons_: scene-level binding is a Scenescape domain concept — different cameras in the same scene serve different spatial-awareness tasks — and ViPPET would need scene awareness it does not own.
- **Direct Scenescape↔Geti integration for models.** _Pros_: fewer hops. _Cons_: duplicates Model Downloader, couples Scenescape to yet another API, and breaks the platform's intended separation of concerns (ViPPET owns pipeline creation and verification).
- **Push pipeline definitions by reference (ID/version) in exported scenes.** _Pros_: smaller artifact. _Cons_: deployment would require ViPPET to be reachable in production, but ViPPET is not intended to be deployed in production.
- **Make Stream Manager a hard dependency.** _Pros_: a uniform video acquisition path. _Cons_: regresses today's direct-source deployments and complicates usage in scenarios where Stream Manager is not desired or available.

## Consequences

### Positive

- Smaller Scenescape surface area: the custom model installer and pipeline generator are removed over time.
- Clear separation of concerns aligned with the OEP architecture.
- Scenescape team focus shifts to core spatial-awareness value (sensor fusion, tracking, scene state).
- Deployments remain operable without ViPPET (self-contained exported scenes), without Stream Manager (optional dependency), and without Model Downloader (when models are embedded in the exported package).
- A staged transition preserves existing deployments throughout the rollout.

### Negative

- Cross-component dependency on ViPPET delivery, DLSPS evolution, and Stream Manager delivery timelines. Model Downloader is required only on the standard (non-air-gap) deployment path.
- Temporary duality: both the legacy flow (static JSON configurations plus custom dynamic pipeline configuration on Kubernetes) and the new ViPPET-based flow coexist until parity.
- When ViPPET is deployed with its own Model Downloader instance, providing efficient model sharing between the Scenescape and ViPPET deployments — without maintaining redundant downloads or copies — may be complex from a technical or UX perspective.

## References

- Follow-up Design Doc: `docs/design/mlops-integration-reuse.md`
