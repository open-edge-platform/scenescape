# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod

from scene_common import log


class PerceptualSensorCalibrationController(ABC):
  """Modality-agnostic base strategy for perceptual sensor calibration.

  A calibration strategy localizes a perceptual sensor (point cloud today, and
  in future camera / radar / thermal) against a scene, returning a
  sensor-to-scene transform. Concrete strategies are registered per modality and
  selected by the calibration context's modality router, so adding a modality is
  a strategy registration rather than a change to the calibration handlers.
  """

  def __init__(self, calibration_data_interface):
    self.calibration_data_interface = calibration_data_interface
    self.socketio = None
    self.socket_scene_clients = None

  def notify_scene_registration(self, scene_id, response):
    """Emit a scene-registration result over Socket.IO, if a client is bound."""
    if not self.socket_scene_clients:
      return
    socket_id = self.socket_scene_clients.get(scene_id)
    if socket_id and self.socketio:
      self.socketio.emit("register_result",
                         {"scene_id": scene_id, "data": response}, to=socket_id)
      log.info(f"Sent WebSocket result to {socket_id} for {scene_id}")
    return

  @abstractmethod
  def process_scene_for_calibration(self, sceneobj, map_update=False):
    """Prepare (and cache) the scene representation used for calibration."""
    raise NotImplementedError

  @abstractmethod
  def reset_scene(self, scene):
    """Invalidate any cached scene representation for the scene."""
    raise NotImplementedError

  @abstractmethod
  def is_map_updated(self, sceneobj):
    """Report whether the scene map needs (re)processing."""
    raise NotImplementedError

  @abstractmethod
  def generate_calibration(self, sceneobj, sensor_config, msg):
    """Localize the sensor against the scene and return transform + metrics."""
    raise NotImplementedError
