#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration for SceneScape tests.

Tests are collected directly from their source directories.
Each test file declares a module-level SCENESCAPE_SPEC (FuncTestSpec)
that describes the Docker Compose profile it needs.  An autouse
scenescape_env fixture starts the right compose stack and
injects CLI option values before the test runs.
Tests without a SCENESCAPE_SPEC (unit tests) get a no-op.
"""

import logging
import os
import re
import socket
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

from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER, AUTH_BROWSER  # noqa: F401

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

@pytest.fixture(scope="session", autouse=True)
def loopback_hosts():
  """Resolve SceneScape service hostnames to loopback in this test process."""
  if not _ORCHESTRATION_AVAILABLE:
    yield
    return

  original_getaddrinfo = socket.getaddrinfo

  def _loopback_getaddrinfo(host, *args, **kwargs):
    if isinstance(host, str) and host in _HOST_ALIASES:
      host = "127.0.0.1"
    return original_getaddrinfo(host, *args, **kwargs)

  logger.info("Using process-local loopback DNS for: %s", ", ".join(_HOST_ALIASES))
  socket.getaddrinfo = _loopback_getaddrinfo
  try:
    yield
  finally:
    socket.getaddrinfo = original_getaddrinfo


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
  env_path = Path(repo_root) / ".env"
  env_text = env_path.read_text() if env_path.exists() else ""
  env_ver = re.search(r"^VERSION=(.+)$", env_text, re.MULTILINE)
  image_version = os.environ.get("IMAGE_VERSION",
                                 env_ver.group(1) if env_ver else "latest")

  # Detect the latest local dlstreamer-pipeline-server image tag.
  dlstreamer_version = os.environ.get("DLSTREAMER_VERSION", "")
  if not dlstreamer_version:
    _dls_images = DockerClient().image.list("intel/dlstreamer-pipeline-server")
    _dls_tags = [
      t.split(":")[-1]
      for img in _dls_images
      for t in img.repo_tags
      if t.startswith("intel/dlstreamer-pipeline-server:")
    ]
    if _dls_tags:
      dlstreamer_version = sorted(_dls_tags)[-1]

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
  env_lines = (
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
  # Only set DLSTREAMER_VERSION when detected; omitting lets compose defaults apply.
  if dlstreamer_version:
    env_lines += f"DLSTREAMER_VERSION={dlstreamer_version}\n"
  env_file.write_text(env_lines)
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
  """Attach FuncTestSpec to each collected item from its module."""
  for item in items:
    spec = getattr(item.module, 'SCENESCAPE_SPEC', None)
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


def pytest_runtest_call(item):
  """Switch from setup log to test log right before test body executes."""
  if not _ORCHESTRATION_AVAILABLE or _testlog is None:
    return
  spec = getattr(item, "_scenescape_spec", None)
  if spec is None:
    return
  _testlog.begin_test_phase()

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
