# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Import existing person identity annotations without generating pseudo-labels."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

from tools.reid_evaluation.evaluate import SPLITS
from tools.reid_evaluation.inference import file_sha256


def _sample(name: str, key: str, identity: str, camera: str,
            split: str, image: Path) -> dict:
  sample_id = hashlib.sha256(json.dumps([name, key]).encode("utf-8")).hexdigest()
  return {"id": sample_id, "identity": f"{name}:{identity}", "camera": f"{name}:{camera}",
          "split": split, "image": str(image.resolve())}


def import_market1501(root: Path) -> dict:
  """Import official query/gallery folders; ignore training data and junk PID -1."""
  root = root.resolve()
  samples = []
  excluded = 0
  pattern = re.compile(r"(-1|\d{4})_c([1-6])s\d+_\d+_\d+\.jpg", re.IGNORECASE)
  for folder, split in (("bounding_box_test", "gallery"), ("query", "test")):
    directory = root / folder
    if not directory.is_dir():
      raise ValueError(f"Missing Market-1501 directory: {directory}")
    images = sorted(path for path in directory.iterdir() if path.suffix.lower() == ".jpg")
    if not images:
      raise ValueError(f"No JPEG crops in {directory}")
    for image in images:
      match = pattern.fullmatch(image.name)
      if not match:
        raise ValueError(f"Invalid Market-1501 filename: {image.name}")
      identity, camera = match.groups()
      if identity == "-1":
        excluded += 1
        continue
      if split == "test" and int(identity) == 0:
        raise ValueError(f"Market-1501 query cannot use distractor identity 0: {image.name}")
      samples.append(_sample("market1501", f"{folder}/{image.name}", str(int(identity)),
                             camera, split, image))
  return {"dataset": {
    "name": "market1501", "source": "dataset-provided filename annotations",
    "importer": "market1501", "excluded_junk_samples": excluded,
    "protocol": "SceneScape evaluator; not the official Market-1501 scoring protocol",
    "notes": [
      "Training images are not imported. Gallery PID 0 distractors are retained.",
      "Default scoring excludes all same-camera gallery images, including other identities; "
      "official Market-1501 excludes same-identity/same-camera matches instead.",
      "No calibration split is inferred. Unknown identities are not synthesized.",
    ],
  }, "samples": samples}


def import_csv(annotations: Path, name: str) -> dict:
  """Import image, identity, camera, split columns; resolve images relative to the CSV."""
  if not name.strip():
    raise ValueError("Dataset name must not be empty")
  annotations = annotations.resolve()
  samples = []
  with annotations.open(newline="", encoding="utf-8-sig") as stream:
    reader = csv.DictReader(stream)
    required = {"image", "identity", "camera", "split"}
    if not reader.fieldnames or not required <= set(reader.fieldnames):
      raise ValueError("Annotations CSV requires image, identity, camera, split columns")
    for line, row in enumerate(reader, 2):
      if None in row or any(value is None for value in row.values()):
        raise ValueError(f"Malformed annotations CSV row {line}")
      values = {key: row[key].strip() for key in required}
      if not all(values.values()) or values["split"] not in SPLITS:
        raise ValueError(f"Row {line} requires non-empty labels and gallery/calibration/test split")
      image = (annotations.parent / values["image"]).resolve()
      key = row.get("id", "").strip() or values["image"]
      sample = _sample(name, key, values["identity"], values["camera"], values["split"], image)
      if row.get("track_id", "").strip():
        sample["track_id"] = row["track_id"].strip()
      samples.append(sample)
  return {"dataset": {"name": name, "source": "dataset-provided CSV annotations",
                      "importer": "csv", "annotations_sha256": file_sha256(annotations)},
          "samples": samples}


def write_manifest(manifest: dict, output: Path) -> dict:
  """Validate imported annotations and write a new manifest without overwriting existing data."""
  samples = manifest["samples"]
  counts = Counter(sample["split"] for sample in samples)
  if not counts["gallery"] or not counts["test"]:
    raise ValueError("Imported dataset must contain gallery and test samples")
  seen_ids = set()
  seen_images = set()
  for sample in samples:
    if sample["id"] in seen_ids:
      raise ValueError("Duplicate sample ID in imported annotations")
    seen_ids.add(sample["id"])
    image = Path(sample["image"])
    if not image.is_file():
      raise ValueError(f"Crop image does not exist: {image}")
    if image in seen_images:
      raise ValueError(f"Repeated crop image in imported annotations: {image}")
    seen_images.add(image)
  calibration = {s["identity"] for s in samples if s["split"] == "calibration"}
  test = {s["identity"] for s in samples if s["split"] == "test"}
  if calibration & test:
    raise ValueError("Calibration and test query identities must be disjoint")
  manifest["dataset"]["samples_by_split"] = dict(counts)
  output.parent.mkdir(parents=True, exist_ok=True)
  with output.open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
  return {"manifest": str(output), "samples": len(samples), "samples_by_split": dict(counts),
          "dataset": manifest["dataset"]}


def main(argv=None) -> int:
  """Convert a locally obtained labeled dataset into evaluator input."""
  parser = argparse.ArgumentParser(description=__doc__)
  commands = parser.add_subparsers(dest="format", required=True)
  market = commands.add_parser("market1501", help="Import query and bounding_box_test folders")
  market.add_argument("--root", type=Path, required=True)
  market.add_argument("--output", type=Path, required=True)
  labeled = commands.add_parser("csv", help="Import existing image/identity/camera/split annotations")
  labeled.add_argument("--annotations", type=Path, required=True)
  labeled.add_argument("--name", required=True, help="Stable dataset namespace")
  labeled.add_argument("--output", type=Path, required=True)
  args = parser.parse_args(argv)
  try:
    manifest = (import_market1501(args.root) if args.format == "market1501"
                else import_csv(args.annotations, args.name))
    result = write_manifest(manifest, args.output)
  except (ValueError, OSError, csv.Error) as error:
    parser.error(str(error))
  print(json.dumps(result, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
