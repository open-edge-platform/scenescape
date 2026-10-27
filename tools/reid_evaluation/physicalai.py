# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Extract a closed-set cross-camera ReID dataset from PhysicalAI ground truth."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path

from tools.reid_evaluation.datasets import _sample, write_manifest
from tools.reid_evaluation.inference import file_sha256


def _field(obj: dict, name: str):
  spaced = name.replace("_", " ")
  if name in obj and spaced in obj:
    raise ValueError(f"Ambiguous annotation fields: {name} and {spaced}")
  return obj[name] if name in obj else obj.get(spaced)


def _observations(ground_truth: dict, cameras: dict, object_type: str,
                  frame_step: int, max_frames: int) -> list:
  if not isinstance(ground_truth, dict) or not ground_truth:
    raise ValueError("Ground truth must be a non-empty frame-ID object")
  if any(not isinstance(key, str) or not key.isdecimal() for key in ground_truth):
    raise ValueError("Ground-truth frame IDs must be non-negative integer strings")
  frames = sorted((int(key), key) for key in ground_truth)
  if len({number for number, _ in frames}) != len(frames):
    raise ValueError("Ground truth contains duplicate numeric frame IDs")
  observations = []
  for frame, key in [item for item in frames if item[0] % frame_step == 0][:max_frames]:
    objects = ground_truth[key]
    if not isinstance(objects, list):
      raise ValueError(f"Ground-truth frame {key} must contain an object list")
    seen = set()
    for obj in objects:
      if not isinstance(obj, dict) or not isinstance(_field(obj, "object_type"), str):
        raise ValueError(f"Malformed object at frame {key}")
      if _field(obj, "object_type") != object_type:
        continue
      identity = _field(obj, "object_id")
      if isinstance(identity, bool) or not isinstance(identity, int) or identity < 0:
        raise ValueError(f"Invalid object_id at frame {key}")
      if identity in seen:
        raise ValueError(f"Duplicate object_id {identity} at frame {key}")
      seen.add(identity)
      boxes = _field(obj, "2d_bounding_box_visible")
      if not isinstance(boxes, dict):
        raise ValueError(f"Missing visible bounding boxes at frame {key}")
      for camera, box in boxes.items():
        if camera not in cameras:
          continue
        if (not isinstance(box, list) or len(box) != 4
            or any(isinstance(v, bool) or not isinstance(v, (int, float))
                   or not math.isfinite(v) for v in box)
            or box[2] <= box[0] or box[3] <= box[1]):
          raise ValueError(f"Invalid bounding box for camera {camera}, frame {key}")
        observations.append({"frame": frame, "identity": identity, "camera": camera, "box": box})
  if not observations:
    raise ValueError(f"No sampled {object_type!r} observations match the supplied cameras")
  return observations


