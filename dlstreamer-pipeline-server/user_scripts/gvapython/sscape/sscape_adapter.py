# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
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

    # Capture original resolution before videoscale resizes the frame.
    # Runs once on first frame, then reuses cached values.
    if not hasattr(self, '_orig_w'):
      try:
        vi = frame.video_info()
        self._orig_w, self._orig_h = vi.width, vi.height
      except Exception:
        self._orig_w, self._orig_h = 0, 0

    frame.add_message(json.dumps({
      'postdecode_timestamp': f"{datetime.fromtimestamp(now, tz=timezone(TIMEZONE)).strftime(DATETIME_FORMAT)[:-3]}Z",
      'timestamp_for_next_block': now,
      'fps': self.fps,
      'original_width': self._orig_w,
      'original_height': self._orig_h,
    }))
    return True

class PostInferenceDataPublish:
  def __init__(self, *args, **kwargs):
    # Extract configuration from GStreamer parameters
    config = {}
    
    # Handle both args and kwargs for backward compatibility
    if args and len(args) > 0:
      # If first argument is a string (cameraid), use legacy direct parameter mode  
      if isinstance(args[0], str):
        config['cameraid'] = args[0]
        config['metadatagenpolicy'] = args[1] if len(args) > 1 else 'detectionPolicy' 
        config['publish_image'] = args[2] if len(args) > 2 else False
      else:
        # Base64 config in args - not expected for this class but handle gracefully
        pass
        
    # Check for kwarg parameter (GStreamer parameter injection)
    elif 'kwarg' in kwargs:
      config = kwargs['kwarg'] if isinstance(kwargs['kwarg'], dict) else {}
    else:
      # Direct kwargs passing
      config = kwargs.copy()
      
    # Set defaults for required parameters
    self.cameraid = config.get('cameraid', 'default_camera')
    self.is_publish_image = config.get('publish_image', False)
    metadatagenpolicy = config.get('metadatagenpolicy', 'detectionPolicy')
    
    self.is_publish_calibration_image = False
    self.cam_auto_calibrate = False
    self.cam_auto_calibrate_intrinsics = None
    self.setupMQTT()
    self.metadatagenpolicy = metadatapolicies[metadatagenpolicy]
    self.frame_level_data = {'id': self.cameraid, 'debug_mac': getMACAddress()}
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

    # Scale factor: bboxes are in gvametaconvert resolution (e.g. 640x640),
    # image may have been resized to original resolution. For OpenVINO
    # pipelines both match, so scale = 1.0.
    bbox_w = self.frame_level_data.get('_bbox_w', img.shape[1])
    bbox_h = self.frame_level_data.get('_bbox_h', img.shape[0])
    sx = img.shape[1] / bbox_w
    sy = img.shape[0] / bbox_h

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
        bx = obj['bounding_box_px']['x']
        by = obj['bounding_box_px']['y']
        bw = obj['bounding_box_px']['width']
        bh = obj['bounding_box_px']['height']
        topleft_cv = (int(bx * sx), int(by * sy))
        bottomright_cv = (int((bx + bw) * sx), int((by + bh) * sy))
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

  def buildImgData(self, imgdatadict, gvaframe, annotate, original_image_base64=None):
    imgdatadict.update({
      'timestamp': self.frame_level_data['timestamp'],
      'id': self.cameraid
    })
    image = original_image_base64
    if image is None:
      with gvaframe.data() as img:
        image = np.array(img, copy=True)
    else:
      try:
        decoded_image = base64.b64decode(image)
        original_image = cv2.imdecode(np.frombuffer(decoded_image, np.uint8), cv2.IMREAD_COLOR)
        if original_image is None:
          raise ValueError("Failed to decode original image from base64")
        image = original_image
      except (ValueError, Exception) as e:
        print(f"Error using original image: {e}. Falling back to current frame.")

    # Scale image back to original resolution if it was resized for inference.
    # e.g. 640x640 → 1920x1080. Bboxes are also scaled in annotateObjects.
    orig_w = self.frame_level_data.get('_orig_w', 0)
    orig_h = self.frame_level_data.get('_orig_h', 0)
    if orig_w > 0 and orig_h > 0 and (image.shape[1] != orig_w or image.shape[0] != orig_h):
      image = cv2.resize(image, (orig_w, orig_h))

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
      'rate': float(gvadata['fps']),
      '_orig_w': int(gvadata.get('original_width', 0)),
      '_orig_h': int(gvadata.get('original_height', 0)),
    })
    if 'initial_intrinsics' in gvadata:
      self.frame_level_data['initial_intrinsics'] = gvadata['initial_intrinsics']
    objects = defaultdict(list)
    if 'objects' in gvadata and len(gvadata['objects']) > 0:
      framewidth, frameheight = gvadata['resolution']['width'], gvadata['resolution']['height']

      # Scale detection pixel coords from inference resolution to original camera resolution.
      # When GStreamer videoscale reduces the frame for Triton (e.g. 1920x1080 → 640x640),
      # detection coords must be rescaled to original camera space so SceneScape's
      # calibration (performed at original resolution) correctly projects to the 3D map.
      orig_w = self.frame_level_data.get('_orig_w', 0)
      orig_h = self.frame_level_data.get('_orig_h', 0)
      if orig_w > 0 and orig_h > 0 and (orig_w != framewidth or orig_h != frameheight):
        proj_w, proj_h = orig_w, orig_h
        sx = orig_w / framewidth
        sy = orig_h / frameheight
      else:
        proj_w, proj_h = framewidth, frameheight
        sx, sy = 1.0, 1.0

      self.frame_level_data['_bbox_w'] = proj_w
      self.frame_level_data['_bbox_h'] = proj_h

      for det in gvadata['objects']:
        vaobj = {}
        if sx != 1.0 or sy != 1.0:
          det = dict(det)
          det['x'] = int(det['x'] * sx)
          det['y'] = int(det['y'] * sy)
          det['w'] = int(det['w'] * sx)
          det['h'] = int(det['h'] * sy)
        self.metadatagenpolicy(vaobj, det, proj_w, proj_h)
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
