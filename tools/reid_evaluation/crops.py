# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Export detector-assisted person crops and convert human-reviewed labels to an evaluation manifest."""

import argparse
import csv
import json
import math
from pathlib import Path
import re

import numpy as np

from tools.reid_evaluation.inference import file_sha256

REVIEW_FIELDS = ["id", "image", "camera", "identity", "split", "include", "frame",
                 "timestamp_seconds", "confidence", "x", "y", "width", "height"]


def person_boxes(output, width, height, confidence=0.7, minimum_area=5000, person_label=1):
  """Decode normalized SSD [image, label, score, xmin, ymin, xmax, ymax] output."""
  if not 0 <= confidence <= 1 or minimum_area < 0 or width <= 0 or height <= 0:
    raise ValueError("Invalid detection thresholds or frame size")
  values = np.asarray(output)
  if values.ndim < 2 or values.shape[-1] != 7:
    raise ValueError(
        "Detector must have SSD output with seven values per detection; YOLO is not supported")
  boxes = []
  for row in values.reshape(-1, 7):
    if not np.isfinite(row).all() or row[0] < 0 or row[1] != person_label or row[2] < confidence:
      continue
    left = max(0, min(width, math.floor(float(row[3]) * width)))
    top = max(0, min(height, math.floor(float(row[4]) * height)))
    right = max(0, min(width, math.ceil(float(row[5]) * width)))
    bottom = max(0, min(height, math.ceil(float(row[6]) * height)))
    if right <= left or bottom <= top or (right - left) * (bottom - top) < minimum_area:
      continue
    boxes.append({"x": left, "y": top, "width": right - left, "height": bottom - top,
                  "confidence": float(row[2])})
  return boxes


