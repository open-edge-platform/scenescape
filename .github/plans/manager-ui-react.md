<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Manager UI — ViPPET Design Ethos & React Alignment

This plan captures the **2D Manager** design ethos distilled from the Open Edge
Platform / ViPPET alignment work, and lays out an incremental path to a React
base so Scenescape’s administrative and scene-workspace UI can track ViPPET
closely.

**Out of scope:** the **3D scene UI** (`scenescape3d`, lil-gui panels, THREE.js
workspace). It is unique to Scenescape and **stays as-is** (separate stack,
separate visual language). Do not fold 3D into this React/ViPPET track unless a
future ADR explicitly revisits that boundary.

---

## 1. Goals

1. **Visual parity with ViPPET (2D)** — same Intel OEP light palette, type,
   density, and interaction patterns users already see in the broader platform.
2. **Structural fitness** — live scene workspace (map + cameras + side tools)
   expressed as components and state, not jQuery template clones and CSS
   overrides of Bootstrap `input-group`s.
3. **Incremental delivery** — Django remains the host for auth, routing, and
   server-rendered CRUD; React mounts where interactivity is highest.
4. **Clear 2D / 3D split** — React + ViPPET for Manager 2D; 3D UI unchanged.

---

## 2. Design ethos (2D Manager)

These principles are the product of the current OEP-style polish. Future UI work
(React or not) should follow them.

### 2.1 Platform alignment

| Token / cue | Direction |
| ----------- | --------- |
| Brand | `#0054ae` primary; `#001e50` nav; soft accent `#0099ec` |
| Surface | Light only for Manager 2D: `#f4f5f5` page, `#ffffff` cards, `#e9e9e9` borders |
| Type | Montserrat headings, Open Sans body (ViPPET / OEP stack) |
| Radius | Soft, modest (`~0.625rem`) — not pill-heavy chrome |
| Status | Green `#008a00` / red `#da2e56`; muted text `#808080` |

Prefer **shared names** with ViPPET where possible (map `--ss-*` → platform
token names during the React extraction) so theming stays one-way syncable.

### 2.2 Page chrome

- **Breadcrumbs** for hierarchy (Scenes → scene name → …).
- **Page header**: title + sparse toolbar actions; rate / export / 3D link stay
  secondary to the workspace, not a second dashboard.
- **Form pages**: `page-header` + single form card + action row aligned to the
  field grid — create/update/delete should feel like ViPPET admin forms.
- **Modals / confirms**: OEP dialog chrome; destructive actions explicit;
  help content in modals, not competing primary buttons.
- **Toasts / notices**: quiet, consistent 2D treatment (do not restyle 3D toasts
  under this plan).

### 2.2.1 Form field width (ViPPET / Geti practice)

Neither ViPPET nor Geti (Adobe Spectrum) stretch short text fields across the
full viewport. Forms live in a **readable content column**; field width tracks
expected content, not browser width.

| Cue | Direction |
| --- | --------- |
| Default form card | Cap at ~`48rem` (`.ss-form-card`) — room for label track + field |
| Label column | Fixed track (~`10.5–12.5rem`), left-aligned; do **not** rely on Bootstrap `col-sm-2` percentages inside a capped card (they scrunch labels) |
| Short fields (name, ID, selects) | Cap inputs at ~`28rem` inside the card |
| Wide editors (maps, geospatial, long pipelines) | Opt in with `.ss-form-card--wide` (~`64rem`); textareas may use the card width |
| Geti / Spectrum reference | Form `maxWidth` ~`300–320px` / `size-3000` for simple stacks; Scenescape side-label rows need a wider card + dedicated label track, **not** fluid full-bleed |
| Anti-pattern | Uncapped `col-sm-10` inputs across `container-fluid`, or percentage label cols inside a narrow max-width card |

React forms should use the same caps via tokens / layout primitives (`FormCard`
default vs `wide`), not page-level `width: 100%` on every `TextField`.

### 2.3 Scene detail workspace (canonical 2D layout)

The scene detail page is the reference composition for live 2D work:

```
┌────────────────────────────────────────────────────────────┐
│ Breadcrumb · Scene title · sparse toolbar (rate, 3D, …)   │
├──────────────────────────────────────────┬─────────────────┤
│ Map (flex-grow, fits pane)               │ Toggles         │
│                                          │ Tabs            │
│                                          │ Tab body ↺ only │
│ Camera filmstrip (horizontal)            │ scroll region   │
└──────────────────────────────────────────┴─────────────────┘
```

