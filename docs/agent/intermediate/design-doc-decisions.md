# Design Doc Decisions — `docs/design/mlops-integration-reuse.md`

> **Purpose:** Living decision log for the MLOps integration design document. Captures decisions taken while drafting that supplement (not override) [ADR-12](../../adr/0012-mlops-integration-reuse.md). Sections are added per drafting iteration; later iterations may amend earlier entries — when they do, the amendment is recorded in place rather than appended at the end, so this file always reflects the current intent.

## Drafting status

- §1–§4 — drafted.
- §5.1 Component-level architecture — drafted.
- §5.2 End-to-end process model — drafted.
- §5.3 Responsibility matrix and cross-cutting concerns — drafted.
- §5.4 Client-library integration layer — drafted.
- §5.5 Per-contract specifications (one subsection per OEP component) — drafted.
- §5.6 Per-service SceneScape deltas — drafted.
- §5.7 Scene export/import format — drafted.
- §5.8 Deployment topology — drafted.
- §6 Alternatives, §7 Risks, §8 Rollout/Migration, §9 Testing & Monitoring, §10 Open Questions, §11 References — pending.
- PR description at `docs/agent/design-pull-request-description.md` — pending.

> **Note on subsection numbering.** When deciding what each subsection of §5 covers, refer to the *Drafting status* list above (it tracks the actual numbering used in the document). Earlier planning notes in this file may use a different §5 sub-numbering; that is the planning sequence, not the final structure.

---

## Step-1 decisions

1. **Listing-call permanence** — SceneScape's runtime call to Model Downloader's listing endpoint is **permanent** (UI model-pick/update flow, even post-ViPPET integration). Mirror ADR-12's neutral phrasing; drop the "needed only until parity" qualifier from `adr-vs-design-split.md`.
2. **Phase 4 exit criterion** — Removal of the legacy dynamic pipeline configuration (custom Kubernetes pipeline generation + pod recreation).
3. **gvapython migration** — Deferred item under *Open Questions*. Brief subsection: custom logic in `dlstreamer-pipeline-server/user_scripts/gvapython/sscape/`, migration to Gst Analytics Python required, breakdown deferred to next phase, cross-link the ViPPET-pipeline-definition delta and the DLSPS-runtime-API delta.
4. **Numbering** — Use "Delta 1–6" (from `responsibilities.md` §3) throughout the planning notes. The design document body itself avoids numeric cross-references and uses descriptive names instead (see *Wording disciplines* below).

## Step-2 drift resolutions (intermediate sources vs. ADR-12)

- **D1 (listing-call wording)** — Mirror ADR-12 neutral phrasing.
- **D2 (multi–Model-Downloader topology)** — *Risks* section cites ADR-12's broader phrasing; *Deployment topology* enumerates concrete ownership-disambiguation options.
- **D4 (backwards-compat scope)** — Treat *static JSON* (Docker bind-mount + Kubernetes config maps) and *custom dynamic pipeline configuration on Kubernetes* as **two distinct legacy mechanisms** with separate parity gates. Follow ADR-12 phrasing, not `responsibilities.md` §4.4.

## Step-2 structural backbone

- §1 Overview → links to ADR §Decision.
- §2 Goals → links to ADR §Decision.
- §3 Non-Goals → derived from `adr-vs-design-split.md` *Out of scope* + ADR §Alternatives.
- §4 Background/Context — short; **includes SceneScape Component Reference** (see Step-4); links to ADR §Context for motivation.
- §5 Proposed Design (subsections — see *Drafting status* for current numbering).
- §6 Alternatives → references ADR §Alternatives.
- §7 Risks → references ADR §Negative; adds design-level risks (incl. D2).
- §8 Rollout/Migration → 4 phases × 6 deltas; Phase 4 exit = legacy dynamic pipeline removed; decision-timing column.
- §9 Testing & Monitoring → per-delta strategy.
- §10 Open Questions → parametrization format, parity criteria, gvapython migration, multi–Model-Downloader topology, OMZ → public-models migration, client-library repository location.
- §11 References → ADR-12, intermediates, presentation extracts, diagram SVGs.

## Step-3 decisions (JIRA + NOKIA cross-check)

