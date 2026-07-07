#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Example client for the 3D Mapping Models API
Demonstrates how to send images to the API and receive 3D reconstruction results.
Note: The model type is determined at container build time, not at runtime.
"""

import base64
import json
from pathlib import Path
from typing import List
import argparse
import urllib3
import os
import sys

# Disable SSL warnings when using --insecure flag
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
POLL_TIMEOUT = 900

TOOLS_DIR = Path(__file__).resolve().parent
MAPPING_SRC_DIR = TOOLS_DIR.parent / "src"
if str(MAPPING_SRC_DIR) not in sys.path:
  sys.path.insert(0, str(MAPPING_SRC_DIR))

from mapping_client import MappingClient

def send_reconstruction_request(
  client: MappingClient,
  image_paths: List[str],
  video_path: str,
  use_keyframes: bool = True,
  output_format: str = "glb",
  mesh_type: str = "mesh"
):
  """Send reconstruction request to the API"""

  # Prepare request payload
  payload = {
    "output_format": output_format,
    "mesh_type": mesh_type,
    "use_keyframes": use_keyframes
  }

  if image_paths:
    for img_path in image_paths:
      p = Path(img_path)
      if not p.exists():
        raise FileNotFoundError(f"Image not found: {img_path}")
    payload["images"] = image_paths

  if video_path:
    p = Path(video_path)
    if not p.exists():
      raise FileNotFoundError(f"Video not found: {video_path}")
    payload["video"] = video_path

  print(f"Sending request to {client.url}reconstruction")
  if image_paths and video_path:
    print(f"- Images: {len(image_paths)}")
    print(f"- Video: {video_path}")
  elif image_paths:
    print(f"- Images: {len(image_paths)}")
  else:
    print(f"- Video: {video_path}")
  print(f"- Output format: {output_format}")
  print(f"- Mesh type: {mesh_type}")

  try:
    started = client.performReconstruction(payload)

    if started.status_code in (200, 202) and not started.errors:

      if "processing_time" in started and started.get("success"):
        model_used = started.get("model", "unknown")
        print(f"✅ Success! Model: {model_used}, Processing time: {started['processing_time']:.2f}s")
        return started

      rid = started.get("request_id")
      if not rid:
        print(f"❌ Unexpected response (no request_id): {started}")
        return None

      print(f"✅ Accepted. request_id={rid}. Polling for completion...")
      final = client.waitForReconstruction(
          rid,
          timeout_s=int(os.getenv("GUNICORN_TIMEOUT", "900")),
          poll_s=1.5,
      )
      model_used = final.get("model", "unknown")
      pt = final.get("processing_time", None)
      if pt is not None:
        print(f"✅ Complete! Model: {model_used}, Processing time: {pt:.2f}s")
      else:
        print(f"✅ Complete! Model: {model_used}")
      return final

    else:
      print(f"❌ Error {started.status_code}: {started.errors}")
      return None
  except Exception as e:
    print(f"❌ Error: {e}")
    return None

def save_glb_file(glb_data: str, output_path: str):
  """Save base64 encoded GLB data to file"""
  try:
    glb_bytes = base64.b64decode(glb_data)
    with open(output_path, "wb") as f:
      f.write(glb_bytes)
    print(f"✅ GLB file saved: {output_path}")
  except Exception as e:
    print(f"❌ Failed to save GLB file: {e}")

def check_api_health(client: MappingClient):
  """Check API health and available models"""
  try:
    health = client.healthCheckEndpoint()
    if health:
      print(f"✅ API is healthy")
    else:
      print(f"❌ Health check failed: {health.status_code}, {health.errors}")
      return False

    return True

  except Exception as e:
    print(f"❌ Failed to connect to API: {e}")
    return False

def main():
  parser = argparse.ArgumentParser(description="3D Mapping Models API Client")
  parser.add_argument("--api-url", default="https://localhost:8444/v1",
             help="API server URL (default: https://localhost:8444/v1)")
  parser.add_argument("--video",
             help="Path to input video file")
  parser.add_argument("--images", nargs="+",
             help="Paths to input images")
  parser.add_argument("--output", default="reconstruction.glb",
             help="Output GLB file path (default: reconstruction.glb)")
  parser.add_argument("--format", choices=["glb", "json"], default="glb",
             help="Output format (default: glb)")
  parser.add_argument("--mesh-type", choices=["mesh", "pointcloud"], default="mesh",
             help="Output type: mesh (watertight) or pointcloud")
  parser.add_argument("--all-frames", dest="use_keyframes", action="store_false",
            help="Process all frames when processing a video")
  parser.add_argument("--health-check", action="store_true",
             help="Only check API health and model information")
  parser.add_argument("--insecure", action="store_true",
             help="Disable SSL certificate verification (for self-signed certificates)")
  args = parser.parse_args()

  # Determine SSL verification setting
  verify_ssl = not args.insecure
  timeout_s = int(os.getenv("GUNICORN_TIMEOUT", str(POLL_TIMEOUT)))
  client = MappingClient(url=args.api_url, verify_ssl=verify_ssl, timeout=timeout_s)

  # Check API health
  if not check_api_health(client):
    return 1

  if args.health_check:
    return 0

  # Validate that at least one input is provided
  if not args.images and not args.video:
    print("❌ Error: At least one of --images or --video must be provided")
    return 1

  # Send reconstruction request
  result = send_reconstruction_request(
    client,
    args.images,
    args.video,
    args.use_keyframes,
    args.format,
    args.mesh_type,
  )

  if result and result.get("success"):
    print(f"📊 Reconstruction details:")
    print(f"   - Model used: {result.get('model', 'unknown')}")
    print(f"   - Camera poses: {len(result['camera_poses'])}")
    print(f"   - Intrinsics matrices: {len(result['intrinsics'])}")

    if args.format == "glb" and result.get("glb_data"):
      save_glb_file(result["glb_data"], args.output)
    elif args.format == "json":
      # Save full JSON result
      with open(args.output, "w") as f:
        json.dump(result, f, indent=2)
      print(f"✅ JSON result saved: {args.output}")

    # Optionally save camera data separately for GLB format
    if args.format == "glb":
      camera_data_path = args.output.replace(".glb", "_camera_data.json")
      with open(camera_data_path, "w") as f:
        json.dump({
          "model": result.get("model"),
          "camera_poses": result["camera_poses"],
          "intrinsics": result["intrinsics"],
          "processing_time": result["processing_time"]
        }, f, indent=2)
      print(f"✅ Camera data saved: {camera_data_path}")

    return 0
  else:
    return 1

if __name__ == "__main__":
  sys.exit(main())
