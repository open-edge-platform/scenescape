# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

import logging
from pathlib import Path
from .common_types import PipelineGenerationValueError, InferenceRegion
from .model_chain import parse_model_chain, InferenceNode

logger = logging.getLogger(__name__)


class PipelineGenerator:
  """Generates a GStreamer pipeline string from camera settings and model config."""

  # the paths in the DLSPS container, to be mounted
  models_folder = '/home/pipeline-server/models'
  gva_python_path = '/home/pipeline-server/user_scripts/gvapython/sscape'
  video_path = '/home/pipeline-server/videos'

  def __init__(self, camera_settings: dict, model_config: dict):
    self.camera_settings = camera_settings
    self.model_config = model_config
    camera_chain = camera_settings.get('camerachain', '')
    self.model_name = camera_chain
    self.model_chain = parse_model_chain(
      camera_chain, self.models_folder, model_config)
    self.input = self._parse_source(
      camera_settings.get('command', ''),
      PipelineGenerator.video_path)

    # Apply device rule set to determine pipeline components
    self._apply_device_rule_set()

    self.timestamper = [f'gvapython class=PostDecodeTimestampCapture function=processFrame module={self.gva_python_path}/sscape_adapter.py name=timesync']
    self.undistort = self.add_camera_undistort(camera_settings) if self.camera_settings.get('undistort') else []
    self.adapter = [
      'videoconvert',
      'video/x-raw,format=BGR',
      'gvametapublish',
      f'gvapython class=PostInferenceDataPublish function=processFrame module={self.gva_python_path}/sscape_adapter.py name=datapublisher'
    ]
    self.metadata_conversion = ['gvametaconvert add-tensor-data=true name=metaconvert']
    self.sink = ['appsink sync=false']

  def _apply_device_rule_set(self):
    """Apply device-based rule set to determine pipeline components."""
    decode_device = self.camera_settings.get('cv_subsystem', 'AUTO')
    # For now, get device from first model in model_chain
    if isinstance(self.model_chain, InferenceNode):
      inference_device = self.model_chain.inference_model.get_target_device()
    else:
      # For sequential/parallel nodes, use first node's device
      if self.model_chain.nodes:
        inference_device = self.model_chain.nodes[0].inference_model.get_target_device()
      else:
        inference_device = 'CPU'

    # Validate inputs
    if decode_device not in ['CPU', 'GPU', 'GPU_NVIDIA', 'AUTO']:
      raise PipelineGenerationValueError(f"Unsupported decode device: {decode_device}. Supported values are 'CPU', 'GPU', 'GPU_NVIDIA', 'AUTO'.")

    # Decoder selection: Triton models force NVDEC hardware decode.
    # GPU_NVIDIA explicitly requests NVDEC. GPU uses Intel VA-API.
    # NVDEC is dedicated hardware separate from CUDA cores - no inference impact.
    # nvh264dec max-display-delay=0: output frames immediately (no B-frame reorder delay).
    # Post-decode queue leaky=downstream: drops oldest frame when full, keeps newest.
    # videorate drop-only=true: zero look-ahead latency (no frame buffering for rate decision).
    if self._has_triton_model() or decode_device == "GPU_NVIDIA":
      self.decode = ["nvh264dec max-display-delay=0", "queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 leaky=downstream",
                     "videorate drop-only=true max-rate=10"]
    elif decode_device == "CPU":
      self.decode = ["decodebin force-sw-decoders=true", "videoconvert"]
    elif decode_device == "GPU":
      self.decode = ["decodebin3", "vapostproc"]
    else:  # AUTO
      self.decode = ["decodebin3"]

    self.memory_uses_va_surfaces = (decode_device != "CPU" and inference_device == "GPU")
    if self.memory_uses_va_surfaces:
      self.memory_caps = ["video/x-raw(memory:VAMemory)"]
      self.preprocessing_backend = "va-surface-sharing"
    else:
      self.memory_caps = ["video/x-raw"]
      if inference_device == "GPU":
        self.preprocessing_backend = "opencv"
      else:
        self.preprocessing_backend = ""

    self.post_gpu_inference_conversion = (self.model_chain.get_output_device() == "GPU")

  def _parse_source(self, source: str, video_volume_path: str) -> list:
    """
    Parses the GStreamer source element type based on the source string.
    Supported source types are 'rtsp', 'file'.

    @param source: The source string as typed by the user (e.g., RTSP URL, file path).
    @return: array of Gstreamer source elements
    """
    if source.startswith('rtsp://'):
      return [
        f'rtspsrc location={source} latency=0 drop-on-latency=true do-retransmission=false buffer-mode=auto name=source',
        'rtph264depay',
        'h264parse']
    elif source.startswith('file://'):
      filepath = Path(video_volume_path) / Path(source[len('file://'):])
      return [
        f'multifilesrc loop=TRUE location={filepath} name=source']
    elif source.startswith('http://') or source.startswith('https://'):
      return [
        f'souphttpsrc location={source} name=source',
        'multipartdemux']
    else:
      raise PipelineGenerationValueError(
        f"Unsupported source type in {source}. Supported types are 'rtsp://...' (raw H.264), 'http(s)://...' (MJPEG) and 'file://... (relative to video folder)'.")

  def add_camera_undistort(self, camera_settings: dict) -> list[str]:
    intrinsics_keys = [
      'intrinsics_fx',
      'intrinsics_fy',
      'intrinsics_cx',
      'intrinsics_cy']
    dist_coeffs_keys = [
      'distortion_k1',
      'distortion_k2',
      'distortion_p1',
      'distortion_p2',
      'distortion_k3']
    # Validation here can be removed if done prior to this step or we add a
    # flag to enable undistort in calib UI
    if not all(key in camera_settings for key in intrinsics_keys):
      return []
    if not all(key in camera_settings for key in dist_coeffs_keys):
      return []
    try:
      dist_coeffs = [float(camera_settings[key])
                     for key in dist_coeffs_keys]
    except Exception:
      return []
    if all(coef == 0 for coef in dist_coeffs):
      return []

    element = f"cameraundistort settings=cameraundistort0"
    return [element]

  def set_timestamper(self, new_timestamper: list[str]):
    """
    Overrides the timestamper element(s) of the pipeline.
    """
    self.timestamper = new_timestamper
    return self

  def set_adapter(self, new_adapter: list[str]):
    """
    Overrides the adapter element(s) of the pipeline.
    """
    self.adapter = new_adapter
    return self

  def set_sink(self, new_sink: list[str]):
    """
    Overrides the sink element(s) of the pipeline.
    """
    self.sink = new_sink
    return self

  def generate(self) -> str:
    """
    Generates a GStreamer pipeline string from the serialized pipeline.
    """
    manual_pipeline = self.camera_settings.get('manual_pipeline') or self.camera_settings.get('custom_pipeline')
    if manual_pipeline and manual_pipeline.strip() and manual_pipeline != 'auto':
      return manual_pipeline.strip()

    pipeline_components = []

    pipeline_components.extend(self.input)
    pipeline_components.extend(self.decode)
    pipeline_components.extend(self.memory_caps)
    pipeline_components.extend(self.undistort)
    pipeline_components.extend(self.timestamper)

    # Triton YOLO preprocessing: CPU resize to exact input dimensions + bounded queue
    if self._needs_triton_preprocessing():
      w = 640
      h = 640
      if isinstance(self.model_chain, InferenceNode):
        params = self.model_chain.inference_model.params.get('model_params', {})
        w = params.get('input-width', 640)
        h = params.get('input-height', 640)
      pipeline_components.extend([
          f"videoscale ! videoconvert ! video/x-raw,format=BGR,width={w},height={h}",
          "queue max-size-buffers=2 max-size-bytes=0 max-size-time=0"
      ])

    # Set preprocessing backend for all models in model_chain
    if self.preprocessing_backend:
      if isinstance(self.model_chain, InferenceNode):
        self.model_chain.inference_model.set_preprocessing_backend(self.preprocessing_backend)
      else:
        for node in self.model_chain.nodes:
          node.inference_model.set_preprocessing_backend(self.preprocessing_backend)

    self.model_chain.set_inference_input(InferenceRegion.FULL_FRAME)
    pipeline_components.extend(self.model_chain.serialize())

    # TODO: optimize queue latency with leaky and max-size-buffers parameters
    pipeline_components.extend(["queue"])
    pipeline_components.extend(self.metadata_conversion)
    if self.post_gpu_inference_conversion:
      pipeline_components.extend([
          "vapostproc",
          "video/x-raw,format=BGRA"
      ])
    # SceneScape metadata adapter and publisher
    # Triton path: skip redundant videoconvert + BGR caps (already done pre-inference)
    if self._needs_triton_preprocessing():
      pipeline_components.extend([
        f'gvapython class=PostInferenceDataPublish function=processFrame module={self.gva_python_path}/sscape_adapter.py name=datapublisher',
        'gvametapublish name=destination'
      ])
    else:
      pipeline_components.extend(self.adapter)
    pipeline_components.extend(self.sink)
    return ' ! '.join(pipeline_components)

  def get_model_chain(self):
    return self.model_chain

  def get_metadata_policy(self) -> str:
    return self.model_chain.get_metadata_policy()

  def _needs_triton_preprocessing(self) -> bool:
    """Check if pipeline requires Triton YOLO preprocessing stages."""
    if isinstance(self.model_chain, InferenceNode):
      params = self.model_chain.inference_model.params
      return (params.get('model_type') == 'triton' and
              params.get('model_params', {}).get('model-type') == 'yolo')
    else:
      for node in getattr(self.model_chain, 'nodes', []):
        params = node.inference_model.params
        if (params.get('model_type') == 'triton' and
            params.get('model_params', {}).get('model-type') == 'yolo'):
          return True
    return False

  def _has_triton_model(self) -> bool:
    """Check if any model in the chain uses Triton backend."""
    if isinstance(self.model_chain, InferenceNode):
      return self.model_chain.inference_model.params.get('model_type') == 'triton'
    else:
      for node in getattr(self.model_chain, 'nodes', []):
        if node.inference_model.params.get('model_type') == 'triton':
          return True
    return False
