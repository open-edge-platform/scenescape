#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration for SceneScape tests.

Tests are collected directly from their source directories.
Each test file declares a module-level SCENESCAPE_SPEC (FuncTestSpec)
that describes the Docker Compose profile it needs.

Session-scoped fixtures start one compose stack per profile.
Tests explicitly request "scenescape_env" which resolves the right
session fixture and injects per-test CLI options.
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

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
if str(_TESTS_DIR) not in sys.path:
  sys.path.insert(0, str(_TESTS_DIR))
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

# TODO: Exclude satellite test suites that need deps only available inside Docker.
collect_ignore_glob = [
  "api/*",
  "autocalibration/*",
  "mapping/*",
  "perf_tests/*",
  "sscape_tests/account-security/*",
  "system/metric/*",
  "pipeline_runner/*",
  "ntlb/*",
  "tools/*",
  "tracker/*",
]

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

@pytest.fixture(scope="session")
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
    ("--env-profiles",     dict(default=None,
                                help="Comma-separated list of env profile names to run tests against")),
    ("--collect-container-logs", dict(default="failed", choices=["failed", "all", "none"],
                  help="Container log collection mode: failed (default), all, or none")),
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
  broker_port: int = 1883
  https_port: int = 443

  def restore_db(self):
    """Reload the database from the original test archive.

    Flushes all data (keeping the schema), reloads fixture data from
    the EXAMPLEDB archive, and recreates auth users.
    """
    logger.info("Restoring database from EXAMPLEDB archive...")
    manage = "$SCENESCAPE_HOME/manage.py"
    self.docker.compose.execute(
      "web",
      ["sh", "-c", f"python {manage} flush --no-input"],
      tty=False,
    )
    self.docker.compose.execute(
      "web",
      ["sh", "-c",
       "tar xjf $EXAMPLEDB -C /tmp"
       f" && python {manage} loaddata /tmp/data.json"
       " && rm -f /tmp/data.json /tmp/meta.json"],
      tty=False,
    )
    self.docker.compose.execute(
      "web",
      ["sh", "-c",
       "find -L /run/secrets -name '*.auth'"
       f"  -exec python {manage} createuser --skip-existing {{}} \\;"
       " && DJANGO_SUPERUSER_PASSWORD=$SUPASS"
       f"    python {manage} createsuperuser"
       "    --no-input --username=admin"
       "    --email=admin@domain.com 2>/dev/null || true"],
      tty=False,
    )
    logger.info("Database restored.")


def _find_free_port():
  """Find an available TCP port on localhost."""
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(("", 0))
    return s.getsockname()[1]


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

@pytest.fixture(scope="session")
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
_HOST_ALIASES = [
  "broker.scenescape.intel.com",
  "web.scenescape.intel.com",
  "autocalibration.scenescape.intel.com",
]

@pytest.fixture(scope="session")
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

def _inject_options(config, spec, secrets_dir, supass, env=None):
  """Set config.option attributes so getoption() returns correct values.

  Called by the scenescape_env fixture before the test body runs.
  Both "params" fixtures and "Diagnostic.__init__" read from
  "request.config.getoption()", which delegates to this namespace.
  """
  opt = config.option

  if spec.require_password:
    opt.user = "admin"
    opt.password = supass

  # Resolve auth file on the host.
  opt.auth = f"{secrets_dir}/{spec.auth or 'controller.auth'}"
  opt.rootcert = f"{secrets_dir}/certs/scenescape-ca.pem"

  # When a ScenescapeEnv is provided, inject its dynamic ports.
  if env is not None:
    opt.broker_port = env.broker_port
    opt.weburl = f"https://web.scenescape.intel.com:{env.https_port}"
    opt.resturl = f"https://web.scenescape.intel.com:{env.https_port}/api/v1"

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
# Compose lifecycle helper (used by session-scoped profile fixtures)
# ---------------------------------------------------------------------------

