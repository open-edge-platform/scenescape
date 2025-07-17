# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import os
import socket
import sys
import traceback
import urllib
import uuid
import zipfile
from functools import partial

import numpy as np
import paho.mqtt.client as mqtt
from PIL import Image

from django.contrib.postgres.fields import ArrayField
from django.core.files.base import ContentFile
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models, transaction
from django.conf import settings
from django.contrib.sessions.models import Session
from django.contrib.auth.models import User
from django.utils.text import get_valid_filename

from scene_common.camera import Camera as ScenescapeCamera, CameraPose as ScenescapeCameraPose
from scene_common.geometry import Region as ScenescapeRegion, Tripwire as ScenescapeTripwire
from scene_common.glb_top_view import generateOrthoView, getMeshSize
from scene_common.mesh_util import extractMeshFromGLB
from scene_common.mqtt import PubSub
from scene_common.options import *
from scene_common.scene_model import SceneModel as ScenescapeScene
from scene_common.scenescape import SceneLoader
from scene_common.timestamp import get_epoch_time
from manager.validators import validate_map_file, validate_glb, validate_zip_file, validate_map_corners_lla

from scene_common import log

# FIXME - when entire app has transitioned to using APIs
# move this definition to views.py
def sendUpdateCommand(scene_id=None, camera_data=None):
  broker = os.environ.get("BROKER")
  auth = os.environ.get("BROKERAUTH")
  rootcert = os.environ.get("BROKERROOTCERT")
  if rootcert is None:
    rootcert = "/run/secrets/certs/scenescape-ca.pem"
  cert = os.environ.get("BROKERCERT")
  if broker is not None:
    client = PubSub(auth, cert, rootcert, broker)
    try:
      client.connect()
    except socket.gaierror as e:
      log.error("Unable to connect", e)
    else:
      if scene_id:
        client.publish(PubSub.formatTopic(PubSub.CMD_SCENE_UPDATE, scene_id = scene_id), "update")
      if camera_data:
        client.publish(PubSub.formatTopic(PubSub.CMD_KUBECLIENT), json.dumps(camera_data), qos=2)
      msg = client.publish(PubSub.formatTopic(PubSub.CMD_DATABASE), "update", qos=1)
      if not msg.is_published() and msg.rc == mqtt.MQTT_ERR_SUCCESS:
        client.loopStart()
        msg.wait_for_publish()
        client.loopStop()
  return

def sanitizeZipPath(instance, filename):
  """! Sanitize the filename, remove any existing file, and return a safe path under MEDIA_ROOT."""
  safe_filename = get_valid_filename(os.path.basename(filename))
  full_path = os.path.join(settings.MEDIA_ROOT, safe_filename)
  os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
  if os.path.exists(full_path):
    os.remove(full_path)
  return safe_filename

class FailedLogin(models.Model):
  ip = models.GenericIPAddressField(null=True)
  delay = models.FloatField(default=0.0)

  class Meta:
    db_table = "db_failedlogin_entry"
    verbose_name = "FailedLogin Entry"
    verbose_name_plural = "FailedLogin Entries"

class UserSession(models.Model):
  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
  session = models.OneToOneField(Session, on_delete=models.CASCADE)

class SceneImport(models.Model):
  zipFile = models.FileField(null=True, upload_to=sanitizeZipPath, blank=False, editable=True)

