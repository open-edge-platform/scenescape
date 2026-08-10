#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Service profile definitions for end-to-end tests.

Each profile encodes the Docker Compose file combination and container
readiness checks that a group of tests requires.
"""

import os
import stat
from dataclasses import dataclass, field

COMPOSE = "tests/compose"
DLS = f"{COMPOSE}/dlstreamer"
HIER = f"{COMPOSE}/hierarchy"
# Mounted only when the host has usable DRM nodes (see resolve_compose_files).
_GPU_DRI_OVERRIDES = (
  ("compose-retail_video", f"{DLS}/compose-gpu-dri-retail.yml"),
  ("compose-queuing_video", f"{DLS}/compose-gpu-dri-queuing.yml"),
)


@dataclass(frozen=True)
class WaitConfig:
  """Readiness configuration for a single container."""
  log_pattern: str = "Container is ready"
  timeout: int = 90


@dataclass(frozen=True)
class ServiceProfile:
  """A named set of compose files + readiness checks for a test group."""
  name: str
  compose_files: tuple[str, ...]
  wait_for: dict[str, WaitConfig] = field(default_factory=dict)


def _host_has_dri(dri_path="/dev/dri"):
  """True when *dri_path* contains at least one DRM character device.

  WSL and some VMs expose an empty ``/dev/dri`` directory. Docker still fails
  with ``not a device node`` if compose mounts that path, so existence alone
  is not enough.
  """
  if not os.path.isdir(dri_path):
    return False
  try:
    for name in os.listdir(dri_path):
      path = os.path.join(dri_path, name)
      try:
        if stat.S_ISCHR(os.stat(path).st_mode):
          return True
      except OSError:
        continue
  except OSError:
    return False
  return False


def resolve_compose_files(compose_files, dri_path="/dev/dri"):
  """Return compose files, appending GPU DRI overrides when available.

  Docker Compose fails hard if ``devices: [/dev/dri:/dev/dri]`` is declared
  but the host has no usable DRM nodes (missing path, or empty ``/dev/dri``
  on WSL / VMs without GPU passthrough). Keep DRI out of the base video
  compose files and only merge matching per-service overrides when a real
  device node exists so CPU-only hosts can still start video profiles.
  """
  files = list(compose_files)
  if not _host_has_dri(dri_path):
    return tuple(files)
  for marker, override in _GPU_DRI_OVERRIDES:
    if any(marker in path for path in files) and override not in files:
      files.append(override)
  return tuple(files)


# Common wait configs reused across profiles
_QDRANT = WaitConfig(log_pattern=r"Qdrant HTTP listening on 55555")
_PGSERVER = WaitConfig(
  log_pattern="database system is ready to accept connections",
  timeout=300,
)
_BROKER = WaitConfig(log_pattern=r"mosquitto version .* running")
_WEB = WaitConfig()
_SCENE = WaitConfig(log_pattern="Subscribed to")
_AUTOCALIBRATION = WaitConfig(timeout=1200)
_MAPPING = WaitConfig(timeout=600)
_ANALYTICS = WaitConfig(log_pattern="Subscribed to")


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

FULL_STACK = ServiceProfile(
  name="full_stack",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-scene.yml",
    f"{COMPOSE}/compose-web.yml",
    f"{COMPOSE}/compose-analytics.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "scene": _SCENE,
    "broker": _BROKER,
    "analytics": _ANALYTICS,
  },
)

FULL_STACK_WITH_MAPPING = ServiceProfile(
  name="full_stack_with_mapping",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-scene.yml",
    f"{COMPOSE}/compose-web.yml",
    f"{COMPOSE}/compose-analytics.yml",
    f"{COMPOSE}/compose-mapping.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "scene": _SCENE,
    "broker": _BROKER,
    "mapping": _MAPPING,
  },
)

FULL_STACK_WITH_MAPPING_AND_VIDEO = ServiceProfile(
  name="full_stack_with_mapping_and_video",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{DLS}/compose-retail_video.yml",
    f"{COMPOSE}/compose-scene.yml",
    f"{COMPOSE}/compose-web.yml",
    f"{COMPOSE}/compose-analytics.yml",
    f"{COMPOSE}/compose-cams.yml",
    f"{COMPOSE}/compose-mapping.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "scene": _SCENE,
    "broker": _BROKER,
    "retail-video": WaitConfig(),
    "mapping": _MAPPING,
  },
)

# Retail video + core stack without mapping (mapanything). Use when tests need
# camera detections but not the mapping service.
FULL_STACK_WITH_RETAIL_VIDEO = ServiceProfile(
  name="full_stack_with_retail_video",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{DLS}/compose-retail_video.yml",
    f"{COMPOSE}/compose-scene.yml",
    f"{COMPOSE}/compose-web.yml",
    f"{COMPOSE}/compose-cams.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "scene": _SCENE,
    "broker": _BROKER,
    "retail-video": WaitConfig(),
  },
)

FULL_STACK_WITH_VIDEO_AND_RETAIL = ServiceProfile(
  name="full_stack_with_video_and_retail",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{DLS}/compose-retail_video.yml",
    f"{DLS}/compose-queuing_video.yml",
    f"{COMPOSE}/compose-scene.yml",
    f"{COMPOSE}/compose-web_default.yml",
    f"{COMPOSE}/compose-cams.yml",
    f"{COMPOSE}/compose-analytics.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "queuing-video": WaitConfig(),
    "retail-video": WaitConfig(),
    "scene": _SCENE,
    "analytics": _ANALYTICS,
  },
)

REID = ServiceProfile(
  name="reid",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-vdms.yml",
    f"{DLS}/compose-retail_video_reid.yml",
    f"{DLS}/compose-queuing_video_reid.yml",
    f"{COMPOSE}/compose-scene_reid.yml",
    f"{COMPOSE}/compose-web_default.yml",
    f"{COMPOSE}/compose-cams.yml",
    f"{COMPOSE}/compose-analytics.yml",
  ),
  wait_for={
    "broker": _BROKER,
    "ntpserv": WaitConfig(),
    "pgserver": _PGSERVER,
    "vdms": WaitConfig(),
    "web": _WEB,
    "queuing-video": WaitConfig(),
    "retail-video": WaitConfig(),
    "scene": _SCENE,
  },
)

# ReID controller + vector DB without DLStreamer/GPU video. Used by hierarchy
# enrollment tests that inject camera MQTT detections instead of live streams.
REID_CORE = ServiceProfile(
  name="reid_core",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-vdms.yml",
    f"{COMPOSE}/compose-scene_reid.yml",
    # Use compose-web.yml (testdb / Demo) so hierarchy helpers can link Demo.
    f"{COMPOSE}/compose-web.yml",
  ),
  wait_for={
    "broker": _BROKER,
    "ntpserv": WaitConfig(),
    "pgserver": _PGSERVER,
    "vdms": WaitConfig(),
    "web": _WEB,
    "scene": _SCENE,
  },
)

REID_QDRANT = ServiceProfile(
  name="reid_qdrant",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-qdrant.yml",
    f"{DLS}/compose-retail_video_reid.yml",
    f"{DLS}/compose-queuing_video_reid.yml",
    f"{COMPOSE}/compose-scene_reid_qdrant.yml",
    f"{COMPOSE}/compose-web_default.yml",
    f"{COMPOSE}/compose-cams.yml",
  ),
  wait_for={
    "broker": _BROKER,
    "ntpserv": WaitConfig(),
    "pgserver": _PGSERVER,
    "qdrant": _QDRANT,
    "web": _WEB,
    "queuing-video": WaitConfig(),
    "retail-video": WaitConfig(),
    "scene": _SCENE,
  },
)

REID_CORE_QDRANT = ServiceProfile(
  name="reid_core_qdrant",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-qdrant.yml",
    f"{COMPOSE}/compose-scene_reid_qdrant.yml",
    f"{COMPOSE}/compose-web.yml",
  ),
  wait_for={
    "broker": _BROKER,
    "ntpserv": WaitConfig(),
    "pgserver": _PGSERVER,
    "qdrant": _QDRANT,
    "web": _WEB,
    "scene": _SCENE,
  },
)

_HIER_BASE = (
  f"{HIER}/compose-common.yml",
  f"{HIER}/compose-parent-base.yml",
  f"{HIER}/compose-child1-base.yml",
  f"{HIER}/compose-child2-base.yml",
  f"{HIER}/compose-parent-analytics.yml",
)

_HIER_WAIT = {
  "parent-broker": _BROKER,
  "child1-broker": _BROKER,
  "child2-broker": _BROKER,
  "parent-ntpserv": WaitConfig(),
  "parent-pgserver": _PGSERVER,
  "child1-pgserver": _PGSERVER,
  "child2-pgserver": _PGSERVER,
  "parent-web": _WEB,
  "child1-web": _WEB,
  "child2-web": _WEB,
  "parent-scene": _SCENE,
  "child1-scene": _SCENE,
  "child2-scene": _SCENE,
  "parent-analytics": _ANALYTICS,
}

# All three controllers share one VDMS (priority 1).
REID_HIER_SHARED = ServiceProfile(
  name="reid_hier_shared",
  compose_files=_HIER_BASE + (
    f"{HIER}/compose-vdms-shared.yml",
    f"{HIER}/compose-parent-scene-reid.yml",
    f"{HIER}/compose-child1-scene-reid.yml",
    f"{HIER}/compose-child2-scene-reid.yml",
    f"{HIER}/compose-deps-vdms-shared.yml",
  ),
  wait_for={**_HIER_WAIT, "vdms-shared": WaitConfig()},
)

# Children share VDMS; parent has no ReID (priority 2).
REID_HIER_CHILDREN_ONLY = ServiceProfile(
  name="reid_hier_children_only",
  compose_files=_HIER_BASE + (
    f"{HIER}/compose-vdms-shared.yml",
    f"{HIER}/compose-parent-scene.yml",
    f"{HIER}/compose-child1-scene-reid.yml",
    f"{HIER}/compose-child2-scene-reid.yml",
    f"{HIER}/compose-deps-vdms-shared-children.yml",
  ),
  wait_for={**_HIER_WAIT, "vdms-shared": WaitConfig()},
)

# Parent has VDMS; children have no ReID (priority 3).
REID_HIER_PARENT_ONLY = ServiceProfile(
  name="reid_hier_parent_only",
  compose_files=_HIER_BASE + (
    f"{HIER}/compose-vdms-shared.yml",
    f"{HIER}/compose-parent-scene-reid.yml",
    f"{HIER}/compose-child1-scene.yml",
    f"{HIER}/compose-child2-scene.yml",
    f"{HIER}/compose-deps-vdms-shared-parent.yml",
  ),
  wait_for={**_HIER_WAIT, "vdms-shared": WaitConfig()},
)

# Parent+child1 share reid-a; child2 has no ReID (priority 4).
REID_HIER_PARTIAL = ServiceProfile(
  name="reid_hier_partial",
  compose_files=_HIER_BASE + (
    f"{HIER}/compose-vdms-a.yml",
    f"{HIER}/compose-parent-scene-reid.yml",
    f"{HIER}/compose-child1-scene-reid.yml",
    f"{HIER}/compose-child2-scene.yml",
    f"{HIER}/compose-deps-partial.yml",
  ),
  wait_for={**_HIER_WAIT, "vdms-a": WaitConfig()},
)

# Parent+child1 on reid-a; child2 on reid-b (priority 5 negative).
REID_HIER_SPLIT = ServiceProfile(
  name="reid_hier_split",
  compose_files=_HIER_BASE + (
    f"{HIER}/compose-vdms-a.yml",
    f"{HIER}/compose-vdms-b.yml",
    f"{HIER}/compose-parent-scene-reid.yml",
    f"{HIER}/compose-child1-scene-reid.yml",
    f"{HIER}/compose-child2-scene-reid.yml",
    f"{HIER}/compose-deps-split.yml",
  ),
  wait_for={**_HIER_WAIT, "vdms-a": WaitConfig(), "vdms-b": WaitConfig()},
)

REID_SEMANTIC = ServiceProfile(
  name="reid_semantic",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-vdms.yml",
    f"{DLS}/compose-queuing_video_reid_semantic.yml",
    f"{COMPOSE}/compose-scene_reid.yml",
    f"{COMPOSE}/compose-web_default.yml",
    f"{COMPOSE}/compose-cams.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "queuing-video": WaitConfig(),
    "scene": _SCENE,
  },
)

REID_SEMANTIC_QDRANT = ServiceProfile(
  name="reid_semantic_qdrant",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-qdrant.yml",
    f"{DLS}/compose-queuing_video_reid_semantic.yml",
    f"{COMPOSE}/compose-scene_reid_qdrant.yml",
    f"{COMPOSE}/compose-web_default.yml",
    f"{COMPOSE}/compose-cams.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "qdrant": _QDRANT,
    "queuing-video": WaitConfig(),
    "scene": _SCENE,
  },
)

FULL_STACK_AUTOCALIBRATION = ServiceProfile(
  name="full_stack_autocalibration",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-scene.yml",
    f"{COMPOSE}/compose-web_calibration.yml",
    f"{DLS}/compose-queuing_video.yml",
    f"{DLS}/compose-retail_video.yml",
    f"{COMPOSE}/compose-autocalibration.yml",
    f"{COMPOSE}/compose-cams.yml",
    f"{COMPOSE}/compose-analytics.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "broker": _BROKER,
    "scene": _SCENE,
    "queuing-video": WaitConfig(),
    "retail-video": WaitConfig(),
    "autocalibration": _AUTOCALIBRATION,
    "web": _WEB,
  },
)

SCENE_NO_DB = ServiceProfile(
  name="scene_no_db",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-scene_no_db.yml",
  ),
  wait_for={
    "scene": _SCENE,
  },
)

MARKERLESS = ServiceProfile(
  name="markerless",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-web.yml",
    f"{COMPOSE}/compose-autocalibration.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "autocalibration": _AUTOCALIBRATION,
  },
)

INFERENCE_PERF = ServiceProfile(
  name="inference_perf",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-cams.yml",
    f"{DLS}/compose-retail_video.yml",
  ),
  wait_for={
    "broker": _BROKER,
    "retail-video": WaitConfig(timeout=120),
  },
)

FULL_STACK_AUTOCALIBRATION_NO_APRILTAGS = ServiceProfile(
  name="full_stack_autocalibration_no_apriltags",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-scene.yml",
    f"{COMPOSE}/compose-web_default.yml",
    f"{COMPOSE}/compose-autocalibration.yml",
    f"{COMPOSE}/compose-analytics.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "broker": _BROKER,
    "scene": _SCENE,
    "autocalibration": _AUTOCALIBRATION,
    "web": _WEB,
  },
)

# Analytics + Manager only (no Scene Controller / Tracker). Used to inject
# Tracker-shaped DATA_SCENE over MQTT and assert Analytics events without
# duplicating Controller tracking coverage in FULL_STACK.
ANALYTICS_MQTT = ServiceProfile(
  name="analytics_mqtt",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{COMPOSE}/compose-web.yml",
    f"{COMPOSE}/compose-analytics.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "broker": _BROKER,
    "analytics": _ANALYTICS,
  },
)

# Registry: maps profile name -> ServiceProfile for CLI lookup
PROFILE_REGISTRY: dict = {
  p.name: p
  for p in [
    FULL_STACK,
    FULL_STACK_WITH_MAPPING,
    FULL_STACK_WITH_MAPPING_AND_VIDEO,
    FULL_STACK_WITH_RETAIL_VIDEO,
    FULL_STACK_WITH_VIDEO_AND_RETAIL,
    REID,
    REID_CORE,
    REID_QDRANT,
    REID_CORE_QDRANT,
    REID_HIER_SHARED,
    REID_HIER_CHILDREN_ONLY,
    REID_HIER_PARENT_ONLY,
    REID_HIER_PARTIAL,
    REID_HIER_SPLIT,
    REID_SEMANTIC,
    REID_SEMANTIC_QDRANT,
    FULL_STACK_AUTOCALIBRATION,
    FULL_STACK_AUTOCALIBRATION_NO_APRILTAGS,
    SCENE_NO_DB,
    MARKERLESS,
    INFERENCE_PERF,
    ANALYTICS_MQTT,
  ]
}
