#!/usr/bin/env python3
"""
Test script for pipeline generator

Tests the pipeline generator against all possible combinations and verifies
the output matches the templates in pipelines.txt
"""

import os
import sys
import re
from pipeline_generator import generate_pipeline


def load_reference_pipelines():
    """Load reference pipelines from pipelines.txt file."""
    pipelines = {}
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pipelines_file = os.path.join(script_dir, "pipelines.txt")
    
    with open(pipelines_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            # Parse line: "Decode device X, inference device Y: <pipeline>"
            match = re.match(r'Decode device (\w+), inference device (\w+):\s+(.+)', line)
            if match:
                decode_dev, inference_dev, pipeline = match.groups()
                key = (decode_dev, inference_dev)
                pipelines[key] = pipeline.strip()
    
    return pipelines


def normalize_pipeline(pipeline):
    """Normalize pipeline string for comparison (remove extra whitespace)."""
    # Replace multiple spaces with single space and strip
    normalized = re.sub(r'\s+', ' ', pipeline.strip())
    return normalized


def test_all_combinations():
    """Test all possible combinations of decode and inference devices."""
    
    print("Loading reference pipelines from pipelines.txt...")
    reference_pipelines = load_reference_pipelines()
    
    print(f"Found {len(reference_pipelines)} reference pipelines")
    print()
    
    # All possible combinations
    decode_devices = ['CPU', 'AUTO', 'GPU']
    inference_devices = ['CPU', 'GPU']
    
    all_passed = True
    
    for decode_dev in decode_devices:
        for inference_dev in inference_devices:
            print(f"Testing: Decode={decode_dev}, Inference={inference_dev}")
            
            # Generate pipeline using our script
            try:
                generated = generate_pipeline(decode_dev, inference_dev)
                generated_normalized = normalize_pipeline(generated)
            except Exception as e:
                print(f"  ERROR: Failed to generate pipeline: {e}")
                all_passed = False
                continue
            
            # Get reference pipeline
            key = (decode_dev, inference_dev)
            if key not in reference_pipelines:
                print(f"  ERROR: No reference pipeline found for {key}")
                all_passed = False
                continue
                
            reference = reference_pipelines[key]
            reference_normalized = normalize_pipeline(reference)
            
            # Compare
            if generated_normalized == reference_normalized:
                print(f"  ✓ PASS")
            else:
                print(f"  ✗ FAIL")
                print(f"    Generated: {generated_normalized}")
                print(f"    Reference: {reference_normalized}")
                print(f"    Difference found!")
                all_passed = False
            
            print()
    
    if all_passed:
        print("🎉 All tests PASSED!")
        return True
    else:
        print("❌ Some tests FAILED!")
        return False


def main():
    """Main test function."""
    print("Pipeline Generator Test Suite")
    print("=" * 40)
    
    success = test_all_combinations()
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()