def _compose_lifecycle(profile, repo_root, secrets_dir, supass, tmp_path_factory,
                       exampledb=""):
  """Start a Docker Compose stack for a profile; yield ScenescapeEnv; tear down.

  This is a generator meant to be called via ``yield from`` in
  session-scoped profile fixtures.
  """
  project_name = f"test-{uuid.uuid4().hex[:8]}"
  exampledb = exampledb or "tests/testdb.tar.bz2"
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

  tmp_path = tmp_path_factory.mktemp(profile.name)
  # Allocate dynamic host ports so parallel stacks never collide.
  broker_port = _find_free_port()
  https_port = _find_free_port()
  autocalib_port = _find_free_port()
  retail_dls_port = _find_free_port()
  queuing_dls_port = _find_free_port()

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
    f"BROKER_PORT={broker_port}\n"
    f"HTTPS_PORT={https_port}\n"
    f"AUTOCALIB_PORT={autocalib_port}\n"
    f"RETAIL_DLS_PORT={retail_dls_port}\n"
    f"QUEUING_DLS_PORT={queuing_dls_port}\n"
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

  try:
    logger.info("=" * 60)
    logger.info("Starting test environment: %s", project_name)
    logger.info("Profile: %s", profile.name)
    logger.info("Ports: broker=%d, https=%d", broker_port, https_port)
    logger.info("=" * 60)

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

    yield ScenescapeEnv(
      docker=docker,
      project_name=project_name,
      network=network,
      repo_root=repo_root,
      secrets_dir=secrets_dir,
      supass=supass,
      broker_port=broker_port,
      https_port=https_port,
    )

  finally:
    # Silence terminal output immediately — teardown logs go to file only.
    if _testlog is not None:
      _testlog.silence_console()

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
# Session-scoped profile fixtures
# ---------------------------------------------------------------------------

if _ORCHESTRATION_AVAILABLE:
  from tests.utils.profiles import (
    FULL_STACK, FULL_STACK_WITH_VIDEO_AND_RETAIL,
    REID, REID_SEMANTIC, FULL_STACK_AUTOCALIBRATION,
    SCENE_NO_DB, MARKERLESS,
  )

  def _make_profile_fixture(profile, **kw):
    """Create a session-scoped fixture for a ServiceProfile."""
    @pytest.fixture(scope="session")
    def _fixture(repo_root, secrets_dir, supass, tmp_path_factory):
      yield from _compose_lifecycle(profile, repo_root, secrets_dir, supass,
                                    tmp_path_factory, **kw)
    _fixture.__doc__ = f"Session-scoped {profile.name} compose environment."
    return _fixture

  full_stack_env = _make_profile_fixture(FULL_STACK)
  full_stack_video_retail_env = _make_profile_fixture(FULL_STACK_WITH_VIDEO_AND_RETAIL)
  reid_env = _make_profile_fixture(REID)
  reid_semantic_env = _make_profile_fixture(REID_SEMANTIC)
  full_stack_autocalibration_env = _make_profile_fixture(
    FULL_STACK_AUTOCALIBRATION, exampledb="tests/calibrationdb.tar.bz2")
  scene_no_db_env = _make_profile_fixture(SCENE_NO_DB)
  markerless_env = _make_profile_fixture(MARKERLESS)

  # Map profile name -> fixture name for the resolver.
  _PROFILE_FIXTURE_MAP = {
    p.name: f for p, f in [
      (FULL_STACK, "full_stack_env"),
      (FULL_STACK_WITH_VIDEO_AND_RETAIL, "full_stack_video_retail_env"),
      (REID, "reid_env"),
      (REID_SEMANTIC, "reid_semantic_env"),
      (FULL_STACK_AUTOCALIBRATION, "full_stack_autocalibration_env"),
      (SCENE_NO_DB, "scene_no_db_env"),
      (MARKERLESS, "markerless_env"),
    ]
  }


