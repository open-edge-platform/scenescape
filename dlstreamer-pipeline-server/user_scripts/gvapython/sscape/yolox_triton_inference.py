#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Nokia
# SPDX-License-Identifier: Apache-2.0
"""
TensorRT End-to-End Model Inference via Triton Server

Integrates TensorRT e2e models (with EfficientNMS_TRT baked in) with
DLStreamer Pipeline Server via Triton Inference Server.

Supports any detection model that outputs the standard e2e format:
  num_dets, det_boxes, det_scores, det_classes
This includes YOLOX, YOLOv7-e2e, and other models with NMS on GPU.

Features:
- gRPC communication with Triton Server
- DALI ensemble support (preprocessing on GPU)
- Base64 configuration injection for GStreamer
- Label filtering
- Per-stage latency measurements
"""

import json
import base64
import logging
import numpy as np
import time
import os
from typing import List, Dict
from collections import deque

try:
  import tritonclient.grpc as grpcclient
  from tritonclient.utils import InferenceServerException
  TRITON_AVAILABLE = True
except ImportError:
  TRITON_AVAILABLE = False
  grpcclient = None
  InferenceServerException = Exception

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - [%(levelname)s] - %(message)s'
)

logger = logging.getLogger('yolox_triton_inference')

# =============================================================================
# Fine-Grained Latency Instrumentation
# =============================================================================
ENABLE_TIMING = os.environ.get('TRITON_ENABLE_TIMING', '1') == '1'
TIMING_WINDOW_SIZE = 100

class TimingStats:
  """Rolling window statistics for latency measurements."""
  def __init__(self, window_size=TIMING_WINDOW_SIZE):
    self.window_size = window_size
    self.preprocess_times = deque(maxlen=window_size)
    self.grpc_submit_times = deque(maxlen=window_size)
    self.gpu_inference_times = deque(maxlen=window_size)
    self.postprocess_times = deque(maxlen=window_size)
    self.total_times = deque(maxlen=window_size)
    self.frame_count = 0
    self.last_report_time = time.time()
    self.report_interval = 10.0

  def record(self, preprocess_ms, grpc_submit_ms, gpu_inference_ms, postprocess_ms, total_ms):
    self.preprocess_times.append(preprocess_ms)
    self.grpc_submit_times.append(grpc_submit_ms)
    self.gpu_inference_times.append(gpu_inference_ms)
    self.postprocess_times.append(postprocess_ms)
    self.total_times.append(total_ms)
    self.frame_count += 1

  def should_report(self):
    now = time.time()
    if now - self.last_report_time >= self.report_interval:
      self.last_report_time = now
      return True
    return False

  def get_stats(self):
    def calc_percentiles(data):
      if not data:
        return {'avg': 0, 'p50': 0, 'p95': 0, 'p99': 0, 'min': 0, 'max': 0}
      arr = np.array(data)
      return {
          'avg': float(np.mean(arr)),
          'p50': float(np.percentile(arr, 50)),
          'p95': float(np.percentile(arr, 95)),
          'p99': float(np.percentile(arr, 99)),
          'min': float(np.min(arr)),
          'max': float(np.max(arr))
      }
    return {
        'preprocess': calc_percentiles(self.preprocess_times),
        'grpc_submit': calc_percentiles(self.grpc_submit_times),
        'gpu_inference': calc_percentiles(self.gpu_inference_times),
        'postprocess': calc_percentiles(self.postprocess_times),
        'total': calc_percentiles(self.total_times),
        'frame_count': self.frame_count,
        'window_frames': len(self.total_times)
    }

_timing_stats = TimingStats() if ENABLE_TIMING else None

# COCO dataset class labels (80 classes)
COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
    'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
    'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
    'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
    'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake',
    'chair', 'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop',
    'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier',
    'toothbrush'
]