class Scene(models.Model):
  #FIXME: enable manual as an option. Auto calibration compute should be performed when manual is chosen.
  #This will avoid utilizing compute resources unnecessarily.

  DEFAULT_MESH_ROTATION = 90.0

  id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
  name = models.CharField(max_length=200, unique=True)
  thumbnail = models.ImageField(default=None, null=True, editable=False)
  map = models.FileField("Scene map as .glb or image or .zip", default=None, null=True, blank=True,
                            validators=[FileExtensionValidator(["glb","png","jpeg","jpg","zip"]),
                                        validate_map_file])
  scale = models.FloatField("Pixels per meter", default=None, null=True, blank=True,
                            validators=[MinValueValidator(np.nextafter(0, 1))])
  rotation_x = models.FloatField("X Rotation (degrees)", default=0.0, null=True, blank=False)
  rotation_y = models.FloatField("Y Rotation (degrees)", default=0.0, null=True, blank=False)
  rotation_z = models.FloatField("Z Rotation (degrees)", default=0.0, null=True, blank=False)
  translation_x = models.FloatField("X Translation (meters)", default=0.0,
                                    null=True, blank=False)
  translation_y = models.FloatField("Y Translation (meters)", default=0.0,
                                    null=True, blank=False)
  translation_z = models.FloatField("Z Translation (meters)", default=0.0,
                                    null=True, blank=False)
  scale_x = models.FloatField("X Scale", default=1.0, null=True, blank=False)
  scale_y = models.FloatField("Y Scale", default=1.0, null=True, blank=False)
  scale_z = models.FloatField("Z Scale", default=1.0, null=True, blank=False)
  map_processed = models.DateTimeField("Last Processed at", null=True, editable=False)
  output_lla = models.BooleanField("Output geospatial coordinates", choices=BOOLEAN_CHOICES, default=False, null=True)
  map_corners_lla = models.JSONField("Geospatial coordinates of the four map corners in JSON format",
                                      default=None, null=True, blank=True, validators=[validate_map_corners_lla],
                                      help_text=(
                                        "Provide the array of four map corners geospatial coordinates (lat, long, alt).\n"
                                        "Required only if 'Output geospatial coordinates' is set to `Yes`.\n"
                                        "Expected order: starting from the bottom-left corner counterclockwise.\nExpected JSON format: "
                                        "'[ [lat1, lon1, alt1], [lat2, lon2, alt2], [lat3, lon3, alt3], [lat4, lon4, alt4] ]'"))
  camera_calibration = models.CharField("Calibration Type", max_length=20, choices=CALIBRATION_CHOICES, default=MANUAL)
  polycam_data = models.FileField(blank=True, null=True, validators=[
                                  FileExtensionValidator(["zip"]), validate_zip_file])
  dataset_dir = models.CharField(blank=True, max_length=200, editable=False)
  output_dir = models.CharField(blank=True, max_length=200, editable=False)
  output = models.CharField(null=True, blank=True, max_length=500, editable=False)
  retrieval_conf = models.JSONField(null=True, blank=True, editable=False)
  global_descriptor_file = models.FileField(blank=True, null=True,
                                            validators=[FileExtensionValidator(["h5"])],
                                            editable=False)
  number_of_localizations = models.IntegerField(
    verbose_name="Number Of Localizations", default=50, null=True, blank=True)
  global_feature = models.CharField(
    verbose_name="Global Feature Matching Algorithm", max_length=200,
    default="netvlad", blank=True)
  def _getDefaultSiftDict():
    return {"sift": dict()}
  local_feature = models.JSONField(default=_getDefaultSiftDict, null=True, blank=True)
  def _getDefaultNnRatioDict():
    return {"NN-ratio": dict()}
  matcher = models.JSONField(default=_getDefaultNnRatioDict, null=True, blank=True)
  minimum_number_of_matches = models.IntegerField(
    verbose_name="Minimum Number Of Matches", default=20, null=True, blank=True)
  polycam_hash = models.CharField(null=True, blank=True, max_length=100,
                  editable=False)
  apriltag_size = models.FloatField("AprilTag Size (meters)", max_length=10, default=0.162, null=True, blank=True)
  regulated_rate = models.FloatField("Regulate Rate (Hz)", default=30, blank=True, validators=[MinValueValidator(0.001)])
  external_update_rate = models.FloatField("Max External Update Rate (Hz)", default=30, blank=True, validators=[MinValueValidator(0.001)])
  inlier_threshold = models.FloatField("Feature Match Confidence Threshold", default=0.5, blank=True, validators=[MinValueValidator(0.0)])

  def __str__(self):
    return self.name

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._original_map = self.map
    self._original_scale = self.scale
    self._original_rotation_x = self.rotation_x
    self._original_rotation_y = self.rotation_y
    self._original_rotation_z = self.rotation_z
    self._original_translation_x = self.translation_x
    self._original_translation_y = self.translation_y
    self._original_translation_z = self.translation_z
    self._original_calibration_mode = self.camera_calibration
    self._original_polycam_data = self.polycam_data
    self._original_matcher = self.matcher
    self._original_num_of_localization = self.number_of_localizations
    self._original_global_feature = self.global_feature
    self._original_local_feature = self.local_feature
    self._original_min_num_of_matches = self.minimum_number_of_matches
    self._original_apriltag_size = self.apriltag_size
    self._original_inlier_threshold = self.inlier_threshold
    return

  def changedCalibrationParams(self):
    return self._original_calibration_mode != self.camera_calibration or \
            self._original_matcher != self.matcher or \
            self._original_num_of_localization != self.number_of_localizations or \
            self._original_global_feature != self.global_feature or \
            self._original_local_feature != self.local_feature or \
            self._original_min_num_of_matches != self.minimum_number_of_matches or \
            self._original_scale != self.scale or \
            self._original_apriltag_size != self.apriltag_size or \
            self._original_inlier_threshold != self.inlier_threshold

  def regenerateThumbnail(self):
    return self.map != self._original_map or \
           self._original_rotation_x != self.rotation_x or \
           self._original_rotation_y != self.rotation_y or \
           self._original_rotation_z != self.rotation_z or \
           self._original_translation_x != self.translation_x or \
           self._original_translation_y != self.translation_y or \
           self._original_translation_z != self.translation_z

  def autoAlignSceneMap(self):
    """! Rotate the glb from y-up to z-up and translate to first
      quadrant.
    """
    if self.map and os.path.splitext(self.map.path)[1].lower() == ".glb":
      self.rotation_x = self.DEFAULT_MESH_ROTATION
      self.rotation_y = 0.0
      self.rotation_z = 0.0
      mesh, _ = extractMeshFromGLB(self.map.path, rotation=np.array([self.rotation_x, self.rotation_y, self.rotation_z]))
      width, height, depth = getMeshSize(mesh)
      self.translation_x = width/2
      self.translation_y = height/2
      self.translation_z = depth/2
    return

  def resetRotation(self):
    self.rotation_x = 0.0
    self.rotation_y = 0.0
    self.rotation_z = 0.0
    return

  def resetTranslation(self):
    self.translation_x = 0.0
    self.translation_y = 0.0
    self.translation_z = 0.0
    return

  def saveThumbnail(self):
    img_data, pixels_per_meter = generateOrthoView(self, self.map.path)
    self.scale = pixels_per_meter
    img = Image.fromarray(np.uint8(img_data))
    with ContentFile(b'') as imgfile:
      img.save(imgfile, format='PNG')
      self.thumbnail.save(self.name + '_2d.png', imgfile, save=False)
    return

  def save(self, *args, **kwargs):
    updated_scene = self.id
    self.dataset_dir = f"{os.getcwd()}/datasets/{self.name}"
    self.output_dir = f"{os.getcwd()}/datasets/{self.name}/output_dir"
    try:
      glb_from_zip = None
      # use glb from zip uploaded in map and copy zip to polycam data
      if (self._original_map != self.map) and \
                      os.path.splitext(self.map.name)[1].lower() == ".zip":
        glb_from_zip = self.map
        self.polycam_data = self.map
        self.camera_calibration = MARKERLESS
      # use glb from zip uploaded in polycam data
      if (self._original_polycam_data != self.polycam_data):
        glb_from_zip = self.polycam_data

      if self.changedCalibrationParams():
        self.map_processed = None

      super().save(*args, **kwargs)

      if glb_from_zip:
        with zipfile.ZipFile(glb_from_zip.path, 'r') as zf:
          base_file_name = zf.namelist()[0].split("/")[0]
          glb_content = zf.read(os.path.join(base_file_name, "raw.glb"))
          self.map.save(f"{self.name}.glb", ContentFile(glb_content), save=False)

      if self._original_map != self.map or glb_from_zip:
        self.autoAlignSceneMap()
      if self.regenerateThumbnail() or glb_from_zip:
        if not self.map:
          self.thumbnail = None
          self.map_processed = None
        else:
          ext = os.path.splitext(self.map.path)[1].lower()
          if ext == ".glb":
            self.saveThumbnail()
          else:
            self.thumbnail = None
            self.resetRotation()
            self.resetTranslation()
        super().save(*args, **kwargs)
    except FileNotFoundError as e:
      log.error(f"Failed to save scene , {str(e)}")
    transaction.on_commit(partial(sendUpdateCommand, scene_id = updated_scene))
    return

  def delete(self, *args, **kwargs):
    super(Scene, self).delete(*args, **kwargs)
    transaction.on_commit(sendUpdateCommand)
    if self.map:
      storage, path = self.map.storage, self.map.path
      storage.delete(path)
    return

  def roiJSON(self):
    jdata = []
    for region in self.regions.all():
      rdict = {'title': region.name, 'points': [], 'uuid':str(region.uuid), 
               'volumetric': region.volumetric, 'height': region.height, 'buffer_size': region.buffer_size}
      thresholds, range_max = region.get_sectors()
      rdict['sectors'] = {'thresholds':thresholds, 'range_max':range_max}

      # provide points in the right order, so ROI polygon is formed properly
      for point in region.points.all().order_by('sequence'):
        # FIXME - UI should be handling scaling
        rdict['points'].append([point.x, point.y])
      jdata.append(rdict)
    return json.dumps(jdata)

  def tripwireJSON(self):
    jdata = []
    for tripwire in self.tripwires.all():
      rdict = {'title': tripwire.name, 'points': [], 'uuid':str(tripwire.uuid)}
      for point in tripwire.points.all():
        # FIXME - UI should be handling scaling
        rdict['points'].append([point.x, point.y])
      jdata.append(rdict)
    return json.dumps(jdata)

  @property
  def scenescapeScene(self):
    mScene = SceneLoader.sceneWithName(self.name)
    if not mScene:
      mScene = ScenescapeScene(self.name, self.map.path if self.map else None, self.scale)
      mScene.output_lla = self.output_lla
      mScene.map_corners_lla = self.map_corners_lla
      mScene.mesh_translation = [self.translation_x, self.translation_y, self.translation_z]
      mScene.mesh_rotation = [self.rotation_x, self.rotation_y, self.rotation_z]
      try:
        self.scenescapeSceneUpdateSensors(mScene)
        self.scenescapeSceneUpdateRegions(mScene)
        SceneLoader.addScene(mScene)
      except:
        traceback.print_exc()
    return mScene

  def scenescapeSceneUpdateSensors(self, mScene, force=False):
    # print("Updating sensors")
    for sensor in self.sensor_set.all():
      if sensor.type == "camera" and (force or sensor.sensor_id not in mScene.cameras):
        cam = sensor.cam

        if cam.transforms is None:
          continue

        sInfo = cam.transformation

        if cam.intrinsics_fx != None and cam.intrinsics_fy != None \
           and cam.intrinsics_cx != None and cam.intrinsics_cy != None:
          sInfo['intrinsics'] = [cam.intrinsics_fx, cam.intrinsics_fy,
                                 cam.intrinsics_cx, cam.intrinsics_cy]
        elif cam.intrinsics_fx != None:
          sInfo['intrinsics'] = [cam.intrinsics_fx]
          if cam.intrinsics_fy != None:
            sInfo['intrinsics'].append(cam.intrinsics_fy)

        if cam.distortion_k1 != None and cam.distortion_k2 != None \
           and cam.distortion_p1 != None and cam.distortion_p2 != None \
           and cam.distortion_k3 != None:
          sInfo['distortion'] = [cam.distortion_k1, cam.distortion_k2,
                                 cam.distortion_p1, cam.distortion_p2, cam.distortion_k3]

        mScene.cameras[sensor.sensor_id] = ScenescapeCamera(
            sensor.sensor_id, sInfo, resolution=(cam.width, cam.height))
    return

  def createSceneScapeRegion(self, existing, region):
    info = {'area': "poly"}
    if hasattr(region, 'area'):
      info['area'] = region.area

    if hasattr(region, 'map_x') and region.map_x is not None:
      info['center'] = (region.map_x, region.map_y)
    if hasattr(region, 'radius') and region.radius is not None:
      info['radius'] = region.radius

    uiPoints = region.points.all()
    if len(uiPoints):
      info['points'] = [(pt.x, pt.y) for pt in uiPoints]
    elif info['area'] == "poly":
      return

    if hasattr(region, 'sensor_id'):
      region_id = region.sensor_id
    else:
      region_id = region.name
    if region_id in existing:
      existing[region_id].updatePoints(info)
    else:
      if hasattr(region, 'uuid'):
        uuid = region.uuid
      else:
        uuid = region_id
      existing[region_id] = ScenescapeRegion(uuid, region_id, info)
    return

  def scenescapeSceneUpdateRegions(self, mScene):
    oldRegions = list(mScene.regions.keys())
    for region in self.regions.all():
      self.createSceneScapeRegion(mScene.regions, region)

    newRegions = list(mScene.regions.keys())
    delRegions = list(set(oldRegions) - set(newRegions))
    for k in delRegions:
      mScene.regions.pop(k)

    oldTripwires = list(mScene.tripwires.keys())
    info = {}
    for tripwire in self.tripwires.all():
      uiPoints = tripwire.points.all()
      if len(uiPoints) == 0:
        continue

      info['points'] = [(pt.x, pt.y) for pt in uiPoints]
      if tripwire.name in mScene.tripwires:
        mScene.tripwires[tripwire.name].updatePoints(info)
      else:
        mScene.tripwires[tripwire.name] = ScenescapeTripwire(tripwire.uuid, tripwire.name, info['points'])

    newTripwires = list(mScene.tripwires.keys())
    delTripwires = list(set(oldTripwires) - set(newTripwires))
    for k in delTripwires:
      mScene.tripwires.pop(k)

    oldSensors = list(mScene.sensors.keys())
    for sensor in self.sensor_set.all():
      if sensor.type != "generic":
        continue

      sensor = SingletonSensor.objects.get(pk=sensor.id)
      self.createSceneScapeRegion(mScene.sensors, sensor)

    newSensors = list(mScene.sensors.keys())
    delSensors = list(set(oldSensors) - set(newSensors))
    for k in delSensors:
      mScene.sensors.pop(k)
    return

  def browserAuth(self):
    auth = os.environ.get("BROKERAUTH")
    if auth is None:
      auth = settings.BROWSER_AUTH_FILE
    data = ""
    if not os.path.exists(auth) and not os.path.isabs(auth):
      auth = os.path.join(os.path.dirname(__file__), auth)
    if os.path.exists(auth):
      with open(auth) as json_file:
        data = json.load(json_file)
    else:
      log.error("COULD NOT OPEN", auth, file=sys.stderr)
    return data

  def wssConnection(self):
    log.info("Getting wss connection string.")
    data = self.browserAuth()
    userpass = urllib.parse.quote(data['user'], safe="") \
      + ":" + urllib.parse.quote(data['password'], safe="") + "@"
    return "wss://" + userpass + "localhost/mqtt"

  def mqttUser(self):
    data = self.browserAuth()
    return data['user']

  def mqttPassword(self):
    data = self.browserAuth()
    return data['password']

