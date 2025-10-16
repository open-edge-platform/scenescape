#!/usr/bin/env python3
"""
GStreamer Pipeline Generator

Generates GStreamer pipeline templates based on decode and inference device configurations.
"""

import argparse
import sys


def generate_pipeline(decode_device, inference_device):
    """
    Generate a GStreamer pipeline template based on device configurations.
    
    Args:
        decode_device (str): Decode device - one of 'CPU', 'GPU', 'AUTO'
        inference_device (str): Inference device - one of 'CPU', 'GPU'
        
    Returns:
        str: Complete GStreamer pipeline template
    """
    
    # Validate inputs
    if decode_device not in ['CPU', 'GPU', 'AUTO']:
        raise ValueError(f"Invalid decode_device: {decode_device}. Must be one of: CPU, GPU, AUTO")
    
    if inference_device not in ['CPU', 'GPU']:
        raise ValueError(f"Invalid inference_device: {inference_device}. Must be one of: CPU, GPU")
    
    # Master Rule Set Implementation
    
    # Rule 1: Decoder selection
    if decode_device == "CPU":
        decoder = "decodebin force-sw-decoders=true"
    else:  # AUTO or GPU
        decoder = "decodebin3"
    
    # Rule 2: Pre-inference vapostproc
    pre_inference_vapostproc = (decode_device == "GPU")
    
    # Rule 3: Memory type and preprocessing
    memory_uses_va_surfaces = (decode_device != "CPU" and inference_device == "GPU")
    
    if memory_uses_va_surfaces:
        memory_caps = "video/x-raw(memory:VAMemory)"
        preprocessing = "pre-process-backend=va-surface-sharing"
    else:
        memory_caps = "video/x-raw"
        if inference_device == "GPU":
            preprocessing = "pre-process-backend=opencv"
        else:
            preprocessing = ""
    
    # Rule 4: Post-inference processing
    post_inference_conversion = (inference_device == "GPU")
    
    # Build pipeline components
    components = []
    
    # Source
    components.append("<source>")
    
    # Decoder
    components.append(decoder)
    
    # Pre-inference vapostproc (for GPU decode)
    if pre_inference_vapostproc:
        components.append("vapostproc")
    
    # Memory caps
    components.append(memory_caps)
    
    # Pre-processing python
    components.append("gvapython ...")
    
    # Inference with device and preprocessing
    inference_part = f"gvadetect model=... device={inference_device}"
    if preprocessing:
        inference_part += f" {preprocessing}"
    components.append(inference_part)
    
    # Queue and metadata conversion
    components.append("queue")
    components.append("gvametaconvert ...")
    
    # Post-inference format conversion (for GPU inference)
    if post_inference_conversion:
        components.extend([
            "vapostproc",
            "video/x-raw,format=BGRA",
            "videoconvert",
            "video/x-raw,format=BGR"
        ])
    
    # Post-processing python and sink
    components.extend([
        "gvapython class=PostInferenceDataPublish ...",
        "appsink ..."
    ])
    
    # Join with GStreamer pipeline syntax
    pipeline = " ! ".join(components)
    
    return pipeline


def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate GStreamer pipeline templates based on device configurations"
    )
    parser.add_argument(
        "decode_device",
        choices=["CPU", "GPU", "AUTO"],
        help="Decode device (CPU, GPU, or AUTO)"
    )
    parser.add_argument(
        "inference_device", 
        choices=["CPU", "GPU"],
        help="Inference device (CPU or GPU)"
    )
    
    args = parser.parse_args()
    
    try:
        pipeline = generate_pipeline(args.decode_device, args.inference_device)
        print(f"Decode device {args.decode_device}, inference device {args.inference_device}: {pipeline}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()