class TritonClient:
  """
  Triton Inference Server client for e2e TensorRT model inference.
  Works with any model outputting: num_dets, det_boxes, det_scores, det_classes.
  """
  def __init__(self, config):
    self.server_url = config.get('triton_url', 'localhost:8001')
    self.conf_thresh = float(config.get('confidence_threshold', 0.25))
    self.input_width = int(config.get('input_width', 640))
    self.input_height = int(config.get('input_height', 640))

    # DALI Ensemble mode: preprocessing runs on GPU inside Triton
    self.use_ensemble = config.get('use_ensemble', False)
    if self.use_ensemble:
      self.model_name = config.get('ensemble_model_name', 'yolox_s_ensemble')
      self.input_name = 'INPUT_IMAGES'
    else:
      self.model_name = config.get('model_name', 'yolox_s_fp16')
      self.input_name = config.get('input_name', 'images')

    self.output_names = ['num_dets', 'det_boxes', 'det_scores', 'det_classes']
    logger.info(f"Triton e2e model: {self.model_name}, ensemble={self.use_ensemble}")

    # Label filtering
    labels_config = config.get('labels', None)
    if labels_config is None:
      self.allowed_labels = None
    elif isinstance(labels_config, list):
      self.allowed_labels = set(label.lower().strip() for label in labels_config)
    elif isinstance(labels_config, str):
      self.allowed_labels = set(label.lower().strip() for label in labels_config.split(','))
    else:
      self.allowed_labels = None

    if self.allowed_labels:
      logger.info(f"Label filtering enabled. Allowed labels: {self.allowed_labels}")

    self.client = None
    if TRITON_AVAILABLE:
      try:
        self.client = grpcclient.InferenceServerClient(url=self.server_url)
        if not self.client.is_model_ready(self.model_name):
          logger.warning(f"Model {self.model_name} not ready yet.")
        else:
          logger.info(f"Connected to Triton: {self.server_url}")
      except Exception as e:
        logger.error(f"Triton Connection Error: {e}")

  def infer(self, frame_data, width, height):
    """Run inference on a single frame with timing instrumentation."""
    global _timing_stats
    if not self.client: return []

    t_total_start = time.perf_counter() if ENABLE_TIMING else 0

    # =========== STAGE 1: Preprocess ===========
    t_preprocess_start = time.perf_counter() if ENABLE_TIMING else 0

    if self.use_ensemble:
      # DALI Ensemble: send raw UINT8 BGR HWC frame
      input_tensor = np.expand_dims(frame_data, axis=0)
      input_dtype = "UINT8"
    else:
      # Direct TensorRT: send FP16 CHW tensor
      # YOLOX expects BGR [0, 255] — no color conversion, no normalization.
      input_tensor = frame_data.transpose(2, 0, 1).astype(np.float16)
      input_tensor = np.expand_dims(input_tensor, axis=0)
      input_dtype = "FP16"

    t_preprocess_end = time.perf_counter() if ENABLE_TIMING else 0

    # =========== STAGE 2: gRPC Submit ===========
    t_grpc_submit_start = time.perf_counter() if ENABLE_TIMING else 0

    inputs = [grpcclient.InferInput(self.input_name, input_tensor.shape, input_dtype)]
    inputs[0].set_data_from_numpy(input_tensor)
    outputs = [grpcclient.InferRequestedOutput(name) for name in self.output_names]

    t_grpc_submit_end = time.perf_counter() if ENABLE_TIMING else 0

    try:
      # =========== STAGE 3: GPU Inference ===========
      t_gpu_start = time.perf_counter() if ENABLE_TIMING else 0
      res = self.client.infer(self.model_name, inputs, outputs=outputs)
      t_gpu_end = time.perf_counter() if ENABLE_TIMING else 0

      # =========== STAGE 4: Postprocess ===========
      t_postprocess_start = time.perf_counter() if ENABLE_TIMING else 0
      detections = self.postprocess_e2e(res, width, height)

      # Apply label filtering
      if self.allowed_labels:
        detections = [d for d in detections if d['label'].lower() in self.allowed_labels]

      t_postprocess_end = time.perf_counter() if ENABLE_TIMING else 0
      t_total_end = time.perf_counter() if ENABLE_TIMING else 0

      # =========== TIMING: Record and Report ===========
      if ENABLE_TIMING and _timing_stats:
        preprocess_ms = (t_preprocess_end - t_preprocess_start) * 1000
        grpc_submit_ms = (t_grpc_submit_end - t_grpc_submit_start) * 1000
        gpu_inference_ms = (t_gpu_end - t_gpu_start) * 1000
        postprocess_ms = (t_postprocess_end - t_postprocess_start) * 1000
        total_ms = (t_total_end - t_total_start) * 1000

        _timing_stats.record(preprocess_ms, grpc_submit_ms, gpu_inference_ms, postprocess_ms, total_ms)

        if _timing_stats.should_report():
          stats = _timing_stats.get_stats()
          logger.info(
              f"[TIMING] Last {stats['window_frames']} frames | "
              f"Total: avg={stats['total']['avg']:.1f}ms p95={stats['total']['p95']:.1f}ms p99={stats['total']['p99']:.1f}ms | "
              f"GPU: avg={stats['gpu_inference']['avg']:.1f}ms p95={stats['gpu_inference']['p95']:.1f}ms | "
              f"Preproc: {stats['preprocess']['avg']:.2f}ms | "
              f"gRPC: {stats['grpc_submit']['avg']:.2f}ms | "
              f"Postproc: {stats['postprocess']['avg']:.2f}ms"
          )

      return detections
    except Exception as e:
      logger.error(f"Inference failed: {e}")
      return []

  def postprocess_e2e(self, result, img_w, img_h):
    """
    Process e2e model output (NMS already done on GPU via EfficientNMS_TRT).
    Output tensors: num_dets, det_boxes, det_scores, det_classes

    Works with any model using this output format (YOLOX, YOLOv7-e2e, etc).
    DLStreamer pipeline already resized frame to input dims, so no scaling needed.
    """
    try:
      num_dets = result.as_numpy('num_dets')[0][0]
      det_boxes = result.as_numpy('det_boxes')[0]    # [100, 4] x1,y1,x2,y2
      det_scores = result.as_numpy('det_scores')[0]  # [100]
      det_classes = result.as_numpy('det_classes')[0] # [100]
    except Exception as e:
      logger.error(f"E2E output parsing failed: {e}")
      return []

    detections = []
    for i in range(int(num_dets)):
      score = float(det_scores[i])
      if score < self.conf_thresh:
        continue

      x1, y1, x2, y2 = det_boxes[i]
      x1 = max(0, min(int(x1), img_w))
      y1 = max(0, min(int(y1), img_h))
      x2 = max(0, min(int(x2), img_w))
      y2 = max(0, min(int(y2), img_h))

      w = x2 - x1
      h = y2 - y1
      if w <= 0 or h <= 0:
        continue

      class_id = int(det_classes[i])
      label = COCO_CLASSES[class_id] if class_id < len(COCO_CLASSES) else f"class_{class_id}"

      detections.append({
          "x": x1,
          "y": y1,
          "w": w,
          "h": h,
          "confidence": score,
          "label": label
      })

    return detections

