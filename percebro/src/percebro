#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import base64
import json
import re
import sys
import os
from argparse import ArgumentParser
from uuid import getnode as get_mac

import cv2
import ntplib
import numpy as np
from termcolor import colored

from framebuffer import FrameBuffer
from inferizer import Inferizer, InferenceParameters
from modelchain import ModelChain
from sensor import PercebroSensor
from vcr import VCR
from videoframe import VideoFrame
from videosource import VideoSource

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import adjust_time, get_iso_time, get_epoch_time
from scene_common.transform import CameraIntrinsics
from scene_common import log

def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("broker", nargs="?", default="localhost",
                      help="hostname or IP of MQTT broker")
  parser.add_argument("--camerachain", "-m", "--model", help="model to use for camera",
                      type=str)
  parser.add_argument("--camera", "-i", "--input", action="append",
                      help="video source to be used. If using /dev/video0 the"
                      " argument should be -i 0", required=True)
  parser.add_argument("--cameraid", "--mqttid", action="append",
                      help="camera id to use instead of MAC+input")
  parser.add_argument("--sensor", action="append",
                      help="name and optional bounding box to publish as sensor")
  parser.add_argument("--sensorchain", action="append",
                      help="model chain to use for sensor")
  parser.add_argument("--sensorattrib", action="append",
                      help="attribute/field name of data to use for sensor value")
  parser.add_argument("-e", "--threshold", help="Threshold to filter keypoints",
                      type=float, default=0.5)
  parser.add_argument("--window", action="store_true", help="Display a window")
  parser.add_argument("--usetimestamps", action="store_true",
                      help="Use file timestamps to synchronize videos")
  parser.add_argument("--ntp", help="NTP server, default is to use mqtt broker")
  parser.add_argument("--virtual",
                      help="JSON list for virtual cameras")
  parser.add_argument("--debug", action="store_true",
                      help="Run in debug mode, don't connect to MQTT broker or NTP server")
  parser.add_argument("--aspect", help="aspect ratio to force")
  parser.add_argument("--intrinsics", action="append", help="camera intrinsics as diagonal_fov, \"[horizontal_fov, vertical_fov]\", or \"[fx, fy, cx, cy]\"")
  parser.add_argument("--distortion", action="append", help="camera distortion coeffs, \"[k1,k2,p1,p2[,k3[,k4,k5,k6[,s1,s2,s3,s4[,taux,tauy]]]]]\"")
  parser.add_argument("--override-saved-intrinsics", action="store_true",
                      help="Override camera intrinsics in database with command line values")
  parser.add_argument("--frames", type=int, help="process this many frames and then exit")
  parser.add_argument("--stats", action="store_true", help="Print FPS/latency stats")
  parser.add_argument("--waitforstable", action="store_true", help="Print FPS/latency stats")
  parser.add_argument("--preprocess", action="store_true",
                      help="Preprocess video files into json files and exit")
  parser.add_argument("--realtime", action="store_true",
                      help="Drop frames to keep video at original speed during processing"
                      " <preprocess only>")
  parser.add_argument("--faketime", action="store_true",
                      help="Write timestamps as fast as they occur <preprocess only>")
  parser.add_argument("--modelconfig", help="JSON file with model configuration",
                      default="model-config.json")
  parser.add_argument("--resturl", default="web.scenescape.intel.com",
                      help="URL of REST server")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")
  parser.add_argument("--cert", help="path to client certificate")
  parser.add_argument("--auth", help="user:password or JSON file for MQTT authentication")
  parser.add_argument("--cvcores", help="Number of threads to request for OpenCV",
                      type=int, default=2)
  parser.add_argument("--ovcores", help="Number of threads to request for OpenVINO",
                      type=int, default=4)
  parser.add_argument("--unwarp", action="store_true", help="Unwarp image before inference")
  parser.add_argument("--ovmshost", help="OVMS host", type=str, default="ovms:9000")
  parser.add_argument("--resolution", action="append",
                      help="Requested frame resolution (WxH)")
  parser.add_argument("--framerate", action="append",
                      help="Requested framerate", type=float)
  parser.add_argument("--cv_subsystem", default="CPU",
                      help="Hardware device requested for decoding. "
                      "Options are 'CPU' (default), 'ANY', 'GPU', or 'GPU.X' where X refers to the card available at /dev/dri/cardX")
  parser.add_argument("--maxcache", help="Max video cache size in frames. Specify the desired max number of frames to process in parallel.",
                      type=int, default=0)
  parser.add_argument("--filter", type=str,
                      help="Bounding box filtering for sub-detections. Options are 'bottom', 'top', or 'none'."
                      " This will allow only the bottom-most, top-most, or all detections through. Default is 'none'")
  parser.add_argument("--disable_rotation", action='store_true',
                      help="Disable closest face rotation algorithm for 3d object detection")
  parser.add_argument("--maxdistance", help="Max distance from camera for object detection. Objects beyond this threshold will be dropped.",
                      action='append' )
  parser.add_argument("--infrared",
                      help="Use infrared channel, for RealSense cameras or ROSBAG files. Note this will affect all cameras for this instance.",
                      action='store_true' )
  return parser