# ---------------------------------------------------------------------------
# Function-scoped resolver
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def scenescape_env(request, secrets_dir, supass, loopback_hosts):
  """Resolve the session-scoped profile fixture and inject per-test options.

  Each test that needs a compose environment must explicitly request this
  fixture.  It reads SCENESCAPE_SPEC from the test module to determine
  which session-scoped profile fixture to activate, then injects CLI
  options (auth, password, extra_args) for this specific test.
  """
  # When --env-profiles is active, _env_matrix_setup parametrizes a per-profile
  # FuncTestSpec into callspec.params; prefer that over the module-level default.
  if hasattr(request.node, 'callspec') and '_env_matrix_setup' in request.node.callspec.params:
    spec = request.node.callspec.params['_env_matrix_setup']
  else:
    spec = getattr(request.node, '_scenescape_spec', None) or getattr(request.module, 'SCENESCAPE_SPEC', None)
  if spec is None:
    pytest.fail(
      f"{request.module.__name__} requests scenescape_env but has no SCENESCAPE_SPEC"
    )

  if not _ORCHESTRATION_AVAILABLE:
    pytest.skip("python-on-whales not installed; run from host venv")

  fixture_name = _PROFILE_FIXTURE_MAP.get(spec.profile.name)
  if fixture_name is None:
    pytest.fail(f"No session fixture for profile {spec.profile.name!r}")

  env = request.getfixturevalue(fixture_name)

  # Inject per-test CLI option values.
  _inject_options(request.config, spec, secrets_dir, supass, env=env)

  return env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_marker(item):
  """Derive a pytest marker name from the test module filename.

  ``test_roi_mqtt.py`` -> ``roi_mqtt``
  """
  return item.module.__name__.split(".")[-1].removeprefix("test_")


# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------

# Log directory: tests/test_logs/{group}/{test_name}-{timestamp}.log
_LOG_BASE = _TESTS_DIR / "test_logs"

def _get_item_spec(item):
  """Return the FuncTestSpec for an item, preferring matrix callspec over module default."""
  if hasattr(item, 'callspec') and '_env_matrix_setup' in item.callspec.params:
    return item.callspec.params['_env_matrix_setup']
  return getattr(item, '_scenescape_spec', None) or getattr(item.module, 'SCENESCAPE_SPEC', None)

def pytest_collection_modifyitems(config, items):
  """Attach FuncTestSpec to each collected item, add markers, and sort by profile."""
  for item in items:
    spec = getattr(item.module, 'SCENESCAPE_SPEC', None)
    if spec is not None:
      item._scenescape_spec = spec
      marker_name = _derive_marker(item)
      config.addinivalue_line("markers", f"{marker_name}: FuncTestSpec marker")
      item.add_marker(getattr(pytest.mark, marker_name))

  # When running with --env-profiles, group tests by profile so each Docker
  # Compose environment starts once and handles all its tests before teardown.
  if config.getoption("env_profiles", default=None):
    from tests.utils.profiles import PROFILE_REGISTRY
    profile_order = {name: i for i, name in enumerate(PROFILE_REGISTRY)}
    original_order = {item: i for i, item in enumerate(items)}
    def _sort_key(item):
      spec = _get_item_spec(item)
      profile_rank = profile_order.get(spec.profile.name, 999) if spec else 999
      return (profile_rank, original_order[item])
    items.sort(key=_sort_key)

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
  test_name = _derive_marker(item)
  log_path = _testlog.setup(test_name, group=group, log_base=_LOG_BASE)
  logger.info("Test log: %s", log_path)

def pytest_runtest_call(item):
  """Switch file logging from setup log to per-test log for call/teardown."""
  if not _ORCHESTRATION_AVAILABLE or _testlog is None:
    return
  spec = getattr(item, "_scenescape_spec", None)
  if spec is None:
    return
  _testlog.begin_test_phase()

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
  """Attach setup/call/teardown reports to each item for teardown decisions."""
  outcome = yield
  rep = outcome.get_result()
  setattr(item, f"rep_{rep.when}", rep)

def pytest_runtest_teardown(item, nextitem):
  """Collect container logs according to configured collection mode."""
  if not _ORCHESTRATION_AVAILABLE:
    return

  mode = item.config.getoption("collect_container_logs", default="failed")
  if mode == "none":
    return

  rep_setup = getattr(item, "rep_setup", None)
  rep_call = getattr(item, "rep_call", None)
  failed = bool(
    (rep_setup is not None and rep_setup.failed)
    or (rep_call is not None and rep_call.failed)
  )
  if mode == "failed" and not failed:
    return

  env = item.funcargs.get("scenescape_env") if hasattr(item, "funcargs") else None
  if env is None:
    return

  if mode == "all":
    logger.info("Collecting container logs (mode=all): %s", item.nodeid)
  else:
    logger.info("Collecting container logs for failed test: %s", item.nodeid)
  collect_logs(env.docker, scan_for_tracebacks=True)

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
  config.addinivalue_line("markers", "test_name(name): sets the XML test name attribute")
