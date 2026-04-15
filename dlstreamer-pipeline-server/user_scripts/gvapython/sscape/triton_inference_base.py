#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Nokia
# SPDX-License-Identifier: Apache-2.0
"""
Base classes for TensorRT model inference via Triton Server.

Provides reusable infrastructure for all Triton inference scripts:
- TimingStats: rolling-window latency instrumentation
- TritonClientBase: gRPC client with e2e and legacy postprocessing
- ProcessFrameBase: GStreamer gvapython integration
- init_and_process factory: singleton entry point

Model-specific scripts inherit from these and override only:
- DEFAULT_CLASSES / ANCHORS / STRIDES
- Preprocessing (e.g. YOLOX skips RGB conversion)
- Post-inference classification (e.g. object association logic)
"""

import json
import base64
import logging
import numpy as np
import cv2
import time
import os
from collections import deque

try:
  import tritonclient.grpc as grpcclient
  from tritonclient.utils import InferenceServerException
  TRITON_AVAILABLE = True
except ImportError:
  TRITON_AVAILABLE = False
  grpcclient = None
  InferenceServerException = Exception

# Enable/disable timing via environment variable (default: enabled)
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


class TritonClientBase:
  """
  Base Triton Inference Server client for TensorRT models.

  Subclasses should set class attributes:
      DEFAULT_CLASSES: list of class label strings
      ANCHORS: list of anchor arrays (for legacy postprocessing)
      STRIDES: list of stride ints (for legacy postprocessing)
  """
  DEFAULT_CLASSES = []
  ANCHORS = []
  STRIDES = [8, 16, 32]

  def __init__(self, config, logger, timing_stats=None):
    self.logger = logger
    self._timing_stats = timing_stats
    self.server_url = config.get('triton_url', 'localhost:8001')
    self.conf_thresh = float(config.get('confidence_threshold', 0.25))
    self.nms_thresh = float(config.get('nms_threshold', 0.45))
    self.input_width = int(config.get('input_width', 640))
    self.input_height = int(config.get('input_height', 640))

    # Resolve class labels from config or defaults
    self.class_labels = self._resolve_class_labels(config)

    # Label filtering
    labels_config = config.get('labels', None)
    if labels_config is None:
      self.allowed_labels = None
    elif isinstance(labels_config, list):
      self.allowed_labels = set(l.lower().strip() for l in labels_config) or None
    elif isinstance(labels_config, str):
      self.allowed_labels = set(l.lower().strip() for l in labels_config.split(',')) or None
    else:
      self.allowed_labels = None

    if self.allowed_labels:
      self.logger.info(f"Label filtering enabled. Allowed labels: {self.allowed_labels}")
    else:
      self.logger.info("Label filtering disabled. All detected objects will be forwarded.")

    # DALI Ensemble mode
    self.use_ensemble = config.get('use_ensemble', False)
    if self.use_ensemble:
      self.model_name = config.get('ensemble_model_name', self._default_ensemble_model_name())
      self.input_name = 'INPUT_IMAGES'
      self.output_names = ['num_dets', 'det_boxes', 'det_scores', 'det_classes']
      self.logger.info(f"DALI Ensemble mode: model={self.model_name}, input={self.input_name}")
    else:
      self.model_name = config.get('model_name', self._default_model_name())
      self.input_name = config.get('input_name', 'images')
      self.output_names = config.get('output_names', self._default_output_names()).split(',') \
          if isinstance(config.get('output_names', self._default_output_names()), str) \
          else config.get('output_names', self._default_output_names().split(','))

    # Detect end-to-end model
    self.is_e2e_model = 'num_dets' in self.output_names or 'det_boxes' in self.output_names
    if self.is_e2e_model:
      self.logger.info(f"End-to-end model detected (NMS on GPU). Output names: {self.output_names}")
    else:
      self.logger.info(f"Legacy model detected (NMS on CPU). Output names: {self.output_names}")

    # Connect to Triton
    self.client = None
    if TRITON_AVAILABLE:
      try:
        self.client = grpcclient.InferenceServerClient(url=self.server_url)
        if not self.client.is_model_ready(self.model_name):
          self.logger.warning(f"Model {self.model_name} not ready yet.")
        else:
          self.logger.info(f"Connected to Triton: {self.server_url}")
      except Exception as e:
        self.logger.error(f"Triton Connection Error: {e}")

  def _resolve_class_labels(self, config):
    """Resolve class labels from config, falling back to DEFAULT_CLASSES."""
    return list(self.DEFAULT_CLASSES)

  def _default_model_name(self):
    return 'model_fp16'

  def _default_ensemble_model_name(self):
    return 'model_ensemble'

  def _default_output_names(self):
    return 'output0,output1,output2'

  def preprocess(self, frame_data):
    """
    Preprocess frame for inference. Override for model-specific preprocessing.
    Returns (input_tensor, input_dtype).
    """
    if self.use_ensemble:
      input_tensor = np.expand_dims(frame_data, axis=0)
      return input_tensor, "UINT8"
    else:
      rgb = cv2.cvtColor(frame_data, cv2.COLOR_BGR2RGB)
      input_tensor = rgb.transpose(2, 0, 1).astype(np.float16) / 255.0
      input_tensor = np.expand_dims(input_tensor, axis=0)
      return input_tensor, "FP16"

  def postprocess_detections(self, raw_detections):
    """
    Hook for post-inference classification logic (e.g. object association).
    Default: apply label filtering and return.
    Override in subclasses for model-specific logic.
    """
    if self.allowed_labels:
      filtered = [d for d in raw_detections if d['label'].lower() in self.allowed_labels]
      if len(raw_detections) != len(filtered):
        self.logger.debug(f"Label filter: {len(raw_detections)} -> {len(filtered)} detections")
      return filtered
    return raw_detections

  def infer(self, frame_data, width, height):
    """Run inference with timing instrumentation."""
    if not self.client:
      return []

    t_total_start = time.perf_counter() if ENABLE_TIMING else 0

    # Stage 1: Preprocess
    t_preprocess_start = time.perf_counter() if ENABLE_TIMING else 0
    input_tensor, input_dtype = self.preprocess(frame_data)
    t_preprocess_end = time.perf_counter() if ENABLE_TIMING else 0

    # Stage 2: gRPC Submit
    t_grpc_submit_start = time.perf_counter() if ENABLE_TIMING else 0
    inputs = [grpcclient.InferInput(self.input_name, input_tensor.shape, input_dtype)]
    inputs[0].set_data_from_numpy(input_tensor)
    outputs = [grpcclient.InferRequestedOutput(name) for name in self.output_names]
    t_grpc_submit_end = time.perf_counter() if ENABLE_TIMING else 0

    try:
      # Stage 3: GPU Inference
      t_gpu_start = time.perf_counter() if ENABLE_TIMING else 0
      res = self.client.infer(self.model_name, inputs, outputs=outputs)
      t_gpu_end = time.perf_counter() if ENABLE_TIMING else 0

      # Stage 4: Postprocess
      t_postprocess_start = time.perf_counter() if ENABLE_TIMING else 0

      if self.is_e2e_model:
        raw_detections = self.postprocess_e2e(res, width, height)
      else:
        results = [res.as_numpy(name) for name in self.output_names]
        raw_detections = self.postprocess_legacy(results, width, height)

      detections = self.postprocess_detections(raw_detections)

      t_postprocess_end = time.perf_counter() if ENABLE_TIMING else 0
      t_total_end = time.perf_counter() if ENABLE_TIMING else 0

      # Timing report
      if ENABLE_TIMING and self._timing_stats:
        preprocess_ms = (t_preprocess_end - t_preprocess_start) * 1000
        grpc_submit_ms = (t_grpc_submit_end - t_grpc_submit_start) * 1000
        gpu_inference_ms = (t_gpu_end - t_gpu_start) * 1000
        postprocess_ms = (t_postprocess_end - t_postprocess_start) * 1000
        total_ms = (t_total_end - t_total_start) * 1000

        self._timing_stats.record(preprocess_ms, grpc_submit_ms, gpu_inference_ms, postprocess_ms, total_ms)

        if self._timing_stats.should_report():
          stats = self._timing_stats.get_stats()
          self.logger.info(
              f"[TIMING] Last {stats['window_frames']} frames | "
              f"Total: avg={stats['total']['avg']:.1f}ms p95={stats['total']['p95']:.1f}ms p99={stats['total']['p99']:.1f}ms | "
              f"GPU: avg={stats['gpu_inference']['avg']:.1f}ms p95={stats['gpu_inference']['p95']:.1f}ms | "
              f"Preproc: {stats['preprocess']['avg']:.2f}ms | "
              f"gRPC: {stats['grpc_submit']['avg']:.2f}ms | "
              f"Postproc: {stats['postprocess']['avg']:.2f}ms"
          )

      return detections
    except Exception as e:
      self.logger.error(f"Inference failed: {e}")
      return []

  def postprocess_e2e(self, result, img_w, img_h):
    """
    Process end-to-end model output (NMS already done on GPU).
    Output tensors: num_dets, det_boxes, det_scores, det_classes.
    Override to add model-specific filtering (e.g. edge margin).
    """
    try:
      num_dets = result.as_numpy('num_dets')[0][0]
      det_boxes = result.as_numpy('det_boxes')[0]
      det_scores = result.as_numpy('det_scores')[0]
      det_classes = result.as_numpy('det_classes')[0]
    except Exception as e:
      self.logger.error(f"E2E output parsing failed: {e}")
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
      label = self.class_labels[class_id] if class_id < len(self.class_labels) else f"class_{class_id}"

      detections.append({
          "x": x1, "y": y1, "w": w, "h": h,
          "confidence": score, "label": label
      })

    return detections

  def postprocess_legacy(self, outputs, img_w, img_h):
    """
    Anchor-based decoding with class-aware NMS.
    Uses self.ANCHORS and self.STRIDES.
    Override for vectorized implementations.
    """
    all_boxes = []
    all_scores = []
    all_class_ids = []

    for i, output in enumerate(outputs):
      stride = self.STRIDES[i]
      anchors = self.ANCHORS[i]
      batch, num_anchors, grid_h, grid_w, _ = output.shape

      for a in range(num_anchors):
        for y in range(grid_h):
          for x in range(grid_w):
            row = output[0, a, y, x]
            obj_conf = row[4]
            if obj_conf < self.conf_thresh:
              continue

            classes = row[5:]
            class_id = np.argmax(classes)
            score = obj_conf * classes[class_id]
            if score < self.conf_thresh:
              continue

            cx = (2 * (1/(1+np.exp(-row[0]))) - 0.5 + x) * stride
            cy = (2 * (1/(1+np.exp(-row[1]))) - 0.5 + y) * stride
            w = (2 * (1/(1+np.exp(-row[2])))) ** 2 * anchors[a][0]
            h = (2 * (1/(1+np.exp(-row[3])))) ** 2 * anchors[a][1]

            x1 = int(cx - w/2)
            y1 = int(cy - h/2)

            all_boxes.append([x1, y1, int(w), int(h)])
            all_scores.append(float(score))
            all_class_ids.append(class_id)

    # Class-aware NMS via offset
    max_wh = 4096
    boxes_for_nms = []
    for i, box in enumerate(all_boxes):
      c_offset = all_class_ids[i] * max_wh
      boxes_for_nms.append([box[0] + c_offset, box[1] + c_offset, box[2], box[3]])

    indices = cv2.dnn.NMSBoxes(boxes_for_nms, all_scores, self.conf_thresh, self.nms_thresh)

    final_detections = []
    if len(indices) > 0:
      idx_list = indices.flatten() if hasattr(indices, 'flatten') else indices
      for i in idx_list:
        box = all_boxes[i]
        class_id = all_class_ids[i]
        if class_id >= len(self.class_labels):
          continue
        final_detections.append({
            "x": max(0, box[0]),
            "y": max(0, box[1]),
            "w": min(box[2], img_w - box[0]),
            "h": min(box[3], img_h - box[1]),
            "confidence": all_scores[i],
            "label": self.class_labels[class_id]
        })
    return final_detections


