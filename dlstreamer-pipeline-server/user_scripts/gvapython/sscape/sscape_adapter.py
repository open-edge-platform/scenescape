# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime
from uuid import getnode as get_mac

import cv2
import ntplib
import numpy as np
import paho.mqtt.client as mqtt
from pytz import timezone

from utils import publisher_utils as utils
from sscape_policies import (
  detectionPolicy,
  detection3DPolicy,
  reidPolicy,
  classificationPolicy,
  ocrPolicy,
)
from sscape_3d_detector import Object3DChainedDataProcessor

ROOT_CA = os.environ.get("ROOT_CA", "/run/secrets/certs/scenescape-ca.pem")
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
TIMEZONE = "UTC"

metadatapolicies = {
  "detectionPolicy": detectionPolicy,
  "detection3DPolicy": detection3DPolicy,
  "reidPolicy": reidPolicy,
  "classificationPolicy": classificationPolicy,
  "ocrPolicy": ocrPolicy,
}

def getMACAddress():
  if 'MACADDR' in os.environ:
    return os.environ['MACADDR']

  a = get_mac()
  h = iter(hex(a)[2:].zfill(12))
  return ":".join(i + next(h) for i in h)

class PostDecodeTimestampCapture:
  def __init__(self, ntpServer=None):
    self.log = logging.getLogger('SSCAPE_ADAPTER')
    self.log.setLevel(logging.INFO)
    self.ntpClient = ntplib.NTPClient()
    self.ntpServer = ntpServer
    self.lastTimeSync = None
    self.timeOffset = 0
    self.timestamp_for_next_block = None
    self.fps = 5.0
    self.fps_alpha = 0.75 # for weighted average
    self.last_calculated_fps_ts = None
    self.fps_calc_interval = 1 # calculate fps every 1s
    self.frame_cnt = 0

  def processFrame(self, frame):
    now = time.time()
    self.frame_cnt += 1
    if not self.last_calculated_fps_ts:
      self.last_calculated_fps_ts = now
    if (now - self.last_calculated_fps_ts) > self.fps_calc_interval:
      self.fps = self.fps * self.fps_alpha + (1 - self.fps_alpha) * (self.frame_cnt / (now - self.last_calculated_fps_ts))
      self.last_calculated_fps_ts = now
      self.frame_cnt = 0

    if self.ntpServer:
      # if ntpServer is available, check if it is time to recalibrate
      if not self.lastTimeSync or now - self.lastTimeSync > 1000 :
        response = self.ntpClient.request(host=self.ntpServer, port=123)
        self.timeOffset = response.offset
        self.lastTimeSync = now

    now += self.timeOffset
    self.timestamp_for_next_block = now
    frame.add_message(json.dumps({
      'postdecode_timestamp': f"{datetime.fromtimestamp(now, tz=timezone(TIMEZONE)).strftime(DATETIME_FORMAT)[:-3]}Z",
      'timestamp_for_next_block': now,
      'fps': self.fps
    }))
    return True

