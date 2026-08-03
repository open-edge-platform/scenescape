#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ReID backend registry."""

import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from controller import reid_registry


@pytest.fixture(autouse=True)
def _clear_backend_env(monkeypatch):
  monkeypatch.delenv("REID_DATABASE", raising=False)
  yield


class TestSupportedBackends:
  def test_both_backends_are_registered(self):
    assert reid_registry.supported_backends() == ["QDRANT", "VDMS"]


class TestNormalizeBackendName:
  def test_defaults_to_env_selection(self, monkeypatch):
    monkeypatch.setenv("REID_DATABASE", "QDRANT")
    assert reid_registry.normalize_backend_name() == "QDRANT"

  def test_defaults_to_vdms_when_env_unset(self):
    assert reid_registry.normalize_backend_name() == "VDMS"

  def test_explicit_name_overrides_env(self, monkeypatch):
    monkeypatch.setenv("REID_DATABASE", "QDRANT")
    assert reid_registry.normalize_backend_name("vdms") == "VDMS"

  def test_name_is_trimmed_and_uppercased(self):
    assert reid_registry.normalize_backend_name("  qdrant  ") == "QDRANT"

  def test_unknown_name_lists_supported_values(self):
    with pytest.raises(ValueError) as excinfo:
      reid_registry.normalize_backend_name("MILVUS")
    message = str(excinfo.value)
    assert "MILVUS" in message
    assert "VDMS" in message and "QDRANT" in message

  def test_unknown_env_value_is_rejected(self, monkeypatch):
    monkeypatch.setenv("REID_DATABASE", "not-a-backend")
    with pytest.raises(ValueError):
      reid_registry.normalize_backend_name()


class TestGetReidDatabaseClass:
  def test_returns_vdms_adapter(self):
    from controller.vdms_adapter import VDMSDatabase
    assert reid_registry.get_reid_database_class("VDMS") is VDMSDatabase

  def test_returns_qdrant_adapter(self):
    from controller.qdrant_adapter import QdrantDatabase
    assert reid_registry.get_reid_database_class("QDRANT") is QdrantDatabase

  def test_missing_client_library_names_the_backend(self):
    def _fail_import(module_path):
      raise ImportError("No module named 'qdrant_client'")

    with patch.object(reid_registry, 'import_module', _fail_import):
      with pytest.raises(ImportError) as excinfo:
        reid_registry.get_reid_database_class("QDRANT")
    message = str(excinfo.value)
    assert "QDRANT" in message
    assert "controller.qdrant_adapter" in message


class TestLazyImports:
  """A deployment should only load the client library of its selected backend."""

  @staticmethod
  def _clients_loaded_after(*statements):
    """Run statements in a clean interpreter; report which clients got imported."""
    script = "\n".join([
      "import sys",
      *statements,
      "print(int('qdrant_client' in sys.modules), int('vdms' in sys.modules))",
    ])
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(path for path in sys.path if path)
    result = subprocess.run(
      [sys.executable, "-c", script],
      capture_output=True, text=True, env=env, check=False)
    assert result.returncode == 0, f"subprocess failed: {result.stderr}"
    qdrant, vdms = result.stdout.split()
    return qdrant == "1", vdms == "1"

  def test_importing_registry_loads_neither_client(self):
    qdrant_loaded, vdms_loaded = self._clients_loaded_after(
      "import controller.reid_registry")
    assert not qdrant_loaded
    assert not vdms_loaded

  def test_selecting_vdms_does_not_load_qdrant_client(self):
    qdrant_loaded, vdms_loaded = self._clients_loaded_after(
      "from controller.reid_registry import get_reid_database_class",
      "get_reid_database_class('VDMS')")
    assert not qdrant_loaded
    assert vdms_loaded

  def test_selecting_qdrant_does_not_load_vdms_client(self):
    qdrant_loaded, vdms_loaded = self._clients_loaded_after(
      "from controller.reid_registry import get_reid_database_class",
      "get_reid_database_class('QDRANT')")
    assert qdrant_loaded
    assert not vdms_loaded


class TestCreateReidDatabase:
  def test_passes_kwargs_to_adapter(self):
    with patch.object(reid_registry, 'get_reid_database_class') as mock_lookup:
      reid_registry.create_reid_database("VDMS", dimensions=None, set_name="x")
    mock_lookup.assert_called_once_with("VDMS")
    mock_lookup.return_value.assert_called_once_with(dimensions=None, set_name="x")

  def test_unknown_backend_raises_before_construction(self):
    with pytest.raises(ValueError):
      reid_registry.create_reid_database("MILVUS")