def _json_default(obj):
  if isinstance(obj, np.generic):
    return obj.item()
  if isinstance(obj, np.ndarray):
    return obj.tolist()
  raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def mqttDidConnect(client, userdata, flags, rc):
  global cams

  if rc != 0:
    log.error("Unable to connect to broker:", rc)
    exit(1)

  for cam in cams:
    log.info("Subscribing", cam.mqttTopic)
    client.addCallback(cam.mqttTopic, handleCameraMessage)
    log.info("Subscribing", cam.camcalibtopic)
    client.addCallback(cam.camcalibtopic, handleCameraMessage)
    log.info("Subscribing", PubSub.formatTopic(PubSub.SYS_PERCEBRO_STATUS, camera_id=cam.mqttID))
    client.addCallback(PubSub.formatTopic(PubSub.SYS_PERCEBRO_STATUS, camera_id=cam.mqttID), handleSysPercebroMessage)
    cam.sendImage = True

  return

def getMACAddress():
  if 'MACADDR' in os.environ:
    return os.environ['MACADDR']

  log.info("Getting MAC the hard way")
  a = get_mac()
  h = iter(hex(a)[2:].zfill(12))
  return ":".join(i + next(h) for i in h)

def findUnique(name, all):
  if len(all) == 1:
    return all[0]
  commonPrefix = os.path.commonprefix(all)
  revAll = []
  for path in all:
    revAll.append(path[::-1])
  commonSuffix = os.path.commonprefix(revAll)
  return name[len(commonPrefix):-len(commonSuffix)]

def publishObjects(all_objects, ts, mac_addr, mqttid, client, rate,
                   ts_end, processing_time, intrinsics, frame_rate=-1):
  pub = {'timestamp': ts,
         'debug_timestamp_end': ts_end,
         'debug_processing_time': processing_time,
         'debug_mac': mac_addr,
         'id': mqttid,
         'objects': all_objects,
         'rate': rate,
         'intrinsics': intrinsics['intrinsics'],
         'distortion': intrinsics['distortion'],
         'frame_rate': frame_rate
        }
  client.publish(
    PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=mqttid),
    json.dumps(pub, default=_json_default)
  )
  return

def handleSysPercebroMessage(client, userdata, message):
  topic = PubSub.parseTopic(message.topic)
  msg = message.payload.decode("utf-8")
  if str(msg) == "isAlive":
    client.publish(PubSub.formatTopic(PubSub.SYS_PERCEBRO_STATUS, camera_id=topic['camera_id']), "running")
  return

