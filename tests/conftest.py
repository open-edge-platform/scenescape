#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration for SceneScape tests.

Tests are collected directly from their source directories.
TEST_REGISTRY maps test file paths to FuncTestSpec objects
that describe the Docker Compose profile each test needs.  An autouse
scenescape_env fixture starts the right compose stack and
injects CLI option values before the test runs.
Tests not in the registry (unit tests) get a no-op.
"""

import logging
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_TESTS_DIR) not in sys.path:
  sys.path.insert(0, str(_TESTS_DIR))
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# In-container: controller module (optional)
# ---------------------------------------------------------------------------
_controller_src = _REPO_ROOT / "controller" / "src"
if str(_controller_src) not in sys.path:
  sys.path.insert(0, str(_controller_src))

try:
  from controller.controller_mode import ControllerMode
  _controller_mode_available = True
except ImportError:
  _controller_mode_available = False

# ---------------------------------------------------------------------------
# Environmental dependencies (host-only)
# ---------------------------------------------------------------------------
_ORCHESTRATION_AVAILABLE = False
_testlog = None
try:
  from python_on_whales import DockerClient
  import utils.log as _testlog
  from utils import stream_subprocess
  from utils.containers import collect_logs, wait_for_services
  _ORCHESTRATION_AVAILABLE = True
except ImportError:
  pass

# Use the test logger hierarchy when orchestration deps are present;
# fall back to stdlib so in-container tests still emit warnings etc.
if _testlog is not None:
  logger = _testlog.get_logger("conftest")
else:
  logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-container fixtures (ControllerMode)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def initialize_controller_mode(request):
  """Initialize ControllerMode before any tests run.

  No-ops gracefully when running outside the Docker environment.
  """
  if not _controller_mode_available:
    yield
    return
  analytics_only = request.config.getoption("analytics_only", default=False)
  ControllerMode.initialize(analytics_only=analytics_only)
  yield
  ControllerMode.reset()


# ---------------------------------------------------------------------------
# CLI option registration
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
  """Register all shared CLI options for functional, UI, and unit tests."""
  _opts = [
    ("--user",             dict(default="admin",
                                help="user to log into REST server")),
    ("--password",         dict(default=None,
                                help="password to log into REST server")),
    ("--auth",             dict(default="/run/secrets/controller.auth",
                                help="user:password or JSON file for MQTT authentication")),
    ("--rootcert",         dict(default="/run/secrets/certs/scenescape-ca.pem",
                                help="path to CA certificate")),
    ("--broker_url",       dict(default="broker.scenescape.intel.com",
                                help="hostname or IP of MQTT broker")),
    ("--broker_port",      dict(default=1883, type=int,
                                help="MQTT broker port")),
    ("--weburl",           dict(default="https://web.scenescape.intel.com",
                                help="Web URL of the server")),
    ("--resturl",          dict(default="https://web.scenescape.intel.com/api/v1",
                                help="URL of REST server")),
    ("--scene_name",       dict(default="Demo",
                                help="name of scene to test against")),
    ("--scene",            dict(default="Demo",
                                help="name of scene (Diagnostic compat)")),
    ("--scene_id",         dict(default="3bc091c7-e449-46a0-9540-29c499bca18c",
                                help="UUID of scene (Diagnostic compat)")),
    ("--visibility_topic", dict(default="regulated",
                                help="Visibility policy: regulated, unregulated, none")),
    ("--hours",            dict(default="24",
                                help="stability test duration in hours")),
    ("--analytics-only",   dict(action="store_true", default=False,
                                help="Enable analytics-only mode for tests")),
  ]
  for name, kw in _opts:
    try:
      parser.addoption(name, **kw)
    except ValueError:
      pass


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

AUTH_CONTROLLER = "controller.auth"
AUTH_BROWSER = "browser.auth"

@dataclass
class FuncTestSpec:
  """Specification for a single functional/UI test."""
  id: str
  profile: object  # ServiceProfile
  auth: str = ""
  require_password: bool = True
  extra_args: list = None
  exampledb: str = ""
  extra_env: dict = None

  def __post_init__(self):
    if self.extra_args is None:
      self.extra_args = []
    if self.extra_env is None:
      self.extra_env = {}

@dataclass
class ScenescapeEnv:
  """Yielded by the scenescape_env fixture."""
  docker: object  # DockerClient
  project_name: str
  network: str
  repo_root: str
  secrets_dir: str
  supass: str


# ---------------------------------------------------------------------------
# Test registry: maps repo-relative file paths -> FuncTestSpec
# ---------------------------------------------------------------------------

try:
  from utils.profiles import (
    AUTO_CALIBRATION_UI,
    BROKER_AND_DB,
    BROKER_VDMS_DB,
    BROKER_WEB,
    FULL_STACK,
    FULL_STACK_CALIBRATION,
    FULL_STACK_WITH_VIDEO,
    FULL_STACK_WITH_VIDEO_AND_RETAIL,
    FULL_STACK_WITH_VIDEO_NO_NTP,
    MARKERLESS,
    REID,
    REID_DATA_FLOW,
    REID_SEMANTIC,
    SCENE_NO_DB,
    WEB_ONLY,
  )
  _profiles_available = True
except ImportError:
  _profiles_available = False

if _profiles_available:
  TEST_REGISTRY: dict[str, FuncTestSpec] = {
    # --- WEB_ONLY (pgserver + web) ---
    "manager/tests/test_rest_test.py": FuncTestSpec(
      id="rest_test", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_different_formats_maps_api.py": FuncTestSpec(
      id="different_formats_maps_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_scene_import_api.py": FuncTestSpec(
      id="scene_import_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_scenes_summary_api.py": FuncTestSpec(
      id="scenes_summary_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_object_crud_api.py": FuncTestSpec(
      id="object_crud_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_add_delete_3d_object_api.py": FuncTestSpec(
      id="add_delete_3d_object_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_upload_3d_glb_file_api.py": FuncTestSpec(
      id="upload_3d_glb_file_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_upload_only_3d_glb_files_api.py": FuncTestSpec(
      id="upload_only_3d_glb_files_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_sensor_area_api.py": FuncTestSpec(
      id="sensor_area_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_superuser_crud_operations_api.py": FuncTestSpec(
      id="superuser_crud_operations_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_sensor_location_api.py": FuncTestSpec(
      id="sensor_location_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_sensor_scene_api.py": FuncTestSpec(
      id="sensor_scene_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_calibrate_all_sensor_types_api.py": FuncTestSpec(
      id="calibrate_all_sensor_types_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_api_large_strings.py": FuncTestSpec(
      id="api_large_strings", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),
    "manager/tests/test_manual_camera_calibration_api.py": FuncTestSpec(
      id="manual_camera_calibration_api", profile=WEB_ONLY,
      auth=AUTH_CONTROLLER,
    ),

    # --- FULL_STACK (broker + ntp + pgserver + scene + web) ---
    "tests/functional/test_roi_mqtt.py": FuncTestSpec(
      id="mqtt_roi", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_tripwire_mqtt.py": FuncTestSpec(
      id="mqtt_tripwire", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_mqtt_sensor_roi.py": FuncTestSpec(
      id="mqtt_sensor_roi", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_mqtt_slow_sensor_roi.py": FuncTestSpec(
      id="mqtt_slow_sensor_roi", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_add_orphaned_cameras.py": FuncTestSpec(
      id="add_orphaned_cameras", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_child_scenes.py": FuncTestSpec(
      id="child_scenes", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_camera_deletion_api.py": FuncTestSpec(
      id="camera_deletion_api", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_camera_intrinsics_api.py": FuncTestSpec(
      id="camera_intrinsics_api", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_delete_roi_mqtt.py": FuncTestSpec(
      id="delete_roi_mqtt", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_delete_sensor_mqtt_api.py": FuncTestSpec(
      id="delete_sensor_mqtt_api", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_delete_sensor_scene_api.py": FuncTestSpec(
      id="delete_sensor_scene_api", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_delete_sensors_api.py": FuncTestSpec(
      id="delete_sensors_api", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/ui/test_delete_tripwire_mqtt.py": FuncTestSpec(
      id="delete_tripwire_mqtt", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_geospatial_ingest_publish.py": FuncTestSpec(
      id="geospatial_ingest_publish", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_orphaned_sensor.py": FuncTestSpec(
      id="orphaned_sensor", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),
    "tests/functional/test_sensors_send_mqtt_messages.py": FuncTestSpec(
      id="sensors_send_events", profile=FULL_STACK,
      auth=AUTH_CONTROLLER,
    ),

    # --- BROKER_AND_DB (no containers to wait for) ---
    "tests/security/system/test_negative_mqtt_insecure_auth.py": FuncTestSpec(
      id="mqtt_auth", profile=BROKER_AND_DB,
      require_password=False,
      auth="",
    ),
    "tests/security/system/test_negative_mqtt_insecure_cert.py": FuncTestSpec(
      id="mqtt_cert", profile=BROKER_AND_DB,
      require_password=False,
      auth="",
    ),

    # --- SCENE_NO_DB ---
    "controller/tests/test_scene_import_json.py": FuncTestSpec(
      id="scene_import_json", profile=SCENE_NO_DB,
      auth=AUTH_CONTROLLER,
    ),

    # --- FULL_STACK_WITH_VIDEO ---
    "tests/ui/test_out_of_box.py": FuncTestSpec(
      id="out_of_box", profile=FULL_STACK_WITH_VIDEO,
      auth=AUTH_BROWSER,
    ),
    "tests/functional/test_camera_bound_visibility_regulated.py": FuncTestSpec(
      id="visibility_regulated", profile=FULL_STACK_WITH_VIDEO,
      auth=AUTH_BROWSER,
      extra_args=["--visibility_topic", "regulated"],
    ),
    "tests/functional/test_camera_bound_visibility_unregulated.py": FuncTestSpec(
      id="visibility_unregulated", profile=FULL_STACK_WITH_VIDEO,
      auth=AUTH_BROWSER,
      extra_args=["--visibility_topic", "unregulated"],
    ),
    "tests/functional/test_camera_bound_visibility_none.py": FuncTestSpec(
      id="visibility_none", profile=FULL_STACK_WITH_VIDEO,
      auth=AUTH_BROWSER,
      extra_args=["--visibility_topic", "none"],
    ),

    # --- FULL_STACK_WITH_VIDEO_NO_NTP ---
    # out_of_box_no_ntp reuses the same test script as out_of_box but with
    # a different profile. Since registry is keyed by path, only one entry
    # per file is possible.  Use FULL_STACK_WITH_VIDEO as default;
    # out_of_box_no_ntp must be run with an explicit marker or separate
    # invocation.

    # --- FULL_STACK_WITH_VIDEO_AND_RETAIL ---
    "tests/functional/test_scene_details_api.py": FuncTestSpec(
      id="scene_details_api", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
      auth=AUTH_CONTROLLER,
    ),
    "tests/ui/test_bounding_box.py": FuncTestSpec(
      id="bounding_box", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
      auth=AUTH_BROWSER,
    ),
    "tests/ui/test_scene_import.py": FuncTestSpec(
      id="scene_import", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
      auth=AUTH_CONTROLLER,
    ),
    "tests/ui/test_live_button_works.py": FuncTestSpec(
      id="live_view_button", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
      require_password=True,
      auth="",
    ),
    "tests/ui/test_show_telemetry_button.py": FuncTestSpec(
      id="show_telemetry_button", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
      auth=AUTH_CONTROLLER,
    ),

    # --- FULL_STACK_CALIBRATION ---
    "tests/functional/test_auto_calibration_api.py": FuncTestSpec(
      id="auto_calibration_api", profile=FULL_STACK_CALIBRATION,
      auth=AUTH_BROWSER,
      exampledb="tests/calibrationdb.tar.bz2",
    ),

    # --- REID ---
    "tests/functional/test_reid_performance_degradation.py": FuncTestSpec(
      id="reid_performance_degradation", profile=REID,
    ),
    "tests/functional/test_reid_unique_count.py": FuncTestSpec(
      id="reid_unique_count", profile=REID,
    ),

    # --- REID_DATA_FLOW ---
    "tests/functional/test_reid_data_flow.py": FuncTestSpec(
      id="reid_data_flow", profile=REID_DATA_FLOW,
    ),

    # --- REID_SEMANTIC ---
    "tests/functional/test_reid_semantic_unique_count.py": FuncTestSpec(
      id="reid_semantic_unique_count", profile=REID_SEMANTIC,
    ),

    # --- BROKER_VDMS_DB ---
    "tests/functional/test_vdms_similarity_search.py": FuncTestSpec(
      id="vdms_similarity_search", profile=BROKER_VDMS_DB,
      auth=AUTH_CONTROLLER,
    ),

    # --- System stability ---
    "tests/system/stability/test_sscape_stability.py": FuncTestSpec(
      id="system_stability", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
      require_password=False,
      auth="",
      extra_args=["--hours", os.environ.get("STABILITY_HOURS", "24")],
    ),

    # --- Compose-based unit test ---
    "tests/sscape_tests/markerless/": FuncTestSpec(
      id="markerless_unit", profile=MARKERLESS,
      require_password=False,
      auth="",
    ),

    # --- UI tests: BROKER_WEB ---
    "tests/ui/test_camera_control_panel.py": FuncTestSpec(
      id="3d_camera_control_panel", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_scene_control_panel.py": FuncTestSpec(
      id="3d_scene_control_panel", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_add_delete_3d_object.py": FuncTestSpec(
      id="add_delete_3d_object", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_calibrate_all_sensor_types.py": FuncTestSpec(
      id="calibrate_all_sensor_types", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_camera_deletion.py": FuncTestSpec(
      id="camera_deletion", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_camera_intrinsics.py": FuncTestSpec(
      id="camera_intrinsics", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_camera_perspective.py": FuncTestSpec(
      id="camera_perspective", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_delete_sensor_scene.py": FuncTestSpec(
      id="delete_sensor_scene", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_delete_sensors.py": FuncTestSpec(
      id="delete_sensors", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_different_formats_maps.py": FuncTestSpec(
      id="different_formats_maps", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_timestamp_format.py": FuncTestSpec(
      id="timestamp_format", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_manual_camera_calibration.py": FuncTestSpec(
      id="manual_camera_calibration", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_object_crud.py": FuncTestSpec(
      id="object_crud", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_restricted_media_access.py": FuncTestSpec(
      id="restricted_media_access", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_scenes_summary.py": FuncTestSpec(
      id="scenes_summary", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_sensor_area.py": FuncTestSpec(
      id="sensor_area", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_sensor_location.py": FuncTestSpec(
      id="sensor_location", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_sensor_scene.py": FuncTestSpec(
      id="sensor_scene", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_superuser_crud_operations.py": FuncTestSpec(
      id="superuser_crud_operations", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_upload_3d_glb_file.py": FuncTestSpec(
      id="upload_3d_glb_file", profile=BROKER_WEB,
      require_password=True, auth="",
    ),
    "tests/ui/test_upload_only_3d_glb_files.py": FuncTestSpec(
      id="upload_only_3d_glb_files", profile=BROKER_WEB,
      require_password=True, auth="",
    ),

    # --- UI tests: FULL_STACK ---
    "tests/ui/test_delete_sensor_mqtt.py": FuncTestSpec(
      id="delete_sensor_mqtt", profile=FULL_STACK,
      require_password=True, auth=AUTH_CONTROLLER,
    ),
    "tests/ui/test_view_3d_glb_file.py": FuncTestSpec(
      id="view_3d_glb_file", profile=FULL_STACK,
      require_password=True, auth="",
    ),
    "tests/ui/test_persistence_on_page_navigate.py": FuncTestSpec(
      id="persistence_navigate", profile=FULL_STACK,
      require_password=True, auth="",
    ),
    "tests/ui/test_persistence_on_restart.py": FuncTestSpec(
      id="persistence_restart", profile=FULL_STACK,
      require_password=True, auth="",
    ),

    # --- UI tests: FULL_STACK_WITH_VIDEO_AND_RETAIL ---
    "tests/ui/test_3d_ui_calibration_points.py": FuncTestSpec(
      id="3d_ui_calibration_points", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
      require_password=True, auth="",
    ),
    "tests/ui/test_camera_status.py": FuncTestSpec(
      id="camera_status", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
      require_password=True, auth="",
    ),
    "tests/ui/test_scene_details.py": FuncTestSpec(
      id="scene_details", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
      require_password=True, auth="",
    ),

    # --- UI tests: AUTO_CALIBRATION_UI ---
    "tests/ui/test_auto_calibration_ui.py": FuncTestSpec(
      id="auto_calibration_ui", profile=AUTO_CALIBRATION_UI,
      require_password=True, auth="",
      exampledb="sample_data/exampledb.tar.bz2",
    ),
    "tests/ui/test_calibrate_camera_3d_ui_2d_ui.py": FuncTestSpec(
      id="calibrate_camera_3d_ui_2d_ui", profile=AUTO_CALIBRATION_UI,
      require_password=True, auth="",
    ),
  }
else:
  TEST_REGISTRY: dict[str, FuncTestSpec] = {}


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def repo_root():
  """Absolute path to the repository root."""
  return str(_REPO_ROOT)

@pytest.fixture(scope="session")
def version(repo_root):
  """Image version tag from version.txt."""
  return (Path(repo_root) / "version.txt").read_text().strip()

@pytest.fixture(scope="session")
def secrets_dir(repo_root):
  """Path to the secrets directory."""
  sdir = os.path.join(repo_root, "manager", "secrets")
  assert os.path.isdir(sdir), f"Secrets directory not found: {sdir}"
  return sdir

@pytest.fixture(scope="session")
def supass():
  """Superuser password for tests (from SUPASS env var or random)."""
  return os.environ.get("SUPASS") or subprocess.check_output(
    ["openssl", "rand", "-base64", "12"], text=True,
  ).strip()

@pytest.fixture
def params(request, scenescape_env):
  """Connection parameters built from CLI options.

  Depends on scenescape_env to ensure options are injected first.
  """
  return {
    'user': request.config.getoption('--user'),
    'password': request.config.getoption('--password'),
    'auth': request.config.getoption('--auth'),
    'rootcert': request.config.getoption('--rootcert'),
    'broker_url': request.config.getoption('--broker_url'),
    'broker_port': request.config.getoption('--broker_port'),
    'weburl': request.config.getoption('--weburl'),
    'resturl': request.config.getoption('--resturl'),
    'scene_name': request.config.getoption('--scene_name'),
  }

def pytest_report_teststatus(report, config):
  if report.when == "call":
    return report.outcome, "", ""

@pytest.fixture(scope="session", autouse=True)
def _docker_prune_at_exit():
  """Run docker system prune once at the end of the test session."""
  yield
  if not _ORCHESTRATION_AVAILABLE:
    return
  try:
    DockerClient().system.prune()
  except Exception:
    pass

# Hostnames that must resolve to 127.0.0.1 for TLS cert verification.
_HOST_ALIASES = ["broker.scenescape.intel.com", "web.scenescape.intel.com"]
_HOSTS_MARKER = "# scenescape-test-aliases"

@pytest.fixture(scope="session", autouse=True)
def loopback_hosts():
  """Ensure Docker service hostnames resolve to 127.0.0.1 on the host."""
  if not _ORCHESTRATION_AVAILABLE:
    yield
    return

  hosts_path = Path("/etc/hosts")
  entry = f"127.0.0.1 {' '.join(_HOST_ALIASES)}  {_HOSTS_MARKER}\n"

  try:
    content = hosts_path.read_text()
  except OSError:
    logger.warning("/etc/hosts not readable; skipping alias setup")
    yield
    return

  if all(alias in content for alias in _HOST_ALIASES):
    logger.info("Host aliases already present in /etc/hosts")
    yield
    return

  try:
    with hosts_path.open("a") as fh:
      fh.write(entry)
    logger.info("Added host aliases to /etc/hosts")
  except OSError:
    logger.warning(
      "Cannot write /etc/hosts. Add manually:\n  %s", entry.strip()
    )
    yield
    return

  yield


# ---------------------------------------------------------------------------
# Option injection helper
# ---------------------------------------------------------------------------

def _inject_options(config, spec, secrets_dir, supass):
  """Set config.option attributes so getoption() returns correct values.

  Called by the scenescape_env fixture after compose is ready, before
  the test body runs. Both "params" fixtures and "Diagnostic.__init__"
  read from "request.config.getoption()", which delegates to this
  namespace.

  Only overrides options that differ from the registered defaults
  (credentials and path translation). Static defaults (broker_url,
  weburl, etc.) are already set by pytest_addoption.
  """
  opt = config.option

  if spec.require_password:
    opt.user = "admin"
    opt.password = supass

  # Resolve auth file on the host.
  opt.auth = f"{secrets_dir}/{spec.auth or 'controller.auth'}"
  opt.rootcert = f"{secrets_dir}/certs/scenescape-ca.pem"

  # Parse extra_args (--key value pairs) into option attributes.
  if spec.extra_args:
    i = 0
    while i < len(spec.extra_args):
      arg = spec.extra_args[i]
      if arg.startswith("--") and i + 1 < len(spec.extra_args):
        key = arg.lstrip("-").replace("-", "_")
        setattr(opt, key, spec.extra_args[i + 1])
        i += 2
      else:
        i += 1


# ---------------------------------------------------------------------------
# Function-scoped autouse fixture: compose lifecycle + option injection
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function", autouse=True)
def scenescape_env(request, repo_root, secrets_dir, supass, tmp_path):
  """Start Docker Compose for tests in the registry; no-op for others.

  After compose is ready, injects CLI option values into
  request.config.option so that both ``params`` fixtures and the
  ``Diagnostic`` class read the correct connection details.
  """
  spec = getattr(request.node, "_scenescape_spec", None)
  if spec is None:
    yield None
    return

  if not _ORCHESTRATION_AVAILABLE:
    pytest.skip("python-on-whales not installed; run from host venv")

  profile = spec.profile
  project_name = f"test-{uuid.uuid4().hex[:8]}"
  exampledb = spec.exampledb or "tests/testdb.tar.bz2"
  image_version = os.environ.get("IMAGE_VERSION", "latest")

  os.environ["SECRETSDIR"] = secrets_dir

  compose_file_paths = [os.path.join(repo_root, cf) for cf in profile.compose_files]

  controller_auth_path = os.path.join(secrets_dir, "controller.auth")
  try:
    controller_auth = Path(controller_auth_path).read_text().strip()
  except OSError:
    controller_auth = ""

  django_secrets_path = Path(secrets_dir) / "django" / "secrets.py"
  try:
    db_password_match = re.search(
      r"DATABASE_PASSWORD='([^']+)'",
      django_secrets_path.read_text(),
    )
    database_password = db_password_match.group(1) if db_password_match else supass
  except OSError:
    database_password = supass

  env_file = tmp_path / ".env"
  env_file.write_text(
    f"SECRETSDIR={secrets_dir}\n"
    f"SUPASS={supass}\n"
    f"VERSION={image_version}\n"
    f"CONTROLLER_AUTH={controller_auth}\n"
    f"DBROOT={tmp_path / 'db'}\n"
    f"EXAMPLEDB={exampledb}\n"
    f"DATABASE_PASSWORD={database_password}\n"
    f"UID={os.getuid()}\n"
    f"GID={os.getgid()}\n"
    f"VISIBILITY=regulated\n"
    f"VISIBILITY_TOPIC=regulated\n"
  )
  (tmp_path / "db").mkdir(exist_ok=True)

  docker = DockerClient(
    compose_files=compose_file_paths,
    compose_project_name=project_name,
    compose_project_directory=repo_root,
    compose_env_files=[str(env_file)],
  )

  network = f"{project_name}_scenescape-test"
  _saved_env = {}

  try:
    logger.info("=" * 60)
    logger.info("Starting test environment: %s", project_name)
    logger.info("Profile: %s", profile.name)
    logger.info("=" * 60)

    skip_init = request.node.get_closest_marker("skip_init")
    if not skip_init:
      logger.info("Running init-sample-data and install-models...")
      stream_subprocess(
        ["make", "init-sample-data", "install-models"],
        cwd=repo_root,
        env={**os.environ, "COMPOSE_PROJECT_NAME": project_name},
      )

    logger.info("Starting compose services...")
    docker.compose.up(detach=True, pull="never")

    if profile.wait_for:
      wait_for_services(docker, project_name, profile.wait_for)

    # Inject CLI option values before the test body runs.
    _inject_options(request.config, spec, secrets_dir, supass)

    # Apply extra_env to os.environ, saving originals for cleanup.
    _saved_env = {}
    if spec.extra_env:
      for key in spec.extra_env:
        _saved_env[key] = os.environ.get(key)
      os.environ.update(spec.extra_env)

    yield ScenescapeEnv(
      docker=docker,
      project_name=project_name,
      network=network,
      repo_root=repo_root,
      secrets_dir=secrets_dir,
      supass=supass,
    )

  finally:
    # Restore environment variables modified by extra_env.
    for key, orig in _saved_env.items():
      if orig is None:
        os.environ.pop(key, None)
      else:
        os.environ[key] = orig

    # Silence terminal output immediately — teardown logs go to file only.
    if _testlog is not None:
      _testlog.silence_console()

    # Collect logs and scan for tracebacks in a single pass.
    logger.info("Collecting container logs: %s", project_name)
    collect_logs(docker, scan_for_tracebacks=True)

    logger.info("Cleaning up: %s", project_name)
    try:
      docker.compose.down(remove_orphans=True, volumes=True)
    except Exception as exc:
      logger.warning("compose down failed: %s", exc)

    bare_docker = DockerClient()
    for vol in [
      f"{project_name}_vol-models",
      f"{project_name}_vol-db",
      f"{project_name}_vol-migrations",
      f"{project_name}_vol-sample-data",
      f"{project_name}_vol-media",
    ]:
      try:
        bare_docker.volume.remove(vol)
      except Exception:
        pass

    logger.info("Cleanup complete: %s", project_name)


# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------

# Log directory: tests/test_logs/{group}/{test_name}-{timestamp}.log
_LOG_BASE = Path(__file__).parent / "test_logs"

def pytest_collection_modifyitems(config, items):
  """Attach FuncTestSpec to each collected item from the registry."""
  for item in items:
    try:
      rel_path = str(Path(item.fspath).resolve().relative_to(_REPO_ROOT))
    except ValueError:
      continue
    spec = TEST_REGISTRY.get(rel_path)
    if spec is not None:
      item._scenescape_spec = spec

def pytest_runtest_setup(item):
  """Create a per-test log file before the fixture setup phase runs."""
  if not _ORCHESTRATION_AVAILABLE or _testlog is None:
    return
  spec = getattr(item, "_scenescape_spec", None)
  if spec is None:
    return
  path_str = str(item.fspath)
  if "sscape_tests" in path_str:
    group = "unit"
  elif "/ui/" in path_str:
    group = "ui"
  else:
    group = "functional"
  log_path = _testlog.setup(spec.id, group=group, log_base=_LOG_BASE)
  logger.info("Test log: %s", log_path)

def pytest_runtest_logreport(report):
  """Log test phase results to the per-test log file."""
  if not _ORCHESTRATION_AVAILABLE or _testlog is None:
    return
  if report.when == "call":
    result = report.outcome.upper()
    logger.info("=" * 60)
    logger.info("TEST RESULT: %s — %s", report.nodeid, result)
    if report.failed and report.longreprtext:
      for line in report.longreprtext.splitlines():
        logger.info("  %s", line)
    logger.info("=" * 60)

def pytest_configure(config):
  config.addinivalue_line("markers", "skip_init: skip init-sample-data step")
  config.addinivalue_line("markers", "test_name(name): sets the XML test name attribute")

  # Allow conftest.py loading from repo root down into manager/ and controller/.
  config.option.confcutdir = str(_REPO_ROOT)