**Ethos rules for this page:**

1. **One page scroll max — prefer zero.** Desktop: lock the shell to the
   viewport; only the side tab body scrolls. Avoid dual scrollbars (page +
   side panel).
2. **Map + cameras correlate.** Camera cards live under the map (filmstrip),
   not buried in the Cameras tab. The Cameras tab is management / help only.
3. **Side panel is vertical-first.** Entity editors (ROI, tripwire, sensors)
   are stacked cards: index + name + delete; options in a narrow column; no
   horizontal `input-group` toolbars forced into a ~28rem rail.
4. **Help is quiet.** `?` beside the panel title (or equivalent text link),
   never a full-width primary “info” button next to “+ New …”.
5. **Primary actions earn primary paint.** “+ New …” / Save are the loud
   controls; rates, dismiss, and help stay muted.
6. **Focus / map mode** may hide chrome and refit the map; camera strip can
   collapse without inventing a second layout system.
7. **Numeric telemetry** is readable (e.g. camera FPS to 2 decimal places).

### 2.4 Density and restraint

- Prefer one job per panel section.
- Prefer fewer full-width stacked buttons over icon soups.
- Cards in the filmstrip should be readable (comfortable preview height/width),
  not postage stamps — horizontal scroll is acceptable; crushing the preview is not.
- Do not import 3D “glass / lil-gui” aesthetics into 2D Manager.
- Do not stretch admin form inputs to the viewport edge (§2.2.1).

### 2.5 What we are aligning *to*

**ViPPET / Open Edge Platform 2D admin patterns**, not a generic dashboard look
and not Scenescape 3D. When unsure: match ViPPET spacing, type, buttons, and
form structure first; keep Scenescape-only concepts (scene map, ROI, tripwires,
filmstrip) as **domain components** styled with those tokens.

---

## 3. Current stack vs target

| Layer | Today (2D) | Target |
| ----- | ---------- | ------ |
| Shell | Django templates + Bootstrap 4-ish | Django shell (auth, nav) + React mounts |
| Scene workspace | `sceneDetail.html` + monolithic `sscape.js` + Snap.svg | React app island: layout, tabs, entity forms, MQTT-driven rates |
| Map / SVG | Snap.svg in `sscape.js` | Keep SVG/map engine initially behind an adapter; replace later if needed |
| Design tokens | `:root` `--ss-*` in `style.css` | Shared token module consumed by React (and optionally CSS vars for legacy pages) |
| Forms / lists | Server templates (`cam_*`, `scene_*`, …) | Phase later: React or keep SSR with shared token CSS |
| 3D | Separate JS entry / UI | **Unchanged** |

---

## 4. React migration plan (ViPPET-aligned)

### Phase 0 — Contract with ViPPET

- Inventory ViPPET (or OEP design-system) primitives we will reuse or mirror:
  Button, TextField, Modal, Tabs, Breadcrumb, Toast, Card, PageHeader.
- Publish a **token mapping table** (`ss.*` ↔ ViPPET names) in this folder or
  adjacent `manager` design notes.
- Decide package strategy: consume a published ViPPET UI package **if** license
  and versioning allow; otherwise a thin `manager/ui` package that **copies
  token values and API shapes** for easy later swap.

**Exit:** documented component/token checklist reviewers can use on every PR.

### Phase 1 — Tooling island

- Add a small frontend toolchain (Vite recommended) under e.g.
  `manager/ui/` producing a hashed bundle served as Django static.
- One mount point: `<div id="ss-scene-detail-root">` with JSON bootstrap
  (`scene`, sensors, rois, tripwires, urls, auth token).
- CI: lint/format/test for the UI package; `make` target to build into
  `manager/src/manager/static/`.
- **Do not** rewrite 3D build or `scenescape3d.js`.

**Exit:** empty React root renders inside existing scene detail without
regressing MQTT/map (map can still be legacy until Phase 2).

### Phase 2 — Scene detail shell in React (highest ROI)

Port layout and chrome first, keep map drawing in an adapter:

1. `SceneDetailPage` — viewport-locked shell, breadcrumb, header toolbar.
2. `SceneMapPane` — hosts existing SVG/map via ref/adapter (`fitSceneMapDisplay`
   behavior preserved).
3. `CameraFilmstrip` — cards, FPS formatting, calibrate links.
4. `SceneSidePanel` — toggles, tabs, scroll region only inside tab body.
5. Help as title affordance → existing modals (React modal wrappers with ViPPET
   chrome).

