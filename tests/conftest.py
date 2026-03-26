#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration for tests

Contains two sets of fixtures:
  - ControllerMode (in-container): initializes the tracker controller mode
    for functional tests running inside Docker containers.
  - Environmental (host): manages Docker Compose lifecycle for end-to-end test runs.
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
sys.path.insert(0, str(_TESTS_DIR))

# ---------------------------------------------------------------------------
# In-container: controller module (optional)
# ---------------------------------------------------------------------------
_controller_src = Path(__file__).resolve().parents[1] / "controller" / "src"
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
  from utils.containers import collect_logs, scan_tracebacks, wait_for_services
  from utils.runner import run_test_in_container, run_unit_test
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


def pytest_addoption(parser):
  """Add shared command-line options for all tests."""
  try:
    parser.addoption(
      "--analytics-only",
      action="store_true",
      default=False,
      help="Enable analytics-only mode for tests (tracker disabled)",
    )
  except ValueError:
    pass

# ---------------------------------------------------------------------------
# end-to-end orchestration dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FuncTestSpec:
  """Specification for a single functional test."""
  id: str
  profile: object  # ServiceProfile
  script: str
  auth: str = ""
  require_password: bool = True
  extra_args: list = None
  test_image: str = ""
  exampledb: str = ""
  extra_env: dict = None

  def __post_init__(self):
    if self.extra_args is None:
      self.extra_args = []
    if self.extra_env is None:
      self.extra_env = {}

@dataclass
class UnitTestSpec:
  """Specification for a unit test (no compose stack)."""
  id: str
  test_folder: str
  docker_image: str
  pythonpath: str = "/home/scenescape/SceneScape/"

@dataclass
class ScenescapeEnv:
  """Yielded by the scenescape_env fixture."""
  docker: object  # DockerClient
  project_name: str
  network: str
  test_image: str
  repo_root: str
  secrets_dir: str
  supass: str


# ---------------------------------------------------------------------------
# end-to-end session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def repo_root():
  """Absolute path to the repository root."""
  return str(Path(__file__).resolve().parents[1])

@pytest.fixture(scope="session")
def version(repo_root):
  """Image version tag from version.txt."""
  return (Path(repo_root) / "version.txt").read_text().strip()

@pytest.fixture(scope="session")
def secrets_dir(repo_root):
  """Path to the secrets directory."""
  sdir = os.environ.get("SECRETSDIR") or os.path.join(repo_root, "manager", "secrets")
  sdir = os.path.abspath(sdir)
  assert os.path.isdir(sdir), f"Secrets directory not found: {sdir}"
  return sdir

@pytest.fixture(scope="session")
def supass():
  """Superuser password for tests (from SUPASS env var or random)."""
  return os.environ.get("SUPASS") or subprocess.check_output(
    ["openssl", "rand", "-base64", "12"], text=True,
  ).strip()

