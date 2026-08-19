#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Service profile definitions for end-to-end tests.

Each profile encodes the Docker Compose file combination and container
readiness checks that a group of tests requires.
"""

from dataclasses import dataclass, field

COMPOSE = "tests/compose"
DLS = f"{COMPOSE}/dlstreamer"


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
# Mapping can take much longer to become ready during the long-run stability
# test (model download/cache warm-up); scope the larger timeout to STABILITY
# only so other mapping-based profiles keep failing fast.
_MAPPING_STABILITY = WaitConfig(timeout=6000)


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
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "scene": _SCENE,
    "broker": _BROKER,
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
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "queuing-video": WaitConfig(),
    "retail-video": WaitConfig(),
    "scene": _SCENE,
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
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "broker": _BROKER,
    "scene": _SCENE,
    "autocalibration": _AUTOCALIBRATION,
    "web": _WEB,
  },
)

# Full-stack profile used by the long-run stability test.
STABILITY = ServiceProfile(
  name="stability",
  compose_files=(
    f"{DLS}/compose-broker.yml",
    f"{COMPOSE}/compose-ntp.yml",
    f"{COMPOSE}/compose-pgserver.yml",
    f"{DLS}/compose-retail_video.yml",
    f"{DLS}/compose-queuing_video.yml",
    f"{COMPOSE}/compose-scene.yml",
    f"{COMPOSE}/compose-web_default.yml",
    f"{COMPOSE}/compose-cams.yml",
    f"{COMPOSE}/compose-autocalibration.yml",
    f"{COMPOSE}/compose-mapping.yml",
    f"{COMPOSE}/compose-controller_analytics.yml",
  ),
  wait_for={
    "broker": _BROKER,
    "pgserver": _PGSERVER,
    "web": _WEB,
    "scene": _SCENE,
    "queuing-video": WaitConfig(),
    "retail-video": WaitConfig(),
    "autocalibration": _AUTOCALIBRATION,
    "mapping": _MAPPING_STABILITY,
    "controller-analytics": _SCENE,
  },
)

# Registry: maps profile name -> ServiceProfile for CLI lookup
PROFILE_REGISTRY: dict = {
  p.name: p
  for p in [
    FULL_STACK,
    FULL_STACK_WITH_MAPPING,
    FULL_STACK_WITH_MAPPING_AND_VIDEO,
    FULL_STACK_WITH_VIDEO_AND_RETAIL,
    REID,
    REID_QDRANT,
    REID_SEMANTIC,
    REID_SEMANTIC_QDRANT,
    FULL_STACK_AUTOCALIBRATION,
    FULL_STACK_AUTOCALIBRATION_NO_APRILTAGS,
    SCENE_NO_DB,
    MARKERLESS,
    INFERENCE_PERF,
    STABILITY,
  ]
}
