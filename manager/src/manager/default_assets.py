# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Canonical default Asset3D library entries (vehicle, cyclist).

Single source of truth for sizes/colors used by:
  - management command ``init_default_assets`` (always-run on manager init)
  - data migration ``0005_default_asset3d_objects`` (one-shot on migrate)

Sizes are derived from observed LiDAR detections:
  vehicle  - avg of three detections: x=4.04 m, y=1.66 m, z=1.55 m
  cyclist  - single detection:        x=1.85 m, y=0.65 m, z=1.84 m

Lifecycle: migrate seeds on first apply; ``init_default_assets`` re-ensures
idempotently on every manager start so defaults exist even if the migration
was applied before this seed existed or rows were deleted.
"""

DEFAULT_ASSETS = [
  {
    "name": "vehicle",
    "x_size": 4.04,
    "y_size": 1.66,
    "z_size": 1.55,
    "tracking_radius": 10.0,
    "mark_color": "#0099ff",
    "shift_type": 1,
    "rotation_from_velocity": True,
  },
  {
    "name": "cyclist",
    "x_size": 1.85,
    "y_size": 0.65,
    "z_size": 1.84,
    "tracking_radius": 2.0,
    "mark_color": "#f39c12",
    "shift_type": 1,
    "rotation_from_velocity": True,
  },
]
