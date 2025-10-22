#!/usr/bin/env python3

"""
Example client for the 3D Mapping Models API
Demonstrates how to send images to the API and receive 3D reconstruction results.
"""

import base64
import json
import requests
from pathlib import Path
from typing import List
import argparse

def encode_image_to_base64(image_path: str) -> str:
    """Encode image file to base64 string"""
    with open(image_path, "rb") as f:
        image_data = f.read()
        encoded = base64.b64encode(image_data).decode('utf-8')
        return encoded

def send_reconstruction_request(
    api_url: str,
    image_paths: List[str],
    model_type: str = "mapanything",
    output_format: str = "glb",
    mesh_type: str = "mesh"
):
    """Send reconstruction request to the API"""
    
    # Prepare image data
    images = []
    for img_path in image_paths:
        if not Path(img_path).exists():
            raise FileNotFoundError(f"Image not found: {img_path}")
        
        encoded_data = encode_image_to_base64(img_path)
        images.append({
            "data": encoded_data,
            "filename": Path(img_path).name
        })
    
    # Prepare request payload
    payload = {
        "images": images,
        "model_type": model_type,
        "output_format": output_format
    }
    
    # Add mesh_type parameter (works for both models)
    payload["mesh_type"] = mesh_type
    
    print(f"Sending request to {api_url}/reconstruct")
    print(f"- Images: {len(images)}")
    print(f"- Model: {model_type}")
    print(f"- Output format: {output_format}")
    
    try:
        # Send POST request
        response = requests.post(
            f"{api_url}/reconstruct",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300  # 5 minute timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Processing time: {result['processing_time']:.2f}s")
            return result
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - is the API server running?")
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

def check_api_health(api_url: str):
    """Check API health and available models"""
    try:
        # Health check
        response = requests.get(f"{api_url}/health", timeout=10)
        if response.status_code == 200:
            health = response.json()
            print(f"✅ API is healthy")
            print(f"   Device: {health['device']}")
            print(f"   Models loaded: {health['models']}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
        
        # List models
        response = requests.get(f"{api_url}/models", timeout=10)
        if response.status_code == 200:
            models = response.json()
            print("📋 Available models:")
            for model, info in models['model_status'].items():
                status = "✅ Loaded" if info['loaded'] else "❌ Not loaded"
                print(f"   - {model}: {status}")
                print(f"     {info['description']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to connect to API: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="3D Mapping Models API Client")
    parser.add_argument("--api-url", default="http://localhost:8000", 
                       help="API server URL (default: http://localhost:8000)")
    parser.add_argument("--images", nargs="+", required=False,
                       help="Paths to input images")
    parser.add_argument("--model", choices=["mapanything", "vggt"], default="mapanything",
                       help="Model to use (default: mapanything)")
    parser.add_argument("--output", default="reconstruction.glb",
                       help="Output GLB file path (default: reconstruction.glb)")
    parser.add_argument("--mesh-type", choices=["mesh", "pointcloud"], default="mesh",
                       help="Output type: mesh (watertight) or pointcloud")
    parser.add_argument("--health-check", action="store_true",
                       help="Only check API health and available models")
    
    args = parser.parse_args()
    
    # Check API health
    if not check_api_health(args.api_url):
        return 1
    
    if args.health_check:
        return 0
    
    if not args.images:
        print("❌ Please provide image paths with --images")
        return 1
    
    # Send reconstruction request
    result = send_reconstruction_request(
        args.api_url,
        args.images,
        args.model,
        "glb",
        args.mesh_type
    )
    
    if result and result.get("success"):
        print(f"📊 Reconstruction details:")
        print(f"   - Camera poses: {len(result['camera_poses'])}")
        print(f"   - Intrinsics matrices: {len(result['intrinsics'])}")
        
        if result.get("glb_data"):
            save_glb_file(result["glb_data"], args.output)
        
        # Optionally save camera data
        camera_data_path = args.output.replace(".glb", "_camera_data.json")
        with open(camera_data_path, "w") as f:
            json.dump({
                "camera_poses": result["camera_poses"],
                "intrinsics": result["intrinsics"],
                "processing_time": result["processing_time"]
            }, f, indent=2)
        print(f"✅ Camera data saved: {camera_data_path}")
        
        return 0
    else:
        return 1

if __name__ == "__main__":
    exit(main())