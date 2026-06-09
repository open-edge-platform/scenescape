# Content Split — ADR vs. Design Doc

> **Purpose:** Decide which content from [diagrams-summary.md](./diagrams-summary.md) and [responsibilities.md](./responsibilities.md) belongs in the ADR (`docs/adr/0012-mlops-integration-reuse.md`) versus a follow-up Design Doc. Follows the guidance in [../../../docs/README.md](../../README.md):
>
> - **ADR** = *What did we decide and why?* — short, decision-focused (1–2 pages).
> - **Design Doc** = *How will we implement this?* — detailed blueprint (5–20 pages).
>
> This intermediate is a working artifact: it does not need to follow either template and will be used to seed the design doc later.

---

## ADR scope (goes into `0012-mlops-integration-reuse.md`)

The ADR captures the **architectural decisions** SceneScape commits to. It is intentionally short and avoids implementation detail.

### Context (ADR)

- SceneScape today owns custom solutions for model download/management and visual pipeline building (static JSON configs + custom generator → K8s config maps with pod recreation).
- The Open-Edge-Platform now offers (or will offer) reusable components covering these capabilities: Model Downloader, ViPPET, DLSPS (existing, evolving), and the new Stream Manager.
- Maintaining SceneScape-specific implementations of these capabilities is redundant, costly, and divergent from the platform direction.
- Motivation is broader than UX: engineering efficiency, focus on core SceneScape functionalities (spatial awareness, sensor fusion, tracking), reduction of redundant effort across OEP.

### Decision (ADR)

- **Delegate** model management, visual pipeline building, and video-source acquisition to platform components; **reuse** them in place of SceneScape-specific implementations.
- Component assignments (one-sentence form, full detail in responsibilities matrix lives in the design doc):
  - **Model Downloader** — model lifecycle.
  - **ViPPET** — pipeline authoring; SceneScape consumes pipeline definitions via **REST pull**.
  - **DLSPS** — pipeline execution; evolve from static JSON / pod recreation toward runtime pipeline API, staged.
  - **Stream Manager** — camera discovery, video capture, livestream/replay; **optional** dependency for SceneScape.
  - **Geti** — model training; **no direct SceneScape↔Geti integration** (mediated via Model Downloader and Stream Manager).
- **SceneScape retains ownership** of: scene model, scene-level pipeline-to-source mapping, pipeline runtime orchestration against DLSPS, multimodal fusion/tracking, scene export/import.
- Adopt a **uniform dynamic API-based approach** to pipeline configuration and management for both Docker Compose and Kubernetes SceneScape deployments, replacing today's split implementation (manual static configuration for Docker Compose; custom pipeline generation with K8s config maps for Kubernetes).
- **Exported scenes embed pipeline definitions by value** so deployment is possible without ViPPET.
- **Exported scenes reference models by identifier** (not by value); Model Downloader is therefore required at deployment time to materialize the referenced models on the shared model volume.
- **SceneScape does not call Model Downloader's download endpoint.** Model download is handled out-of-band:
  - at deployment time or scene import by an **external job or script**, or
  - during pipeline development by the user via the **ViPPET UI**, into a volume shared with SceneScape.
  SceneScape's own runtime call to Model Downloader is limited to the **listing endpoint**, used when the user needs to see available models to choose or update a model in a pipeline definition.
- **Backwards compatibility:** existing static JSON pipeline configs (Docker bind-mount and K8s config maps) and the custom dynamic pipeline configuration on Kubernetes remain supported until feature parity with the ViPPET-based flow is achieved.
- **Phased rollout** (Phase names only; no release numbers):
  - *Foundation* — ADR + design baseline.
  - *Model Management Delegation* — adopt the shared model volume populated by Model Downloader; add a deployment-time job for downloading models; use the Model Downloader listing endpoint to enumerate installed models in the existing Kubernetes dynamic pipeline configuration flow.
  - *Pipeline Building Delegation & Stream Manager Adoption* — Stream Manager consumption; scene-level pipeline-to-source mapping; extend scene export/import to support externally downloaded models and embedded pipeline definitions.
  - *Pipeline Building Delegation & Stream Manager Adoption – Part 2* — full ViPPET pipeline-definition consumption; evolved DLSPS runtime integration; deprecate the custom dynamic pipeline configuration in favor of the uniform API-based dynamic pipeline configuration.