def handleCameraMessage(client, userdata, message):
  global sendAllCamImages, cams
  global cameraChain

  topic = PubSub.parseTopic(message.topic)
  msg = str(message.payload.decode("utf-8"))
  camName = topic['camera_id']
  for cam in cams:
    if cam.mqttID == camName:
      if msg == "getimage":
        cam.sendImage = True

      elif msg.startswith("getimage:"):
        descriptor = json.loads(msg[len("getimage:"):])
        vdata = cam.frameBuffer.getFrame()
        if not vdata:
          return

        topic = PubSub.formatTopic(PubSub.CHANNEL, channel=descriptor['channel'])
        timestamp_iso, frame = _parseVdata(descriptor, vdata)
        publishImage(topic, frame, vdata, client, timestamp_iso)
        log.info("PUBLISHED", topic, timestamp_iso)

      elif msg == "startcapture":
        if not hasattr(cam, 'vcr'):
          cam.vcr = VCR(cam.url)
        cam.vcr.startCapture()

      elif msg == "stopcapture":
        if hasattr(cam, 'vcr'):
          cam.vcr.stopCapture()

      elif msg.startswith("getvideo:"):
        if hasattr(cam, 'vcr'):
          descriptor = json.loads(msg[len("getimage:"):])
          topic = PubSub.formatTopic(PubSub.VIDEO_CHANNEL, camera_id=cam.mqttID,
                                     channel=descriptor['channel'])
          cam.vcr.publishVideoInNewThread(client, topic)

      elif msg == "localize":
        cam.sendImageForCalibration = True
        cam.autocalibrate = True

      elif msg == "getcalibrationimage":
        cam.sendImageForCalibration = True

      elif 'updatecamera' in msg:
        data = json.loads(msg).get('updatecamera')
        intrinsics = CameraIntrinsics(data.get('intrinsics'), data.get('distortion'))
        cam.intrinsics = intrinsics
      break
  else:
    sendAllCamImages = True

  return

def _parseVdata(descriptor, vdata):
  timestamp_iso = get_iso_time(vdata.begin)
  frameType = descriptor.get('frame_type', "annotated")
  frame = None
  if isinstance(frameType, str):
    frameType = [frameType]
  if "unannotated" in frameType:
    frame = vdata.unannotatedFrame()
  elif "annotated" in frameType:
    frame = vdata.annotatedFrame(cameraChain)
  return timestamp_iso, frame

def logStats(models, vdata, cams, vcache, latencyAvg, averageStable):
  for m in models:
    model = models[m]
    if model.dependencies is None:
      break
  odata = vdata.output[m]
  fpsStr = "%iobj %i" % (len(odata.data[0]), len(vcache))
  for m in models:
    fpsStr += " %s:%2i" % (m, models[m].engine.waitingCount)
  total = 0
  for idx, cam in enumerate(cams):
    if cam.frameAvg is None:
      return

    if len(fpsStr):
      fpsStr += "   "
    fpsStr += cam.mqttID + " FPS %02.1f" % (1 / cam.frameAvg)
    total += 1 / cam.frameAvg
  avgStr = "%0.2f %0.3fms" % (total, latencyAvg * 1000)
  eol = '\n'
  if sys.stdout.isatty():
    color = "green" if averageStable else "yellow"
    avgStr = colored(avgStr, color)
    eol = '\r'

  print(vdata.frameCount, avgStr, fpsStr + "   ", end=eol, file=sys.stderr)
  return

def extractOffsets(inputs):
  offsets = []
  for name in inputs:
    o = 0
    match = re.search("=([-+][.0-9]+)$", name)
    if match:
      name = name[:match.start()]
      o = float(match.group(1))
      log.debug("OFFSET", o)
    offsets.append((name, o))
  names = [x[0] for x in offsets]
  return names, offsets

def extractResolution(resolution, idx):
  if resolution and idx < len(resolution):
    sep = resolution[idx].find('x')
    if sep < 0:
      log.error("Invalid resolution requested. Need WxH")
    else:
      width = int(resolution[idx][:sep])
      height = int(resolution[idx][sep+1:])
      return (width, height)
  return None

def extractAspectRatio(aspect, cam):
  if aspect:
    sep = aspect.find(':')
    if sep < 0:
      sep = aspect.find('x')
    if sep < 0:
      ar = float(aspect)
    else:
      ar = float(aspect[:sep]) / float(aspect[sep+1:])
    cam.aspect = ar
  return

