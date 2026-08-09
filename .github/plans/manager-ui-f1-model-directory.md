<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Follow-on F1 — Model directory React

## Status

Initial React island ships on `model/list/`:

- Mount: `#ss-models-directory-root` → `models-directory.js`
- API: `GET /api/v1/model-directory/?action=load&format=json` (JSON tree)
- Legacy jQuery `model_list.js` / HTML fragment load path retired from the template

## Remaining (optional parity)

- Create folder / upload / extract zip / delete / copy-path actions in React
  (API already supports POST/DELETE; UI currently browse + refresh)
- Drop unused `model/includes/model_directory.html` when no HTML consumers remain
- K8s-only BAT covering browse + upload if product requires full parity
