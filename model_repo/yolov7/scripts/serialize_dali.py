#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Nokia
# SPDX-License-Identifier: Apache-2.0
"""
Serialize DALI preprocessing pipeline for YOLOv7 on Triton.

Run this inside the Triton container (or any container with nvidia-dali).

YOLOv7 preprocessing:
  1. Normalize [0, 255] -> [0, 1] (std=[255, 255, 255])
  2. HWC -> CHW layout conversion
  3. Cast to FP16 (engine built with --inputIOFormats=fp16:chw)
  4. BGR -> RGB channel reorder (fn.slice + fn.cat)

Usage:
    python serialize_dali.py --output model.dali
    python serialize_dali.py --output model.dali --input-size 1280  # for w6/e6/d6/e6e

Requires: nvidia-dali (pre-installed in Triton container)
"""

import argparse

import nvidia.dali as dali
import nvidia.dali.fn as fn
import nvidia.dali.types as types


def parse_args():
  parser = argparse.ArgumentParser(description="Serialize YOLOv7 DALI pipeline")
  parser.add_argument("--output", type=str, required=True,
                      help="Output model.dali file path")
  parser.add_argument("--batch-size", type=int, default=32,
                      help="Max batch size (default: 32)")
  parser.add_argument("--input-size", type=int, default=640,
                      help="Input image size (default: 640)")
  return parser.parse_args()


def main():
  args = parse_args()

  @dali.pipeline_def(batch_size=args.batch_size, num_threads=4, device_id=0)
  def yolov7_preprocess():
    images = fn.external_source(device="gpu", name="INPUT_IMAGES",
                                dtype=types.UINT8, ndim=3)
    # YOLOv7 expects RGB [0, 1] input.
    # Step 1: Normalize [0, 255] -> [0, 1], HWC -> CHW, cast to FP16
    images = fn.crop_mirror_normalize(images, dtype=types.FLOAT16,
                                      output_layout="CHW",
                                      mean=[0.0, 0.0, 0.0],
                                      std=[255.0, 255.0, 255.0])
    # Step 2: BGR -> RGB by slicing and re-concatenating channels
    # fn.flip does not support float16; fn.slice+cat is the correct approach.
    # After CHW: channel 0=B, channel 1=G, channel 2=R
    ch_r = fn.slice(images, start=[2, 0, 0],
                    shape=[1, args.input_size, args.input_size],
                    axes=[0, 1, 2])
    ch_g = fn.slice(images, start=[1, 0, 0],
                    shape=[1, args.input_size, args.input_size],
                    axes=[0, 1, 2])
    ch_b = fn.slice(images, start=[0, 0, 0],
                    shape=[1, args.input_size, args.input_size],
                    axes=[0, 1, 2])
    images = fn.cat(ch_r, ch_g, ch_b, axis=0)
    return images

  pipe = yolov7_preprocess()
  pipe.build()
  pipe.serialize(filename=args.output)

  print(f"Saved: {args.output}")
  print(f"  Input:  UINT8 BGR HWC [{args.input_size}, {args.input_size}, 3]")
  print(f"  Output: FP16  RGB CHW [3, {args.input_size}, {args.input_size}]")
  print(f"  Normalization: divide by 255 ([0, 255] -> [0, 1])")
  print(f"  Color conversion: BGR -> RGB (channel reverse)")
  print(f"  Max batch size: {args.batch_size}")


if __name__ == "__main__":
  main()