def setupCameras(mac_addr, inputs, intrinsics, distortion, aspect, mqttid,
                 realtime, usetimestamps, preprocess, unwarpFlag, REST_client=None,
                 cvSubsystem='ANY', resolution=None, framerate=None, max_distance=None):
  cams = []
  names, offsets = extractOffsets(inputs)
  startTime = endTime = None

  for idx, (name, offset) in enumerate(offsets):
    uniqueID = findUnique(name, names)
    use_intrins = parseIntrinsics(intrinsics, idx)
    use_distort = parseDistortion(distortion, idx)
    cam_resolution = extractResolution(resolution, idx)

    if REST_client and REST_client.isAuthenticated:
      log.info("Getting camera info for", mqttid[idx])
      cam_info = REST_client.getCamera(mqttid[idx])
      if cam_info.statusCode == 200:
        stored_intrins = cam_info.get("intrinsics", use_intrins)
        if 'fx' in stored_intrins and 'fy' in stored_intrins:
          use_intrins['fx'], use_intrins['fy'] = stored_intrins['fx'], stored_intrins['fy']
        use_distort = cam_info.get("distortion", use_distort)
      else:
        log.info("No stored camera info for ", mqttid[idx])

    use_max_distance = float(max_distance[idx]) if max_distance is not None else None
    cam = VideoSource(name, use_intrins, use_distort, uniqueID, loop=not preprocess,
                      cvSubsystem=cvSubsystem, resolution=cam_resolution, max_distance=use_max_distance)
    if not hasattr(cam, 'intrinsics'):
      log.error("Intrinsics required for:", name)
      exit(1)
    cam.unwarp = unwarpFlag

    if framerate and idx < len(framerate):
      if not cam.setFramerate(framerate[idx]):
        log.error("Failed setting desired framerate {}".format(framerate[idx]))
        return None

    if mqttid and idx < len(mqttid):
      cam.mqttID = mqttid[idx]
    else:
      cam.mqttID = mac_addr + "-" + uniqueID[-2:]
      cam.mqttID = cam.mqttID.replace("/", "_")

    extractAspectRatio(aspect, cam)

    if preprocess:
      path, ext = os.path.splitext(cam.camID)
      path += ".json"
      cam.jsonFile = open(path, "w")

    if cam.frameCount == 1:
      cam.loop = True

    cam.mqttTopic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=cam.mqttID)
    cam.camcalibtopic = PubSub.formatTopic(PubSub.DATA_AUTOCALIB_CAM_POSE, camera_id="#")
    cam.startOffset = offset
    cam.realTime = realtime or not preprocess
    cam.sendImage = False
    cam.sendImageForCalibration = False
    cam.frameBuffer = FrameBuffer()
    cam.frameLast = get_epoch_time()
    cam.frameCount = 0
    cam.frameAvg = None
    if cam.supportsPositionUpdate():
      _setStartEndPos(usetimestamps, cam, endTime, startTime)
    cams.append(cam)

  return cams

def _setStartEndPos(usetimestamps, cam, endTime, startTime):
  if not usetimestamps:
    cstart = 0
  else:
    cstart = cam.startTime
  cstart += cam.startOffset
  cend = cstart + cam.length / 1000
  if cstart >= 0 and (not startTime or startTime < cstart):
    startTime = cstart
  if not endTime or endTime > cend:
    endTime = cend

  spos = startTime - cstart
  epos = endTime - cstart
  if spos > epos:
    log.error("Start is beyond end", cam.camID, spos, epos)
    exit(1)
  log.info("Range", cam.mqttID, spos, epos)
  cam.setStartPosition(spos)
  cam.setEndPosition(epos)
  return

def parseIntrinsics(intrinsics, idx):
  use_intrins = None
  if intrinsics and idx < len(intrinsics):
    use_intrins = intrinsics[idx]
  if isinstance(use_intrins, str):
    use_intrins = json.loads(use_intrins)
  return use_intrins