class ChildScene(models.Model):
  child = models.OneToOneField(Scene, default=None, null=True, blank=True,
                               on_delete=models.CASCADE, related_name="parent")
  child_name = models.CharField("Child Name", default=None, max_length=200, null=True, blank=True)
  remote_child_id = models.UUIDField("Remote Child ID", default=None, null=True, blank=True, unique=True)
  parent = models.ForeignKey(Scene, null=False, blank=False,
                             on_delete=models.CASCADE, related_name="children")
  child_type = models.CharField(default="local", max_length=15, blank=False)

  class Meta:
    constraints = [
      models.CheckConstraint(
        check=models.Q(child__isnull=False, child_name__isnull=True) | models.Q(child__isnull=True, child_name__isnull=False),
        name="%(app_label)s_%(class)s_either_child_or_child_name"
      ),
      models.UniqueConstraint(
        name="%(app_label)s_%(class)s_local_child_unique_relationships",
        fields=["child", "parent"],
      ),
      models.UniqueConstraint(
        name="%(app_label)s_%(class)s_remote_child_unique_relationships",
        fields=["child_name", "parent"],
      ),
      models.CheckConstraint(
        name="%(app_label)s_%(class)s_prevent_self_follow",
        check=~models.Q(child=models.F("parent")),
      ),
    ]

  transform1 = models.FloatField(default=1.0, null=True, blank=True)
  transform2 = models.FloatField(default=0.0, null=True, blank=True)
  transform3 = models.FloatField(default=0.0, null=True, blank=True)
  transform4 = models.FloatField(default=0.0, null=True, blank=True)
  transform5 = models.FloatField(default=0.0, null=True, blank=True)
  transform6 = models.FloatField(default=1.0, null=True, blank=True)
  transform7 = models.FloatField(default=0.0, null=True, blank=True)
  transform8 = models.FloatField(default=0.0, null=True, blank=True)
  transform9 = models.FloatField(default=0.0, null=True, blank=True)
  transform10 = models.FloatField(default=0.0, null=True, blank=True)
  transform11 = models.FloatField(default=1.0, null=True, blank=True)
  transform12 = models.FloatField(default=0.0, null=True, blank=True)
  transform13 = models.FloatField(default=0.0, null=True, blank=True)
  transform14 = models.FloatField(default=0.0, null=True, blank=True)
  transform15 = models.FloatField(default=0.0, null=True, blank=True)
  transform16 = models.FloatField(default=1.0, null=True, blank=True)
  transform_type = models.CharField(max_length=10, choices=CHILD_SCENE_TRANSFORM_CHOICES,
                                    default=MATRIX)
  host_name = models.CharField("Hostname or IP", max_length=200, null=True, blank=True)
  mqtt_username = models.CharField("MQTT Username", max_length=200, null=True, blank=True)
  mqtt_password = models.CharField("MQTT Password", max_length=200, null=True, blank=True)
  retrack = models.BooleanField("Retrack objects", choices=BOOLEAN_CHOICES, default=True, blank=True)

  @property
  def cameraPose(self):
    return ScenescapeCameraPose(ScenescapeCameraPose.arrayToDictionary(
      [self.transform1, self.transform2, self.transform3, self.transform4,
       self.transform5, self.transform6, self.transform7, self.transform8,
       self.transform9, self.transform10, self.transform11, self.transform12,
       self.transform13, self.transform14, self.transform15, self.transform16],
      self.transform_type), None)

  def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    transaction.on_commit(sendUpdateCommand)
    return

  def delete(self, *args, **kwargs):
    super().delete(*args, **kwargs)
    transaction.on_commit(sendUpdateCommand)
    return

