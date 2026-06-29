#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compare pose adjustment quality across detection datasets.

Compares bbox sizes between:
- occluded (no adjustment) = detections with occlusion, original bboxes
- no_occlusion (ground truth baseline) = detections without occlusion
- adjusted = detections with occlusion after pose adjustment

Produces metrics and plots showing how well pose adjustment recovers
the ground truth bbox size.

Usage:
  python controller/tools/compare_pose_adjustment.py \
      --occluded detections.json \
      --baseline no_occlusion_detections.json \
      --adjusted adjusted.json \
      --output-dir comparison_results
"""

import argparse
import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np


def load_detections_by_timestamp(path):
  """Load NDJSON, return dict: timestamp → list of detection objects."""
  frames = {}
  with open(path) as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      d = json.loads(line)
      ts = d['timestamp']
      frames[ts] = d['objects']
  return frames


def get_bbox_height(obj):
  """Get normalized bbox height from detection object."""
  bb = obj.get('detection', {}).get('bounding_box', {})
  y_min = bb.get('y_min', 0)
  y_max = bb.get('y_max', 0)
  return y_max - y_min


def get_bbox_area(obj):
  """Get normalized bbox area from detection object."""
  bb = obj.get('detection', {}).get('bounding_box', {})
  x_min = bb.get('x_min', 0)
  x_max = bb.get('x_max', 0)
  y_min = bb.get('y_min', 0)
  y_max = bb.get('y_max', 0)
  return (x_max - x_min) * (y_max - y_min)


def get_bbox_bottom(obj):
  """Get normalized bbox bottom (y_max) from detection object."""
  bb = obj.get('detection', {}).get('bounding_box', {})
  return bb.get('y_max', 0)


def find_matching_object(target_objects, ref_id):
  """Find object with matching id in a list."""
  for obj in target_objects:
    if obj.get('id') == ref_id:
      return obj
  return None


def compute_metrics(occluded_frames, baseline_frames, adjusted_frames):
  """Compute per-frame metrics for common timestamps.

  Since IDs may differ between occluded/baseline recordings of the same
  person, we match the largest detection at each timestamp.
  """
  common_ts = sorted(
    set(occluded_frames.keys()) & set(baseline_frames.keys()) & set(adjusted_frames.keys())
  )

  records = []
  for ts in common_ts:
    occ_objs = occluded_frames[ts]
    base_objs = baseline_frames[ts]
    adj_objs = adjusted_frames[ts]

    # Take the largest detection from each (primary person)
    occ_obj = max(occ_objs, key=get_bbox_area) if occ_objs else None
    base_obj = max(base_objs, key=get_bbox_area) if base_objs else None

    if occ_obj is None or base_obj is None:
      continue

    # Find the adjusted version matching the occluded object's ID
    occ_id = occ_obj.get('id')
    adj_obj = find_matching_object(adj_objs, occ_id) if occ_id else None
    if adj_obj is None:
      # Fallback: largest in adjusted
      adj_obj = max(adj_objs, key=get_bbox_area) if adj_objs else None
    if adj_obj is None:
      continue

    records.append({
      'timestamp': ts,
      'baseline_height': get_bbox_height(base_obj),
      'occluded_height': get_bbox_height(occ_obj),
      'adjusted_height': get_bbox_height(adj_obj),
      'baseline_area': get_bbox_area(base_obj),
      'occluded_area': get_bbox_area(occ_obj),
      'adjusted_area': get_bbox_area(adj_obj),
      'baseline_bottom': get_bbox_bottom(base_obj),
      'occluded_bottom': get_bbox_bottom(occ_obj),
      'adjusted_bottom': get_bbox_bottom(adj_obj),
    })

  return records


def print_summary(records):
  """Print summary statistics."""
  if not records:
    print("No matching frames found.")
    return

  baseline_h = np.array([r['baseline_height'] for r in records])
  occluded_h = np.array([r['occluded_height'] for r in records])
  adjusted_h = np.array([r['adjusted_height'] for r in records])

  # Height error (how much smaller than baseline)
  occ_error = baseline_h - occluded_h
  adj_error = baseline_h - adjusted_h

  print(f"\n{'='*60}")
  print("POSE ADJUSTMENT COMPARISON METRICS")
  print(f"{'='*60}")
  print(f"Matched frames: {len(records)}")
  print("\n--- Bbox Height (normalized) ---")
  print(f"{'Metric':<30} {'Occluded':>12} {'Adjusted':>12} {'Baseline':>12}")
  print(f"{'Mean height':<30} {occluded_h.mean():>12.4f} {adjusted_h.mean():>12.4f} {baseline_h.mean():>12.4f}")
  print(f"{'Median height':<30} {np.median(occluded_h):>12.4f} {np.median(adjusted_h):>12.4f} {np.median(baseline_h):>12.4f}")

  print("\n--- Height Error (baseline - predicted) ---")
  print(f"{'Metric':<30} {'Occluded':>12} {'Adjusted':>12}")
  print(f"{'Mean error':<30} {occ_error.mean():>12.4f} {adj_error.mean():>12.4f}")
  print(f"{'Median error':<30} {np.median(occ_error):>12.4f} {np.median(adj_error):>12.4f}")
  print(f"{'Std error':<30} {occ_error.std():>12.4f} {adj_error.std():>12.4f}")
  print(f"{'Max error':<30} {occ_error.max():>12.4f} {adj_error.max():>12.4f}")
  print(f"{'Mean abs error':<30} {np.abs(occ_error).mean():>12.4f} {np.abs(adj_error).mean():>12.4f}")

  # Recovery ratio: how much of the lost height was recovered
  # Only consider frames where there was actual loss
  mask = occ_error > 0.01
  recovery_pct = None
  if mask.sum() > 0:
    recovery_pct = np.clip((adjusted_h[mask] - occluded_h[mask]) / (baseline_h[mask] - occluded_h[mask]), 0, 2)
    print("\n--- Recovery (frames where occlusion caused >1% height loss) ---")
    print(f"{'Frames with loss':<30} {mask.sum():>12}")
    print(f"{'Mean recovery %':<30} {recovery_pct.mean()*100:>11.1f}%")
    print(f"{'Median recovery %':<30} {np.median(recovery_pct)*100:>11.1f}%")

  print(f"{'='*60}\n")

  return {
    'n_frames': len(records),
    'baseline_h': baseline_h,
    'occluded_h': occluded_h,
    'adjusted_h': adjusted_h,
    'occ_error': occ_error,
    'adj_error': adj_error,
    'recovery_pct': recovery_pct,
    'frames_with_loss': int(mask.sum()),
  }


def save_summary_markdown(stats, output_dir):
  """Save summary metrics as a Markdown file."""
  if stats is None:
    return

  occ_error = stats['occ_error']
  adj_error = stats['adj_error']
  baseline_h = stats['baseline_h']
  occluded_h = stats['occluded_h']
  adjusted_h = stats['adjusted_h']
  recovery_pct = stats['recovery_pct']

  error_reduction = (1 - np.abs(adj_error).mean() / np.abs(occ_error).mean()) * 100 if np.abs(occ_error).mean() > 0 else 0

  lines = [
    "# Pose Adjustment Evaluation Results\n",
    f"Matched frames: **{stats['n_frames']}**\n",
    "## Bounding Box Height (normalized)\n",
    "| Metric | Occluded | Adjusted | Baseline |",
    "|--------|----------|----------|----------|",
    f"| Mean height | {occluded_h.mean():.4f} | {adjusted_h.mean():.4f} | {baseline_h.mean():.4f} |",
    f"| Median height | {np.median(occluded_h):.4f} | {np.median(adjusted_h):.4f} | {np.median(baseline_h):.4f} |",
    "",
    "## Height Error (baseline - predicted)\n",
    "| Metric | Occluded | Adjusted | Improvement |",
    "|--------|----------|----------|-------------|",
    f"| Mean error | {occ_error.mean():.4f} | {adj_error.mean():.4f} | {(1 - adj_error.mean()/occ_error.mean())*100:.1f}% |" if occ_error.mean() > 0 else f"| Mean error | {occ_error.mean():.4f} | {adj_error.mean():.4f} | - |",
    f"| Mean abs error | {np.abs(occ_error).mean():.4f} | {np.abs(adj_error).mean():.4f} | {error_reduction:.1f}% |",
    f"| Median error | {np.median(occ_error):.4f} | {np.median(adj_error):.4f} | {(1 - np.median(adj_error)/np.median(occ_error))*100:.1f}% |" if np.median(occ_error) > 0 else f"| Median error | {np.median(occ_error):.4f} | {np.median(adj_error):.4f} | - |",
    f"| Std error | {occ_error.std():.4f} | {adj_error.std():.4f} | {(1 - adj_error.std()/occ_error.std())*100:.1f}% |" if occ_error.std() > 0 else f"| Std error | {occ_error.std():.4f} | {adj_error.std():.4f} | - |",
    f"| Max error | {occ_error.max():.4f} | {adj_error.max():.4f} | {(1 - adj_error.max()/occ_error.max())*100:.1f}% |" if occ_error.max() > 0 else f"| Max error | {occ_error.max():.4f} | {adj_error.max():.4f} | - |",
    "",
  ]

  if recovery_pct is not None and len(recovery_pct) > 0:
    lines.extend([
      "## Recovery (frames with >1% height loss due to occlusion)\n",
      "| Metric | Value |",
      "|--------|-------|",
      f"| Frames with loss | {stats['frames_with_loss']} |",
      f"| Mean recovery | {recovery_pct.mean()*100:.1f}% |",
      f"| Median recovery | {np.median(recovery_pct)*100:.1f}% |",
      "",
    ])

  lines.extend([
    "## Plots\n",
    "- `height_over_time.png` — bbox height across all three datasets",
    "- `height_error.png` — error relative to baseline over time",
    "- `error_distribution.png` — histogram of height errors",
    "- `bottom_over_time.png` — bbox bottom edge (foot position)",
  ])

  path = os.path.join(output_dir, 'results.md')
  with open(path, 'w') as f:
    f.write('\n'.join(lines) + '\n')
  print(f"Summary saved to {path}")


def plot_height_over_time(records, output_dir):
  """Plot bbox height over time for all three datasets."""
  timestamps = np.array([r['timestamp'] for r in records]) / 1e9
  baseline_h = np.array([r['baseline_height'] for r in records])
  occluded_h = np.array([r['occluded_height'] for r in records])
  adjusted_h = np.array([r['adjusted_height'] for r in records])

  _, ax = plt.subplots(figsize=(14, 6))
  ax.plot(timestamps, baseline_h, 'g-', label='Baseline (no occlusion)', alpha=0.8, linewidth=1.5)
  ax.plot(timestamps, occluded_h, 'r-', label='Occluded (no adjustment)', alpha=0.7, linewidth=1)
  ax.plot(timestamps, adjusted_h, 'b-', label='Adjusted (pose adjustment)', alpha=0.8, linewidth=1.5)
  ax.set_xlabel('Time (seconds)')
  ax.set_ylabel('Bbox Height (normalized)')
  ax.set_title('Bounding Box Height Over Time')
  ax.legend()
  ax.grid(True, alpha=0.3)
  plt.tight_layout()
  plt.savefig(os.path.join(output_dir, 'height_over_time.png'), dpi=150)
  plt.close()


def plot_height_error(records, output_dir):
  """Plot height error (baseline - predicted) over time."""
  timestamps = np.array([r['timestamp'] for r in records]) / 1e9
  baseline_h = np.array([r['baseline_height'] for r in records])
  occluded_h = np.array([r['occluded_height'] for r in records])
  adjusted_h = np.array([r['adjusted_height'] for r in records])

  occ_error = baseline_h - occluded_h
  adj_error = baseline_h - adjusted_h

  _, ax = plt.subplots(figsize=(14, 5))
  ax.plot(timestamps, occ_error, 'r-', label='Occluded error', alpha=0.7, linewidth=1)
  ax.plot(timestamps, adj_error, 'b-', label='Adjusted error', alpha=0.8, linewidth=1.5)
  ax.axhline(0, color='g', linestyle='--', alpha=0.5, label='Perfect (0 error)')
  ax.set_xlabel('Time (seconds)')
  ax.set_ylabel('Height Error (baseline - predicted)')
  ax.set_title('Bbox Height Error Over Time (positive = bbox too small)')
  ax.legend()
  ax.grid(True, alpha=0.3)
  plt.tight_layout()
  plt.savefig(os.path.join(output_dir, 'height_error.png'), dpi=150)
  plt.close()


def plot_error_distribution(records, output_dir):
  """Plot histogram of height errors."""
  baseline_h = np.array([r['baseline_height'] for r in records])
  occluded_h = np.array([r['occluded_height'] for r in records])
  adjusted_h = np.array([r['adjusted_height'] for r in records])

  occ_error = baseline_h - occluded_h
  adj_error = baseline_h - adjusted_h

  _, ax = plt.subplots(figsize=(10, 5))
  bins = np.linspace(min(occ_error.min(), adj_error.min()), max(occ_error.max(), adj_error.max()), 40)
  ax.hist(occ_error, bins=bins, alpha=0.6, label='Occluded error', color='red')
  ax.hist(adj_error, bins=bins, alpha=0.6, label='Adjusted error', color='blue')
  ax.axvline(0, color='g', linestyle='--', alpha=0.7, label='Perfect')
  ax.set_xlabel('Height Error (baseline - predicted)')
  ax.set_ylabel('Count')
  ax.set_title('Distribution of Bbox Height Errors')
  ax.legend()
  ax.grid(True, alpha=0.3)
  plt.tight_layout()
  plt.savefig(os.path.join(output_dir, 'error_distribution.png'), dpi=150)
  plt.close()


def plot_bottom_comparison(records, output_dir):
  """Plot bbox bottom (y_max) over time — shows foot position."""
  timestamps = np.array([r['timestamp'] for r in records]) / 1e9
  baseline_b = np.array([r['baseline_bottom'] for r in records])
  occluded_b = np.array([r['occluded_bottom'] for r in records])
  adjusted_b = np.array([r['adjusted_bottom'] for r in records])

  _, ax = plt.subplots(figsize=(14, 5))
  ax.plot(timestamps, baseline_b, 'g-', label='Baseline bottom', alpha=0.8, linewidth=1.5)
  ax.plot(timestamps, occluded_b, 'r-', label='Occluded bottom', alpha=0.7, linewidth=1)
  ax.plot(timestamps, adjusted_b, 'b-', label='Adjusted bottom', alpha=0.8, linewidth=1.5)
  ax.set_xlabel('Time (seconds)')
  ax.set_ylabel('Bbox Bottom y_max (normalized)')
  ax.set_title('Bounding Box Bottom Edge Over Time (foot position)')
  ax.legend()
  ax.grid(True, alpha=0.3)
  plt.tight_layout()
  plt.savefig(os.path.join(output_dir, 'bottom_over_time.png'), dpi=150)
  plt.close()


def build_argparser():
  parser = argparse.ArgumentParser(
    description='Compare pose adjustment quality metrics',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
  )
  parser.add_argument('--occluded', required=True, help='Occluded detections (no adjustment)')
  parser.add_argument('--baseline', required=True, help='No-occlusion detections (ground truth)')
  parser.add_argument('--adjusted', required=True, help='Adjusted detections (pose adjustment applied)')
  parser.add_argument('--output-dir', default='comparison_results', help='Output directory for plots')
  return parser


def main():
  args = build_argparser().parse_args()

  os.makedirs(args.output_dir, exist_ok=True)

  occluded_frames = load_detections_by_timestamp(args.occluded)
  baseline_frames = load_detections_by_timestamp(args.baseline)
  adjusted_frames = load_detections_by_timestamp(args.adjusted)

  print(f"Loaded: occluded={len(occluded_frames)} frames, "
        f"baseline={len(baseline_frames)} frames, "
        f"adjusted={len(adjusted_frames)} frames")

  records = compute_metrics(occluded_frames, baseline_frames, adjusted_frames)
  stats = print_summary(records)

  if records:
    plot_height_over_time(records, args.output_dir)
    plot_height_error(records, args.output_dir)
    plot_error_distribution(records, args.output_dir)
    plot_bottom_comparison(records, args.output_dir)
    save_summary_markdown(stats, args.output_dir)
    print(f"Plots saved to {args.output_dir}/")


if __name__ == '__main__':
  sys.exit(main() or 0)