### Alternatives Considered (ADR)

- **Status quo: keep custom SceneScape implementations** (model installer, pipeline generator, direct camera sources). Pros: no integration work. Cons: redundant with platform, ongoing maintenance burden, very limited interoperability with other OEP components.
- **Push pipeline-to-source mapping into ViPPET.** Pros: single source of pipeline metadata. Cons: scene-level binding is a SceneScape domain concept (cameras serve scene-specific spatial-awareness tasks); ViPPET would need scene awareness it does not own.
- **Direct SceneScape↔Geti integration for models.** Pros: fewer hops. Cons: duplicates Model Downloader, couples SceneScape to yet another API, breaks the platform's intended separation of concerns (ViPPET owns pipeline creation and verification).
- **Push pipeline definitions by reference (ID/version) in exported scenes.** Pros: smaller artifact. Cons: deployment would require ViPPET to be reachable in production, but ViPPET is not intended to be deployed in production.
- **Make Stream Manager a hard dependency.** Pros: uniform video acquisition path. Cons: regresses today's direct-source deployments and complicates usage in scenarios where Stream Manager is not desired or available.

### Consequences (ADR)

**Positive**

- Smaller SceneScape surface area: removes custom model installer and pipeline generator over time.
- Clear separation of concerns aligned with OEP architecture.
- SceneScape team focus shifts to core spatial-awareness value.
- Deployments remain operable without ViPPET (self-contained exported scenes) and without Stream Manager (optional dependency).
- Staged transition preserves existing deployments.

**Negative**

- Cross-component dependency on Model Downloader, ViPPET, DLSPS evolution, and Stream Manager delivery timelines.
- Temporary duality: both the legacy flow (static JSON configs plus custom dynamic pipeline configuration on Kubernetes) and the new ViPPET-based flow coexist until parity.
- New runtime call from SceneScape to Model Downloader's listing endpoint adds a small new integration surface; it is needed only until the custom dynamic pipeline configuration on Kubernetes is deprecated (full parity with ViPPET).
- When ViPPET is deployed with its own embedded Model Downloader instance, and SceneScape's DLSPS reads from a separately populated model volume, the deployment design must disambiguate which Model Downloader instance owns which model volume.

### References (ADR)

- Component Interaction diagram: [SceneScape_MLOps-Component Interaction.drawio.svg](../diagrams/SceneScape_MLOps-Component%20Interaction.drawio.svg)
- Follow-up Design Doc (to be written separately): `docs/design/mlops-integration-reuse.md` (placeholder)

---

## Design-Doc scope (goes into the follow-up design doc)

The Design Doc explains **how** SceneScape implements the decisions above. It is the right home for everything below.

### Architecture & interaction detail

- Full responsibility matrix per component (Section 1 of [responsibilities.md](./responsibilities.md)).
- Cross-cutting concerns table (Section 2 of `responsibilities.md`).
- Process Model walkthrough (stages 1–7) and Component Interaction edges (Section 1 and 2 of [diagrams-summary.md](./diagrams-summary.md)).
- Per-contract specification:
  - SceneScape↔Stream Manager (livestream/replay APIs consumed; optional dependency mode).
  - SceneScape↔ViPPET (REST pull for pipeline definitions; pull cadence; auth; versioning).
  - SceneScape↔DLSPS (today: pod recreation in K8s; target: runtime pipeline API; MQTT inference output topic conventions).
  - SceneScape↔Model Downloader (deployment-time job semantics; runtime listing endpoint usage; shared-volume conventions).
  - SceneScape↔Geti (none; document why and what indirection looks like).

### Inputs and outputs (per Process Model step and per contract)

A dedicated section enumerating, for each item, the concrete data that flows in and out. Used to make the implementation contract unambiguous.

**Per Process Model step** (stages 1–7 in [diagrams-summary.md §1](./diagrams-summary.md)):

