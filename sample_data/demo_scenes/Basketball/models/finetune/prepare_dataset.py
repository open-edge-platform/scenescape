#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Sample Basketball demo frames and teacher-label person + basketball.

Default teacher is Grounding DINO (text → boxes), not YOLO-World: open-vocab
detectors that already fail on this footage must not define the fine-tune
labels. SAM3 is a strong alternative when HF-gated weights + CUDA are
available; use --teacher sam3 then.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


CLASSES = ["person", "basketball"]


def nms_class_aware(boxes, scores, classes, iou_thr=0.45):
  """Per-class NMS (xyxy + score + cls)."""
  keep = []
  for cls in np.unique(classes):
    idx = np.where(classes == cls)[0]
    if idx.size == 0:
      continue
    b, s = boxes[idx], scores[idx]
    order = s.argsort()[::-1]
    while order.size:
      i = order[0]
      keep.append(int(idx[i]))
      if order.size == 1:
        break
      rest = order[1:]
      xx1 = np.maximum(b[i, 0], b[rest, 0])
      yy1 = np.maximum(b[i, 1], b[rest, 1])
      xx2 = np.minimum(b[i, 2], b[rest, 2])
      yy2 = np.minimum(b[i, 3], b[rest, 3])
      inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
      area_i = (b[i, 2] - b[i, 0]) * (b[i, 3] - b[i, 1])
      area_r = (b[rest, 2] - b[rest, 0]) * (b[rest, 3] - b[rest, 1])
      iou = inter / (area_i + area_r - inter + 1e-9)
      order = rest[iou <= iou_thr]
  return keep


def sample_frames(video: Path, out_dir: Path, stride: int, prefix: str) -> list[Path]:
  out_dir.mkdir(parents=True, exist_ok=True)
  cap = cv2.VideoCapture(str(video))
  if not cap.isOpened():
    raise FileNotFoundError(video)
  paths = []
  idx = 0
  saved = 0
  while True:
    ok, frame = cap.read()
    if not ok:
      break
    if idx % stride == 0:
      path = out_dir / f"{prefix}_f{idx:05d}.jpg"
      cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
      paths.append(path)
      saved += 1
    idx += 1
  cap.release()
  print(f"sampled {saved} frames from {video.name} (stride={stride})")
  return paths


def _write_yolo_labels(img_path: Path, labels_dir: Path, xyxy, scores, cls,
                       thr_person: float, thr_ball: float) -> tuple[int, int]:
  h, w = cv2.imread(str(img_path)).shape[:2]
  if len(cls) == 0:
    (labels_dir / f"{img_path.stem}.txt").write_text("")
    return 0, 0
  mask = np.zeros(len(cls), dtype=bool)
  for i, c in enumerate(cls):
    thr = thr_person if int(c) == 0 else thr_ball
    mask[i] = float(scores[i]) >= thr
  xyxy, scores, cls = xyxy[mask], scores[mask], cls[mask]
  if len(cls) == 0:
    (labels_dir / f"{img_path.stem}.txt").write_text("")
    return 0, 0
  keep = nms_class_aware(xyxy, scores, cls, iou_thr=0.45)
  lines = []
  n_person = n_ball = 0
  for i in keep:
    x1, y1, x2, y2 = map(float, xyxy[i])
    cw = max(1e-6, x2 - x1)
    ch = max(1e-6, y2 - y1)
    cx = (x1 + x2) / 2.0 / w
    cy = (y1 + y2) / 2.0 / h
    c = int(cls[i])
    if c not in (0, 1):
      continue
    lines.append(f"{c} {cx:.6f} {cy:.6f} {cw / w:.6f} {ch / h:.6f}")
    if c == 0:
      n_person += 1
    else:
      n_ball += 1
  (labels_dir / f"{img_path.stem}.txt").write_text(
    ("\n".join(lines) + ("\n" if lines else "")))
  return n_person, n_ball