def export_physicalai(args: argparse.Namespace) -> dict:
  """Crop annotated videos using explicit camera mapping and deterministic split rules."""
  try:
    import cv2
  except ImportError as error:
    raise ValueError("Install requirements-crops.txt for OpenCV video decoding") from error
  if not args.scene.strip() or not args.object_type.strip():
    raise ValueError("Scene namespace and object type must be non-empty")
  if (args.frame_step <= 0 or args.max_frames <= 0 or args.query_gap_frames < 0
      or not math.isfinite(args.minimum_area) or args.minimum_area < 0):
    raise ValueError("Invalid frame sampling, query gap, or minimum area")
  if args.output.exists():
    raise ValueError("Output already exists; choose a new directory")
  mapping_path = args.videos.resolve()
  mapping = json.loads(mapping_path.read_text())
  if (not isinstance(mapping, dict) or len(mapping) < 2
      or any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
             for k, v in mapping.items())):
    raise ValueError("Video mapping must contain at least two camera IDs and video paths")
  cameras = {camera: (mapping_path.parent / path).resolve() for camera, path in mapping.items()}
  if args.gallery_camera not in cameras:
    raise ValueError("Gallery camera must be present in the video mapping")
  for video in cameras.values():
    if not video.is_file():
      raise ValueError(f"Missing camera video: {video}")
  if len(set(cameras.values())) != len(cameras):
    raise ValueError("Each camera must reference a different video")
  observations = _observations(json.loads(args.ground_truth.read_text()), cameras,
                               args.object_type, args.frame_step, args.max_frames)
  provenance = {
    "ground_truth_sha256": file_sha256(args.ground_truth),
    "videos_sha256": {camera: file_sha256(path) for camera, path in cameras.items()},
  }
  args.output.mkdir(parents=True, mode=0o700)
  (args.output / "crops").mkdir()
  candidates = []
  excluded = Counter()
  for camera, video in sorted(cameras.items()):
    capture = cv2.VideoCapture(str(video))
    try:
      if not capture.isOpened():
        raise ValueError(f"Cannot open video for camera {camera}")
      current_frame = -1
      decoded_frame = -1
      frame = None
      for observation in (item for item in observations if item["camera"] == camera):
        target = observation["frame"]
        while current_frame < target:
          if not capture.grab():
            raise ValueError(f"Video ended before annotated frame {target}, camera {camera}")
          current_frame += 1
        if frame is None or decoded_frame != target:
          success, frame = capture.retrieve()
          if not success or frame is None:
            raise ValueError(f"Cannot decode frame {target}, camera {camera}")
          decoded_frame = target
        height, width = frame.shape[:2]
        box = observation["box"]
        left, top = max(0, math.floor(box[0])), max(0, math.floor(box[1]))
        right, bottom = min(width, math.ceil(box[2])), min(height, math.ceil(box[3]))
        if right <= left or bottom <= top or (right - left) * (bottom - top) < args.minimum_area:
          excluded["small_or_outside_box"] += 1
          continue
        sample = _sample(
          args.scene, f"{camera}/{target}/{observation['identity']}",
          str(observation["identity"]), camera, "test", args.output / "unused.png")
        sample.update(frame=target, bounding_box=[left, top, right, bottom])
        image = args.output / "crops" / f"{sample['id']}.png"
        if not cv2.imwrite(str(image), frame[top:bottom, left:right]):
          raise OSError(f"Cannot save crop: {image}")
        sample["image"] = str(image.resolve())
        candidates.append(sample)
    finally:
      capture.release()
  gallery = {}
  gallery_camera = f"{args.scene}:{args.gallery_camera}"
  for sample in candidates:
    if sample["camera"] == gallery_camera:
      gallery.setdefault(sample["identity"], sample)
  samples = []
  for sample in candidates:
    reference = gallery.get(sample["identity"])
    if sample is reference:
      sample["split"] = "gallery"
      samples.append(sample)
    elif reference is None:
      excluded["identity_without_gallery"] += 1
    elif sample["camera"] == gallery_camera:
      excluded["extra_gallery_camera_observation"] += 1
    elif sample["frame"] < reference["frame"] + args.query_gap_frames:
      excluded["query_before_gap"] += 1
    else:
      samples.append(sample)
  manifest = {"dataset": {
    "name": args.scene, "source": "NVIDIA PhysicalAI-SmartSpaces ground-truth annotations",
    "source_url": "https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces",
    "license": "CC-BY-4.0", "importer": "physicalai-json-2025-2026", **provenance,
    "protocol": "closed-set crop retrieval, not official HOTA tracking evaluation",
    "gallery_camera": args.gallery_camera, "object_type": args.object_type,
    "frame_step": args.frame_step, "max_sampled_frames": args.max_frames,
    "query_gap_frames": args.query_gap_frames, "minimum_area": args.minimum_area,
    "excluded_observations": dict(excluded),
    "notes": ["One earliest valid gallery crop per identity; other-camera queries after the gap.",
              "Unenrolled identities excluded; unknown false-accept rate is not measurable.",
              "Requires synchronized videos with annotation frame 0 matching video frame 0.",
              "Failed exports may leave partial crops; retry with a new output directory."],
  }, "samples": samples}
  return write_manifest(manifest, args.output / "manifest.json")


def main(argv=None) -> int:
  """Export one locally obtained PhysicalAI scene without manual identity labeling."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--ground-truth", type=Path, required=True)
  parser.add_argument("--videos", type=Path, required=True, help="JSON camera-ID to video-path mapping")
  parser.add_argument("--scene", required=True, help="Unique edition/scene namespace")
  parser.add_argument("--gallery-camera", required=True)
  parser.add_argument("--object-type", default="Person", help="Exact annotation class name")
  parser.add_argument("--frame-step", type=int, default=30)
  parser.add_argument("--max-frames", type=int, default=100)
  parser.add_argument("--query-gap-frames", type=int, default=30)
  parser.add_argument("--minimum-area", type=float, default=5000)
  parser.add_argument("--output", type=Path, required=True)
  args = parser.parse_args(argv)
  try:
    result = export_physicalai(args)
  except (ValueError, OSError) as error:
    parser.error(str(error))
  print(json.dumps(result, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
