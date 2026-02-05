#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Interactive demo script for exploring MetricTestDataset.

This script demonstrates how to use the MetricTestDataset implementation
to load and view scene config, camera inputs, and ground truth data.
"""

import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from datasets.metric_test_dataset import MetricTestDataset
from utils.format_converters import read_csv_to_dataframe
import json


def print_separator(title=""):
  """Print a formatted separator line."""
  if title:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print('=' * 80)
  else:
    print('-' * 80)


def explore_scene_config(dataset):
  """Display scene configuration."""
  print_separator("SCENE CONFIGURATION")

  scene_config = dataset.get_scene_config()

  print(f"Scene UID: {scene_config['uid']}")
  print(f"Scene Name: {scene_config['name']}")
  print(f"Number of Cameras: {len(scene_config['cameras'])}\n")

  for i, camera in enumerate(scene_config['cameras'], 1):
    print(f"Camera {i}:")
    print(f"  UID: {camera['uid']}")
    print(f"  Name: {camera['name']}")
    print(f"  Intrinsics:")
    print(f"    fx: {camera['intrinsics']['fx']}")
    print(f"    fy: {camera['intrinsics']['fy']}")
    print(f"    cx: {camera['intrinsics']['cx']}")
    print(f"    cy: {camera['intrinsics']['cy']}")
    print()

  # Pretty-print full JSON
  print("Full Scene Config (JSON):")
  print(json.dumps(scene_config, indent=2))


def explore_inputs(dataset, camera_id="x1", max_frames=5):
  """Display sample camera input data."""
  print_separator(f"CAMERA INPUTS - {camera_id.upper()} (first {max_frames} frames)")

  inputs = list(dataset.get_inputs(camera_id))

  print(f"Total frames available: {len(inputs)}")
  print(f"Camera FPS setting: {dataset._camera_fps}\n")

  for i, frame_data in enumerate(inputs[:max_frames]):
    print(f"Frame {i}:")
    print(f"  Timestamp: {frame_data.get('timestamp', 'N/A')}")
    print(f"  Camera ID: {frame_data.get('id', 'N/A')}")
    print(f"  Frame number: {frame_data.get('frame', 'N/A')}")

    objects = frame_data.get('objects', {})
    total_detections = sum(len(objs) for objs in objects.values())
    print(f"  Total detections: {total_detections}")

    for category, detections in objects.items():
      print(f"    {category}: {len(detections)} detection(s)")
      for det in detections[:2]:  # Show first 2 detections
        print(f"      - ID: {det.get('id', 'N/A')}, "
              f"Confidence: {det.get('confidence', 'N/A')}")
    print()

  # Show one complete frame as JSON
  if inputs:
    print_separator()
    print("Sample Frame (JSON):")
    print(json.dumps(inputs[0], indent=2))


def explore_ground_truth(dataset, max_rows=20):
  """Display ground truth data."""
  print_separator("GROUND TRUTH DATA")

  gt_path = dataset.get_ground_truth()
  print(f"Ground truth CSV path: {gt_path}\n")

  # Read CSV
  df = read_csv_to_dataframe(
    gt_path,
    has_header=False,
    column_names=["frame", "id", "x", "y", "z", "conf", "class", "vis"]
  )

  print(f"Total rows: {len(df)}")
  print(f"Frame range: {df['frame'].min()} - {df['frame'].max()}")
  print(f"Unique object IDs: {df['id'].nunique()}")
  print(f"Object IDs: {sorted(df['id'].unique().tolist())}\n")

  print(f"First {max_rows} rows:")
  print(df.head(max_rows).to_string(index=False))

  print(f"\n\nStatistics:")
  print(df.describe())

  # Show object trajectories
  print_separator()
  print("Object Trajectory Summary:")
  for obj_id in sorted(df['id'].unique()):
    obj_data = df[df['id'] == obj_id]
    print(f"  Object ID {obj_id}:")
    print(f"    Frames: {obj_data['frame'].min()} - {obj_data['frame'].max()} "
          f"({len(obj_data)} detections)")
    print(f"    X range: [{obj_data['x'].min():.2f}, {obj_data['x'].max():.2f}]")
    print(f"    Y range: [{obj_data['y'].min():.2f}, {obj_data['y'].max():.2f}]")


def compare_fps_settings(dataset):
  """Compare different FPS settings."""
  print_separator("FPS SETTINGS COMPARISON")

  for fps in [1, 10, 30]:
    dataset.set_camera_fps(fps)
    inputs = list(dataset.get_inputs("x1"))
    print(f"{fps} FPS: {len(inputs)} frames")


def main():
  """Main demo function."""
  # Path to dataset
  dataset_path = Path(__file__).parent.parent.parent.parent / \
    "tests" / "system" / "metric" / "test_data"

  if not dataset_path.exists():
    print(f"ERROR: Dataset not found at {dataset_path}")
    print("Please ensure you're running from tools/tracker/evaluation directory")
    sys.exit(1)

  print("=" * 80)
  print("  MetricTestDataset Interactive Demo")
  print("=" * 80)
  print(f"\nDataset path: {dataset_path}\n")

  # Create dataset instance
  dataset = MetricTestDataset(str(dataset_path))

  # Configure dataset
  dataset.set_cameras(["x1", "x2"]).set_camera_fps(30)

  # Menu
  while True:
    print("\n" + "=" * 80)
    print("MENU:")
    print("  1. View Scene Configuration")
    print("  2. View Camera Inputs (x1)")
    print("  3. View Camera Inputs (x2)")
    print("  4. View Ground Truth Data")
    print("  5. Compare FPS Settings")
    print("  6. Change Configuration")
    print("  7. Reset Dataset")
    print("  0. Exit")
    print("=" * 80)

    choice = input("\nEnter your choice: ").strip()

    if choice == "1":
      explore_scene_config(dataset)

    elif choice == "2":
      max_frames = input("How many frames to display? (default: 5): ").strip()
      max_frames = int(max_frames) if max_frames else 5
      explore_inputs(dataset, "x1", max_frames)

    elif choice == "3":
      max_frames = input("How many frames to display? (default: 5): ").strip()
      max_frames = int(max_frames) if max_frames else 5
      explore_inputs(dataset, "x2", max_frames)

    elif choice == "4":
      max_rows = input("How many rows to display? (default: 20): ").strip()
      max_rows = int(max_rows) if max_rows else 20
      explore_ground_truth(dataset, max_rows)

    elif choice == "5":
      compare_fps_settings(dataset)
      # Reset to 30 FPS
      dataset.set_camera_fps(30)

    elif choice == "6":
      print("\nCurrent configuration:")
      print(f"  Cameras: {dataset._cameras}")
      print(f"  FPS: {dataset._camera_fps}")

      print("\nChange what?")
      print("  1. Cameras")
      print("  2. FPS")

      sub_choice = input("Enter choice: ").strip()

      if sub_choice == "1":
        print("\nAvailable cameras: x1, x2")
        cameras = input("Enter camera IDs (comma-separated): ").strip()
        camera_list = [c.strip() for c in cameras.split(",") if c.strip()]
        try:
          dataset.set_cameras(camera_list)
          print(f"✓ Cameras set to: {dataset._cameras}")
        except Exception as e:
          print(f"✗ Error: {e}")

      elif sub_choice == "2":
        print("\nAvailable FPS: 1, 10, 30")
        fps = input("Enter FPS: ").strip()
        try:
          dataset.set_camera_fps(int(fps))
          print(f"✓ FPS set to: {dataset._camera_fps}")
        except Exception as e:
          print(f"✗ Error: {e}")

    elif choice == "7":
      dataset.reset()
      print("✓ Dataset reset to defaults (cameras: [x1, x2], FPS: 30)")

    elif choice == "0":
      print("\nGoodbye!")
      break

    else:
      print("\n✗ Invalid choice. Please try again.")

    input("\nPress Enter to continue...")


if __name__ == "__main__":
  main()
