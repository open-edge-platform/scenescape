# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Optional OpenVINO feature extraction from labeled person crops."""

import hashlib
import importlib.metadata
from pathlib import Path
import time

import numpy as np


def file_sha256(path):
  """Hash a model, image, or manifest without loading the entire file into memory."""
  digest = hashlib.sha256()
  with Path(path).open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def extract_embeddings(samples, manifest_dir, model_path, device="CPU", color_order="BGR",
                       layout="NCHW", pixel_scale=1.0, mean=(0, 0, 0), std=(1, 1, 1),
                       warmup=5, output_name=None):
  """Extract one vector per crop and record the exact preprocessing and runtime."""
  try:
    import openvino as ov
    from PIL import Image
  except ImportError as error:
    raise ValueError(
        "Image inference requires OpenVINO and Pillow; install requirements.txt") from error
  if warmup < 0 or not np.isfinite([pixel_scale, *mean, *std]).all() or any(value <= 0 for value in std):
    raise ValueError("Preprocessing must be finite, std positive, and warmup non-negative")
  model_path = Path(model_path).resolve()
  if model_path.suffix.lower() != ".xml":
    raise ValueError("Provide an OpenVINO IR .xml model and its adjacent .bin weights")
  weights = model_path.with_suffix(".bin")
  model_hashes = {"xml_sha256": file_sha256(model_path), "bin_sha256": file_sha256(weights)}
  compiled = ov.Core().compile_model(str(model_path), device)
  if len(compiled.inputs) != 1:
    raise ValueError("Only single-input ReID models are supported")
  input_port = compiled.input(0)
  shape = tuple(input_port.shape)
  if len(shape) != 4:
    raise ValueError("ReID model must have a static four-dimensional image input")
  channels = shape[1] if layout == "NCHW" else shape[-1]
  if shape[0] != 1 or channels != 3 or min(shape) <= 0:
    raise ValueError("ReID model must have a static, batch-one, three-channel image input")
  height, width = shape[2:4] if layout == "NCHW" else shape[1:3]
  input_dtype = input_port.element_type.to_dtype()
  if not np.issubdtype(input_dtype, np.floating) and (
          pixel_scale != 1 or any(mean) or tuple(std) != (1, 1, 1)):
    raise ValueError("Integer model inputs require unmodified 0-255 preprocessing")
  if output_name is None and len(compiled.outputs) != 1:
    raise ValueError("Multi-output models require --output-name")
  output_port = compiled.output(output_name) if output_name else compiled.output(0)
  request = compiled.create_infer_request()
  inference_ms = []
  preprocessing_ms = []
  prepared = []
  image_splits = {}
  for sample in samples:
    image_path = Path(sample["image"])
    image_path = image_path if image_path.is_absolute() else manifest_dir / image_path
    image_hash = file_sha256(image_path)
    if image_hash in image_splits and image_splits[image_hash] != sample["split"]:
      raise ValueError("The same source image appears in multiple splits")
    image_splits[image_hash] = sample["split"]
    started = time.perf_counter()
    with Image.open(image_path) as image:
      pixels = np.asarray(image.convert("RGB").resize((width, height), Image.Resampling.BILINEAR),
                          dtype=np.float32)
    if color_order == "BGR":
      pixels = pixels[..., ::-1]
    pixels = (pixels * pixel_scale - np.asarray(mean, dtype=np.float32)) / \
        np.asarray(std, dtype=np.float32)
    tensor = pixels.transpose(2, 0, 1)[None] if layout == "NCHW" else pixels[None]
    tensor = np.ascontiguousarray(tensor, dtype=input_dtype)
    preprocessing_ms.append((time.perf_counter() - started) * 1000)
    if not prepared:
      for _ in range(warmup):
        request.infer({input_port: tensor})
    started = time.perf_counter()
    result = request.infer({input_port: tensor})
    inference_ms.append((time.perf_counter() - started) * 1000)
    embedding = np.asarray(result[output_port], dtype=np.float32).reshape(-1)
    row = {key: value for key, value in sample.items() if key != "image"}
    row.update(embedding=embedding.tolist(), source_image_sha256=image_hash)
    prepared.append(row)

  def timing(values):
    return {"mean": float(np.mean(values)), "p50": float(np.percentile(values, 50)),
            "p95": float(np.percentile(values, 95)), "p99": float(np.percentile(values, 99))}

  return prepared, {
      **model_hashes, "artifact": model_path.name, "device": device,
      "output_names": sorted(output_port.names), "output_shape": list(output_port.shape),
      "openvino_version": importlib.metadata.version("openvino"),
      "preprocessing": {"color_order": color_order, "layout": layout, "input_shape": list(shape),
                        "dtype": np.dtype(input_dtype).name, "resize": "Pillow bilinear",
                        "pillow_version": importlib.metadata.version("Pillow"),
                        "pixel_scale": pixel_scale, "mean": list(mean), "std": list(std)},
  }, {
      "source": "measured_crop_inference", "warmup_iterations": warmup,
      "inference_ms": timing(inference_ms), "preprocessing_ms": timing(preprocessing_ms),
      "serial_inference_crops_per_second": 1000 / float(np.mean(inference_ms)),
  }