def parseDistortion(distortion, idx):
  use_distort = None
  if distortion and idx < len(distortion):
    use_distort = distortion[idx]
  if isinstance(use_distort, str):
    use_distort = json.loads(use_distort)
  return use_distort

def connectToMQTT(auth, cert, rootcert, broker):
  """! Connects to the MQTT broker.

  @param    broker    Contains name and port of MQTT broker
  @param    client    Handles MQTT communications.

  @return   None
  """
  client = PubSub(auth, cert, rootcert, broker)

  log.info("Connecting to broker", broker)
  client.onConnect = mqttDidConnect

  client.connect()
  client.loopStart()

  return client

def getVideoFrame(virtual, cam, now, filtering=None, disable_3d_rotation=False, use_infrared=False):
  """! Creates and configures Video Frame object

  @param    virtual   Virtual cameras loaded from JSON file.
  @param    cam       Contains information of a camera.
  @param    now       Contains the current real time.

  @return   A newly created VideoFrame object
  """
  frame = cam.capture()

  if frame is None:
    return None

  if not hasattr(cam, 'frameCount'):
    cam.frameCount = 0
  cam.frameCount += 1

  if hasattr(frame, "depth"):
    if use_infrared:
      # Skip frames that are captured when the laser is on.
      while frame.infrared_metadata:
        frame = cam.capture()
      vdata = VideoFrame(cam, frame.infrared, virtual, depth=frame.depth, \
                         filtering=filtering, disable_3d_rotation=disable_3d_rotation, is_gray=True)
    else:
      vdata = VideoFrame(cam, frame.color, virtual, depth=frame.depth, \
                         filtering=filtering, disable_3d_rotation=disable_3d_rotation)

  else:
    vdata = VideoFrame(cam, frame, virtual, \
                       filtering=filtering, disable_3d_rotation=disable_3d_rotation)

  if hasattr(cam, 'jsonFile'):
    vdata.jsonFile = cam.jsonFile
  vdata.begin = now
  vdata.frameCount = cam.frameCount

  return vdata

def frameToBase64(frame):
  """! Converts a frame to base64 encoding.

  @param    frame    Frame of a video from a camera.

  @return   Base64 encoding of the frame
  """
  _, jpeg = cv2.imencode(".jpg", frame)
  return base64.b64encode(jpeg).decode('utf-8')

def publishImage(topic, frame, vdata, client, ts, additional_data=None):
  """! Publish image to the MQTT broker.
  @param    topic            Topic on which the message is to be published.
  @param    frame            Frame of a video from a camera.
  @param    vdata            A VideoFrame object that stores information about a frame.
  @param    client           Handles MQTT communications.
  @param    ts               Contains video frame begin timestamp.
  @param    additional_data  Additional data to be sent in the image dictionary.

  @return   None
  """

  camIntrinsics = vdata.cam.intrinsics.intrinsics.tolist()
  camDistortion = vdata.cam.intrinsics.distortion.tolist()

  image_dict = {
    'timestamp': ts,
    'intrinsics': camIntrinsics,
    'distortion': camDistortion,
    'id': vdata.cam.mqttID,
  }

  if frame is not None:
    image_dict['image'] = frameToBase64(frame)

  if additional_data:
    image_dict.update(additional_data)

  client.publish(topic, json.dumps(image_dict))
  return

def processSensors(sensors, now, client):
  for sensor in sensors:
    vdata = sensor.available(now)
    if not vdata:
      continue

    allObjects = sensor.modelChain.getAllObjects(vdata)
    flatObjects = sensor.modelChain.flatten(allObjects)
    if not flatObjects:
      continue

    value = []
    for object in flatObjects:
      if sensor.attrib:
        data = object[sensor.attrib]
      else:
        data = {}
        for attrib in object:
          if not attrib.startswith("debug_") and attrib not in ("id", "category"):
            data[attrib] = object[attrib]
      value.append(data)
    if len(value) == 1:
      value = value[0]

    sensorData = {
      'id': sensor.mqttID,
      'subtype': flatObjects[0]['category'],
      'timestamp': get_iso_time(vdata.begin),
      'value': value,
    }
    if client:
      topic = PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensorData['id'])
      client.publish(topic, json.dumps(sensorData))
    else:
      log.info("Detected", sensorData)

  return