class PubSubACL(models.Model):
  user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='acls')
  topic = models.CharField(choices=TOPIC_CHOICES, max_length=50)
  access = models.IntegerField(choices=ACCESS_CHOICES, default=0)

  class Meta:
    constraints = [
      models.UniqueConstraint(
        fields=["user", "topic"],
        name="%(app_label)s_%(class)s_unique_user_topic"
      )
    ]

  def __str__(self):
    return f"ACL for {self.user.username} on {self.topic} (Access choice: {self.access})"

class CalibrationMarker(models.Model):
  marker_id = models.CharField(max_length=50, primary_key=True)
  apriltag_id = models.CharField(max_length=10)
  dims = ArrayField(models.FloatField())
  scene = models.ForeignKey(Scene, on_delete=models.CASCADE)

  def __str__(self):
    return self.marker_id

class Sensor(models.Model):
  sensor_id = models.CharField(max_length=20, default=None, unique=True, verbose_name="Sensor ID")
  name = models.CharField(max_length=200, unique=True)
  sensor_type_choices = (('camera', 'Camera'),
                         ('generic', 'generic'))
  type = models.CharField(max_length=200, choices=sensor_type_choices)
  scene = models.ForeignKey(Scene, null=True, on_delete=models.SET_NULL)
  icon = models.ImageField(default=None, null=True, blank=True)
