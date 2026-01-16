#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (C) 2025 Intel Corporation

"""Test feature matching functionality."""

import sys
import tempfile
from pathlib import Path
from test_utils import setup_hloc_path, print_test_header, print_test_result


def create_test_image(output_path: Path, width: int = 640, height: int = 480):
    """Create synthetic test image."""
    try:
        import numpy as np
        from PIL import Image, ImageDraw
        
        img = np.zeros((height, width, 3), dtype=np.uint8)
        square_size = 40
        for i in range(0, height, square_size):
            for j in range(0, width, square_size):
                if (i // square_size + j // square_size) % 2 == 0:
                    img[i:i+square_size, j:j+square_size] = [200, 200, 200]
        
        pil_img = Image.fromarray(img)
        draw = ImageDraw.Draw(pil_img)
        draw.ellipse([100, 100, 180, 180], fill=(255, 100, 100))
        draw.rectangle([400, 200, 500, 300], fill=(100, 255, 100))
        
        pil_img.save(output_path)
        return True
    except ImportError:
        return False


def test_feature_matching():
    """Test feature matching between images."""
    print_test_header("Feature Matching")
    
    try:
        from hloc import extract_features, match_features
        import h5py
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            images_dir = tmp_path / "images"
            images_dir.mkdir()
            
            print("  Creating test image pair...")
            if not create_test_image(images_dir / "img1.jpg"):
                print("  ⚠️  Skipping (PIL not available)")
                print_test_result(True, "Skipped - dependencies missing")
                return True
            
            create_test_image(images_dir / "img2.jpg")
            
            # Extract features
            print("  Extracting features...")
            features_file = tmp_path / "features.h5"
            conf = extract_features.confs['superpoint_aachen']
            extract_features.main(
                conf=conf,
                image_dir=images_dir,
                export_dir=tmp_path,
                feature_path=features_file
            )
            
            # Create pairs
            pairs_file = tmp_path / "pairs.txt"
            pairs_file.write_text("img1.jpg img2.jpg\n")
            
            # Match features
            print("  Matching features with SuperGlue...")
            matches_file = tmp_path / "matches.h5"
            match_conf = match_features.confs['superglue']
            match_features.main(
                conf=match_conf,
                pairs=pairs_file,
                features=features_file,
                export_dir=tmp_path,
                matches=matches_file
            )
            
            if not matches_file.exists():
                print_test_result(False, "No matches file created")
                return False
            
            # Verify matches
            with h5py.File(matches_file, 'r') as f:
                pair_key = 'img1.jpg/img2.jpg'
                if pair_key not in f:
                    print_test_result(False, f"Pair {pair_key} not in output")
                    return False
                
                matches = f[pair_key]['matches0'][:]
                scores = f[pair_key]['matching_scores0'][:]
                
                valid_matches = (matches >= 0).sum()
                print(f"  ✓ Found {valid_matches} matches")
                print(f"  ✓ Score range: {scores.min():.3f} - {scores.max():.3f}")
        
        print_test_result(True)
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print_test_result(False, str(e))
        return False


def main():
    """Run matching tests."""
    try:
        setup_hloc_path()
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1
    
    passed = test_feature_matching()
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