def main():
  global cams, sendAllCamImages
  global cameraChain

  args = build_argparser().parse_args()
  if not args.camerachain and not args.sensorchain:
    log.error("No camerachain or sensorchain provided")
    exit(1)
  if args.filter \
      and args.filter != 'bottom' \
      and args.filter != 'top' \
      and args.filter != 'none':
    log.error("Invalid filtering requested. Must be 'bottom', 'top', or 'none'.")
    exit(1)
  cv2.setNumThreads(args.cvcores)

  Inferizer.loadModelConfig(args.modelconfig)

  mac_addr = getMACAddress()

  cams = []
  sendAllCamImages = False
  virtual = None
  if args.virtual:
    virtual = json.loads(args.virtual)
  singleStep = False
  doStep = False
  client = None
  REST_client = None
  sensors = []

  if not args.debug and not args.preprocess and not args.override_saved_intrinsics:
    REST_client = RESTClient("https://" + args.resturl + "/api/v1",\
                             args.rootcert, args.auth)

  cams = setupCameras(mac_addr, args.camera, args.intrinsics, args.distortion, args.aspect,
                      args.cameraid, args.realtime, args.usetimestamps, args.preprocess,
                      args.unwarp, REST_client, args.cv_subsystem, args.resolution,
                      args.framerate, args.maxdistance)

  if cams is None:
    log.error("Camera setup failed!")
    return 1

  infParams = InferenceParameters(args.threshold, args.ovcores, args.ovmshost)
  cameraChain = ModelChain(args.camerachain, infParams)

  if args.sensor:
    sensors = PercebroSensor.initializeSensors(args.sensor, args.sensorattrib,
                                               args.sensorchain, infParams)

  # Enable video loop for videos with fewer frames than requested in command line
  for cam in cams:
    if cam.frameCount is not None and args.frames is not None:
      if cam.frameCount < args.frames:
        cam.loop = True

  if not args.debug and not args.preprocess:
    client = connectToMQTT(args.auth, args.cert, args.rootcert, args.broker)

  if args.window:
    for cam in cams:
      cv2.namedWindow(cam.mqttID, cv2.WINDOW_NORMAL)

  ntpServer = args.ntp
  ntpClient = ntplib.NTPClient()
  timeOffset = 0
  lastTimeSync = None

  averageStable = False
  done = False
  camSent = np.zeros(len(cams))

  if args.faketime:
    preprocess_begin = get_epoch_time()

  max_vcache = max(8, 2 * len(cams)) + 1
  if args.maxcache > 0:
    max_vcache = args.maxcache
  log.info("Using max video cache size of", max_vcache)

  nextCam = 0
  while not done:
    if not singleStep or doStep:
      doStep = False

      now = get_epoch_time()
      if not args.debug and not args.preprocess:
        timeOffset, lastTimeSync = adjust_time(now, ntpServer, ntpClient, lastTimeSync, timeOffset, ntplib.NTPException)
      now += timeOffset

      vdata = None
      if len(cameraChain.vcache) < max_vcache:
        cam, nextCam = _getNextCam(nextCam)
        # When preprocessing a file we go thru frames as fast as possible,
        # so we need to generate a frame timestamp.
        if args.preprocess:
          frame_num = cam.getNumberOfFrames()
          if not args.faketime:
            # opencv returns garbage numbers for MSEC get, calculate it myself
            now = (frame_num * 1000) / cam.fps
            now -= cam.startPosition
            now /= 1000
          else:
            now = get_epoch_time()

        vdata = getVideoFrame(virtual, cam, now, args.filter, args.disable_rotation, args.infrared)

        if not vdata and not cam.loop:
          done = True
          break

        if vdata:
          camSent[nextCam] += 1
          if args.preprocess:
            vdata.frameNum = frame_num

      cameraChain.detect(vdata)
      for sensor in sensors:
        sensor.detect(vdata)

      vdata = cameraChain.available(now)
      if vdata:
        vdata.cam.frameBuffer.addFrame(vdata)
        vdata.updateFrameAverage()
        if hasattr(vdata.cam, 'averageStable'):
          averageStable = vdata.cam.averageStable
        unannotated_frame = vdata.unannotatedFrame()
        annotated_frame = unannotated_frame.copy()
        vdata.annotateFPS(annotated_frame)
        vdata.annotateVirtual(annotated_frame)

        allObjects = cameraChain.getAllObjects(vdata)
        flatObjects = cameraChain.flatten(allObjects)

        if args.preprocess and args.faketime:
          ts = get_iso_time(vdata.begin - preprocess_begin)
        else:
          ts = get_iso_time(vdata.begin)
        ts_end = get_iso_time(vdata.end)

        fps = 1
        if vdata.cam.frameAvg is not None:
          fps = round(1 / vdata.cam.frameAvg, 1)
        if not args.debug and not args.preprocess:
          # FIXME - publish all objects at top level
          publishObjects(allObjects, ts, mac_addr, vdata.cam.mqttID, client, fps,
                          ts_end, vdata.end - vdata.begin, vdata.cam.intrinsics.asDict(), int(cam.fps))
        elif args.preprocess:
          detections = {'timestamp': ts,
                        'id': vdata.cam.mqttID,
                        'frame': int(vdata.frameNum),
                        'objects': flatObjects
                        }
          vdata.jsonFile.write(json.dumps(detections))
          vdata.jsonFile.write("\n")

        if args.stats and len(cameraChain.orderedModels):
          logStats(cameraChain.orderedModels, vdata, cams, cameraChain.vcache,
                   vdata.cam.latencyAvg, averageStable)

        if sendAllCamImages:
          for cam in cams:
            cam.sendImage = True
          sendAllCamImages = False

        if args.window or vdata.cam.sendImage or vdata.cam.sendImageForCalibration:
          # FIXME - annotate sensor detections too
          for sensor in sensors:
            if sensor.bounds:
              cv2.rectangle(annotated_frame, *sensor.bounds.cv, VideoFrame.COLOR_VIRTUAL, 4)
          vdata.annotateObjects(annotated_frame, flatObjects)

          if client is not None:
            if vdata.cam.sendImage:
              vdata.cam.sendImage = False
              topic = PubSub.formatTopic(PubSub.IMAGE_CAMERA,
                                         camera_id=vdata.cam.mqttID)
              annotated_frame = vdata.cam.intrinsics.pinholeUndistort(annotated_frame)
              publishImage(topic, annotated_frame, vdata, client, ts)
            if vdata.cam.sendImageForCalibration and unannotated_frame is not None:
              vdata.cam.sendImageForCalibration = False
              topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE,
                                         camera_id=vdata.cam.mqttID)
              if hasattr(vdata.cam, 'autocalibrate') and vdata.cam.autocalibrate:
                vdata.cam.autocalibrate = False
                publishImage(topic, unannotated_frame, vdata, client, ts, {'calibrate': True})
              else:
                publishImage(topic, unannotated_frame, vdata, client, ts)
          if args.window:
            cv2.imshow(vdata.cam.mqttID, annotated_frame)

        if args.frames and vdata.frameCount >= args.frames \
           and (not args.waitforstable or averageStable):
          done = True

    processSensors(sensors, now, client)

    if args.window:
      key = cv2.waitKey(1)
      if key == 27:
        done = True
        break
      elif key == 32:
        singleStep = not singleStep
      elif key == 13:
        singleStep = True
        doStep = True

  cameraChain.terminate()

  if args.stats:
    print( '', file=sys.stderr )

  if args.preprocess:
    for cam in cams:
      cam.jsonFile.close()

  if args.window:
    cv2.destroyAllWindows()

  if sensors:
    for sensor in sensors:
      sensor.terminate()
  return

def _getNextCam(nextCam):
  nextCam += 1
  nextCam %= len(cams)
  cam = cams[nextCam]
  return cam, nextCam

if __name__ == '__main__':
  exit(main() or 0)
