# Copyright (C) 2023-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import json
import threading

from atag_camera_calibration_controller import \
    ApriltagCameraCalibrationController
from auto_camera_calibration_model import CameraCalibrationModel
from markerless_camera_calibration_controller import \
    MarkerlessCameraCalibrationController

from scene_common import log
from scene_common.mqtt import PubSub


class CameraCalibrationContext:
  scene_strategies = {}
  topics_to_subscribe = []

  def __init__(self, broker, broker_auth, cert, root_cert, rest_url, rest_auth):
    self.calibration_data_interface = CameraCalibrationModel(root_cert, rest_url, rest_auth)

    self.scene_strategies["AprilTag"] = ApriltagCameraCalibrationController(calibration_data_interface=self.calibration_data_interface)
    self.scene_strategies["Markerless"] = MarkerlessCameraCalibrationController(calibration_data_interface=self.calibration_data_interface)
    calib_image_topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id="+")
    registerscene_topic = PubSub.formatTopic(PubSub.CMD_AUTOCALIB_SCENE, scene_id="+")
    db_updated_topic = PubSub.formatTopic(PubSub.CMD_SCENE_UPDATE, scene_id="+")
    container_status_topic = PubSub.formatTopic(PubSub.SYS_AUTOCALIB_STATUS)
    self.topics_to_subscribe.append((calib_image_topic, self.generateCameraCalibration))
    self.topics_to_subscribe.append((db_updated_topic, self.updateScenes))
    self.topics_to_subscribe.append((container_status_topic, self.checkCamCalibrationStatus))
    self.topics_to_subscribe.append((registerscene_topic, self.checkSceneRegisterStatus))

    self.register_thread_lock = threading.Lock()
    self.current_processing_scene = None
    self.client = PubSub(broker_auth, cert, root_cert, broker, keepalive=240)
    self.client.onConnect = self.mqttOnConnect
    self.client.connect()

    return

  def mqttOnConnect(self, client, userdata, flags, rc):
    """! Subscribes to a list of topics on MQTT.
    @param   client    Client instance for this callback.
    @param   userdata  Private user data as set in Client.
    @param   flags     Response flags sent by the broker.
    @param   rc        Connection result.

    @return  None
    """
    for topic, callback in self.topics_to_subscribe:
      log.info("Subscribing to " + topic)
      self.client.addCallback(topic, callback)
      log.info("Subscribed " + topic)
    return

  def checkSceneRegisterStatus(self, client, userdata, message):
    """! MQTT callback function used to check the status of the scene if the
    registration is success / failure / registering in progress.
    @param   client      MQTT client.
    @param   userdata    Private user data as set in Client.
    @param   message     Message on MQTT bus.

    @return  None
    """
    msg = message.payload.decode("utf-8")
    topic = PubSub.parseTopic(message.topic)
    scene = self.calibration_data_interface.sceneWithID(topic['scene_id'])
    if scene and scene.camera_calibration == "Manual":
      return
    if str(msg) == "register":
      if self.scene_strategies[scene.camera_calibration].isMapUpdated(scene):
        if self.register_thread_lock.locked():
          register_response = self.current_processing_scene
        else:
          register_response = {"status":"registering"}
          self.sceneUpdateThreadWrapper(scene, map_update=True)
      else:
        register_response = self.scene_strategies[scene.camera_calibration].processSceneForCalibration(scene)
      self.client.publish(PubSub.formatTopic(PubSub.CMD_AUTOCALIB_SCENE,
                                              scene_id=topic['scene_id']),
                                              json.dumps(register_response))
    return

  def sceneUpdateThreadWrapper(self, sceneobj, map_update=False):
    """! function checks if lock is not acquired and processes the
    scene with updated metadata.
    status.
    @param   sceneobj      scene object.
    @param   map_update    boolean for re-registering the scene.

    @return  None
    """
    if not self.register_thread_lock.locked():
      thread= threading.Thread(target=self.processSceneAndPublish, args=(sceneobj, map_update))
      thread.start()
    return

  def processSceneAndPublish(self, sceneobj, map_update):
    """! function processes the uploaded scene(image/glb) and publish back the
    status.
    @param   sceneobj      scene object.
    @param   map_update    boolean for re-registering the scene.

    @return  None
    """
    self.current_processing_scene = {"status":"busy", "scene_id":str(sceneobj.id), "scene_name":sceneobj.name}
    self.client.publish(PubSub.formatTopic(PubSub.CMD_AUTOCALIB_SCENE,
                          scene_id=str(sceneobj.id)),
                      json.dumps(self.current_processing_scene))
    with self.register_thread_lock:
      try:
        response_dict = self.scene_strategies[sceneobj.camera_calibration].processSceneForCalibration(sceneobj, map_update)
        self.client.publish(PubSub.formatTopic(PubSub.CMD_AUTOCALIB_SCENE,
                                  scene_id=str(sceneobj.id)),
                                  json.dumps(response_dict))
      except (FileNotFoundError, KeyError) as e:
        log.error(f"Error in register dataset : {e}")
    self.current_processing_scene = {}
    return

  def generateCameraCalibration(self, client, userdata, message):
    """! MQTT callback function which receives image calibration requests from percebro and
    responds with the camera pose with respect to the scene.
    @param   client      MQTT client.
    @param   userdata    Private user data as set in Client.
    @param   message     Message on MQTT bus.

    @return  None
    """
    msg = message.payload.decode("utf-8")
    topic = PubSub.parseTopic(message.topic)
    if json.loads(msg).get("calibrate") is True:
      sceneobj = self.calibration_data_interface.sceneCameraWithID(topic['camera_id'])
      response = self.scene_strategies[sceneobj.camera_calibration].generateCalibration(sceneobj, msg)
      self.client.publish(response['publish_topic'], response['publish_data'])
    return

  def updateScenes(self, client, userdata, message):
    """! MQTT callback function used to update the scene data that has been stored in the
    database whenever there is an update in the scene model.
    @param   client      MQTT client.
    @param   userdata    Private user data as set in Client.
    @param   message     Message on MQTT bus.

    @return  None
    """
    command = str(message.payload.decode("utf-8"))
    if command == "update":
      topic = PubSub.parseTopic(message.topic)
      sceneobj = self.calibration_data_interface.sceneWithID(topic['scene_id'])
      if sceneobj and sceneobj.camera_calibration != "Manual":
        if self.scene_strategies[sceneobj.camera_calibration].isMapUpdated(sceneobj):
          self.scene_strategies[sceneobj.camera_calibration].resetScene(sceneobj)
          self.sceneUpdateThreadWrapper(sceneobj, map_update=True)
    return

  def checkCamCalibrationStatus(self, client, userdata, message):
    """! MQTT callback function used to check if the camera calibration container is running.
    @param   client      MQTT client.
    @param   userdata    Private user data as set in Client.
    @param   message     Message on MQTT bus.

    @return  None
    """
    msg = message.payload.decode("utf-8")
    if str(msg) == "isAlive":
      self.client.publish(PubSub.formatTopic(PubSub.SYS_AUTOCALIB_STATUS), "running")
    return

  def preprocessScenes(self):
    """! For all scenes in database, preprocess the scene map and store/update results

    @return  None
    """
    all_scene_objects = self.calibration_data_interface.allScenes()
    for scene_object in all_scene_objects:
      if scene_object.camera_calibration != "Manual":
        self.sceneUpdateThreadWrapper(scene_object, map_update=False)
        log.info(f"Validating Scene = {scene_object.name} on start.")
    return

  def loopForever(self):
    return self.client.loopForever()
