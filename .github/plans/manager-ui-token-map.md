<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Manager UI — Token & primitive contract (Phase 0)

Scenescape mirrors ViPPET / Open Edge Platform **light-mode** tokens inside
`manager/ui` rather than depending on a published ViPPET npm package (license /
versioning not confirmed for direct consumption).

When a shared package becomes available, remap these names — do not restyle
ad hoc.

## Token mapping (`ss.*` / `--ss-*` ↔ ViPPET-style)

| Scenescape CSS / JS | ViPPET-oriented name | Value (light) |
| ------------------- | -------------------- | ------------- |
| `--ss-brand` / `tokens.brand` | `color.brand.primary` | `#0054ae` |
| `--ss-brand-hover` | `color.brand.primaryHover` | `#004a9d` |
| `--ss-brand-soft` | `color.brand.accent` | `#0099ec` |
| `--ss-nav-bg` | `color.nav.bg` | `#001e50` |
| `--ss-nav-fg` | `color.nav.fg` | `#ffffff` |
| `--ss-surface` | `color.surface.page` | `#f4f5f5` |
| `--ss-card-bg` | `color.surface.card` | `#ffffff` |
| `--ss-card-border` | `color.border.subtle` | `#e9e9e9` |
| `--ss-input-border` | `color.border.input` | `#aeaeae` |
| `--ss-text` | `color.text.primary` | `#000000` |
| `--ss-text-muted` | `color.text.muted` | `#808080` |
| `--ss-status-ok` | `color.status.ok` | `#008a00` |
| `--ss-status-bad` | `color.status.bad` | `#da2e56` |
| `--ss-font-sans` | `font.family.body` | Open Sans stack |
| `--ss-font-heading` | `font.family.heading` | Montserrat stack |
| `--ss-radius` | `radius.control` | `0.625rem` |
| Form card max | `layout.formCard.maxWidth` | `48rem` |
| Form card wide | `layout.formCard.maxWidthWide` | `64rem` |
| Form card map editor | `layout.formCard.maxWidthMapEditor` | `min(100%, 1280px + 16rem)` |
| Field max | `layout.field.maxWidth` | `28rem` |
| Label track | `layout.form.labelTrack` | `10.5–12.5rem` |

Source of truth for runtime CSS variables remains `:root` in
`manager/src/manager/static/css/style.css` for legacy Django pages. The React
package re-declares the same values in `manager/ui/src/tokens/` so the island
does not depend on global stylesheet load order for its own chrome.

## Primitives checklist (mirror in `manager/ui`)

| Primitive | Status | Notes |
| --------- | ------ | ----- |
| `Button` | Phase 2–4 (landed) | Primary / secondary / danger |
| `PageHeader` | Phase 2–4 (landed) | Title + actions |
| `Tabs` | Phase 2 (landed) | Scene side panel / classic strip |
| `Breadcrumb` | Phase 2 (landed) | Scenes → name (in PageHeader) |
| `Card` | Phase 7 (landed) | Shared surface; `--ss-card-*` tokens |
| `StatusChip` | Phase 7 (landed) | Neutral / ok / bad status labels |
| `TableActions` | Phase 7 (landed) | CSS for list row action clusters |
| `TextField` | Phase 4 (landed) | Label + capped control |
| `FormCard` | Phase 4 (landed) | Capped admin forms |
| `FormSection` | Phase 4 (landed) | Topic blocks + collapsible advanced; field groups |
| `Modal` | Phase 4 (landed) | Bootstrap-compatible chrome |
| `Drawer` | Phase 4–7 (landed) | Create/edit sheets; Tab focus trap |
| `ConfirmDialog` | Phase 4–7 (landed) | Deletes + dirty leave; focus trap |
| `Toast` | Phase 4 (landed) | Quiet status toast |

## Package strategy

**Mirror** token values and API-shaped primitives under `manager/ui`. Do not add
a ViPPET/OEP design-system npm dependency until license and versioning are
confirmed.