#  map = models.ImageField(default=None, null=True, blank=False)

  def __str__(self):
    return self.name

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._original_sensor_id = self.sensor_id
    self._original_name = self.name

  def calibrateString(self):
    return "calibrate-" + self.type

  def areaJSON(self):

    rdict = {'area': self.singletonsensor.area,
             'radius': self.singletonsensor.radius,
             'x': self.singletonsensor.map_x,
             'y': self.singletonsensor.map_y,
             'points': []}
    for point in self.singletonsensor.points.all():
      rdict['points'].append([point.x, point.y])

    sectors = self.singletonsensor.get_sectors()
    rdict['sectors'] = {'thresholds':sectors[0], 'range_max':sectors[1]}

    return json.dumps(rdict)

  def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    transaction.on_commit(sendUpdateCommand)
    return

  def delete(self, *args, **kwargs):
    super().delete(*args, **kwargs)
    transaction.on_commit(sendUpdateCommand)
    return

  def delete(self, *args, **kwargs):
    # Check if an icon file also needs to be deleted
    if self.icon:
      storage, path = self.icon.storage, self.icon.path
      super().delete(*args, **kwargs)
      storage.delete(path)
    else:
      super().delete(*args, **kwargs)
    return

class Cam(Sensor):
  DEFAULT_INTRINSICS = {"fx":570.0,"fy":570.0,"cx":320.0,"cy":240.0}

  command = models.CharField(default=None, max_length=512, null=True,
                             verbose_name="Camera (Video Source)")
  camerachain = models.CharField(default=None, max_length=64, null=True)
  threshold = models.FloatField(default=None, null=True, blank=True)
  aspect = models.CharField(default=None, max_length=64, null=True, blank=True)
  cv_subsystem = models.CharField(default=None, max_length=64, null=True, blank=True,
                                  verbose_name="CV Subsystem")

  # Workaround due to unit tests using a sqlite3 database
  if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
    transforms = models.JSONField(blank=True, default=list)
  else:
    transforms = ArrayField(models.FloatField(blank=True, default=None, null=True),
                            blank=True, default=list)
  transform_type = models.CharField(max_length=26, choices=CAM_TRANSFORM_CHOICES,
                                    default=POINT_CORRESPONDENCE)
  width = models.IntegerField(default=640, null=False, blank=False)
  height = models.IntegerField(default=480, null=False, blank=False)
  scene_x = models.IntegerField(default=None, null=True, blank=True)
  scene_y = models.IntegerField(default=None, null=True, blank=True)
  scene_z = models.IntegerField(default=None, null=True, blank=True)
  intrinsics_fx = models.FloatField(
    default=None, null=True, blank=True, validators=[MinValueValidator(0.001)])
  intrinsics_fy = models.FloatField(
    default=None, null=True, blank=True, validators=[MinValueValidator(0.001)])
  intrinsics_cx = models.FloatField(
    default=None, null=True, blank=True, validators=[MinValueValidator(0.001)])
  intrinsics_cy = models.FloatField(
    default=None, null=True, blank=True, validators=[MinValueValidator(0.001)])
  distortion_k1 = models.FloatField(default=None, null=True, blank=True)
  distortion_k2 = models.FloatField(default=None, null=True, blank=True)
  distortion_p1 = models.FloatField(default=None, null=True, blank=True)
  distortion_p2 = models.FloatField(default=None, null=True, blank=True)
  distortion_k3 = models.FloatField(default=None, null=True, blank=True)
  sensor = models.CharField(max_length=512, null=True, blank=True)
  sensorchain = models.CharField(max_length=64, null=True, blank=True)
  sensorattrib = models.CharField(max_length=64, null=True, blank=True)
  window = models.BooleanField(default=False)
  usetimestamps = models.BooleanField(default=False)
  virtual = models.CharField(max_length=512, null=True, blank=True)
  debug = models.BooleanField(default=False)
  override_saved_intrinstics = models.BooleanField(default=False)
  frames = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
  stats = models.BooleanField(default=False)
  waitforstable = models.BooleanField(default=False)
  preprocess = models.BooleanField(default=False)
  realtime = models.BooleanField(default=False)
  faketime = models.BooleanField(default=False)
  modelconfig = models.CharField(max_length=512, null=True, blank=True)
  rootcert = models.CharField(max_length=64, null=True, blank=True)
  cert = models.CharField(max_length=64, null=True, blank=True)
  cvcores = models.IntegerField(null=True, blank=True)
  ovcores = models.IntegerField(null=True, blank=True)
  unwarp = models.BooleanField(default=False)
  ovmshost = models.CharField(max_length=64, null=True, blank=True)
  framerate = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
  maxcache = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
  filter = models.CharField(max_length=64, choices=CAM_FILTER_CHOICES,
                                    default=NONE)
  disable_rotation = models.BooleanField(default=False)
  maxdistance = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.001)])

  @property
  def transformation(self):
    return ScenescapeCameraPose.arrayToDictionary(self.transforms, self.transform_type)

  def logData(self, sensor_type, jdata):
    timestamp = get_epoch_time(jdata['timestamp'])
    for obj in jdata['objects']:
      # Logging only for person ?!
      if sensor_type == 'person':
        log = DataLog(timestamp)
        log.pk = None
        log.save()
        slog = CamLog(log=log, sensor=self,
                      pid=int(obj['id']),
                      x=obj['bounding_box']['x'], y=obj['bounding_box']['y'],
                      width=obj['bounding_box']['width'],
                      height=obj['bounding_box']['height'])
        slog.save()
    return

  def cameraData(self, action):
    if self.scene is None:
      scene_name = ""
    else:
      scene_name = self.scene.name
    if self._original_sensor_id is None:
      self._original_sensor_id = ""
    if self._original_name is None:
      self._original_name = ""
    camera_data = {
      'sensor_id': self.sensor_id,
      'name': self.name,
      'scene': scene_name,
      'command': self.command,
      'camerachain': self.camerachain,
      'threshold': self.threshold,
      'aspect': self.aspect,
      'cv_subsystem': self.cv_subsystem,
      'intrinsics_cx': self.intrinsics_cx,
      'intrinsics_cy': self.intrinsics_cy,
      'intrinsics_fx': self.intrinsics_fx,
      'intrinsics_fy': self.intrinsics_fy,
      'distortion_k1': self.distortion_k1,
      'distortion_k2': self.distortion_k2,
      'distortion_p1': self.distortion_p1,
      'distortion_p2': self.distortion_p2,
      'distortion_k3': self.distortion_k3,
      'previous_sensor_id': self._original_sensor_id,
      'previous_name': self._original_name,
      'action': action,
      'width': self.width, # resolution
      'height': self.height, # resolution
      'sensor': self.sensor,
      'sensorchain': self.sensorchain,
      'sensorattrib': self.sensorattrib,
      'window': self.window,
      'usetimestamps': self.usetimestamps,
      'virtual': self.virtual,
      'debug': self.debug,
      'override_saved_intrinstics': self.override_saved_intrinstics,
      'frames': self.frames,
      'stats': self.stats,
      'waitforstable': self.waitforstable,
      'preprocess': self.preprocess,
      'realtime': self.realtime,
      'faketime': self.faketime,
      'modelconfig': self.modelconfig,
      'rootcert': self.rootcert,
      'cert': self.cert,
      'cvcores': self.cvcores,
      'ovcores': self.ovcores,
      'unwarp': self.unwarp,
      'ovmshost': self.ovmshost,
      'framerate': self.framerate,
      'maxcache': self.maxcache,
      'filter': self.filter,
      'disable_rotation': self.disable_rotation,
      'maxdistance': self.maxdistance
    }
    return camera_data

  def save(self, *args, **kwargs):
    if self.intrinsics_cx is None:
      self.intrinsics_cx = self.DEFAULT_INTRINSICS['cx']
    if self.intrinsics_cy is None:
      self.intrinsics_cy = self.DEFAULT_INTRINSICS['cy']
    if self.intrinsics_fx is None:
      self.intrinsics_fx = self.DEFAULT_INTRINSICS['fx']
    if self.intrinsics_fy is None:
      self.intrinsics_fy = self.DEFAULT_INTRINSICS['fy']
    super().save(*args, **kwargs)
    transaction.on_commit(partial(sendUpdateCommand,
                                  camera_data = self.cameraData('save')))
    return

  def delete(self, *args, **kwargs):
    super().delete(*args, **kwargs)
    transaction.on_commit(partial(sendUpdateCommand,
                                  camera_data = self.cameraData('delete')))
    return

