#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared Zenodo helpers for VIDETEC-2 download / extract (CC BY 4.0).

Record: https://zenodo.org/records/17799385
"""

from __future__ import annotations

import tarfile
import urllib.request
import zipfile
from pathlib import Path

ZENODO_RECORD_ID = 17799385
ZENODO_RECORD_URL = f"https://zenodo.org/records/{ZENODO_RECORD_ID}"

# Stable content URLs (resume-friendly).
ZENODO_FILES = {
  "Radar_dataset.zip": {
    "url": f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}/files/Radar_dataset.zip/content",
    "min_bytes": 1_800_000_000,
  },
  "gnss.zip": {
    "url": f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}/files/gnss.zip/content",
    "min_bytes": 3_000_000,
  },
  "runs_vru.tar.gz": {
    "url": f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}/files/runs_vru.tar.gz/content",
    "min_bytes": 4_000_000_000,
  },
}

RADAR51_H5 = "radar_dataset_51.h5"
RADAR52_H5 = "radar_dataset_52.h5"


def content_url(filename: str) -> str:
  meta = ZENODO_FILES.get(filename)
  if meta is None:
    raise KeyError(f"unknown Zenodo file {filename!r}")
  return meta["url"]


def download(url: str, dest: Path, expect_min_bytes: int = 0, log_prefix: str = "[videtec]") -> None:
  """Download ``url`` to ``dest`` with optional resume and size gate."""
  dest.parent.mkdir(parents=True, exist_ok=True)
  existing = dest.stat().st_size if dest.exists() else 0
  if expect_min_bytes and existing >= expect_min_bytes:
    print(f"{log_prefix} using cached {dest} ({existing} bytes)", flush=True)
    return
  req = urllib.request.Request(url)
  mode = "wb"
  if existing > 0:
    req.add_header("Range", f"bytes={existing}-")
    mode = "ab"
    print(f"{log_prefix} resuming {dest} from {existing}", flush=True)
  else:
    print(f"{log_prefix} downloading {url} → {dest}", flush=True)
  with urllib.request.urlopen(req, timeout=300) as resp, open(dest, mode) as out:
    if existing and getattr(resp, "status", None) == 200:
      print(f"{log_prefix} server ignored Range; restarting", flush=True)
      out.close()
      dest.unlink()
      return download(url, dest, expect_min_bytes=0, log_prefix=log_prefix)
    n = existing
    while True:
      chunk = resp.read(1 << 20)
      if not chunk:
        break
      out.write(chunk)
      n += len(chunk)
      if n % (50 << 20) < (1 << 20):
        print(f"{log_prefix}   {n / 1e9:.2f} GB", flush=True)
  size = dest.stat().st_size
  print(f"{log_prefix} download done ({size} bytes)", flush=True)
  if expect_min_bytes and size < expect_min_bytes:
    raise SystemExit(
      f"{log_prefix} {dest} too small ({size} < {expect_min_bytes}); delete and retry")


def download_zenodo_file(filename: str, dest_dir: Path, log_prefix: str = "[videtec]") -> Path:
  meta = ZENODO_FILES[filename]
  dest = dest_dir / filename
  download(meta["url"], dest, expect_min_bytes=meta["min_bytes"], log_prefix=log_prefix)
  return dest


def extract_zip(zip_path: Path, dest_dir: Path, members: list[str] | None = None,
                log_prefix: str = "[videtec]", *, flatten: bool = False,
                strip_prefix: str = "") -> None:
  """Extract zip members into ``dest_dir``.

  - ``flatten``: write each file as ``dest_dir / basename`` (Radar_dataset.zip).
  - ``strip_prefix``: drop a leading archive path prefix (gnss.zip → ``gnss/``).
  """
  dest_dir.mkdir(parents=True, exist_ok=True)
  with zipfile.ZipFile(zip_path) as zf:
    names = members if members is not None else zf.namelist()
    for name in names:
      if name.endswith("/"):
        continue
      rel = name
      if strip_prefix and rel.startswith(strip_prefix):
        rel = rel[len(strip_prefix):]
      if not rel:
        continue
      target = dest_dir / (Path(name).name if flatten else rel)
      info = zf.getinfo(name)
      if target.is_file() and target.stat().st_size == info.file_size:
        continue
      target.parent.mkdir(parents=True, exist_ok=True)
      print(f"{log_prefix} extracting {name} → {target}", flush=True)
      with zf.open(info) as src, open(target, "wb") as out:
        while True:
          chunk = src.read(1 << 20)
          if not chunk:
            break
          out.write(chunk)


def extract_tar_member(outer: Path, member: str, dest_dir: Path) -> Path:
  dest_dir.mkdir(parents=True, exist_ok=True)
  out_path = dest_dir / Path(member).name
  if out_path.exists() and out_path.stat().st_size > 0:
    return out_path
  print(f"[videtec] extracting {member}", flush=True)
  with tarfile.open(outer, "r:gz") as tf:
    m = tf.getmember(member)
    m.name = Path(m.name).name
    tf.extract(m, path=dest_dir)
  return dest_dir / Path(member).name
