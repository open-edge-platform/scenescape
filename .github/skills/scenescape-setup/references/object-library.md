<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Object Library (Asset3D): custom object class properties

Read this when the user mentions specific object classes/sizes (e.g. "forklifts are about 1.2m by
2.4m") or wants a custom 3D shape instead of the default cuboid for a tracked object type.

## What it configures

The Object Library is the manager's `Asset3D` model — one entry per detected object class (name
must match the pipeline's object type string, e.g. `person`, `vehicle`, or a custom class).
Defining expected size (and optionally a `.glb` 3D model) lets SceneScape use more accurate models
for tracking and spatial analytics instead of a generic cuboid. See
`docs/user-guide/other-topics/how-to-define-object-properties.md` in the SceneScape repo for the
full field reference (rotation, physics properties like mass/damping/restitution, etc.).

This is fully REST-scriptable via `POST /api/v1/asset` and does not require the web UI.

## Creating an entry

Use [`upload_object_asset.py`](../scripts/upload_object_asset.py):

```bash
python scripts/upload_object_asset.py \
    --deploy-dir <deploy_dir> \
    --name forklift \
    --x-size 1.2 --y-size 2.4 --z-size 2.0
```

With a custom `.glb` shape instead of the default cuboid:

```bash
python scripts/upload_object_asset.py \
    --deploy-dir <deploy_dir> \
    --name forklift \
    --x-size 1.2 --y-size 2.4 --z-size 2.0 \
    --model-3d ~/models/forklift.glb
```

## Notes

- `--name` must exactly match the object class string the detection pipeline publishes; a
  mismatched name creates an unused library entry rather than an error.
- The script covers the commonly-needed fields (size, mark color, optional `.glb`, mass,
  static flag). For less common fields (rotation, damping, restitution, tracking radius, buffer
  sizes), call `POST /api/v1/asset` directly — see the full field list in `Asset3DSerializer`
  (`manager/src/manager/serializers.py`).
- Asset names must be unique; creating an entry with a name that already exists returns a 400.
- List existing entries: `GET https://web.scenescape.intel.com/api/v1/assets`.