def _contact_sheet(rows, output, page):
  from PIL import Image, ImageDraw, ImageOps

  columns, tile_width, tile_height = 5, 160, 280
  sheet = Image.new("RGB", (columns * tile_width,
                    math.ceil(len(rows) / columns) * tile_height), "white")
  draw = ImageDraw.Draw(sheet)
  for index, row in enumerate(rows):
    left, top = (index % columns) * tile_width, (index // columns) * tile_height
    with Image.open(output / row["image"]) as image:
      image = ImageOps.contain(image, (tile_width - 12, tile_height - 42))
      sheet.paste(image, (left + (tile_width - image.width) // 2, top + 4))
    draw.text((left + 4, top + tile_height - 34), row["id"], fill="black")
    draw.text((left + 4, top + tile_height - 18),
              f"t={row['timestamp_seconds']:.2f}s", fill="black")
  sheet.save(output / f"contact-sheet-{page:03d}.jpg", quality=90)


def export_crops(args):
  """Run a local SSD person detector; never assign ground-truth identity or split automatically."""
  try:
    import cv2
    import openvino as ov
  except ImportError as error:
    raise ValueError(
        "Install requirements-crops.txt for OpenCV video decoding and OpenVINO") from error
  if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", args.camera):
    raise ValueError(
        "Camera ID must use 1-128 letters, digits, dots, underscores, colons, or hyphens")
  numeric = [args.every_seconds, args.start_seconds, args.confidence, args.minimum_area]
  if not all(math.isfinite(value) for value in numeric):
    raise ValueError("Sampling and detection parameters must be finite")
  if args.every_seconds <= 0 or args.start_seconds < 0 or args.max_frames <= 0:
    raise ValueError("Sampling interval/max frames must be positive and start time non-negative")
  if not 0 <= args.confidence <= 1 or args.minimum_area < 0 or args.person_label < 0:
    raise ValueError("Invalid confidence, area, or person label")
  video = args.video.resolve()
  detector = args.detector.resolve()
  if not video.is_file() or detector.suffix.lower() != ".xml":
    raise ValueError("Provide an existing video and an OpenVINO SSD IR .xml detector")
  hashes = {"video_sha256": file_sha256(video), "detector_xml_sha256": file_sha256(detector),
            "detector_bin_sha256": file_sha256(detector.with_suffix(".bin"))}
  if args.output.exists():
    raise ValueError("Crop output already exists; use a new directory")
  compiled = ov.Core().compile_model(str(detector), args.device)
  if len(compiled.inputs) != 1 or len(compiled.outputs) != 1:
    raise ValueError("Only single-input, single-output SSD detectors are supported")
  input_port = compiled.input(0)
  shape = tuple(input_port.shape)
  if len(shape) != 4 or shape[:2] != (1, 3):
    raise ValueError("Detector must use static batch-one NCHW BGR input")
  request = compiled.create_infer_request()
  capture = cv2.VideoCapture(str(video))
  if not capture.isOpened():
    raise ValueError("OpenCV could not open the video")
  try:
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(fps) or fps <= 0:
      raise ValueError("Video has no usable FPS; timestamps cannot be inferred")
    first = round(args.start_seconds * fps)
    stride = max(1, round(args.every_seconds * fps))
    args.output.mkdir(parents=True, mode=0o700)
    (args.output / "crops").mkdir()
    rows = []
    sampled_frames = 0
    capture.set(cv2.CAP_PROP_POS_FRAMES, first)
    frame_index = first
    while sampled_frames < args.max_frames:
      if not capture.grab():
        break
      if (frame_index - first) % stride:
        frame_index += 1
        continue
      success, frame = capture.retrieve()
      if not success or frame is None:
        raise ValueError(f"Could not decode video frame {frame_index}")
      resized = cv2.resize(frame, (shape[3], shape[2]), interpolation=cv2.INTER_LINEAR)
      tensor = np.ascontiguousarray(resized.transpose(
          2, 0, 1)[None], dtype=input_port.element_type.to_dtype())
      result = request.infer({input_port: tensor})[compiled.output(0)]
      boxes = person_boxes(result, frame.shape[1], frame.shape[0], args.confidence,
                           args.minimum_area, args.person_label)
      for index, box in enumerate(boxes):
        sample_id = f"f{frame_index:07d}-p{index:02d}"
        image = f"crops/{sample_id}.png"
        left, top = box["x"], box["y"]
        crop = frame[top:top + box["height"], left:left + box["width"]]
        if not cv2.imwrite(str(args.output / image), crop):
          raise OSError(f"Could not save crop {sample_id}")
        rows.append({"id": sample_id, "image": image, "camera": args.camera,
                     "identity": "", "split": "", "include": "yes", "frame": frame_index,
                     "timestamp_seconds": frame_index / fps, **box})
      sampled_frames += 1
      frame_index += 1
  finally:
    capture.release()
  with (args.output / "review.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
  for start in range(0, len(rows), 25):
    _contact_sheet(rows[start:start + 25], args.output, start // 25)
  summary = {"status": "needs_human_identity_and_split_labels", "video": video.name,
             "camera": args.camera, "sampled_frames": sampled_frames, "crop_count": len(rows),
             "fps": fps, "every_seconds": args.every_seconds, "start_seconds": args.start_seconds,
             "confidence_threshold": args.confidence, "minimum_area": args.minimum_area,
             "detector": detector.name, "device": args.device, **hashes,
             "note": "Detection proposals are not identity ground truth; timestamps use frame_index/FPS."}
  (args.output / "export.json").write_text(json.dumps(summary, indent=2) + "\n")
  return summary


def reviewed_manifest(review_csv, output):
  """Create an evaluator manifest only after retained crops have explicit human labels."""
  if output.exists():
    raise ValueError("Manifest output already exists")
  review_csv = review_csv.resolve()
  rows = []
  seen = set()
  with review_csv.open(newline="", encoding="utf-8-sig") as stream:
    reader = csv.DictReader(stream)
    if not reader.fieldnames or not set(REVIEW_FIELDS) <= set(reader.fieldnames):
      raise ValueError("Use the review.csv generated by the crop exporter")
    for row in reader:
      if None in row or any(value is None for value in row.values()):
        raise ValueError("Malformed review CSV row; preserve all exported columns")
      include = row["include"].strip().lower()
      if include in {"no", "false", "0"}:
        continue
      if include not in {"yes", "true", "1"}:
        raise ValueError("Every row must explicitly set include=yes or include=no")
      identity, split = row["identity"].strip(), row["split"].strip()
      if not identity or split not in {"gallery", "calibration", "test"}:
        raise ValueError(f"Crop {row['id']} needs an identity and gallery/calibration/test split")
      if not row["id"].strip() or row["id"] in seen or not row["camera"].strip():
        raise ValueError("Crop IDs must be unique and camera IDs non-empty")
      seen.add(row["id"])
      image = (review_csv.parent / row["image"]).resolve()
      if not image.is_file():
        raise ValueError(f"Crop image is missing for {row['id']}")
      rows.append({"id": row["id"], "identity": identity, "camera": row["camera"],
                   "split": split, "image": str(image)})
  if not rows or not any(row["split"] == "gallery" for row in rows) or not any(
          row["split"] == "test" for row in rows):
    raise ValueError("Reviewed crops must include gallery and test samples")
  manifest = {"dataset": {"name": review_csv.parent.name, "source": "human-reviewed detector crops"},
              "samples": rows}
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(manifest, indent=2) + "\n")
  return {"manifest": str(output), "samples": len(rows),
          "single_camera": len({row["camera"] for row in rows}) == 1,
          "note": "Single-camera evaluation requires --allow-same-camera; use separated times/tracklets."}


def main(argv=None):
  """Run crop export or reviewed-label conversion without modifying a live stack."""
  parser = argparse.ArgumentParser(description=__doc__)
  commands = parser.add_subparsers(dest="command", required=True)
  export = commands.add_parser(
      "export", help="Detect people and save crops/contact sheets for review")
  export.add_argument("--video", type=Path, required=True)
  export.add_argument("--detector", type=Path, required=True)
  export.add_argument("--camera", required=True)
  export.add_argument("--output", type=Path, required=True)
  export.add_argument("--device", default="CPU")
  export.add_argument("--every-seconds", type=float, default=2.0)
  export.add_argument("--start-seconds", type=float, default=0.0)
  export.add_argument("--max-frames", type=int, default=100)
  export.add_argument("--confidence", type=float, default=0.7)
  export.add_argument("--minimum-area", type=float, default=5000)
  export.add_argument("--person-label", type=int, default=1)
  review = commands.add_parser("manifest", help="Convert human-reviewed CSV into evaluator input")
  review.add_argument("--review-csv", type=Path, required=True)
  review.add_argument("--output", type=Path, required=True)
  args = parser.parse_args(argv)
  try:
    result = export_crops(args) if args.command == "export" else reviewed_manifest(
        args.review_csv, args.output)
  except (ValueError, TypeError, OSError, RuntimeError) as error:
    parser.error(str(error))
  print(json.dumps(result, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
