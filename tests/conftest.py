#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration for Scenescape tests.

Tests are collected directly from their source directories.
Each test file declares a module-level SCENESCAPE_SPEC (FuncTestSpec)
that describes the Docker Compose profile it needs.

A single session-scoped ComposeManager ensures at most one Docker
Compose stack runs at a time.  Tests are sorted by profile so the
stack is only restarted when the required profile changes.
"""

import logging
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from scene_common.mqtt import PubSub

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
if str(_TESTS_DIR) not in sys.path:
  sys.path.insert(0, str(_TESTS_DIR))
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

_PERF_TESTS_DIR = _TESTS_DIR / "perf_tests"
if str(_PERF_TESTS_DIR) not in sys.path:
  sys.path.insert(0, str(_PERF_TESTS_DIR))

# Exclude satellite test suites that need deps only available inside Docker.
collect_ignore_glob = [
  "api/*",
  "autocalibration/*",
  "mapping/*",
  "ntlb/*",
  "tools/*",
  "tracker/*",
]

# ---------------------------------------------------------------------------
# In-container: controller / analytics module paths
# ---------------------------------------------------------------------------
_controller_src = _REPO_ROOT / "controller" / "src"
if str(_controller_src) not in sys.path:
  sys.path.insert(0, str(_controller_src))

_analytics_src = _REPO_ROOT / "analytics" / "src"
if str(_analytics_src) not in sys.path:
  sys.path.insert(0, str(_analytics_src))

# ---------------------------------------------------------------------------
# Environmental dependencies (host-only)
# ---------------------------------------------------------------------------
_ORCHESTRATION_AVAILABLE = False
_K8S_AVAILABLE = False
_testlog = None
try:
  from python_on_whales import DockerClient
  from python_on_whales.exceptions import DockerException
  import utils.log as _testlog
  from utils import stream_subprocess
  from utils.containers import collect_logs, wait_for_services
  from utils.profiles import WaitConfig
  _ORCHESTRATION_AVAILABLE = True
except ImportError:
  pass

try:
  from utils.k8s import K8sManager
  _K8S_AVAILABLE = True
except ImportError:
  pass

# Use the test logger hierarchy when orchestration deps are present;
# fall back to stdlib so in-container tests still emit warnings etc.
if _testlog is not None:
  logger = _testlog.get_logger("conftest")
else:
  logger = logging.getLogger(__name__)


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
    ("--auth",             dict(default=str(_REPO_ROOT / "manager" / "secrets" / "controller.auth"),
                                help="user:password or JSON file for MQTT authentication")),
    ("--rootcert",         dict(default=str(_REPO_ROOT / "manager" / "secrets" / "certs" / "scenescape-ca.pem"),
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
    ("--env-profiles",     dict(default=None,
                                help="Comma-separated list of env profile names to run tests against")),
    ("--collect-container-logs", dict(default="failed", choices=["failed", "all", "none"],
                  help="Container log collection mode: failed (default), all, or none")),
    ("--backend",          dict(default="docker", choices=["docker", "kubernetes", "all"],
                                help="Deployment backend: docker (compose), kubernetes (KinD+helm), or all")),
    ("--expect_exceed_max", dict(default="false",
                                help="Whether unique count is expected to exceed max (true/false)")),
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

  def restore_db(self):
    """Reload the database from the original test archive.

    Flushes all data (keeping the schema), reloads fixture data from
    the EXAMPLEDB archive, recreates auth users, marks the database
    as ready, and restarts the scene controller so it picks up the
    fresh DB state.
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

    self.docker.compose.execute(
      "web",
      ["sh", "-c", f"python {manage} updatedbstatus --ready"],
      tty=False,
    )
    logger.info("Database restored.")

    logger.info("Restarting scene controller to refresh cache...")
    try:
      from datetime import datetime, timezone
      import time
      restart_time = datetime.now(timezone.utc)
      self.docker.compose.restart("scene")
      time.sleep(0.5)
      wait_for_services(
        self.docker, self.project_name,
        {"scene": WaitConfig(log_pattern="Subscribed to")},
        since=restart_time,
      )
      logger.info("Scene controller restarted and ready.")
    except Exception as exc:
      logger.warning("Scene controller restart failed: %s", exc)

    # Restart the autocalibration service if it is running
    try:
      from datetime import datetime, timezone
      import time
      containers = self.docker.compose.ps()
      autocalib_running = any(
        c.name and "autocalibration" in c.name and "init" not in c.name
        for c in containers
      )
      if autocalib_running:
        logger.info("Restarting autocalibration service (auth token refresh)...")
        restart_time = datetime.now(timezone.utc)
        self.docker.compose.restart("autocalibration")
        time.sleep(0.5)
        wait_for_services(
          self.docker, self.project_name,
          {"autocalibration": WaitConfig(timeout=120)},
          since=restart_time,
        )
        logger.info("Autocalibration service restarted and ready.")
    except Exception as exc:
      logger.warning("Autocalibration restart failed: %s", exc)

    # Restart the analytics service if it is running (its cached REST auth
    # session is invalidated by the DB flush/reload above, same as autocalibration).
    try:
      from datetime import datetime, timezone
      import time
      containers = self.docker.compose.ps()
      analytics_running = any(
        c.name and "analytics" in c.name and "cluster" not in c.name
        for c in containers
      )
      if analytics_running:
        logger.info("Restarting analytics service (auth token refresh)...")
        restart_time = datetime.now(timezone.utc)
        self.docker.compose.restart("analytics")
        time.sleep(0.5)
        wait_for_services(
          self.docker, self.project_name,
          {"analytics": WaitConfig(log_pattern="Subscribed to")},
          since=restart_time,
        )
        logger.info("Analytics service restarted and ready.")
    except Exception as exc:
      logger.warning("Analytics restart failed: %s", exc)


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
    'expect_exceed_max': request.config.getoption('--expect_exceed_max'),
  }

