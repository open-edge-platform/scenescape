#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Remap object IDs in real-video detection JSONL files to match the synthetic
ground-truth IDs, using IoU matching on bounding_box_px at each timestamp.

Usage:
    python remap_detection_ids.py

Reads  Cam_x1_0.json / Cam_x2_0.json  (real-video detections, IDs are local
per-frame counters) and Default_Cam_x1_0.json / Default_Cam_x2_0.json (synthetic
detections, IDs match the GT), then writes the remapped files in-place, keeping
a backup with the suffix .bak.

Matching strategy per (timestamp, camera, category):
  - Build the set of synthetic bounding boxes with their GT-compatible IDs.
  - Greedily assign each new detection to the synthetic detection with the
    highest IoU; any new detection with no IoU > 0 keeps its original ID
    (logged as a warning).
"""

import json
import shutil
import sys
from pathlib import Path

DATASET_DIR = Path(__file__).parent
CAMERAS = ["Cam_x1_0", "Cam_x2_0"]


def iou(a: dict, b: dict) -> float:
    """Intersection-over-Union of two bounding_box_px dicts {x,y,width,height}."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["width"], ay1 + a["height"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["width"], by1 + b["height"]

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0.0:
        return 0.0
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def load_reference(path: Path) -> dict:
    """Load synthetic JSONL → {timestamp: {category: [{id, bounding_box_px}]}}."""
    ref = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            ts = d["timestamp"]
            ref[ts] = {}
            for cat, objs in d.get("objects", {}).items():
                ref[ts][cat.lower()] = [
                    {"id": o["id"], "bb": o["bounding_box_px"]}
                    for o in objs
                    if "bounding_box_px" in o
                ]
    return ref


def remap_frame(frame: dict, ref_ts: dict, cam_id: str) -> dict:
    """Return a copy of frame with object IDs remapped to match reference."""
    new_objects = {}
    for cat, objs in frame.get("objects", {}).items():
        ref_objs = list(ref_ts.get(cat.lower(), []))  # copy so we can consume
        new_list = []
        for obj in objs:
            bb_new = obj.get("bounding_box_px")
            if bb_new is None:
                new_list.append(obj)
                continue

            # Find best-IoU match in reference for this category
            best_iou, best_idx = 0.0, -1
            for i, ref_obj in enumerate(ref_objs):
                score = iou(bb_new, ref_obj["bb"])
                if score > best_iou:
                    best_iou, best_idx = score, i

            new_obj = dict(obj)
            if best_idx >= 0 and best_iou > 0.0:
                new_obj["id"] = ref_objs[best_idx]["id"]
                ref_objs.pop(best_idx)  # consume so it can't match twice
            else:
                print(
                    f"  WARNING [{cam_id} ts={frame['timestamp']}] "
                    f"no IoU match for {cat} id={obj['id']} "
                    f"bb={bb_new} — keeping original id",
                    file=sys.stderr,
                )
            new_list.append(new_obj)
        new_objects[cat] = new_list

    result = dict(frame)
    result["objects"] = new_objects
    return result


def temporal_remap(frames: list, cam_id: str) -> list:
    """Second pass: fix IDs that have no reference match by carrying forward
    the ID from the best-IoU detection in the previous frame (same category).

    This handles cases where the synthetic reference had fewer persons than the
    real video, leaving some detections with their original local counter ID.
    """
    # prev_ids: {category: [{id, bb}]}  — last seen canonical assignments
    prev_ids: dict = {}
    result = []
    fixed = 0

    # Collect all IDs that are valid canonical GT ids (appeared via IoU match)
    # We determine "suspicious" IDs as those that are not 0 or 1 (persons)
    # Actually: use the reference files to know what canonical IDs exist per category.
    # Simpler heuristic: any id that equals the original local counter that was
    # kept (i.e., not in {0,1} for person) is a candidate for fixing.
    # We rely on the caller to pass reference_ids per category.

    for frame in frames:
        new_objects = {}
        for cat, objs in frame.get("objects", {}).items():
            prev = prev_ids.get(cat, [])
            new_list = []
            for obj in objs:
                bb = obj.get("bounding_box_px")
                if bb is None or not prev:
                    new_list.append(obj)
                    continue

                # Only try to fix if this id looks like an unmatched local counter:
                # i.e. it doesn't appear in prev_ids at all (brand-new id)
                known_ids = {p["id"] for p in prev}
                if obj["id"] in known_ids:
                    # Already a known canonical id — keep it
                    new_list.append(obj)
                    continue

                # Find best-IoU match from previous frame
                best_iou, best_id = 0.0, None
                for p in prev:
                    score = iou(bb, p["bb"])
                    if score > best_iou:
                        best_iou, best_id = score, p["id"]

                new_obj = dict(obj)
                if best_id is not None and best_iou > 0.0:
                    new_obj["id"] = best_id
                    fixed += 1
                new_list.append(new_obj)

            new_objects[cat] = new_list
            prev_ids[cat] = [
                {"id": o["id"], "bb": o["bounding_box_px"]}
                for o in new_list
                if o.get("bounding_box_px")
            ]

        new_frame = dict(frame)
        new_frame["objects"] = new_objects
        result.append(new_frame)

    print(f"[{cam_id}] Temporal pass fixed {fixed} detections")
    return result


def process_camera(cam_id: str) -> None:
    new_path = DATASET_DIR / f"{cam_id}.json"
    ref_path = DATASET_DIR / f"Default_{cam_id}.json"
    bak_path = DATASET_DIR / f"{cam_id}.json.bak"

    print(f"[{cam_id}] Loading reference from {ref_path.name} ...")
    ref = load_reference(ref_path)

    print(f"[{cam_id}] Reading {new_path.name} ...")
    with open(new_path) as f:
        lines = [l for l in f if l.strip()]

    print(f"[{cam_id}] Backing up to {bak_path.name} ...")
    shutil.copy(new_path, bak_path)

    matched = skipped = unmatched_ts = 0
    remapped_frames = []
    for line in lines:
        frame = json.loads(line)
        ts = frame["timestamp"]
        if ts not in ref or not frame.get("objects"):
            remapped_frames.append(frame)
            if ts not in ref and frame.get("objects"):
                unmatched_ts += 1
            skipped += 1
            continue

        remapped = remap_frame(frame, ref[ts], cam_id)
        remapped_frames.append(remapped)
        matched += 1

    print(f"[{cam_id}] Reference pass: {matched} frames remapped, "
          f"{skipped} skipped (empty/no ref), "
          f"{unmatched_ts} had detections with no reference timestamp")

    remapped_frames = temporal_remap(remapped_frames, cam_id)

    print(f"[{cam_id}] Writing remapped data to {new_path.name} ...")
    out_lines = [json.dumps(f, separators=(",", ":")) for f in remapped_frames]
    with open(new_path, "w") as f:
        f.write("\n".join(out_lines) + "\n")

    print(
        f"[{cam_id}] Done."
    )


if __name__ == "__main__":
    for cam in CAMERAS:
        process_camera(cam)
        print()
