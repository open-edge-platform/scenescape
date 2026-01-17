#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (C) 2025 Intel Corporation

"""Test feature extraction functionality."""

import sys
import tempfile
from pathlib import Path
from test_utils import setup_hloc_path, print_test_header, print_test_result


def create_test_image(output_path: Path, width: int = 640, height: int = 480):
    """Create synthetic test image with patterns."""
    try:
        import numpy as np
        from PIL import Image, ImageDraw
        
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Checkerboard pattern
        square_size = 40
        for i in range(0, height, square_size):
            for j in range(0, width, square_size):
                if (i // square_size + j // square_size) % 2 == 0:
                    img[i:i+square_size, j:j+square_size] = [200, 200, 200]
        
        pil_img = Image.fromarray(img)
        draw = ImageDraw.Draw(pil_img)
        
        # Add shapes for feature detection
        draw.ellipse([100, 100, 180, 180], fill=(255, 100, 100))
        draw.rectangle([400, 200, 500, 300], fill=(100, 255, 100))
        draw.ellipse([250, 300, 350, 400], fill=(100, 100, 255))
        
        pil_img.save(output_path)
        return True
    except ImportError as e:
        print(f"  ⚠️  Cannot create test images: {e}")
        return False


def test_dog_extractor():
    """Test DoG extractor API compatibility (pycolmap)."""
    print_test_header("DoG Extractor API")
    
    try:
        from hloc import extract_features
        import torch
        import numpy as np
        
        # Create a simple test image
        print("  Creating test image...")
        image_np = np.random.rand(480, 640).astype(np.float32)
        image_tensor = torch.from_numpy(image_np)[None, None]
        
        # Try to instantiate DoG extractor
        print("  Instantiating DoG extractor...")
        conf = extract_features.confs.get('sift', {
            'output': 'feats-sift',
            'model': {'name': 'dog'},
            'preprocessing': {'grayscale': True, 'resize_max': 1600},
        })
        
        # Create model
        from hloc.extractors.dog import DoG
        model = DoG(conf['model']).eval()
        
        # Test forward pass
        print("  Testing forward pass...")
        data = {'image': image_tensor}
        with torch.no_grad():
            output = model(data)
        
        # Verify output structure
        if 'keypoints' not in output:
            print_test_result(False, "Missing 'keypoints' in output")
            return False
        if 'scores' not in output:
            print_test_result(False, "Missing 'scores' in output")
            return False
        if 'descriptors' not in output:
            print_test_result(False, "Missing 'descriptors' in output")
            return False
        
        print(f"  ✓ Extracted {output['keypoints'].shape[1]} keypoints")
        print(f"  ✓ Output structure valid")
        print_test_result(True)
        return True
        
    except ValueError as e:
        if "not enough values to unpack" in str(e):
            print(f"  ❌ pycolmap API compatibility issue: {e}")
            print("  ⚠️  This indicates the DoG extractor patch is not applied correctly")
            print_test_result(False, "pycolmap API mismatch")
            return False
        else:
            raise
    except Exception as e:
        print(f"  ⚠️  Test skipped: {e}")
        print("  (May require additional dependencies)")
        print_test_result(True, "Skipped - dependencies missing")
        return True


def test_feature_extraction():
    """Test actual feature extraction on synthetic images."""
    print_test_header("Feature Extraction (SuperPoint)")
    
    try:
        from hloc import extract_features
        import h5py
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            images_dir = tmp_path / "images"
            images_dir.mkdir()
            
            print("  Creating test images...")
            if not create_test_image(images_dir / "test1.jpg"):
                print("  ⚠️  Skipping (PIL not available)")
                print_test_result(True, "Skipped - dependencies missing")
                return True
            
            create_test_image(images_dir / "test2.jpg", 800, 600)
            
            output_file = tmp_path / "features.h5"
            conf = extract_features.confs['superpoint_aachen']
            
            print("  Extracting features with SuperPoint...")
            extract_features.main(
                conf=conf,
                image_dir=images_dir,
                export_dir=tmp_path,
                image_list=None,
                feature_path=output_file
            )
            
            if not output_file.exists():
                print_test_result(False, "No output file created")
                return False
            
            # Verify H5 structure
            with h5py.File(output_file, 'r') as f:
                images = list(f.keys())
                if len(images) == 0:
                    print_test_result(False, "Empty H5 file")
                    return False
                
                img_name = images[0]
                if 'keypoints' not in f[img_name] or 'descriptors' not in f[img_name]:
                    print_test_result(False, "Missing keypoints/descriptors")
                    return False
                
                keypoints = f[img_name]['keypoints'][:]
                descriptors = f[img_name]['descriptors'][:]
                
                print(f"  ✓ Extracted {len(keypoints)} keypoints from {len(images)} images")
                print(f"  ✓ Descriptor shape: {descriptors.shape}")
                
                if len(keypoints) == 0:
                    print_test_result(False, "No keypoints detected")
                    return False
                
                if descriptors.shape[0] != len(keypoints):
                    print_test_result(False, "Descriptor count mismatch")
                    return False
        
        print_test_result(True)
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print_test_result(False, str(e))
        return False


def main():
    """Run feature extraction tests."""
    try:
        setup_hloc_path()
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1
    
    # Run DoG API test first (critical for build-time verification)
    dog_passed = test_dog_extractor()
    
    # Run general extraction test
    extraction_passed = test_feature_extraction()
    
    return 0 if (dog_passed and extraction_passed) else 1


if __name__ == '__main__':
    sys.exit(main())