def connect_mqtt(params):
  """Return a connected, looping PubSub client."""
  pubsub = PubSub(
    params["auth"], None, params["rootcert"], params["broker_url"],
    port=int(params["broker_port"]), keepalive=60,
  )
  pubsub.connect()
  pubsub.loopStart()
  for _ in range(100):
    if pubsub.isConnected():
      break
    time.sleep(0.1)
  assert pubsub.isConnected(), "Failed to connect to MQTT broker"
  return pubsub

@pytest.fixture
def mqtt_client(params):
  """Connected PubSub client, cleaned up after the test."""
  client = connect_mqtt(params)
  yield client
  client.loopStop()
  client.disconnect()

def pytest_runtest_makereport(item, call):
  """Hook that runs after each test phase (setup/call/teardown).

  Used to detect when we're in a single-test run (or the last test in a session)
  and clean up the compose stack immediately.
  """
  if not _ORCHESTRATION_AVAILABLE:
    return

  # Only act after the test teardown phase has completed
  if call.when != "teardown":
    return

  # Check if this test used scenescape_env
  if not getattr(item.session, "_scenescape_test_ran", False):
    return

  # Reset the marker for the next test
  item.session._scenescape_test_ran = False

  # If this is the last test in the session (or only one),
  # tear down the compose stack immediately to avoid container leakage.
  remaining_items = [i for i in item.session.items if i != item]
  if not remaining_items:
    if hasattr(item.session, "_compose_manager"):
      manager = item.session._compose_manager
      try:
        manager._stop_current()
        logger.info("Cleaned up compose stack after final test")
      except Exception as exc:
        logger.warning("Failed to clean up compose stack: %s", exc)


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
  "reid.scenescape.intel.com",
]

