<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Tighten empty space on Manager lists and scene detail

Status: **not started**. Design agreed in review; implement in a later PR.
Do not fold into calibrate / geospatial / theme work.

## Problem

Two different layout mistakes produce the same complaint (“large empty
spaces”) on a wide monitor.

### Admin lists (Cameras, Sensors, Object Library)

These are 1–3 short columns plus actions, rendered as a full-width table
inside Django `container-fluid`.

- Object Library is the worst case: one Name column plus actions spanning
  the viewport.
- Columns share leftover width equally, so gaps sit *between* Name / ID /
  Scene instead of after the last column.
- Page title is landing-page scale (`1.75rem`) and the breadcrumb only
  repeats the page name.
- Empty states are a one-line message inside a hollow full-width card.

Scenes Home is a thumbnail gallery and should stay that way. These pages
are lookup inventories, not dashboards.

### Scene detail

This emptiness is mostly **letterboxing**, and it is correct: the map uses
`preserveAspectRatio="xMidYMid meet"` so marks stay on the image. Stretching
the map to fill the stage is what put marks in the wrong place before.

What still *reads* as a hole:

- Unused stage around the map uses a different fill than the page surface.
- Below-mode camera strip left-aligns cards; remaining strip width is a
  quiet gutter (acceptable) unless the chrome color fights it.
- Camera previews use `object-fit: contain` (do not crop). Letterbox inside
  the card should match the card, not look like a broken image.
- Empty tabs (no sensors / children) still occupy the reserved panel peek.
  That peek should stay short; do not pad it to look “full.”

## Goal

Make sparse admin lists read as tools, and make scene-detail unused area
read as margin — without a second density system and without breaking map
coordinates.

## Non-goals

- Do **not** turn Cameras / Sensors / Object Library into scene-style card
  galleries.
- Do **not** stretch the scene map (`slice` / cover) to fill the stage.
- Do **not** grow a single camera card to fill the Below strip.
- Do **not** switch camera previews to `cover` (crops the frame).
- Do **not** add a second compact/comfortable density control.
- Do **not** change Models directory into a table (it is already a capped
  tree). Optional: align its max-width with the list cap if it looks
  inconsistent after Phase 1.
- No user-facing docs unless chrome labels change (they should not).

## Recommended treatment

### Lists — admin inventory, not dashboard

1. Cap the list column at about **56–64rem**, left-aligned — same idea as
   edit forms (`ss-form-card` / `ss-form-card--wide`), not a tiny centered
   island and not full viewport.
2. Size columns to content (`table-layout: auto`). Put leftover space
   **after** the last column.
3. Keep Object Library as a compact name + actions list, not a one-column
   spreadsheet. Same card/table chrome as Cameras/Sensors; do not invent a
   third pattern.
4. Drop the redundant crumb when it only repeats the page title
   (`PageHeader` already strips title-echo crumbs in some cases — finish
   that for these bootstraps).
5. Shrink the list page title toward the scene-detail workspace scale
   (`~1.2rem`) so these feel like tools.
6. Empty states: short block inside a content-sized card, not a huge
   hollow table shell.

### Scene detail — chrome polish, not a new layout

1. Unused map stage uses the same color as the page surface
   (`--ss-surface`) so letterboxing reads as margin, not a hole. Do not
   change `meet` or viewBox sync (`#svgout` + `#svgout-snap`).
2. Keep Auto / Below / Side. That already picks the orientation that
   gives the map the most area. Map focus stays the “give me the whole
   view” escape hatch; do not hide it.
3. Camera strip in Below: left-align cards; leave a quiet gutter. Do not
   flex-grow one card to full width.
4. Keep `contain` on previews. Match letterbox fill to the card
   background.
5. Empty tabs stay a short peek (`ss-empty-state`). Do not pad them to
   the full `--ss-panel-size`.

## Files (expected)

| Area | Likely paths |
| --- | --- |
| List shell | `manager/ui/src/admin/AdminListApp.tsx`, `AdminListApp.css` |
| List title / crumbs | `manager/ui/src/components/PageHeader.tsx`, `PageHeader.css` |
| Bootstrap crumbs | `manager/src/manager/views.py` (`CamListView`, sensor list, `AssetListView`) |
| Scene stage fill | `manager/ui/src/scene/SceneDetailPage.css`, `reactSceneMap.css`, `manager/src/manager/static/css/style.css` (`.scene-map-stage`) |
| Camera strip gutter | `manager/ui/src/scene/CameraStrip.css`, `control/ControlTabEntities.css` |
| Empty tabs | `manager/ui/src/scene/SceneDetailPage.css`, `control/ControlTabEntities.tsx` |
| Built assets | `make -C manager ui-build` |

Hard-contract ids in `manager-ui-hard-contracts.md` stay. Do not rename
`#ss-admin-list-root`, table action hrefs, or scene map ids.

## Implementation slices

Do Phase 1 first. It is the cheap win on a wide monitor.

### Phase 1 — lists

- Cap `.ss-admin-list` / `.ss-admin-table-card` (56–64rem, left-aligned).
- Content-sized columns; actions column hugs chips.
- Quieter title; no title-echo breadcrumb.
- Compact empty state.
- Rebuild UI. Spot-check Cameras, Sensors, Object Library at ~1920px and
  ~1280px.

### Phase 2 — scene detail chrome

- Stage / map leftover fill → `--ss-surface`.
- Camera card letterbox fill → card background.
- Confirm empty-tab peek is not forced to full panel height.
- Rebuild UI. Confirm marks still track the map after resize (Below and
  Side). Confirm Show Trails / Visualize ROIs unchanged.

### Phase 3 — optional consistency

- Models directory max-width matches the list cap if it now looks
  narrower/wider for no reason.
- Scenes Home unchanged (gallery is the right pattern).

## Verification

- `make -C manager ui-build`
- Manual: Cameras / Sensors / Object Library — table does not stretch
  across a wide viewport; columns are not padded mid-row.
- Manual: scene detail — map letterboxes without a contrasting hole;
  marks stay on the image after window and splitter resize.
- Existing UI BAT for scene detail / camera list if those suites run in
  the implementing PR. No new BAT required unless selectors change.

## Out of scope for this plan

- Calibrate workspace size, overlay slider, or resizable calibrate
  splitter (already shipped).
- Geospatial picker, theme tokens, navbar color.
- Rewriting list pages to React virtualized tables or adding search /
  sort / filter (separate if product asks).