def teacher_grounding_dino(images: list[Path], labels_dir: Path, *,
                           model_id: str, thr_person: float, thr_ball: float,
                           device: str):
  """Text-prompted boxes via Grounding DINO (transformers)."""
  import torch
  from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

  labels_dir.mkdir(parents=True, exist_ok=True)
  processor = AutoProcessor.from_pretrained(model_id)
  model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)
  model.eval()

  # GDINO prefers lowercase phrases; trailing period helps some checkpoints.
  text_labels = [["person", "basketball"]]
  n_person = n_ball = 0
  for img_path in images:
    image = Image.open(img_path).convert("RGB")
    inputs = processor(images=image, text=text_labels, return_tensors="pt")
    inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
    with torch.no_grad():
      outputs = model(**inputs)
    # Low box threshold; per-class gates applied in _write_yolo_labels.
    result = processor.post_process_grounded_object_detection(
      outputs,
      inputs["input_ids"],
      threshold=min(thr_person, thr_ball),
      text_threshold=min(thr_person, thr_ball),
      target_sizes=[(image.height, image.width)],
    )[0]
    boxes = result["boxes"].detach().cpu().numpy()
    scores = result["scores"].detach().cpu().numpy()
    raw_labels = result.get("labels", result.get("text_labels", []))
    cls = []
    for lab in raw_labels:
      name = str(lab).strip().lower()
      if "person" in name or name == "0":
        cls.append(0)
      elif "basket" in name or "ball" in name or name == "1":
        cls.append(1)
      else:
        cls.append(-1)
    cls = np.asarray(cls, dtype=int)
    valid = cls >= 0
    p, b = _write_yolo_labels(
      img_path, labels_dir, boxes[valid], scores[valid], cls[valid],
      thr_person, thr_ball)
    n_person += p
    n_ball += b
  print(f"Grounding DINO ({model_id}) boxes: person={n_person} basketball={n_ball}")


def teacher_sam3(images: list[Path], labels_dir: Path, *,
                 thr_person: float, thr_ball: float, device: str):
  """Optional SAM3 text prompts → mask boxes (needs HF access to facebook/sam3 + CUDA)."""
  try:
    from sam3.model_builder import build_sam3_image_model
    from sam3.model.sam3_image_processor import Sam3Processor
  except ImportError as exc:
    raise SystemExit(
      "sam3 not importable. Install facebookresearch/sam3 and request "
      "HF access to facebook/sam3 (gated). On this host prefer "
      "--teacher grounding-dino."
    ) from exc

  labels_dir.mkdir(parents=True, exist_ok=True)
  model = build_sam3_image_model()
  processor = Sam3Processor(model, device=device)
  n_person = n_ball = 0
  for img_path in images:
    image = Image.open(img_path).convert("RGB")
    boxes_all = []
    scores_all = []
    cls_all = []
    for cidx, prompt in enumerate(CLASSES):
      state = processor.set_image(image)
      processor.set_text_prompt(prompt=prompt, state=state)
      # Expected keys vary by sam3 version; be defensive.
      boxes = np.asarray(state.get("boxes", state.get("pred_boxes", [])), dtype=np.float64)
      scores = np.asarray(state.get("scores", state.get("pred_scores", [])), dtype=np.float64)
      if boxes.size == 0:
        continue
      if boxes.ndim == 1:
        boxes = boxes.reshape(1, -1)
      if scores.ndim == 0:
        scores = np.full((boxes.shape[0],), float(scores))
      boxes_all.append(boxes)
      scores_all.append(scores)
      cls_all.append(np.full((boxes.shape[0],), cidx, dtype=int))
    if not boxes_all:
      (labels_dir / f"{img_path.stem}.txt").write_text("")
      continue
    p, b = _write_yolo_labels(
      img_path, labels_dir,
      np.concatenate(boxes_all, axis=0),
      np.concatenate(scores_all, axis=0),
      np.concatenate(cls_all, axis=0),
      thr_person, thr_ball)
    n_person += p
    n_ball += b
  print(f"SAM3 boxes: person={n_person} basketball={n_ball}")


def write_data_yaml(dataset_root: Path) -> Path:
  yaml_path = dataset_root / "data.yaml"
  yaml_path.write_text(
    "\n".join([
      f"path: {dataset_root.resolve()}",
      "train: images/train",
      "val: images/val",
      "names:",
      "  0: person",
      "  1: basketball",
      "",
    ])
  )
  return yaml_path


