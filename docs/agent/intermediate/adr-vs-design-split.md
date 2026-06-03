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
- **Exported scenes embed pipeline definitions by value** so deployment is possible without ViPPET.
- **Backwards compatibility:** existing static JSON pipeline configs (Docker bind-mount and K8s config maps) remain supported until feature parity with the ViPPET-based flow is achieved.
- **Phased rollout** (Phase names only; no release numbers):
  - *Foundation* — ADR + design baseline.
  - *Model Management Delegation* — adopt shared model volume populated by Model Downloader.
  - *Pipeline Building Delegation & Stream Manager Adoption* — Stream Manager consumption, scene-level pipeline-to-source mapping, scene export/import.
  - *Pipeline Building Delegation & Stream Manager Adoption – Part 2* — full ViPPET pipeline-definition consumption, evolved DLSPS runtime integration.

### Alternatives Considered (ADR)

- **Status quo: keep custom SceneScape implementations** (model installer, pipeline generator, direct camera sources). Pros: no integration work. Cons: redundant with platform, ongoing maintenance, divergence from OEP roadmap, blocks DLSPS evolution.
- **Push pipeline-to-source mapping into ViPPET.** Pros: single source of pipeline metadata. Cons: scene-level binding is a SceneScape domain concept (cameras serve scene-specific spatial-awareness tasks); ViPPET would need scene awareness it does not own.
- **Direct SceneScape↔Geti integration for models.** Pros: fewer hops. Cons: duplicates Model Downloader, couples SceneScape to a training-platform API, breaks the platform's intended separation of concerns.
- **Push pipeline definitions by reference (ID/version) in exported scenes.** Pros: smaller artifact. Cons: deployment requires ViPPET to be reachable; violates the "deployable without ViPPET" requirement.
- **Make Stream Manager a hard dependency.** Pros: uniform video acquisition. Cons: regresses today's direct-source deployments; out of step with optional adoption goal.
- **Skip the staged DLSPS transition; require runtime pipeline API up front.** Pros: simpler end-state. Cons: blocks delivery; today's pod-recreation flow already works and must keep working until DLSPS evolves.

### Consequences (ADR)

**Positive**

- Smaller SceneScape surface area: removes custom model installer and pipeline generator over time.
- Clear separation of concerns aligned with OEP architecture.
- SceneScape team focus shifts to core spatial-awareness value.
- Deployments remain operable without ViPPET (self-contained exported scenes) and without Stream Manager (optional dependency).
- Staged transition preserves existing deployments.

**Negative**

- Cross-component dependency on Model Downloader, ViPPET, DLSPS evolution, and Stream Manager delivery timelines.
- Temporary duality: both legacy static JSON flow and new ViPPET-based flow coexist until parity.
- New runtime call from SceneScape to Model Downloader's listing endpoint adds a small new integration surface.
- Co-ownership of model storage between ViPPET and Model Downloader (when co-deployed) requires the deployment design to disambiguate.

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
- Model Downloader as standalone vs. embedded in ViPPET deployment (co-ownership of model storage).
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
