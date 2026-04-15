#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Nokia
# SPDX-License-Identifier: Apache-2.0
"""
TensorRT Model Inference via Triton Server

Integrates any TensorRT model with DLStreamer Pipeline Server via Triton Inference Server.
Supports YOLO-family models with end-to-end NMS (NMS runs on GPU, not CPU).
"""

import json
import base64
import logging
import numpy as np
import cv2
import time
import os
from typing import List, Dict, Tuple, Optional
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

logger = logging.getLogger('yolov7_triton_inference')

# Per-stage latency instrumentation: preprocess / gRPC / GPU inference / postprocess.
ENABLE_TIMING = os.environ.get('TRITON_ENABLE_TIMING', '1') == '1'

# Rolling statistics for timing (last N frames)
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
    self.report_interval = 10.0  # Report every 10 seconds

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
    """Returns avg/p50/p95/p99 for each timing category."""
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

# Global timing stats instance
_timing_stats = TimingStats() if ENABLE_TIMING else None

# YOLOv7 Model Architecture Constants (only used for legacy non-e2e models)
YOLOV7_ANCHORS = [
    [[12, 16], [19, 36], [40, 28]],       # Feature map stride 8 (fine-grained detection)
    [[36, 75], [76, 55], [72, 146]],      # Feature map stride 16 (medium objects)
    [[142, 110], [192, 243], [459, 401]]  # Feature map stride 32 (large objects)
]
STRIDES = [8, 16, 32]

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
  Triton Inference Server client for TensorRT model inference.
  Supports YOLO-family models with END-TO-END NMS (GPU) or legacy anchor-based postprocessing.
  """
  def __init__(self, config):
    self.server_url = config.get('triton_url', 'localhost:8001')
    self.conf_thresh = float(config.get('confidence_threshold', 0.25))
    self.nms_thresh = float(config.get('nms_threshold', 0.45))
    self.input_width = int(config.get('input_width', 640))
    self.input_height = int(config.get('input_height', 640))

    # DALI Ensemble mode: preprocessing (BGR→RGB, normalize, FP16) runs on GPU
    # inside Triton's CUDA context via DALI backend, eliminating ~21ms CPU
    # preprocessing + reducing gRPC transfer (uint8 vs FP16 = 50% smaller)
    self.use_ensemble = config.get('use_ensemble', False)
    if self.use_ensemble:
      self.model_name = config.get('ensemble_model_name', 'yolov7_ensemble')
      self.input_name = 'INPUT_IMAGES'
      self.output_names = ['num_dets', 'det_boxes', 'det_scores', 'det_classes']
      logger.info(f"DALI Ensemble mode: model={self.model_name}, input={self.input_name}")
    else:
      self.model_name = config.get('model_name', 'yolov7_tiny_fp16')
      self.input_name = config.get('input_name', 'images')
      self.output_names = config.get('output_names', 'output0,output1,output2').split(',')

    # Detect if this is an end-to-end model (NMS on GPU)
    # E2E models have outputs: num_dets, det_boxes, det_scores, det_classes
    self.is_e2e_model = 'num_dets' in self.output_names or 'det_boxes' in self.output_names
    if self.is_e2e_model:
      logger.info(f"End-to-end model detected (NMS on GPU). Output names: {self.output_names}")
    else:
      logger.info(f"Legacy model detected (NMS on CPU). Output names: {self.output_names}")

    # Label filtering: if specified, only these labels will be forwarded
    # Can be a list or comma-separated string
    labels_config = config.get('labels', None)
    if labels_config is None:
      self.allowed_labels = None  # No filtering, allow all labels
    elif isinstance(labels_config, list):
      self.allowed_labels = set(label.lower().strip() for label in labels_config)
    elif isinstance(labels_config, str):
      self.allowed_labels = set(label.lower().strip() for label in labels_config.split(','))
    else:
      self.allowed_labels = None

    if self.allowed_labels:
      logger.info(f"Label filtering enabled. Allowed labels: {self.allowed_labels}")
    else:
      logger.info("Label filtering disabled. All detected objects will be forwarded.")

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
    """
    Run inference on a single frame with fine-grained timing instrumentation.

    Timing breakdown (per-stage latency):
    - preprocess_ms: BGR→RGB + normalize + tensor creation
    - grpc_submit_ms: gRPC request serialization and send
    - gpu_inference_ms: Triton server processing (queue + GPU compute)
    - postprocess_ms: Result parsing + NMS (for legacy) + filtering

    Returns: List of detections with bounding boxes
    """
    global _timing_stats
    if not self.client: return []

    # =========== TIMING: Start total ===========
    t_total_start = time.perf_counter() if ENABLE_TIMING else 0

    # =========== STAGE 1: Preprocess ===========
    t_preprocess_start = time.perf_counter() if ENABLE_TIMING else 0

    if self.use_ensemble:
      # DALI Ensemble: send raw uint8 BGR HWC frame to Triton
      # DALI pipeline on GPU handles: BGR→RGB + normalize + HWC→CHW + FP16
      # This eliminates ~21ms of CPU numpy work
      input_tensor = np.expand_dims(frame_data, axis=0)  # Add batch dim: (1, H, W, 3)
      input_dtype = "UINT8"
    else:
      # Direct TensorRT: CPU preprocessing (legacy path)
      rgb = cv2.cvtColor(frame_data, cv2.COLOR_BGR2RGB)
      input_tensor = rgb.transpose(2, 0, 1).astype(np.float16) / 255.0
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
      # =========== STAGE 3: GPU Inference (includes network RTT + queue + compute) ===========
      t_gpu_start = time.perf_counter() if ENABLE_TIMING else 0

      res = self.client.infer(self.model_name, inputs, outputs=outputs)

      t_gpu_end = time.perf_counter() if ENABLE_TIMING else 0

      # =========== STAGE 4: Postprocess ===========
      t_postprocess_start = time.perf_counter() if ENABLE_TIMING else 0

      if self.is_e2e_model:
        # End-to-end model: NMS already done on GPU
        # width/height here are the original image dimensions (640x640 after pipeline resize)
        detections = self.postprocess_e2e(res, width, height)
      else:
        # Legacy model: anchor-based decoding + CPU NMS
        results = [res.as_numpy(name) for name in self.output_names]
        detections = self.postprocess_legacy(results, width, height)

      # Apply label filtering if configured
      if self.allowed_labels:
        filtered_detections = [
            d for d in detections
            if d['label'].lower() in self.allowed_labels
        ]
        if len(detections) != len(filtered_detections):
          logger.debug(f"Label filter: {len(detections)} -> {len(filtered_detections)} detections")
        detections = filtered_detections

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

        # Log periodic timing report
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
    Process end-to-end model output (NMS already done on GPU).
    Output tensors: num_dets, det_boxes, det_scores, det_classes

    This is ~2000x faster than legacy postprocessing because:
    - No anchor decoding needed
    - No NMS computation on CPU
    - Output is only ~4KB vs 8.2MB for raw tensors

    Note: DLStreamer pipeline already resized frame to 640x640,
    so img_w and img_h should be 640x640. No scaling needed.
    """
    try:
      num_dets = result.as_numpy('num_dets')[0][0]  # Scalar: number of detections
      det_boxes = result.as_numpy('det_boxes')[0]   # [100, 4] - x1, y1, x2, y2
      det_scores = result.as_numpy('det_scores')[0] # [100] - confidence scores
      det_classes = result.as_numpy('det_classes')[0]  # [100] - class IDs
    except Exception as e:
      logger.error(f"E2E output parsing failed: {e}")
      return []

    detections = []
    for i in range(int(num_dets)):
      score = float(det_scores[i])
      if score < self.conf_thresh:
        continue

      # Box coordinates are in model input space (640x640)
      # Since DLStreamer already resized to 640x640, no scaling needed
      x1, y1, x2, y2 = det_boxes[i]

      # Convert to integers
      x1 = int(x1)
      y1 = int(y1)
      x2 = int(x2)
      y2 = int(y2)

      # Clamp to image bounds
      x1 = max(0, min(x1, img_w))
      y1 = max(0, min(y1, img_h))
      x2 = max(0, min(x2, img_w))
      y2 = max(0, min(y2, img_h))

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

  def postprocess_legacy(self, outputs, img_w, img_h):
    """
    Convert raw TensorRT model outputs to bounding boxes.
    Uses anchor-based decoding with class-aware NMS.

    NOTE: This is the LEGACY path for models without end-to-end NMS.
    For better performance, use end-to-end models (yolov7_tiny_e2e_v*).

    Note: DLStreamer pipeline already resized frame to 640x640,
    so img_w and img_h should be 640x640. No scaling needed.
    """
    all_boxes = []
    all_scores = []
    all_class_ids = []

    for i, output in enumerate(outputs):
      stride = STRIDES[i]
      anchors = YOLOV7_ANCHORS[i]
      batch, num_anchors, grid_h, grid_w, _ = output.shape

      for a in range(num_anchors):
        for y in range(grid_h):
          for x in range(grid_w):
            row = output[0, a, y, x]
            obj_conf = row[4]
            if obj_conf < self.conf_thresh: continue

            classes = row[5:]
            class_id = np.argmax(classes)
            score = obj_conf * classes[class_id]
            if score < self.conf_thresh: continue

            # Anchor-based coordinate decoding
            cx = (2 * (1/(1+np.exp(-row[0]))) - 0.5 + x) * stride
            cy = (2 * (1/(1+np.exp(-row[1]))) - 0.5 + y) * stride
            w = (2 * (1/(1+np.exp(-row[2])))) ** 2 * anchors[a][0]
            h = (2 * (1/(1+np.exp(-row[3])))) ** 2 * anchors[a][1]

            # No scaling needed - frame is already 640x640
            x1 = int(cx - w/2)
            y1 = int(cy - h/2)

            all_boxes.append([x1, y1, int(w), int(h)])
            all_scores.append(float(score))
            all_class_ids.append(class_id)

    # Class-aware NMS: offset each box by class_id*max_wh so boxes of
    # different classes never overlap in NMS space and suppress independently.
    max_wh = 4096
    boxes_for_nms = []
    for i, box in enumerate(all_boxes):
      c_offset = all_class_ids[i] * max_wh
      boxes_for_nms.append([box[0] + c_offset, box[1] + c_offset, box[2], box[3]])

    # Apply NMS
    indices = cv2.dnn.NMSBoxes(boxes_for_nms, all_scores, self.conf_thresh, self.nms_thresh)

    final_detections = []
    if len(indices) > 0:
      # OpenCV NMS may return tuple, list, or ndarray across versions.
      idx_list = indices.flatten() if hasattr(indices, 'flatten') else indices

      for i in idx_list:
        # Use the original (non-offset) box -- the offset was only for NMS space.
        box = all_boxes[i]
        final_detections.append({
            "x": max(0, box[0]),
            "y": max(0, box[1]),
            "w": min(box[2], img_w - box[0]),
            "h": min(box[3], img_h - box[1]),
            "confidence": all_scores[i],
            "label": COCO_CLASSES[all_class_ids[i]]
        })
    return final_detections

class process_frame:
  """
  GStreamer integration for Triton TensorRT inference.
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

    # Check keyword arguments
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
          # Legacy fallback
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
    # Pass kwarg correctly to constructor
    _processor_instance = process_frame(kwarg=kwarg)

  return _processor_instance.process_frame(frame)