def split_train_val(images: list[Path], images_train: Path, images_val: Path,
                    labels_src: Path, labels_train: Path, labels_val: Path,
                    val_frac: float, seed: int):
  rng = np.random.default_rng(seed)
  order = np.arange(len(images))
  rng.shuffle(order)
  n_val = max(1, int(round(len(images) * val_frac))) if len(images) > 1 else 0
  val_set = set(int(i) for i in order[:n_val])
  images_train.mkdir(parents=True, exist_ok=True)
  images_val.mkdir(parents=True, exist_ok=True)
  labels_train.mkdir(parents=True, exist_ok=True)
  labels_val.mkdir(parents=True, exist_ok=True)
  for i, src in enumerate(images):
    dst_img = images_val if i in val_set else images_train
    dst_lbl = labels_val if i in val_set else labels_train
    rel = dst_img / src.name
    if not rel.exists():
      rel.write_bytes(src.read_bytes())
    lbl = labels_src / f"{src.stem}.txt"
    (dst_lbl / f"{src.stem}.txt").write_text(
      lbl.read_text() if lbl.exists() else "")
  print(f"split train={len(images) - n_val} val={n_val}")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--video-dir", type=Path,
    default=Path(__file__).resolve().parents[2] / "video")
  parser.add_argument(
    "--dataset", type=Path,
    default=Path(__file__).resolve().parent / "dataset")
  parser.add_argument("--stride", type=int, default=10,
                      help="Keep every Nth frame (~15 fps → 1.5 Hz at 10)")
  parser.add_argument(
    "--teacher", choices=("grounding-dino", "sam3"), default="grounding-dino",
    help="Label teacher (default: grounding-dino; sam3 needs gated HF + CUDA)")
  parser.add_argument(
    "--gdino-model", default="IDEA-Research/grounding-dino-tiny",
    help="HF id for Grounding DINO (try -base if ball recall is weak)")
  parser.add_argument("--device", default="cpu")
  parser.add_argument("--thr-person", type=float, default=0.30)
  parser.add_argument("--thr-ball", type=float, default=0.20)
  parser.add_argument("--val-frac", type=float, default=0.15)
  parser.add_argument("--seed", type=int, default=0)
  parser.add_argument("--skip-label", action="store_true",
                      help="Only sample frames; do not run teacher")
  args = parser.parse_args()

  raw_img = args.dataset / "images" / "_raw"
  raw_lbl = args.dataset / "labels" / "_raw"
  paths = []
  for cam, name in (("cam1.mp4", "cam1"), ("cam2.mp4", "cam2")):
    paths.extend(sample_frames(args.video_dir / cam, raw_img, args.stride, name))

  if not args.skip_label:
    if args.teacher == "grounding-dino":
      teacher_grounding_dino(
        paths, raw_lbl,
        model_id=args.gdino_model,
        thr_person=args.thr_person,
        thr_ball=args.thr_ball,
        device=args.device,
      )
    else:
      teacher_sam3(
        paths, raw_lbl,
        thr_person=args.thr_person,
        thr_ball=args.thr_ball,
        device=args.device,
      )

  split_train_val(
    paths,
    args.dataset / "images" / "train",
    args.dataset / "images" / "val",
    raw_lbl,
    args.dataset / "labels" / "train",
    args.dataset / "labels" / "val",
    args.val_frac,
    args.seed,
  )
  yaml_path = write_data_yaml(args.dataset)
  meta = {
    "n_images": len(paths),
    "stride": args.stride,
    "teacher": args.teacher,
    "gdino_model": args.gdino_model if args.teacher == "grounding-dino" else None,
    "thr_person": args.thr_person,
    "thr_ball": args.thr_ball,
    "classes": CLASSES,
    "data_yaml": str(yaml_path),
  }
  (args.dataset / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
  print("wrote", yaml_path)
  print("Review labels under", args.dataset / "labels",
        "then run train_and_export.sh")


if __name__ == "__main__":
  main()
