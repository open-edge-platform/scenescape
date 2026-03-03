# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from .common_types import PipelineGenerationValueError, InferenceRegion
from .model_chain import parse_model_chain, InferenceNode


class PipelineGenerator:
  """Generates a GStreamer pipeline string from camera settings and model config."""

  # the paths in the DLSPS container, to be mounted
  models_folder = '/home/pipeline-server/models'
  gva_python_path = '/home/pipeline-server/user_scripts/gvapython/sscape'
  video_path = '/home/pipeline-server/videos'

  def __init__(self, camera_settings: dict, model_config: dict):
    self.camera_settings = camera_settings
    camera_chain = camera_settings.get('camerachain', '')
    self.model_chain = parse_model_chain(
      camera_chain, self.models_folder, model_config)
    # TODO: make it generic, support USB camera inputs etc.
    # for now we assume this is RTSP, HTTP or file URI
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
      f'gvapython class=PostInferenceDataPublish function=processFrame module={self.gva_python_path}/sscape_adapter.py name=datapublisher'
    ]
    self.metadata_conversion = ['gvametaconvert add-tensor-data=true name=metaconvert']
    self.sink = ['appsink sync=true']

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
    if decode_device not in ['CPU', 'GPU', 'AUTO']:
      raise PipelineGenerationValueError(f"Unsupported decode device: {decode_device}. Supported values are 'CPU', 'GPU', 'AUTO'.")

    # Decoder selection
    if decode_device == "CPU":
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
        f'rtspsrc location={source} latency=200 name=source',
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
    pipeline_components = []

    pipeline_components.extend(self.input)
    pipeline_components.extend(self.decode)
    pipeline_components.extend(self.memory_caps)
    pipeline_components.extend(self.undistort)
    pipeline_components.extend(self.timestamper)

    # Set preprocessing backend for all models in model_chain
    # TODO: in latest DLSPS preprocessing backend should be handled automatically, so remove this block after verification
    if self.preprocessing_backend:
      if isinstance(self.model_chain, InferenceNode):
        self.model_chain.inference_model.set_preprocessing_backend(self.preprocessing_backend)
      else:
        # For sequential/parallel nodes, set for all nodes
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
    pipeline_components.extend(self.adapter)
    pipeline_components.extend(self.sink)
    return ' ! '.join(pipeline_components)

  def get_model_chain(self):
    return self.model_chain

  def get_metadata_policy(self) -> str:
    return self.model_chain.get_metadata_policy()