5. **N1 — Model–camera relationship (canonical wording):**
   - Models are **parameters of pipeline definitions**.
   - Models are **embedded by reference** in exported pipeline definitions (consistent with ADR-12).
   - A pipeline definition can be **mapped to one or more sources (cameras)** — one-to-many.
   - The pipeline-definition-to-source mapping is **persisted in SceneScape scene configuration**.
   - Apply in the per-service deltas (pipeline-to-source mapping delta), the scene export/import format, and the responsibility matrix.
6. **N2 — Model traceability & class-label management** (concrete design constraints):
   - Model ID + version in **both camera and scene metadata** (hashes for verification). → scene export/import format.
   - Class labels managed on Geti side; SceneScape MOT tracks all classes without per-class config. → responsibility matrix + scene-export delta.
7. **N3 — Concrete Model Downloader API** for the per-contract specifications:
   - `GET /api/v1/models[?name=<n>][&hub=...][&precision=...]` returning name, hub, path, precision(s), size, install timestamp, plugin metadata.
   - SceneScape does **not** need DELETE.
   - Do not cite JIRA IDs in the design doc body.
8. **N4 — OMZ → public-models migration** — Brief mention under *Rollout / Migration Plan* (Phase 2 / Model Downloader delta) and *Open Questions*. Do not specify the new model set.

## Step-4 decisions — SceneScape granularity (hybrid policy)

**Policy.** Hybrid. Sections that mirror the ADR (Overview, Goals, Non-Goals, Alternatives, Open Questions) keep "SceneScape" monolithic. Sections describing current state or concrete integration mechanics (Background, Responsibility matrix, Per-contract specs, Per-service deltas, Scene export/import, Deployment topology, Rollout, Testing) refine to named services. Decision-timing column in the per-service deltas and the rollout plan marks each delta as "service ownership decided now" or "deferred per phase".

**Naming.** Use **"SceneScape Component Reference"** (not "glossary") for the inventory section, placed inside Background.

**Component definitions** (canonical wording for §4):

- **Manager** — current monolithic Django service. May split in future into:
  - **Manager (back-end)** — REST API + scene model + DLSPS-lifecycle + scene import/export. Term used independent of split timeline.
  - **Manager (UI)** — thin UI layer over Manager back-end's REST API. Term used independent of split timeline.
- **Scene Controller** — runtime scene state + fusion + tracking; consumes DLSPS MQTT output. **No MLOps-integration changes planned; mentioned only for context.**
- **Auto Camera Calibration** — independent service; may consume images from Stream Manager (deferred).
- **Mapping** *(experimental)* — may consume streams/images from Stream Manager (deferred).
- **`model_installer`** — **removed as part of the Model Downloader delta**.
- **SceneScape-authored DLSPS extensions** *(NOT a separate SceneScape service)* — SceneScape-specific custom code injected statically into DLSPS configuration (currently lives under `dlstreamer-pipeline-server/user_scripts/gvapython/sscape/` in the SceneScape repository, not in the DLSPS repository or codebase). Runs inside the DLSPS pipeline process at runtime. To be refactored and split into more reusable components across Phase 2 and following phases (per ITEP-92811 scope: switch from gvapython to Gst Analytics Python; simplify/break down Python adapter — phase 1, with phase 2 in later releases). The `gvapython → Gst Analytics Python` migration and the adapter breakdown are listed in *Open Questions*.
- **`scene_common`** *(shared library, not a service)*.

**Service-ownership matrix** (drives the per-contract specs, per-service deltas, and rollout plan):

| Delta | Owner | Timing |
|---|---|---|
| 1 (Stream Manager consumption) | Candidates: Manager BE (discovery); DLSPS (stream consumption + timestamped recording); Mapping (streams/images); Auto Camera Calibration (images). List candidates only. | Deferred per phase |
| 2 (ViPPET pipeline definitions) | Manager back-end (pull + cache + persist in scene config) | Decided now |
| 3 (Model Downloader) | Manager **UI** → listing endpoint; `model_installer` removed | Decided now |
| 4 (scene-level pipeline-to-source mapping) | Manager back-end (scene model owner) | Decided now |
| 5 (DLSPS runtime API) | Manager **back-end** → DLSPS REST API for pipeline lifecycle | Decided now (pod-recreation interim retired in Phase 4) |
| 6 (scene export/import) | Manager back-end (extends `manager/src/manager/scene_import.py`) | Decided now |