class process_frame:
  """
  GStreamer integration for Triton e2e inference.
  Processes video frames and attaches detection metadata.
  """
  def __init__(self, *args, **kwargs):
    self.target_dim = 640
    config = {}

    # Parse base64 configuration from args
    if args and len(args) > 0:
      config_data = args[0]
      try:
        import base64
        if config_data.startswith('b64='):
          config_data = config_data[4:]
        json_bytes = base64.b64decode(config_data)
        json_str = json_bytes.decode('utf-8')
        config = json.loads(json_str)
        logger.info(f"Triton config loaded from args: {config.get('triton_url', 'unknown')}")
      except Exception as e:
        logger.error(f"Argument parsing failed: {e}")

    elif 'kwarg' in kwargs:
      kw = kwargs['kwarg']
      try:
        if isinstance(kw, str) and kw.startswith('b64='):
          import base64
          b64_data = kw[4:]
          json_bytes = base64.b64decode(b64_data)
          json_str = json_bytes.decode('utf-8')
          config = json.loads(json_str)
          logger.info(f"Triton config loaded from kwarg: {config.get('triton_url', 'unknown')}")
        elif isinstance(kw, dict):
          config = kw
        else:
          config = json.loads(kw.replace("'", '"'))
      except Exception as e:
        logger.error(f"Kwarg parsing failed: {e}")

    if config is None: config = {}
    self.client = TritonClient(config)

  def process_frame(self, frame, caps=None):
    if self.client is None: return True
    try:
      with frame.data() as mat:
        img_bgr = np.array(mat, copy=True)
        height, width = img_bgr.shape[:2]

      detections = self.client.infer(img_bgr, width, height)

      for d in detections:
        frame.add_region(d['x'], d['y'], d['w'], d['h'], d['label'], d['confidence'])

      if detections:
        logger.debug(f"Triton inference: {len(detections)} objects detected")
      return True
    except Exception as e:
      logger.error(f"Processing error: {e}")
    return True

# Singleton Entry Point
_processor_instance = None

def init_and_process(frame, kwarg=None):
  global _processor_instance
  if _processor_instance is None:
    _processor_instance = process_frame(kwarg=kwarg)

  return _processor_instance.process_frame(frame)