@pytest.fixture(scope="session")
def loopback_hosts():
  """Resolve Scenescape service hostnames to loopback in this test process.

  Patches both socket.getaddrinfo (for high-level callers) and
  socket.socket.connect (for low-level callers like ssl.SSLSocket that call
  socket.connect with a (host, port) tuple directly) so that all Python code
  resolves the aliases to 127.0.0.1 without requiring /etc/hosts changes.
  """
  if not _ORCHESTRATION_AVAILABLE:
    yield
    return

  original_getaddrinfo = socket.getaddrinfo
  original_connect = socket.socket.connect

  def _loopback_getaddrinfo(host, *args, **kwargs):
    if isinstance(host, str) and host in _HOST_ALIASES:
      host = "127.0.0.1"
    return original_getaddrinfo(host, *args, **kwargs)

  def _loopback_connect(self, address):
    if isinstance(address, tuple) and len(address) >= 1:
      host = address[0]
      if isinstance(host, str) and host in _HOST_ALIASES:
        address = ("127.0.0.1",) + address[1:]
    return original_connect(self, address)

  logger.info("Using process-local loopback DNS for: %s", ", ".join(_HOST_ALIASES))
  socket.getaddrinfo = _loopback_getaddrinfo
  socket.socket.connect = _loopback_connect
  try:
    yield
  finally:
    socket.getaddrinfo = original_getaddrinfo
    socket.socket.connect = original_connect


@pytest.fixture(scope="session")
def install_shared_models(request, repo_root):
  """Install models to a shared Docker volume once per test session.

  This fixture ensures models are downloaded and installed only once,
  to a fixed volume name 'scenescape_vol-models', which is then reused
  by all test profiles.

  No-ops when --backend=kubernetes (Helm chart handles model installation).

  All test profiles mount this shared volume so models are always available
  and ready without per-profile installation.
  """
  backend = request.config.getoption("--backend")
  if backend == "kubernetes":
    logger.info("Skipping model installation: Helm chart handles models for Kubernetes")
    yield
    return

  if not _ORCHESTRATION_AVAILABLE:
    logger.warning("Skipping model installation: orchestration not available")
    yield
    return

  logger.info("Installing OpenVINO Zoo models to shared volume (scenescape_vol-models)...")
  try:
    stream_subprocess(
      ["make", "install-models"],
      cwd=repo_root,
      env={**os.environ, "COMPOSE_PROJECT_NAME": "scenescape"},
    )
    logger.info("Shared models volume ready.")
  except Exception as exc:
    logger.error("Model installation failed: %s", exc)

  yield


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

def _spec_visibility_topic(spec):
  """Extract the controller visibility_topic from a spec's extra_args (default regulated)."""
  args = spec.extra_args or []
  for i, arg in enumerate(args):
    if arg == "--visibility_topic" and i + 1 < len(args):
      return args[i + 1]
  return "regulated"


def _compose_lifecycle(profile, repo_root, secrets_dir, supass, tmp_path_factory,
                       exampledb="", collect_container_logs_mode="failed",
                       visibility_topic="regulated"):
  """Start a Docker Compose stack for a profile; yield ScenescapeEnv; tear down.

  This is a generator meant to be called via ``yield from`` in
  session-scoped profile fixtures.
  """
  spec = profile.name.replace("_", "-")
  project_name = f"test-{uuid.uuid4().hex[:4]}-{spec}"
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
    f"VISIBILITY={visibility_topic}\n"
    f"VISIBILITY_TOPIC={visibility_topic}\n"
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

  lifecycle_failed = False
  try:
    logger.info("=" * 60)
    logger.info("Starting test environment: %s", project_name)
    logger.info("Profile: %s", profile.name)
    logger.info("=" * 60)

    logger.info("Running init-sample-data (using pre-installed shared models)...")
    stream_subprocess(
      ["make", "init-sample-data"],
      cwd=repo_root,
      env={**os.environ, "COMPOSE_PROJECT_NAME": project_name},
    )

    logger.info("Starting compose services...")
    try:
      docker.compose.up(detach=True, pull="missing", quiet=True)
    except DockerException as exc:
      logger.error("compose up failed: %s", exc)
      raise

    if profile.wait_for:
      wait_for_services(docker, project_name, profile.wait_for)

    yield ScenescapeEnv(
      docker=docker,
      project_name=project_name,
      network=network,
      repo_root=repo_root,
      secrets_dir=secrets_dir,
      supass=supass,
    )

  except Exception:
    lifecycle_failed = True
    raise

  finally:
    # Silence terminal output immediately — teardown logs go to file only.
    if _testlog is not None:
      _testlog.silence_console()

    # Fallback logging for failures before pytest_runtest_teardown can run
    # (for example compose startup/wait_for_services or fixture setup errors).
    if lifecycle_failed and collect_container_logs_mode != "none":
      logger.info(
        "Collecting fallback container logs after lifecycle failure (mode=%s): %s",
        collect_container_logs_mode,
        project_name,
      )
      try:
        collect_logs(docker, scan_for_tracebacks=True)
      except Exception as exc:
        logger.warning("fallback container log collection failed: %s", exc)

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
# Compose Manager – ensures at most one stack runs at a time
# ---------------------------------------------------------------------------