**Wording disciplines:**

- "SceneScape" valid in monolith sections (per ADR).
- "Manager back-end" / "Manager UI" in concrete-integration sections; never bare "SceneScape Manager" when discussing the BE/UI split.
- "SceneScape-authored DLSPS extensions" — never "SceneScape Python adapter service".
- Scene Controller mentioned only in Background and once in the per-contract specs (existing MQTT contract; no change).
- **No numeric cross-references** inside the body. Use descriptive names ("the DLSPS runtime API delta", "the per-contract specifications below", "the *Constraints* section"). Only ADR-12 anchor links (`#decision`, `#context`) carry section identifiers.
- **No section-intro paragraphs that just enumerate subsections.** Subsection titles are the table of contents.
- **Manager BE/UI labels in matrices are recommendations, not committed boundaries.** Decision on splitting Manager is deferred; until then implementations live in the current monolithic Manager service. Every section using BE/UI labels should reiterate or cross-reference this caveat once.
- **Use "pipeline definition" consistently.** Do not introduce alternative terms like "pipeline graph" or "pipeline body" for the same concept. When distinguishing the DLSPS-consumable graph payload inside a pipeline definition, say "DLSPS-consumable pipeline definition body" or similar — not "pipeline graph".
- **Process Model diagram presents one representative flow.** Always include a caveat that stage order is not fixed (stages may be reordered, repeated, skipped, or parallelized).

## Step-5 decisions — Reusable integration libraries

9. **Naming**: **"client library"** (per OEP component — e.g., *Model Downloader client library*, *ViPPET client library*, *DLSPS client library*, *Stream Manager client library*). Avoid "adapter" (collides with SceneScape-authored DLSPS extensions). No client library for Geti.
10. **Repository location**: **Deferred** — flagged as an *Open Question*. Three candidates: (A) extend `scene_common/` with an `integration/` subpackage; (B) introduce a new top-level `integration_clients/` shared library; (C) per-component decision.
11. **Structural placement in §5**:
    - Dedicated subsection "Client-library integration layer" placed **before** the per-contract specifications. Content: rationale, list of client libraries, common concerns (auth, retry, telemetry, schema validation, test doubles), packaging note (deferred).
    - Per-contract specifications subsection — each contract references the corresponding client library as the implementing layer.
    - Per-service deltas subsection — each delta names which client library is created/extended and which SceneScape services consume it.
    - *Risks* — add "tight coupling to evolving OEP component APIs" → mitigated by isolating churn within client libraries.
    - *Testing & Monitoring* — note client libraries tested in isolation; SceneScape-service tests use the libraries' test doubles.
    - Component Interaction SVG: keep as-is; add one sentence under it noting each SceneScape→OEP arrow is realized via the corresponding client library.

## ADR-12 follow-up edit (2026-06-09)

- **ADR Context**: split into delegation bullets (model management, pipeline building) + a separate paragraph for **existing DLSPS integration being evolved**.
- **ADR Decision**: renamed "Component assignments" to "Delegated capabilities and their target OEP components" (Model Downloader, ViPPET, Stream Manager, Geti-indirect) + new "Existing DLSPS integration being evolved" subgroup (DLSPS only).

## Step-6 decisions — §5.7 and §5.8 scoping

12. **§5.7 Scene export/import format** — Cover **only the delta vs. today**; do not re-specify the existing format. Delta is three items: (a) camera configuration (source ID + calibration) stored separately from pipeline definition; (b) model metadata is part of pipeline definition as a template-parameter value (no separate `models` section); (c) pipeline-to-camera mapping is a first-class section. Keep concise. Container shape (single JSON / multi-file / archive) deferred to *Open Questions*.
13. **§5.8 Multi–Model-Downloader topology** — Keep concise. **Only two options**: O1 (single shared instance) and O2 (separate instances + separate volumes). O3 (separate instances + shared volume backend) removed. Decision tracked in *Open Questions*.
14. **§5.8 Backwards-compatibility implications for topology** — **Removed**: the *Constraints* section and the parity-criterion rows in each delta already cover this; the topology subsection added no new information.
