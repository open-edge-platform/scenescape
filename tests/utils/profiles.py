#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Service profile definitions for end-to-end tests.

Each profile encodes the Docker Compose file combination and container
readiness checks that a group of tests requires.
Derived from tests/Makefile.functional, tests/Makefile.sscape, and
tests/Makefile.user_interface.
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
_PGSERVER = WaitConfig(
  log_pattern="database system is ready to accept connections",
  timeout=300,
)
_BROKER = WaitConfig(log_pattern=r"mosquitto version .* running")
_WEB = WaitConfig()
_SCENE = WaitConfig()
_AUTOCALIBRATION = WaitConfig(timeout=1200)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

WEB_ONLY = ServiceProfile(
  name="web_only",
  compose_files=(
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/web.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
  },
)

FULL_STACK = ServiceProfile(
  name="full_stack",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/scene.yml",
    f"{COMPOSE}/web.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "scene": _SCENE,
    "broker": _BROKER,
  },
)

FULL_STACK_WITH_VIDEO = ServiceProfile(
  name="full_stack_with_video",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{DLS}/retail_video.yml",
    f"{DLS}/queuing_video.yml",
    f"{COMPOSE}/scene.yml",
    f"{COMPOSE}/web_default.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/cams.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "queuing-video": WaitConfig(),
    "retail-video": WaitConfig(),
    "scene": _SCENE,
  },
)

FULL_STACK_WITH_VIDEO_NO_NTP = ServiceProfile(
  name="full_stack_with_video_no_ntp",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{DLS}/retail_video_no_ntp.yml",
    f"{DLS}/queuing_video_no_ntp.yml",
    f"{COMPOSE}/scene_no_ntp.yml",
    f"{COMPOSE}/web_default.yml",
    f"{COMPOSE}/cams.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "queuing-video": WaitConfig(),
    "retail-video": WaitConfig(),
    "scene": _SCENE,
  },
)

FULL_STACK_CALIBRATION = ServiceProfile(
  name="full_stack_calibration",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/scene.yml",
    f"{COMPOSE}/web_calibration.yml",
    f"{DLS}/queuing_video.yml",
    f"{COMPOSE}/autocalibration.yml",
    f"{COMPOSE}/cams.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "queuing-video": WaitConfig(),
    "autocalibration": _AUTOCALIBRATION,
  },
)

FULL_STACK_WITH_VIDEO_AND_RETAIL = ServiceProfile(
  name="full_stack_with_video_and_retail",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{DLS}/retail_video.yml",
    f"{DLS}/queuing_video.yml",
    f"{COMPOSE}/scene.yml",
    f"{COMPOSE}/web.yml",
    f"{COMPOSE}/cams.yml",
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
    f"{DLS}/broker.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/vdms.yml",
    f"{DLS}/retail_video_reid.yml",
    f"{DLS}/queuing_video_reid.yml",
    f"{COMPOSE}/scene_reid.yml",
    f"{COMPOSE}/web_default.yml",
    f"{COMPOSE}/cams.yml",
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

REID_DATA_FLOW = ServiceProfile(
  name="reid_data_flow",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/vdms.yml",
    f"{COMPOSE}/scene_reid.yml",
    f"{COMPOSE}/web_default.yml",
    f"{COMPOSE}/cams.yml",
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

REID_SEMANTIC = ServiceProfile(
  name="reid_semantic",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/vdms.yml",
    f"{DLS}/queuing_video_reid_semantic.yml",
    f"{COMPOSE}/scene_reid.yml",
    f"{COMPOSE}/web_default.yml",
    f"{COMPOSE}/cams.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "queuing-video": WaitConfig(),
    "scene": _SCENE,
  },
)

FULL_STACK_AUTOCALIBRATION = ServiceProfile(
  name="full_stack_autocalibration",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/scene.yml",
    f"{COMPOSE}/web_default.yml",
    f"{DLS}/queuing_video.yml",
    f"{DLS}/retail_video.yml",
    f"{COMPOSE}/autocalibration.yml",
    f"{COMPOSE}/cams.yml",
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

BROKER_AND_DB = ServiceProfile(
  name="broker_and_db",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/web.yml",
  ),
  wait_for={},
)

BROKER_VDMS_DB = ServiceProfile(
  name="broker_vdms_db",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/vdms.yml",
    f"{COMPOSE}/pgserver.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
  },
)

SCENE_NO_DB = ServiceProfile(
  name="scene_no_db",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/scene_no_db.yml",
  ),
  wait_for={
    "scene": _SCENE,
  },
)

MARKERLESS = ServiceProfile(
  name="markerless",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/web.yml",
    f"{COMPOSE}/autocalibration.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
    "autocalibration": _AUTOCALIBRATION,
  },
)

# broker + pgserver + web (with readiness checks) — used by UI/selenium tests
# that don't need the scene container.
BROKER_WEB = ServiceProfile(
  name="broker_web",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{COMPOSE}/web.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "web": _WEB,
  },
)

# Full UI stack with autocalibration + retail/queuing video — used by
# auto-calibration-ui and calibrate-camera-3d-ui-2d-ui tests.
AUTO_CALIBRATION_UI = ServiceProfile(
  name="auto_calibration_ui_stack",
  compose_files=(
    f"{DLS}/broker.yml",
    f"{COMPOSE}/autocalibration.yml",
    f"{COMPOSE}/ntp.yml",
    f"{COMPOSE}/pgserver.yml",
    f"{DLS}/queuing_video.yml",
    f"{DLS}/retail_video.yml",
    f"{COMPOSE}/scene.yml",
    f"{COMPOSE}/web_default.yml",
    f"{COMPOSE}/cams.yml",
  ),
  wait_for={
    "pgserver": _PGSERVER,
    "broker": _BROKER,
    "scene": _SCENE,
    "retail-video": WaitConfig(),
    "queuing-video": WaitConfig(),
    "autocalibration": _AUTOCALIBRATION,
    "web": _WEB,
  },
)

# Registry: maps profile name -> ServiceProfile for CLI lookup
PROFILE_REGISTRY: dict = {
  p.name: p
  for p in [
    WEB_ONLY,
    FULL_STACK,
    FULL_STACK_WITH_VIDEO,
    FULL_STACK_WITH_VIDEO_NO_NTP,
    FULL_STACK_CALIBRATION,
    FULL_STACK_WITH_VIDEO_AND_RETAIL,
    REID,
    REID_DATA_FLOW,
    REID_SEMANTIC,
    FULL_STACK_AUTOCALIBRATION,
    BROKER_AND_DB,
    BROKER_VDMS_DB,
    SCENE_NO_DB,
    MARKERLESS,
    BROKER_WEB,
    AUTO_CALIBRATION_UI,
  ]
}