_PROFILE_EXAMPLEDB = {
  "full_stack_autocalibration": "tests/calibrationdb.tar.bz2",
}


class _ComposeManager:
  """Manages Docker Compose lifecycle so only one stack runs at a time.

  When a test requests a profile different from the currently active one,
  the manager tears down the current stack before starting the new one.
  Tests are sorted by profile in pytest_collection_modifyitems to minimise
  the number of stack restarts.
  """

  def __init__(self, repo_root, secrets_dir, supass, tmp_path_factory):
    self._repo_root = repo_root
    self._secrets_dir = secrets_dir
    self._supass = supass
    self._tmp_path_factory = tmp_path_factory
    self._current_profile_name = None
    self._current_env = None
    self._current_gen = None  # active _compose_lifecycle generator
    self._failed_profiles = {}  # profile name -> exception message

  def get_env(self, profile, visibility_topic="regulated", fresh=False):
    """Return a ScenescapeEnv for *profile*, reusing or restarting as needed.

    When *fresh* is True the currently running stack is always torn down and
    a brand-new stack is started, even if the requested profile matches the
    active one. This reproduces the pristine single-test condition for tests
    that are sensitive to resource accumulation in the long-lived shared
    stack (e.g. WebGL/3D UI tests).
    """
    profile_key = f"{profile.name}:{visibility_topic}"
    if profile_key in self._failed_profiles:
      pytest.fail(
        f"Profile {profile_key!r} already failed to start: "
        f"{self._failed_profiles[profile_key]}"
      )

    if self._current_profile_name == profile_key and not fresh:
      return self._current_env

    self._stop_current()

    exampledb = _PROFILE_EXAMPLEDB.get(profile.name, "")
    gen = _compose_lifecycle(
      profile, self._repo_root, self._secrets_dir,
      self._supass, self._tmp_path_factory, exampledb=exampledb,
      visibility_topic=visibility_topic,
    )
    try:
      env = next(gen)
    except Exception as exc:
      gen.close()
      self._failed_profiles[profile_key] = str(exc)
      raise

    self._current_gen = gen
    self._current_env = env
    self._current_profile_name = profile_key
    return env

  def _stop_current(self):
    """Tear down the currently running compose stack, if any."""
    if self._current_gen is not None:
      self._current_gen.close()  # triggers finally block in _compose_lifecycle
      self._current_gen = None
      self._current_env = None
      self._current_profile_name = None

  def teardown(self):
    """Tear down at session end."""
    self._stop_current()


@pytest.fixture(scope="session")
def _compose_manager(repo_root, secrets_dir, supass, tmp_path_factory, request):
  """Single session-scoped manager that runs at most one compose stack at a time."""
  backend = request.config.getoption("--backend")
  if backend not in ("docker", "all"):
    yield None
    return
  if not _ORCHESTRATION_AVAILABLE:
    yield None
    return
  manager = _ComposeManager(repo_root, secrets_dir, supass, tmp_path_factory)
  request.session._compose_manager = manager
  yield manager
  manager.teardown()


@pytest.fixture(scope="session")
def _k8s_manager(repo_root, supass, tmp_path_factory, request):
  """Session-scoped KinD cluster + Helm deployment manager."""
  backend = request.config.getoption("--backend")
  if backend not in ("kubernetes", "all"):
    yield None
    return
  if not _K8S_AVAILABLE:
    yield None
    return
  manager = K8sManager(repo_root, supass, tmp_path_factory)
  manager.setup()
  yield manager
  manager.teardown()