class SingletonSensor(Sensor):
  map_x = models.FloatField(default=None, null=True, blank=True)
  map_y = models.FloatField(default=None, null=True, blank=True)
  area = models.CharField(max_length=16, choices=AREA_CHOICES, default='scene')
  radius = models.FloatField(default=None, null=True, blank=True)
  singleton_type = models.CharField("Type of Sensor", max_length=20, choices=SINGLETON_CHOICES,
                                    default='environmental')

  def notifydbupdate(self):
    transaction.on_commit(sendUpdateCommand)
    return

  def get_sectors(self):
    if not hasattr(self, 'singleton_scalar_threshold'):
      return [{"color": "green", "color_min": "0"}, {"color": "yellow", "color_min": "2"}, {"color": "red", "color_min": "5"}], 10
    return self.singleton_scalar_threshold.sectors, self.singleton_scalar_threshold.range_max

  def delete(self, *args, **kwargs):
    super().delete(*args, **kwargs)
    transaction.on_commit(sendUpdateCommand)
    return

class DataLog(models.Model):
  timestamp = models.FloatField(db_index=True)

class MobileObject(models.Model):
  timestamp = models.FloatField(db_index=True)
  scene = models.ForeignKey(Scene, null=True, on_delete=models.SET_NULL)
  previous = models.OneToOneField('self', on_delete=models.CASCADE,
                                  null=True, blank=True, default=None)
  pid = models.IntegerField(default=None)
  x = models.FloatField(default=None, null=True, blank=True)
  y = models.FloatField(default=None, null=True, blank=True)

  def velocity(self):
    if not self.previous:
      return None
    xd = self.x - self.previous.x
    yd = self.y - self.previous.y
    td = self.log.timestamp - self.previous.log.timestamp
    if td == 0.0:
      return (0, 0)
    return (xd / td, yd / td)

  def expected(self, ts):
    v = self.velocity()
    if not v:
      v = (0, 0)
    return (self.x + v[0] * (ts - self.log.timestamp),
            self.y + v[1] * (ts - self.log.timestamp))