# ---------------------------------------------------------------------------
# end-to-end function-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def scenescape_env(request, repo_root, secrets_dir, supass, tmp_path):
  """
  Start a SceneScape Docker Compose environment for one test.
  Must be used with indirect parametrize passing a FuncTestSpec.
  """
  if not _ORCHESTRATION_AVAILABLE:
    pytest.skip("python-on-whales not installed; run from host")

  spec = request.param if hasattr(request, "param") else None
  if spec is None:
    pytest.skip("scenescape_env requires indirect parametrize with a FuncTestSpec")

  profile = spec.profile
  image_suffix = spec.test_image or profile.default_test_image
  image_version = os.environ.get("IMAGE_VERSION", "latest")
  test_image = f"scenescape-{image_suffix}:{image_version}"
  project_name = f"sst-{uuid.uuid4().hex[:8]}"
  exampledb = spec.exampledb or "tests/testdb.tar.bz2"

  os.environ["SECRETSDIR"] = secrets_dir

  # Uses original compose files directly. Only the runner container uses test_image.
  compose_file_paths = [os.path.join(repo_root, cf) for cf in profile.compose_files]

  controller_auth_path = os.path.join(secrets_dir, "controller.auth")
  controller_auth = ""
  if os.path.isfile(controller_auth_path):
    controller_auth = Path(controller_auth_path).read_text().strip()

  django_secrets_path = Path(secrets_dir) / "django" / "secrets.py"
  db_password_match = re.search(
    r"DATABASE_PASSWORD='([^']+)'",
    django_secrets_path.read_text(),
  )
  database_password = db_password_match.group(1) if db_password_match else supass

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

  try:
    logger.info("=" * 60)
    logger.info("Starting test environment: %s", project_name)
    logger.info("Profile: %s | Image: %s", profile.name, test_image)
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

    yield ScenescapeEnv(
      docker=docker,
      project_name=project_name,
      network=network,
      test_image=test_image,
      repo_root=repo_root,
      secrets_dir=secrets_dir,
      supass=supass,
    )

  finally:
    # Silence terminal output immediately — teardown logs go to file only.
    if _testlog is not None:
      _testlog.silence_console()

    logger.info("Collecting container logs: %s", project_name)
    collect_logs(docker)

    tracebacks = scan_tracebacks(docker)
    if tracebacks:
      logger.warning("Tracebacks found in: %s", ", ".join(tracebacks))

    logger.info("Cleaning up: %s", project_name)
    try:
      docker.compose.down(remove_orphans=True, volumes=True)
    except Exception as exc:
      logger.warning("compose down failed: %s", exc)

    for vol in [
      f"{project_name}_vol-models",
      f"{project_name}_vol-db",
      f"{project_name}_vol-migrations",
      f"{project_name}_vol-sample-data",
      f"{project_name}_vol-media",
    ]:
      try:
        DockerClient().volume.remove(vol)
      except Exception:
        pass

    try:
      DockerClient().system.prune()
    except Exception:
      pass

    logger.info("Cleanup complete: %s", project_name)

@pytest.fixture(scope="function")
def run_test(request, scenescape_env, supass):
  """Return a callable that runs a test script inside the compose network."""
  env = scenescape_env

  def _run(spec):
    cmd = ["pytest", "-s", spec.script]
    if spec.require_password:
      cmd.append(f"--password={supass}")
    if spec.auth:
      cmd.append(f"--auth={spec.auth}")
    cmd.extend(spec.extra_args)
    return run_test_in_container(
      image=env.test_image,
      command=cmd,
      repo_root=env.repo_root,
      project_name=env.project_name,
      network=env.network,
      extra_env=dict(spec.extra_env) if spec.extra_env else {},
    )

  return _run

@pytest.fixture(scope="function")
def run_unit(repo_root):
  """Return a callable that runs a standalone unit test in a container."""
  image_version = os.environ.get("IMAGE_VERSION", "latest")

  def _run(spec):
    image = f"scenescape-{spec.docker_image}:{image_version}"
    cmd = [
      "sh", "-c",
      f"export PYTHONPATH={spec.pythonpath} && "
      f"pytest -s tests/sscape_tests/{spec.test_folder}/",
    ]
    return run_unit_test(image=image, command=cmd, repo_root=repo_root)

  return _run

# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------

# Log directory: tests/test_logs/{group}/{test_name}-{timestamp}.log
_LOG_BASE = Path(__file__).parent / "test_logs"

def pytest_runtest_setup(item):
  """Create a per-test log file before the fixture setup phase runs."""
  if not _ORCHESTRATION_AVAILABLE or _testlog is None:
    return
  cs = getattr(item, "callspec", None)
  if cs is None:
    return
  spec = (
    cs.params.get("test_spec")
    or cs.params.get("scenescape_env")
    or cs.params.get("unit_spec")
    or cs.params.get("compose_unit_spec")
    or cs.params.get("ui_spec")
  )
  if spec is None or not hasattr(spec, "id"):
    return
  fn = item.function.__name__
  if "unit" in fn:
    group = "unit"
  elif "ui" in fn:
    group = "ui"
  else:
    group = "functional"
  log_path = _testlog.setup(spec.id, group=group, log_base=_LOG_BASE)
  logger.info("Test log: %s", log_path)


def pytest_configure(config):
  config.addinivalue_line("markers", "skip_init: skip init-sample-data step")