**Exit:** no dual page/side scroll; filmstrip + side panel match ethos §2.3;
Django template is a thin host.

### Phase 3 — Domain editors as React state

Replace `#roi-template` / `#tripwire-template` clone flows:

- `RegionEditorList` / `TripwireEditorList` — vertical entity cards (index,
  name, delete, volumetric/height/buffer, occupancy colors).
- Single source of truth in React state; serialize to the same JSON fields the
  backend already expects.
- Map interaction events call into React (add vertex, new tripwire, select).

**Exit:** delete clone-based templates for ROI/tripwire; jQuery handlers for
those forms removed or reduced to the map adapter.

### Phase 4 — Shared ViPPETized primitives everywhere 2D

- Extract `Button`, `Modal`, `PageHeader`, `FormCard`, `Toast` used by scene
  detail.
- Optionally remount high-traffic forms (camera create/calibrate chrome) onto
  the same primitives **without** requiring full SPA routing.
- Retire duplicate CSS in `style.css` as pages move; keep a thin legacy bridge
  (`--ss-*` aliases) until templates are gone.

**Exit:** new 2D UI work lands in React components by default; template-only
pages are legacy.

### Phase 5 — Lists & IA (later)

- Scene / camera / sensor / model lists and nav IA — only after the workspace
  and design-system package are stable.
- Sign-in and other low-interaction pages may remain Django+CSS with tokens.

### Non-goals (explicit)

- Rewriting the **3D** UI in React or ViPPET.
- Forcing a client-side SPA for all Manager URLs in v1.
- Pixel-perfect clone of ViPPET screens that do not exist in Scenescape —
  align **system**, not copy unrelated product pages.

---

## 5. Suggested package sketch

```
manager/ui/
  package.json
  vite.config.*
  src/
    tokens/          # ViPPET-aligned design tokens
    components/      # Button, Modal, Tabs, PageHeader, …
    scene/           # SceneDetailPage, Filmstrip, SidePanel, editors
    map/             # Snap/svg adapter (legacy bridge)
    mqtt/            # telemetry hooks (rates, objects) if extracted
  README.md          # build + Django static integration
```

Django:

- `sceneDetail.html` → bootstrap JSON + `<div id="ss-scene-detail-root">` +
  script tag for the built bundle.
- 3D template/entry untouched.

---

## 6. Alignment checklist (PR gate for 2D UI)

Use on Manager 2D changes (React or transitional CSS):

- [ ] Uses platform tokens (no one-off purple/cream/dark themes).
- [ ] Primary button reserved for primary actions.
- [ ] Help is quiet (icon/link), not a competing CTA.
- [ ] Form cards/fields use capped readable widths (§2.2.1); wide opt-in only when needed.
- [ ] Scene workspace: single scroll in side tab body on desktop.
- [ ] Filmstrip cameras remain correlated under the map.
- [ ] Side editors are vertical-first; no horizontal control strips that clip.
- [ ] Telemetry formatting is human-readable.
- [ ] No changes required to 3D UI for the change to ship.
- [ ] If React: components live under `manager/ui` with ViPPET-mapped names.

---

## 7. Risks & mitigations

| Risk | Mitigation |
| ---- | ---------- |
| Map/SVG logic tightly coupled to jQuery | Adapter layer in Phase 2; port editors before porting geometry |
| Design drift from ViPPET | Phase 0 token/component checklist; prefer shared package |
| Bundle size / two systems | Island only on scene detail first; tree-shake; no full SPA |
| Test gaps | Add UI unit tests for editors; keep existing BAT/UI tests pointed at URLs |
| Accidental 3D restyle | Codeowners / checklist: 3D paths out of scope |

---

## 8. Success criteria

- Scene detail 2D matches ViPPET density and chrome without Bootstrap fights.
- ROI/tripwire editing is component state — no hidden HTML templates.
- New 2D features default to `manager/ui` React components.
- 3D scene experience remains on its current stack with no regression from this
  workstream.
- Design tokens and primitives are documented so ViPPET upgrades are a mapping
  update, not a restyle archaeology exercise.

---

## 9. Immediate next steps (when prioritized)

1. Confirm ViPPET package availability / license for direct dependency vs mirror.
2. Land Phase 0 token mapping + Phase 1 Vite island scaffolding.
3. Port Phase 2 shell using the ethos in §2.3 (viewport lock, filmstrip, quiet
   help) as acceptance criteria.
4. Keep shipping transitional Django/CSS fixes only when they reduce risk for
   the React port (do not expand `sscape.js` further without an adapter plan).