class Vehicle(MobileObject):
  pass

class CamLog(models.Model):
  log = models.OneToOneField(DataLog, on_delete=models.CASCADE,
                             primary_key=True, related_name="camLog")
  sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, db_index=True)
  pid = models.IntegerField(default=None, null=True, blank=True)
  x = models.FloatField(default=None, null=True, blank=True)
  y = models.FloatField(default=None, null=True, blank=True)
  width = models.FloatField(default=None, null=True, blank=True)
  height = models.FloatField(default=None, null=True, blank=True)

class SceneLog(models.Model):
  log = models.OneToOneField(DataLog, on_delete=models.CASCADE, primary_key=True)
  scene = models.ForeignKey(Scene, on_delete=models.CASCADE)

class BoundingBox(models.Model):
  name = models.CharField(max_length=200)

  def boundingBox(self):
    tx = None
    ty = None
    bx = None
    by = None
    for point in self.points.all():
      if not tx or point.x < tx:
        tx = point.x
      if not ty or point.y < ty:
        ty = point.y
      if not bx or point.x > bx:
        bx = point.x
      if not by or point.y > by:
        by = point.y
    if not tx:
      return None
    return ((tx, ty), (bx, by))

  def notifydbupdate(self):
    transaction.on_commit(sendUpdateCommand)
    return

  def delete(self, *args, **kwargs):
    super().delete(*args, **kwargs)
    self.notifydbupdate()
    return