1. **Camera Setup** (Stream Manager) — Inputs: physical/networked camera devices. Outputs: configured camera devices with addressable identifiers (e.g., camera IPs / IDs).
2. **Data Acquisition** (Stream Manager) — Inputs: configured cameras, capture parameters. Outputs: synchronized video files; upload to a Geti instance.
3. **Geti Training** (Geti) — Inputs: uploaded video files. Outputs: annotated datasets, trained and validated model, model artifacts available for download.
4. **DLS Pipeline Development** (ViPPET) — Inputs: Geti-trained model (via Model Downloader). Outputs: pipeline definition (embeddable by value), verified pipeline output.
5. **Scene Development** (SceneScape) — Inputs: pipeline definition from ViPPET (REST pull), available models from Model Downloader listing endpoint, video sources from Stream Manager (or direct sources). Outputs: scene map and configuration, camera poses, scene-level pipeline-to-source mapping, list of referenced models.
6. **Package Preparation** (SceneScape) — Inputs: scene configuration, mappings, embedded pipeline definitions, model references. Outputs: exported scene artifact (self-contained except for referenced models).
7. **Deployment** (SceneScape + Stream Manager + external job) — Inputs: exported scene artifact, target environment. Outputs: deployed scene with models materialized on the shared model volume (by the external job/script), pipelines running on DLSPS, tracked objects and events emitted to business logic.

**Per contract** (per-contract specs above):

- **SceneScape → Stream Manager** — In: stream/replay request parameters. Out (to SceneScape): live or replayed video stream, stream metadata.
- **SceneScape → ViPPET** — In: pipeline-definition query (REST pull). Out (to SceneScape): pipeline definition payload suitable for embedding by value.
- **SceneScape → DLSPS** — In: pipeline start/stop/update commands, pipeline definition payload, source binding. Out (to SceneScape): pipeline lifecycle status and MQTT inference messages.
- **SceneScape → Model Downloader** — In: model listing query. Out (to SceneScape): list of available models with model paths, identifiers and metadata.
- **External job/script (or ViPPET UI) → Model Downloader** — In: model download request by identifier. Out: model files materialized on the shared model volume.

### SceneScape-side deltas — implementation

For each of the 6 deltas (Section 3 of `responsibilities.md`):

- Affected modules (`model_installer`, `manager/src/manager/ppl_generator`, `manager/src/manager/kubeclient.py`, controller pipeline orchestration, scene export/import, DLSPS adapter `dlstreamer-pipeline-server/user_scripts/gvapython/sscape`).
- Migration plan and parity criteria for retiring the legacy static-JSON / pipeline-generator flow.
- Compatibility shims and feature flags (if any).
- Test strategy per delta (unit/functional/integration/UI).

### Scene export/import format

- Schema of the exported scene artifact (pipelines embedded by value).
- Parametrization mechanism for embedded pipeline definitions (deferred from ADR resolutions; to be specified here).
- Model identification scheme on the shared volume (paths, naming, versions).

### Phased rollout — execution plan

- Per-phase concrete tasks, exit criteria, and rollback points.
- Mapping of phases to the 6 deltas (already pre-decided in `responsibilities.md` §4.3; design doc adds task-level breakdown).
- Backwards-compatibility window: when each legacy mechanism may be removed.

### Deployment topology

- Docker Compose and Kubernetes wiring for the shared model volume.
- Model storage sharing between the SceneScape and ViPPET deployments when ViPPET is deployed with its own Model Downloader instance (enumerate options for SceneScape deployed in Docker Compose and Kuberenets. ViPPET is always deployed in Docker Compose).
- Stream Manager opt-in deployment.
- DLSPS configuration for both interim (config-map + pod recreation) and target (runtime API) modes.

### Risks & open items deferred from ADR

- Pipeline definition parametrization details.
- Exact criteria for "feature parity" gate before retiring legacy JSON/pipeline-generator flow.
- gvapython → Gst Analytics Python migration plan for the SceneScape adapter (called out in the JIRA roadmap; design-level activity).

---

## Out of scope for both documents

- Geti-side integration timeline with ViPPET / Model Downloader / Stream Manager.
- Stream Manager's own API design (owned by the Stream Manager team).
- ViPPET's internal pipeline templates and verification tooling.
- Concrete UX flows in the SceneScape Manager UI (separate UX/feature work).
- Release dates, JIRA IDs, GitHub issue numbers.