def _inject_k8s_options(config, spec, k8s_mgr):
  """Set config.option attributes for Kubernetes backend.

  Mirrors _inject_options() but uses port-forwarded endpoints and
  secrets extracted from the Kubernetes cluster.
  """
  opt = config.option
  opt.user = "admin"
  opt.password = k8s_mgr._supass
  opt.auth = k8s_mgr.auth_file
  opt.rootcert = k8s_mgr.cert_file
  opt.broker_url = "broker.scenescape.intel.com"
  opt.broker_port = k8s_mgr.mqtt_port
  opt.weburl = f"https://web.scenescape.intel.com:{k8s_mgr.web_port}"
  opt.resturl = f"https://web.scenescape.intel.com:{k8s_mgr.web_port}/api/v1"

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


@pytest.fixture(scope="function")
def _backend_type(request):
  """Indirect parametrization target for backend selection.

  When --backend=all, pytest_generate_tests parametrizes this with
  ['docker', 'kubernetes']. Otherwise returns the --backend value.
  """
  return request.param if hasattr(request, 'param') else request.config.getoption("--backend")


# ---------------------------------------------------------------------------
# Function-scoped resolver
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def scenescape_env(request, _compose_manager, secrets_dir, supass,
                   loopback_hosts, install_shared_models):
  """Resolve the test environment for the current test's profile and backend.

  Dispatches to Docker Compose (_ComposeManager) or Kubernetes (_K8sManager)
  based on the --backend option or parametrized _backend_type value.

  Each test that needs an environment must explicitly request this fixture.
  It reads SCENESCAPE_SPEC from the test module to determine which profile
  to activate.

  On teardown the database is automatically restored from the baseline
  snapshot so that every test starts and ends with an identical
  environment regardless of what it created or deleted during execution.
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

  # Determine backend: parametrized _backend_type takes priority, then --backend.
  backend = "docker"
  if hasattr(request.node, 'callspec') and '_backend_type' in request.node.callspec.params:
    backend = request.node.callspec.params['_backend_type']
  else:
    backend_opt = request.config.getoption("--backend")
    if backend_opt in ("docker", "kubernetes"):
      backend = backend_opt

  if backend == "kubernetes":
    if not _K8S_AVAILABLE:
      pytest.skip("pytest-kubernetes not installed; install with: pip install pytest-kubernetes")
    _k8s_manager = request.getfixturevalue("_k8s_manager")
    if _k8s_manager is None:
      pytest.skip("Kubernetes manager not available")
    env = _k8s_manager.get_env(spec)
    _inject_k8s_options(request.config, spec, _k8s_manager)
  else:
    if not _ORCHESTRATION_AVAILABLE:
      pytest.skip("python-on-whales not installed; run from host venv")
    if _compose_manager is None:
      pytest.skip("Docker Compose manager not available")
    # Tests marked @pytest.mark.fresh_stack get a brand-new stack so they run
    # against a pristine environment rather than a long-lived stack.
    fresh = request.node.get_closest_marker("fresh_stack") is not None
    env = _compose_manager.get_env(
      spec.profile, _spec_visibility_topic(spec), fresh=fresh)
    _inject_options(request.config, spec, secrets_dir, supass, env=env)

  # If a previous test preserved the database (skipped its post-test restore)
  # and it lived in a different module, restore now so this test starts from the
  # baseline snapshot. Restores are scoped to the running stack: a profile change
  # already restarts the stack with a fresh database, and within-module
  # persistence chains (multiple tests in one file relying on carried-over state)
  # are intentionally left untouched.
  if "web" in spec.profile.wait_for and hasattr(env, "restore_db"):
    preserved = getattr(request.session, "_scenescape_db_preserved", None)
    if preserved is not None:
      preserved_module, preserved_profile_key = preserved
      current_profile_key = f"{spec.profile.name}:{_spec_visibility_topic(spec)}"
      if preserved_profile_key != current_profile_key:
        # Stack was restarted on the profile switch; database is already fresh.
        request.session._scenescape_db_preserved = None
      elif preserved_module != request.module.__name__:
        logger.info(
          "Restoring database before %s: previous module %s preserved it",
          request.module.__name__, preserved_module,
        )
        try:
          env.restore_db()
        except Exception as exc:
          logger.warning("Pre-test DB restore failed: %s", exc)
        request.session._scenescape_db_preserved = None

  yield env

  # Collect container logs based on outcome and mode while the stack is still running.
  _collect_container_logs_if_configured(env, request)

  # Restore database after every test so each test starts from an identical
  # baseline. Only applies to profiles that include a web/database service.
  # Tests marked with @pytest.mark.preserve_db skip this restore so a following
  # test in the same module can verify data survives; the preserved state is
  # recorded so the next test in a different module restores before running.
  if "web" in spec.profile.wait_for:
    if request.node.get_closest_marker("preserve_db"):
      request.session._scenescape_db_preserved = (
        request.module.__name__,
        f"{spec.profile.name}:{_spec_visibility_topic(spec)}",
      )
    else:
      try:
        env.restore_db()
      except Exception as exc:
        logger.warning("Post-test DB restore failed: %s", exc)
      request.session._scenescape_db_preserved = None


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

# Log directory: tests/.test_logs/{group}/{test_id}/{test_id}-{timestamp}.log
_LOG_BASE = _TESTS_DIR / ".test_logs"

def pytest_generate_tests(metafunc):
  """Parametrize tests across backends when --backend=all.

  Creates test IDs like test_out_of_box[docker] and test_out_of_box[kubernetes]
  in VS Code's test explorer.

  Only applies to tests that use the scenescape_env fixture.
  """
  if "scenescape_env" not in metafunc.fixturenames:
    return

  backend = metafunc.config.getoption("--backend")
  if backend == "all":
    if "_backend_type" not in metafunc.fixturenames:
      metafunc.fixturenames.append("_backend_type")
    metafunc.parametrize("_backend_type", ["docker", "kubernetes"], indirect=True)
  elif backend == "kubernetes":
    if "_backend_type" not in metafunc.fixturenames:
      metafunc.fixturenames.append("_backend_type")
    metafunc.parametrize("_backend_type", ["kubernetes"], indirect=True)

def _get_item_spec(item):
  """Return the FuncTestSpec for an item, preferring matrix callspec over module default."""
  if hasattr(item, 'callspec') and '_env_matrix_setup' in item.callspec.params:
    return item.callspec.params['_env_matrix_setup']
  return getattr(item, '_scenescape_spec', None) or getattr(item.module, 'SCENESCAPE_SPEC', None)

def pytest_collection_modifyitems(config, items):
  """Attach FuncTestSpec to each collected item, add markers, and sort by profile.

  Groups tests by profile so the ComposeManager only restarts
  the compose stack when the profile changes, keeping at most one stack
  running at a time.
  """
  for item in items:
    spec = getattr(item.module, 'SCENESCAPE_SPEC', None)
    if spec is not None:
      item._scenescape_spec = spec
      marker_name = _derive_marker(item)
      config.addinivalue_line("markers", f"{marker_name}: FuncTestSpec marker")
      item.add_marker(getattr(pytest.mark, marker_name))

  # Skip kubernetes_only tests when backend is docker-only.
  backend = config.getoption("--backend")
  if backend == "docker":
    skip_k8s = pytest.mark.skip(reason="kubernetes-only test (--backend=docker)")
    for item in items:
      if item.get_closest_marker("kubernetes_only"):
        item.add_marker(skip_k8s)

  # Always sort by profile so _ComposeManager only restarts the stack on profile
  # transitions.  Use PROFILE_REGISTRY order when available so --env-profiles
  # matrix parametrisation runs in a predictable sequence.
  try:
    from tests.utils.profiles import PROFILE_REGISTRY
    profile_order = {name: i for i, name in enumerate(PROFILE_REGISTRY)}
  except ImportError:
    profile_order = {}

  def _sort_key(item):
    spec = _get_item_spec(item)
    if spec is None:
      return (999, "")
    return (profile_order.get(spec.profile.name, 998), spec.profile.name)

  items[:] = sorted(items, key=_sort_key)

def pytest_runtest_setup(item):
  """Create a per-test log file before the fixture setup phase runs."""
  if not _ORCHESTRATION_AVAILABLE or _testlog is None:
    return
  spec = getattr(item, "_scenescape_spec", None)
  is_k8s_only = item.get_closest_marker("kubernetes_only") is not None
  if spec is None and not is_k8s_only:
    return
  path_str = str(item.fspath)
  if "sscape_tests" in path_str:
    group = "unit"
  elif "/ui/" in path_str:
    group = "ui"
  elif is_k8s_only:
    group = "kubernetes"
  else:
    group = "functional"
  test_name = _derive_marker(item)
  log_path = _testlog.setup(test_name, group=group, log_base=_LOG_BASE)
  logger.info("Test log: %s", log_path)
  logger.info("Test: %s", item.nodeid)

def _collect_container_logs_if_configured(env, request):
  """Collect container logs from env if outcome+mode warrant it.

  Called from the scenescape_env fixture teardown before any stack cleanup
  so the containers are still running.
  """
  if not _ORCHESTRATION_AVAILABLE or env is None or not hasattr(env, "docker"):
    return
  mode = request.config.getoption("collect_container_logs", default="failed")
  if mode == "none":
    return
  node = request.node
  rep_setup = getattr(node, "rep_setup", None)
  rep_call = getattr(node, "rep_call", None)
  failed = bool(
    (rep_setup is not None and rep_setup.failed)
    or (rep_call is not None and rep_call.failed)
  )
  if mode == "failed" and not failed:
    return
  if mode == "all":
    logger.info("Collecting container logs (mode=all): %s", node.nodeid)
  else:
    logger.info("Collecting container logs for failed test: %s", node.nodeid)
  if _testlog is not None:
    _testlog.silence_console()
  collect_logs(env.docker, scan_for_tracebacks=True)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
  """Attach setup/call/teardown reports and finalize the per-test log."""
  outcome = yield
  rep = outcome.get_result()
  setattr(item, f"rep_{rep.when}", rep)
  if rep.when == "teardown" and _testlog is not None:
    rep_setup = getattr(item, "rep_setup", None)
    rep_call = getattr(item, "rep_call", None)
    rep_teardown = getattr(item, "rep_teardown", None)
    failed = bool(
      (rep_setup is not None and rep_setup.failed)
      or (rep_call is not None and rep_call.failed)
      or (rep_teardown is not None and rep_teardown.failed)
    )
    _testlog.finalize(passed=not failed)

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
  config.addinivalue_line("markers", "kubernetes_only: test only runs with --backend=kubernetes or --backend=all")
  config.addinivalue_line("markers", "fresh_stack: start a brand-new compose stack for this test instead of reusing the shared one")


# ---------------------------------------------------------------------------
# Common test fixtures
# ---------------------------------------------------------------------------

from tests.common_test_utils import record_test_result

DEMO_SCENE_UID = "3bc091c7-e449-46a0-9540-29c499bca18c"


@pytest.fixture(scope="function", autouse=True)
def record_test_name(request, record_xml_attribute):
  """Record test name from marker if provided; otherwise do nothing."""
  marker = request.node.get_closest_marker("test_name")
  if marker and marker.args:
    record_xml_attribute("name", marker.args[0])


@pytest.fixture(scope="function")
def result_recorder(request):
  """Provides .success(); records exit code with test name on teardown."""
  marker = request.node.get_closest_marker("test_name")
  test_name = (marker.args[0] if marker and marker.args
    else getattr(request.node.module, "TEST_NAME", request.node.name))

  class Result:
    exit_code = 1
    def success(self):
      self.exit_code = 0

  r = Result()
  try:
    yield r
  finally:
    record_test_result(test_name, r.exit_code)


@pytest.fixture(scope="function")
def demo_scene(scenescape_env):
  """Provide the Demo scene UID.

  Database restoration is handled automatically by the scenescape_env
  fixture teardown, so every test gets a clean slate regardless of
  whether it uses this fixture.
  """
  return DEMO_SCENE_UID