class BoundingBoxPoints(models.Model):
  sequence = models.IntegerField(default=None, null=True, blank=True)
  x = models.FloatField(default=None, null=True, blank=True)
  y = models.FloatField(default=None, null=True, blank=True)

class Region(BoundingBox):
  uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
  scene = models.ForeignKey(Scene, on_delete=models.CASCADE, related_name="regions")
  buffer_size = models.FloatField(default=0.0, null=False, blank=False, validators=[MinValueValidator(0)])
  # Currently, there is no ROI support for objects under the ground plane.
  height = models.FloatField(default=1.0, null=False, blank=False, validators=[MinValueValidator(0.001)])
  volumetric = models.BooleanField(choices=BOOLEAN_CHOICES, default=False, null=True)

  def get_sectors(self):
    if not hasattr(self, 'roi_occupancy_threshold'):
      return [{"color": "green", "color_min": "0"}, {"color": "yellow", "color_min": "2"}, {"color": "red", "color_min": "5"}], 10
    return self.roi_occupancy_threshold.sectors, self.roi_occupancy_threshold.range_max

class RegionPoint(BoundingBoxPoints):
  region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="points")

class Tripwire(BoundingBox):
  uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
  scene = models.ForeignKey(Scene, on_delete=models.CASCADE, related_name="tripwires")
  height = models.FloatField(default=1.0, null=False, blank=False)

class TripwirePoint(BoundingBoxPoints):
  tripwire = models.ForeignKey(Tripwire, on_delete=models.CASCADE, related_name="points")

class SingletonAreaPoint(BoundingBoxPoints):
  singleton = models.ForeignKey(
    SingletonSensor, on_delete=models.CASCADE, related_name="points")

class Event(models.Model):
  region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="events")
  timestamp = models.FloatField(db_index=True)

class Asset3D(models.Model):
  name = models.CharField("Class Name", max_length=200, unique=True)
  x_size = models.FloatField("Object size in x-axis", default=1.0, validators=[MinValueValidator(0.0)])
  y_size = models.FloatField("Object size in y-axis", default=1.0, validators=[MinValueValidator(0.0)])
  z_size = models.FloatField("Object size in z-axis", default=1.0, validators=[MinValueValidator(0.0)])
  x_buffer_size = models.FloatField("Object buffer size in x-axis", default=0.0)
  y_buffer_size = models.FloatField("Object buffer size in y-axis", default=0.0)
  z_buffer_size = models.FloatField("Object buffer size in z-axis", default=0.0)
  mark_color = models.CharField("Mark Color", max_length=20, default="#888888", blank=True)
  model_3d = models.FileField(blank=True, null=True,
                              validators=[FileExtensionValidator(["glb"]), validate_glb])
  rotation_x = models.FloatField("X Rotation (degrees)", default=0.0, null=True, blank=True)
  rotation_y = models.FloatField("Y Rotation (degrees)", default=0.0, null=True, blank=True)
  rotation_z = models.FloatField("Z Rotation (degrees)", default=0.0, null=True, blank=True)
  translation_x = models.FloatField("X Translation (meters)", default=0.0,
                                    null=True, blank=True)
  translation_y = models.FloatField("Y Translation (meters)", default=0.0,
                                    null=True, blank=True)
  translation_z = models.FloatField("Z Translation (meters)", default=0.0,
                                    null=True, blank=True)
  scale = models.FloatField("Scale", default=1.0, null=True, blank=True)
  rotation_from_velocity = models.BooleanField(choices=BOOLEAN_CHOICES, default=False, null=True)
  tracking_radius = models.FloatField("Tracking radius (meters)", default=2.0)
  shift_type = models.IntegerField(choices=SHIFT_TYPE, default=1, null=True)
  project_to_map = models.BooleanField(choices=BOOLEAN_CHOICES, default=False, null=True)

  def __str__(self):
    return self.name

  def delete(self, *args, **kwargs):
    # Check if a 3D model also needs to be deleted
    if self.model_3d:
      storage, path = self.model_3d.storage, self.model_3d.path
      # Delete the model before the file
      super().delete(*args, **kwargs)
      # Delete the file after the model
      storage.delete(path)
    else:
      super().delete(*args, **kwargs)
    transaction.on_commit(sendUpdateCommand)
    return

  def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    transaction.on_commit(sendUpdateCommand)
    return

class DatabaseStatus(models.Model):
  is_ready = models.BooleanField(default=False)

  @classmethod
  def get_instance(cls):
    obj, _ = cls.objects.get_or_create(pk=1)
    return obj

  def save(self, *args, **kwargs):
    # Ensure that there is only one instance of this model
    self.pk = 1
    super(DatabaseStatus, self).save(*args, **kwargs)

class RegionOccupancyThreshold(models.Model):
  region = models.OneToOneField(Region, on_delete=models.CASCADE, related_name='roi_occupancy_threshold')
  sectors = models.JSONField(default=list)
  range_max = models.IntegerField(default=10)

  def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    return

  def __str__(self):
    return f"Occupancy Thresholds for {self.region}"

class SingletonScalarThreshold(models.Model):
  singleton = models.OneToOneField(SingletonSensor, on_delete=models.CASCADE, related_name='singleton_scalar_threshold')
  sectors = models.JSONField(default=list)
  range_max = models.IntegerField(default=10)

  def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    return