class ProcessFrameBase:
  """
  GStreamer gvapython integration base class.
  Parses base64 config and creates a TritonClient subclass.

  Subclasses must set:
      CLIENT_CLASS: the TritonClientBase subclass to instantiate
  """
  CLIENT_CLASS = TritonClientBase

  def __init__(self, logger, timing_stats=None, *args, **kwargs):
    self.logger = logger
    self.target_dim = 640
    config = {}

    if args and len(args) > 0:
      config_data = args[0]
      try:
        if config_data.startswith('b64='):
          config_data = config_data[4:]
        json_bytes = base64.b64decode(config_data)
        json_str = json_bytes.decode('utf-8')
        config = json.loads(json_str)
        self.logger.info(f"Triton config loaded from args: {config.get('triton_url', 'unknown')}")
      except Exception as e:
        self.logger.error(f"Argument parsing failed: {e}")

    elif 'kwarg' in kwargs:
      kw = kwargs['kwarg']
      try:
        if isinstance(kw, str) and kw.startswith('b64='):
          b64_data = kw[4:]
          json_bytes = base64.b64decode(b64_data)
          json_str = json_bytes.decode('utf-8')
          config = json.loads(json_str)
          self.logger.info(f"Triton config loaded from kwarg: {config.get('triton_url', 'unknown')}")
        elif isinstance(kw, dict):
          config = kw
        else:
          config = json.loads(kw.replace("'", '"'))
      except Exception as e:
        self.logger.error(f"Kwarg parsing failed: {e}")

    if config is None:
      config = {}
    self.client = self.CLIENT_CLASS(config, logger, timing_stats)

  def process_frame(self, frame, caps=None):
    if self.client is None:
      return True
    try:
      with frame.data() as mat:
        img_bgr = np.array(mat, copy=True)
        height, width = img_bgr.shape[:2]

      detections = self.client.infer(img_bgr, width, height)

      for d in detections:
        frame.add_region(d['x'], d['y'], d['w'], d['h'], d['label'], d['confidence'])

      if detections:
        self.logger.debug(f"Triton inference: {len(detections)} objects detected")
      return True
    except Exception as e:
      self.logger.error(f"Processing error: {e}")
    return True
