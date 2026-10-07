# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Model loading must work on an air-gapped node with seeded caches."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import mapanything_model as mm  # noqa: E402


class _Hub:
  calls = []

  @classmethod
  def from_pretrained(cls, name, **kwargs):
    cls.calls.append(kwargs)
    if kwargs.get("local_files_only") and not getattr(cls, "cached", True):
      raise FileNotFoundError("not in cache")
    return "model"


@pytest.fixture
def hub(monkeypatch):
  monkeypatch.setattr(mm, "pin_cached_torch_hub_refs", lambda: None)
  _Hub.calls = []
  _Hub.cached = True
  return _Hub


def test_cached_weights_never_touch_the_network(monkeypatch, hub):
  monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
  assert mm.load_from_cache_first(_Hub, "facebook/x") == "model"
  assert _Hub.calls == [{"local_files_only": True}]


def test_cache_miss_downloads_when_online(monkeypatch, hub):
  monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
  _Hub.cached = False
  assert mm.load_from_cache_first(_Hub, "facebook/x") == "model"
  assert _Hub.calls == [{"local_files_only": True}, {}]


def test_cache_miss_fails_fast_when_offline_forced(monkeypatch, hub):
  monkeypatch.setenv("HF_HUB_OFFLINE", "1")
  _Hub.cached = False
  with pytest.raises(RuntimeError, match="HF_HUB_OFFLINE"):
    mm.load_from_cache_first(_Hub, "facebook/x")
  assert _Hub.calls == [{"local_files_only": True}]


def test_torch_hub_ref_pinned_to_cached_checkout(monkeypatch, tmp_path):
  torch_hub = pytest.importorskip("torch.hub")
  (tmp_path / "facebookresearch_dinov2_main").mkdir()
  monkeypatch.setattr(torch_hub, "get_dir", lambda: str(tmp_path))
  seen = {}

  def fake_load(repo, *a, **k):
    seen["repo"] = repo
    return "m"

  monkeypatch.setattr(torch_hub, "load", fake_load)
  mm.pin_cached_torch_hub_refs()
  assert torch_hub.load("facebookresearch/dinov2", "dinov2_vitg14") == "m"
  assert seen["repo"] == "facebookresearch/dinov2:main"
  # Explicit refs and uncached repos pass through untouched.
  torch_hub.load("facebookresearch/dinov2:v1", "x")
  assert seen["repo"] == "facebookresearch/dinov2:v1"
  torch_hub.load("someone/other", "x")
  assert seen["repo"] == "someone/other"