class PostInferenceDataPublish:

  CONVERSION_MAP = {
    'GST_VIDEO_FORMAT_NV12' : cv2.COLOR_YUV2BGR_NV12,
    'GST_VIDEO_FORMAT_I420' : cv2.COLOR_YUV2BGR_I420,
    'GST_VIDEO_FORMAT_BGRA' : cv2.COLOR_BGRA2BGR,
    'GST_VIDEO_FORMAT_RGB'  : cv2.COLOR_RGB2BGR
    }

  def __init__(self, cameraid, metadatagenpolicy='detectionPolicy', detection_labels=[], publish_image=False):
    self.cameraid = cameraid

    self.is_publish_image = publish_image
    self.is_publish_calibration_image = False
    self.cam_auto_calibrate = False
    self.cam_auto_calibrate_intrinsics = None
    self.detection_labels = detection_labels
    self.setupMQTT()
    self.metadatagenpolicy = metadatapolicies[metadatagenpolicy]
    self.frame_level_data = {'id': cameraid, 'debug_mac': getMACAddress()}
    self.sub_detector = Object3DChainedDataProcessor()

  def on_connect(self, client, userdata, flags, rc):
    if rc == 0:
      print(f"Connected to MQTT Broker {self.broker}")
      self.client.subscribe(f"scenescape/cmd/camera/{self.cameraid}")
      print(f"Subscribed to topic: scenescape/cmd/camera/{self.cameraid}")
    else:
      print(f"Failed to connect, return code {rc}")
    return

  def setupMQTT(self):
    self.client = mqtt.Client()
    self.client.on_connect = self.on_connect
    self.broker = os.environ.get('MQTT_HOST', 'broker.scenescape.intel.com')
    self.client.connect(self.broker, 1883, 120)
    self.client.on_message = self.handleCameraMessage
    if ROOT_CA and os.path.exists(ROOT_CA):
      self.client.tls_set(ca_certs=ROOT_CA)
    self.client.loop_start()
    return

  def handleCameraMessage(self, client, userdata, message):
    msg = message.payload.decode("utf-8")
    if msg == "getimage":
      self.is_publish_image = True
    elif msg == "getcalibrationimage":
      self.is_publish_calibration_image = True
    else:
      try:
        msg = json.loads(msg)
      except json.JSONDecodeError:
        return
      if isinstance(msg, dict) and msg.get('command') == "localize":
        self.cam_auto_calibrate = True
        if 'payload_intrinsics' in msg:
          self.cam_auto_calibrate_intrinsics = msg['payload_intrinsics']
    return

  def annotateObjects(self, img):
    objColors = ((0, 0, 255), (66, 186, 150), (207, 83, 255), (31, 156, 238))

    if 'car' in self.frame_level_data['objects']:
      intrinsics = self.frame_level_data.get('initial_intrinsics')
      self.sub_detector.annotateObjectAssociations(img, self.frame_level_data['objects'], objColors, 'car', 'license_plate', intrinsics=intrinsics)
      return

    for otype, objects in self.frame_level_data['objects'].items():
      if otype == "person":
        cindex = 0
      elif otype == "vehicle" or otype == "bicycle":
        cindex = 1
      else:
        cindex = 2
      for obj in objects:
        topleft_cv = (int(obj['bounding_box_px']['x']), int(obj['bounding_box_px']['y']))
        bottomright_cv = (int(obj['bounding_box_px']['x'] + obj['bounding_box_px']['width']),
                        int(obj['bounding_box_px']['y'] + obj['bounding_box_px']['height']))
        cv2.rectangle(img, topleft_cv, bottomright_cv, objColors[cindex], 4)
    return

  def annotateFPS(self, img, fpsval):
    fpsStr = f'FPS {fpsval:.1f}'
    scale = int((img.shape[0] + 479) / 480)
    cv2.putText(img, fpsStr, (0, 30 * scale), cv2.FONT_HERSHEY_SIMPLEX,
            1 * scale, (0,0,0), 5 * scale)
    cv2.putText(img, fpsStr, (0, 30 * scale), cv2.FONT_HERSHEY_SIMPLEX,
            1 * scale, (255,255,255), 2 * scale)
    return

  def _tryConvertToBgr(self, raw_frame, video_meta):
    video_format = video_meta.format.value_name
    if video_format in PostInferenceDataPublish.CONVERSION_MAP:
      return cv2.cvtColor(raw_frame, PostInferenceDataPublish.CONVERSION_MAP[video_format])
    else:
      return np.copy(raw_frame)

  def buildImgData(self, imgdatadict, gvaframe, annotate, original_image_base64=None):
    imgdatadict.update({
      'timestamp': self.frame_level_data['timestamp'],
      'id': self.cameraid
    })
    image = None

    if original_image_base64:
      try:
        decoded_image = base64.b64decode(original_image_base64)
        original_image = cv2.imdecode(np.frombuffer(decoded_image, np.uint8), cv2.IMREAD_COLOR)
        if original_image is None:
          raise ValueError("Failed to decode original image from base64")
        image = original_image
      except (Exception) as e:
        print(f"Error using original image: {e}. Falling back to current frame.")

    if image is None:
      with gvaframe.data() as img:
        video_meta = gvaframe.video_meta()
        image = self._tryConvertToBgr(img, video_meta)

    if annotate:
      self.annotateObjects(image)
      self.annotateFPS(image, self.frame_level_data['rate'])
    _, jpeg = cv2.imencode(".jpg", image)
    jpeg = base64.b64encode(jpeg).decode('utf-8')
    imgdatadict['image'] = jpeg
    return

  def buildObjData(self, gvadata):
    now = time.time()
    self.frame_level_data.update({
      'timestamp': gvadata['postdecode_timestamp'],
      'debug_timestamp_end': f"{datetime.fromtimestamp(now, tz=timezone(TIMEZONE)).strftime(DATETIME_FORMAT)[:-3]}Z",
      'debug_processing_time': now - float(gvadata['timestamp_for_next_block']),
      'rate': float(gvadata['fps'])
    })
    if 'initial_intrinsics' in gvadata:
      self.frame_level_data['initial_intrinsics'] = gvadata['initial_intrinsics']
    objects = defaultdict(list)
    if 'objects' in gvadata and len(gvadata['objects']) > 0:
      framewidth, frameheight = gvadata['resolution']['width'], gvadata['resolution']['height']
      # gvadetect sets parent_id field only if inference-region=roi-list (on second gvadetect in your pipeline).
      has_parent_ids = any('parent_id' in det for det in gvadata['objects'])
      if has_parent_ids:
        # Two-pass approach: first build all objects, then nest children into parents.
        # region_id_map allows O(1) parent lookup by region_id.
        region_id_map = {}
        ordered_dets = []
        for det in gvadata['objects']:
          vaobj = {}
          self.metadatagenpolicy(vaobj, det, framewidth, frameheight)
          if self.detection_labels and vaobj['category'] not in self.detection_labels:
            continue
          region_id = det.get('region_id')
          parent_id = det.get('parent_id')
          ordered_dets.append((vaobj, region_id, parent_id))
          if region_id is not None:
            region_id_map[region_id] = vaobj

        for vaobj, region_id, parent_id in ordered_dets:
          otype = vaobj['category']
          if parent_id is not None and parent_id in region_id_map:
            parent_obj = region_id_map[parent_id]
            sub_objects = parent_obj.setdefault('sub_objects', defaultdict(list))
            vaobj['id'] = len(sub_objects[otype]) + 1
            sub_objects[otype].append(vaobj)
          else:
            vaobj['id'] = len(objects[otype]) + 1
            objects[otype].append(vaobj)

        # Convert sub_objects defaultdicts to plain dicts
        for obj_list in objects.values():
          for obj in obj_list:
            if 'sub_objects' in obj:
              obj['sub_objects'] = dict(obj['sub_objects'])
      else:
        # Fast path: no parent_id present.
        for det in gvadata['objects']:
          vaobj = {}
          self.metadatagenpolicy(vaobj, det, framewidth, frameheight)
          if self.detection_labels and vaobj['category'] not in self.detection_labels:
            continue
          otype = vaobj['category']
          vaobj['id'] = len(objects[otype]) + 1
          objects[otype].append(vaobj)

    self.processSubDetections(objects)
    self.frame_level_data['objects'] = objects
    return

  def processSubDetections(self, objects):
    """process sub detection when multiple models are chained together in the pipeline"""
    if 'car' in objects and 'license_plate' in objects:
      intrinsics = self.frame_level_data.get('initial_intrinsics')
      sub_detections = self.sub_detector.associateObjects(objects, 'car', 'license_plate', intrinsics=intrinsics)
      if sub_detections:
        self.frame_level_data['sub_detections'] = sub_detections
    return

  def processFrame(self, frame):
    if self.client.is_connected():
      gvametadata, annotated_img, unannotated_img = {}, {}, {}
      original_image_base64 = None

      utils.get_gva_meta_messages(frame, gvametadata)
      gvametadata['gva_meta'] = utils.get_gva_meta_regions(frame)
      self.mergeRegionsIntoObject(gvametadata)

      if 'original_image_base64' in gvametadata:
        original_image_base64 = gvametadata['original_image_base64']
      self.buildObjData(gvametadata)

      if self.is_publish_image:
        self.buildImgData(annotated_img, frame, True, original_image_base64)
        self.client.publish(f"scenescape/image/camera/{self.cameraid}", json.dumps(annotated_img))
        self.is_publish_image = False

      if self.is_publish_calibration_image:
        if not unannotated_img:
          self.buildImgData(unannotated_img, frame, False, original_image_base64)
        self.client.publish(f"scenescape/image/calibration/camera/{self.cameraid}", json.dumps(unannotated_img))
        self.is_publish_calibration_image = False

      if self.cam_auto_calibrate:
        self.cam_auto_calibrate = False
        if not unannotated_img:
          self.buildImgData(unannotated_img, frame, False)
        unannotated_img['calibrate'] = True
        if self.cam_auto_calibrate_intrinsics:
          unannotated_img['intrinsics'] = self.cam_auto_calibrate_intrinsics
        self.client.publish(f"scenescape/image/calibration/camera/{self.cameraid}", json.dumps(unannotated_img))

      self.client.publish(f"scenescape/data/camera/{self.cameraid}", json.dumps(self.frame_level_data))
      frame.add_message(json.dumps(self.frame_level_data))
    return True

  def mergeRegionsIntoObject(self, gvadata):
    custom_regions = gvadata.get("custom_regions_3d", [])
    objects = gvadata.get("objects", [])

    if not custom_regions or not objects:
      return
    print(f"Merging {len(custom_regions)} custom 3D regions into {len(objects)} objects")

    for det in objects:
      dx = det.get("x")
      dy = det.get("y")
      dw = det.get("w")
      dh = det.get("h")

      best_match = None
      best_score = None

      for region in custom_regions:
        bbox = region.get("bbox", {})
        rx = bbox.get("x")
        ry = bbox.get("y")
        rw = bbox.get("w")
        rh = bbox.get("h")

        if None in (dx, dy, dw, dh, rx, ry, rw, rh):
          continue

        # Exact match first
        if dx == rx and dy == ry and dw == rw and dh == rh:
          best_match = region
          break

        # Fallback: choose nearest bbox if exact match is not found
        score = abs(dx - rx) + abs(dy - ry) + abs(dw - rw) + abs(dh - rh)
        if best_score is None or score < best_score:
          best_score = score
          best_match = region

      if best_match is not None:
        det["extra_params"] = {
          "translation": best_match.get("translation"),
          "rotation": best_match.get("rotation"),
          "dimension": best_match.get("dimension"),
        }
