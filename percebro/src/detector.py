# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
from enum import Enum
import json
import os
from threading import Thread, Lock
import uuid

import cv2
import numpy as np
from openvino.runtime import Core
from ovmsclient import make_grpc_client

from scene_common.geometry import Point, Rectangle
from scene_common import log
from scene_common.timestamp import get_epoch_time

_colorSpaceCodes = {
    'BGR' : None,
    'RGB' : cv2.COLOR_BGR2RGB,
    'GRAY': cv2.COLOR_BGR2GRAY
}

_default_model_config = {
  # Fields are directory, categories, xml
  'pv0078': {
    'directory': "person-vehicle-bike-detection-crossroad-0078",
    'categories': ['background', 'person', 'vehicle', 'bicycle']
  },
  'pv1016': {
    'directory': "person-vehicle-bike-detection-crossroad-1016",
    'categories': ['background', 'vehicle', 'person', 'bicycle']
  },
  'pv0001': {
    'directory': "pedestrian-and-vehicle-detector-adas-0001",
    'categories': ['background', 'vehicle', 'person']
  },
  'v0002': {
    'directory': "vehicle-detection-adas-0002",
    'categories': ['background', 'vehicle']
  },
  'retail': {
    'directory': "person-detection-retail-0013",
    'categories': ['background', 'person']
  },
  'hpe': {
    'directory': "human-pose-estimation-0001"
  },
  'reid': {
    'directory': "person-reidentification-retail-0277"
  },
  'td0001': {
    'directory': "horizontal-text-detection-0001"
  },
  'trresnet': {
    'directory': "text-recognition-resnet-fc"
  },
  'pv2000': {
    'directory': "person-vehicle-bike-detection-2000",
    'categories': ["vehicle", "person", "bicycle", "unknown"]
  },
  'pv2001': {
    'directory': "person-vehicle-bike-detection-2001",
    'categories': ["vehicle", "person", "bicycle", "unknown"]
  },
  'pv2002': {
    'directory': "person-vehicle-bike-detection-2002",
    'categories': ["vehicle", "person", "bicycle", "unknown"]
  },
  'v0200': {
    'directory': "vehicle-detection-0200",
    'categories': ["background", "vehicle"]
  },
  'v0201': {
    'directory': "vehicle-detection-0201",
    'categories': ["background", "vehicle"]
  },
  'v0202': {
    'directory': "vehicle-detection-0202",
    'categories': ["background", "vehicle"]
  },
  'retail3d': {
    'directory': "person-detection-retail-0013",
    'categories': ['background', 'person']
  },
}

class Distributed(Enum):
  NONE = "NONE"
  OVMS = "OVMS"

# Common paths/names for openvino models
COMMON_DIRS = ["model", "FP32", "FP16", ".", "1"]
COMMON_NAMES = ["model", "openvino"]

class NumpyEncoder(json.JSONEncoder):
  def default(self, obj):
    if isinstance(obj, np.ndarray):
      return obj.tolist()
    return json.JSONEncoder.default(self, obj)

class IAData:
  def __init__(self, data, id=None, save=None):
    self.data = data
    self.id = id
    self.save = save
    if not self.id:
      self.id = uuid.uuid4()
    return


class Detector(Thread):
  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    super().__init__()
    self.frameProcessed = 0
    self.distributed = distributed
    self.asynchronous = asynchronous
    self.num_req = 32
    self.done = False
    self.tasksCur = []
    self.tasksDone = []
    self.tasksIncomplete = {}
    self.tasksRemainCount = {}
    self.tasksComplete = []
    self.taskLock = Lock()
    self.immediate = 0
    self.saveDict = False
    #Support different output ordering
    self.defaultOutputOrder = True
    self.idxCategory = 1
    self.idxConfidence = 2
    self.idxOriginX = 3
    self.idxOriginY = 4
    self.idxOppositeX = 5
    self.idxOppositeY = 6
    self.colorSpaceCode = None
    self.keep_aspect = False
    #Indicates if the output of the model is normalized [0 to 1.0]
    self.normalized_output = True
    self.default_normalized_output = True
    #Indicates if the input frame needs to be normalized into [0 to 1.0]
    self.normalize_input = False
    #Used by models with dynamic height/width
    self.input_shape = None
    #Used to configure number of cores for inference
    self.config = None
    #Used to filter-out unwanted categories
    self.blacklist = []
    self.threshold = 0.5
    return

  @classmethod
  def addModels(cls, new_models):
    _default_model_config.update(new_models)
    return

  def run(self):
    # Loop instead of calling self.task.get() to prevent GIL
    while True:
      status = self.task.status
      if status == "SUCCESS":
        break
    res = self.task.result

    self.results = self.deserializeOutput(res[2])
    self.done = True
    self.end = get_epoch_time()
    return

  def callback(self, userdata):
    self.taskLock.acquire()
    #print("CALLBACK", userdata)
    self.tasksDone.append(userdata)
    self.taskLock.release()
    return

  def startInfer(self, data, iid, debugFlag=False):

    if self.distributed == Distributed.NONE:
      self.taskLock.acquire()
      busy = set([x.task for x in self.tasksCur])
      avail = set(range(len(self.async_queue)))
      avail -= busy
      self.taskLock.release()
      if len(avail) == 0:
        return False
      idx = list(avail)[0]
      #print("START", iid, idx)
      data.task = idx
      self.taskLock.acquire()
      self.tasksCur.append(data)
      self.taskLock.release()
      request = self.async_queue[idx]
      if data.data is not None:
        request.set_callback(self.callback, userdata=idx)
        request.start_async(inputs={self.input_blob : data.data})
        if not self.asynchronous:
          request.wait()
      else:
        request.invalid = True
        self.taskLock.acquire()
        self.tasksDone.append(idx)
        self.taskLock.release()

    elif self.distributed == Distributed.OVMS:
      image = data.data.astype(np.float32)
      output = self.client.predict({self.input_blob: image}, self.ovms_modelname)
      result = IAData(output, data.id, data.save)

      self.taskLock.acquire()
      self.tasksComplete.append([result])
      self.taskLock.release()

    return True

  def checkDone(self):
    res_det = None

    # If first task isn't done yet give it another chance unless there
    # are 2 or more tasks already done
    num_done = len(self.tasksDone)
    if len(self.tasksDone) > len(self.tasksCur):
      log.warn("WHAAAAAAAAAAAAAAAAT?", len(self.tasksDone), len(self.tasksCur))
    haveData = num_done and (self.tasksCur[0].task in self.tasksDone) # or num_done > 1)
    if haveData:
      # Can't just take first element from tasksDone, they may not be
      # in the same order as tasksCur
      for idx, task in enumerate(self.tasksCur):
        if task.task in self.tasksDone:
          if self.distributed == Distributed.NONE:
            req = self.async_queue[task.task]
            req.wait()
            if hasattr(req, 'invalid') and req.invalid:
              res_det = None
              req.invalid = False
            else:
              if not self.saveDict:
                res_det = req.results[self.output_blob].copy()
              else:
                res_det = { out.get_any_name(): req.get_output_tensor(idx).data.copy() for idx, out in enumerate(req.model_outputs) }
              #print("BLOB", self.model, task.task, task.id, len(res_det[0][0]))
          else:
            res_det = task.task.results
            task.task.join()

          result = IAData(res_det, task.id, task.save)
          if task.id in self.tasksIncomplete:
            self.taskLock.acquire()
            data = self.tasksIncomplete.pop(task.id)
            self.taskLock.release()
            data.append(result)
            result = data
          else:
            result = [result]

          self.taskLock.acquire()
          self.tasksDone.remove(task.task)
          self.tasksCur.pop(idx)
          remainCount = self.tasksRemainCount.pop(task.id)
          remainCount -= 1
          if remainCount == 0 and task.id not in [x.id for x in self.tasksCur]:
            # FIXME - Need to join on distributed tasks at some point.
            if idx != 0:
              log.info("IGNORING UNFINISHED TASKS")
            self.tasksCur[:idx] = []
          else:
            self.tasksRemainCount[task.id] = remainCount
            self.tasksIncomplete[task.id] = result
            result = None
          self.tasksComplete.append(result)
          self.taskLock.release()
          return True
    return False

  def getDone(self):
    res = None
    self.taskLock.acquire()
    while len(self.tasksComplete):
      res = self.tasksComplete.pop(0)
      if res is not None and res[0] is not None:
        break
    self.taskLock.release()
    return res

  def detect(self, input, debugFlag=False):
    if input is None:
      self.checkDone()
    else:
      processed = self.preprocess(input)
      #print("INPUT", self.model, input.id, len(input.data))
      if processed is None:
        return None
      if len(processed) == 0:
        return IAData([], input.id)

      self.taskLock.acquire()
      self.tasksRemainCount[input.id] = len(processed)
      self.taskLock.release()

      for d in processed:
        while True:
          started = self.startInfer(d, input.id, debugFlag=debugFlag)
          while True:
            if not self.checkDone():
              break
          if started:
            break

    res = self.getDone()
    if res is None or res[0] is None:
      return None
    post_res = []
    for r in res:
      pr = self.postprocess(r)
      post_res.append(pr)
    #print("RESULTS", self.model, res[0].id, len(res), len(post_res[0]))
    return IAData(post_res, id=res[0].id)

  @property
  def waitingIDs(self):
    self.taskLock.acquire()
    tid = set([x.id for x in self.tasksCur])
    tid |= set([k[2] for k in self.tasksComplete])
    self.taskLock.release()
    return tid

  @property
  def waitingCount(self):
    self.taskLock.acquire()
    count = len(self.tasksCur) + len(self.tasksComplete)
    self.taskLock.release()
    return count

  @property
  def waiting(self):
    return self.waitingCount > 0

  def configureDetector(self):
    self.modelPreconfigure()
    if self.distributed == Distributed.OVMS:
      self.modelConfigureOVMS()
      return
    self.modelLoad()
    self.modelCompile()
    self.getModelShape()
    return

  def modelConfigureOVMS(self):
    self.client = make_grpc_client(self.ovmshost)
    log.info(self.ovms_modelname)
    self.model_metadata = self.client.get_model_metadata(model_name=self.ovms_modelname)
    self.input_blob = next(iter(self.model_metadata["inputs"]))
    self.n, self.c, self.h, self.w = self.model_metadata["inputs"][self.input_blob]['shape']
    return

  def modelPreconfigure(self):
    self.core = Core()
    if not self.asynchronous:
      self.num_req = 1
    else:
      self.num_req = self.ov_cores
    if self.device == "CPU":
      self.config = {'NUM_STREAMS': self.ov_cores,
                     'INFERENCE_NUM_THREADS': str(self.ov_cores),
                     'PERFORMANCE_HINT': 'THROUGHPUT'}
      self.core.set_property(device_name=self.device, properties=self.config)

      if self.plugin:
        self.ie.add_extension(self.plugin, self.device)
    return

  def modelLoad(self):
    self.model = self.core.read_model(model=self.model_path,
                            weights=os.path.splitext(self.model_path)[0] + ".bin")

    if self.input_shape is not None:
      self.model.reshape({0: self.input_shape})
    self.inputs_info = self.model.inputs
    self.input_blob = [x for x in next(iter(self.inputs_info)).names][0]
    self.output_blob = [x for x in next(iter(self.model.outputs)).names][0]

    # If there is a separate label output,
    # Save as dict and use same post-process function as ovms.
    found_labels_output = False
    for out in self.model.outputs:
      if out.names == {'labels'}:
        found_labels_output = True
        break

    if len(self.model.outputs) > 1 and found_labels_output:
      log.info("Labels extra output detected")
      self.saveDict = True

    output_blob_shape = self.model.outputs[0].get_partial_shape()
    output_blob_len = len(output_blob_shape)
    # The output order params set in __init__ (self.idxYYY variables)
    #  are the default for omz-style models (with length 7).
    # When the model's result has 5 entries, assume the Geti-optimized format,
    #  unless the user has specifically requested a different output_order
    #  in the model-config file.
    if output_blob_shape[output_blob_len - 1] == 5 \
          and self.defaultOutputOrder:
      self.idxCategory = -1
      self.idxConfidence = 4
      self.idxOriginX = 0
      self.idxOriginY = 1
      self.idxOppositeX = 2
      self.idxOppositeY = 3

    model_shape = list(self.model.inputs[0].get_partial_shape())
    if model_shape[0] != 1:
      model_shape[0] = 1
      self.model.reshape({ self.input_blob: model_shape })
    return

  def modelCompile(self):
    if self.asynchronous:
      self.exec_network = self.core.compile_model(model=self.model, config=self.config,
                                                  device_name=self.device)
    else:
      self.exec_network = self.core.compile_model(model=self.model, device_name=self.device)

    self.async_queue = []
    for i in range(self.num_req):
      self.async_queue.append(self.exec_network.create_infer_request())
    return

  def getModelShape(self):
    self.n, self.c, self.h, self.w = next(iter(self.inputs_info)).shape
    return

  def findXML(self, directory, xml, device,
              default_path="/opt/intel/openvino/deployment_tools/intel_models/intel/"):
    mpath = directory
    xpath = None
    if not os.path.isabs(mpath):
      if os.path.exists(mpath):
        mpath = os.path.abspath(mpath)
      else:
        mpath = os.path.join(default_path, mpath)

    if xml is None:
      for devdir in COMMON_DIRS:
        xdir = os.path.join(mpath, devdir)
        if not os.path.exists(xdir):
          continue

        for fname in [directory] + COMMON_NAMES:
          xml = os.path.basename(fname) + ".xml"
          xpath = os.path.join(xdir, xml)
          if os.path.exists(xpath):
            return xpath

    else:
      xpath = os.path.join(mpath, xml)

    return xpath

  def setParameters(self, model, device, plugin, threshold, ov_cores):
    if self.distributed == Distributed.OVMS:
      self.ovmshost = model['ovmshost']
      self.ovms_modelname = model['external_id']

    mdict = None
    if not model:
      model = list(_default_model_config.keys())[0]
      mdict = _default_model_config[model]
    else:
      # Just a model name
      if isinstance(model,str):
        # Unknown model
        if model not in _default_model_config:
          return
        mdict = _default_model_config[model]
      elif isinstance(model, dict):
        if 'model' in model and model['model'] in _default_model_config:
          mdict = _default_model_config[model['model']]
          mdict.update(model)
        else:
          mdict = model
      else:
        # Unknown config
        return

    #Set the generic threshold now, might get updated by the config parsed in loadConfig
    self.threshold = threshold

    #Not all detectors are loaded thru OpenVINO, end here for those which aren't
    if not 'directory' in mdict:
      self.loadConfig(mdict)
      self.configureDetector()
      return

    mdir = mdict['directory']
    print("Loading model", mdir, "for device", device)
    xpath = self.findXML(mdir, mdict.get('xml', None), device)

    self.device = device
    self.model = model
    self.model_path = xpath
    self.plugin = plugin
    self.ov_cores = ov_cores
    self.loadConfig(mdict)
    self.loadLabelSchema()
    self.configureDetector()
    return

  def _loadCategories(self, label_params):
    categories = []
    if "label_groups" in label_params:
      for group in label_params["label_groups"]:
        if group["relation_type"] != "EMPTY_LABEL":
          for label_id in group["label_ids"]:
            label_info = label_params["all_labels"][label_id]
            categories.append(label_info['name'].lower())
    return categories

  def loadLabelSchema(self):
    labelSchemaPath = os.path.dirname(self.model_path)
    labelSchemaFilePath = labelSchemaPath + '/label_schema.json'
    if os.path.exists(labelSchemaFilePath):
      log.info("Label schema found, attempting to load categories")
      with open(labelSchemaFilePath) as fd:
        schema_data = json.load(fd)
        if 'label_groups' in schema_data:
          self.categories = self._loadCategories(schema_data)
          log.info("Categories detected as", self.categories)
    return

  def loadConfig(self, mdict):
    if mdict:
      self.input_shape = mdict.get('input_shape', None)
      if 'categories' in mdict:
        self.categories = mdict['categories']
      self.keep_aspect = mdict.get('keep_aspect', False)
      if 'output_order' in mdict:
        self.idxCategory = mdict['output_order']['category']
        self.idxConfidence = mdict['output_order']['confidence']
        self.idxOriginX = mdict['output_order']['originX']
        self.idxOriginY = mdict['output_order']['originY']
        self.idxOppositeX = mdict['output_order']['oppositeX']
        self.idxOppositeY = mdict['output_order']['oppositeY']
        self.defaultOutputOrder = False
      if 'colorspace' in mdict:
        self.setColorSpace(mdict)
      if 'normalized_output' in mdict:
        self.normalized_output = mdict['normalized_output']
        self.default_normalized_output = False
      if 'normalize_input' in mdict:
        self.normalize_input = mdict['normalize_input']
      if 'blacklist' in mdict:
        self.blacklist = mdict['blacklist']
      if 'threshold' in mdict:
        self.threshold = mdict['threshold']
    return

  def setColorSpace(self, mdict):
    if mdict['colorspace'] in _colorSpaceCodes:
      self.colorSpaceCode = _colorSpaceCodes[mdict['colorspace']]
    else:
      log.warn("Unknown colorspace {}".format(mdict['colorspace']))
    return

  def preprocessColorspace(self, frame):
    if self.colorSpaceCode is not None:
      return cv2.cvtColor(frame, self.colorSpaceCode)
    return frame

  def preprocess(self, input):
    resized = []
    for frame in input.data:
      if np.prod(frame.shape):
        in_frame = self.resize(frame)

        in_frame = self.preprocessColorspace(in_frame)
        if len(frame.shape) > 2:
          in_frame = in_frame.transpose((2, 0, 1))
        in_frame = in_frame.reshape((self.n, self.c, self.h, self.w))
        if self.normalize_input:
          in_frame = np.ascontiguousarray(in_frame).astype(np.float32)
          in_frame /= 255.0
        resized.append(IAData(in_frame, input.id, frame.shape[1::-1]))
    return resized

  def resize(self, frame):
    """Resizes frame to maintain the model input width and height. If
    self.keep_aspect is true, it resizes frame without distorting the
    original image (keeping the original aspect ratio) and adds padding
    to maintain the model input width and height."""

    if not self.keep_aspect:
      return cv2.resize(frame, (self.w, self.h))

    width, height = frame.shape[1::-1]
    height_ratio, width_ratio = self.h / height, self.w / width
    resized_width, resized_height = width, height

    # Conditions below are to make sure that both height and width of the
    # resized image is lower than model height and width.
    if height_ratio <= width_ratio:
      resized_width, resized_height = int(width * height_ratio), self.h
    else:
      resized_width, resized_height = self.w, int(height * width_ratio)

    top, left = 0, 0
    bottom, right  = self.h - resized_height, self.w - resized_width
    resized_frame = cv2.resize(frame, (resized_width, resized_height))
    frame_with_padding = cv2.copyMakeBorder(
      resized_frame, top, bottom, left, right, cv2.BORDER_CONSTANT, value=[0, 0, 0]
    )
    return frame_with_padding

  # Helper function to 'squeeze' the output buffer from OpenVINO.
  # Some models have a 1x1x200x7 static shape, some others have a 1x200x5 static shape,
  #  and others have a Nx5 dynamic shape (where N is the number of results).
  # We desire the buffer to have a 2 dimensional array (say 200x7, Nx7, Nx5),
  #  in order to loop thru the model results (detections).
  def squeeze_buffer(self, buf, min_dims):
    if isinstance(buf, np.ndarray):
      if len(buf.shape) > min_dims:
        buf = np.squeeze(buf)
      # Cover the corner case where a 1x1x1xM gets squeezed into an M-length list
      if len(buf.shape) == 1 and min_dims > 1:
        buf = np.reshape(buf, (1,-1))
    else:
      buf = buf[0][0]
    return buf

  def _autoDetectUnnormalized(self, x_min, y_min):
    # If user didnt explicitly request normalized_output,
    # and we find something that doesnt look normalized,
    # move to unnormalized to get proper bounding-boxes.
    if self.default_normalized_output and \
        self.normalized_output and \
        (x_min > 1.0 or y_min > 1.0):
      log.info("Auto switching to unnormalized output")
      self.normalized_output = False
    return

  def postprocessAsDict(self, result):
    objects = []
    detections = result.data['boxes']
    labels = result.data['labels']

    detections = self.squeeze_buffer(detections, 2)
    if len(labels.shape) > 1 and labels.shape[1] == 1:
      labels = np.array([self.squeeze_buffer(labels, 1)])
    else:
      labels = self.squeeze_buffer(labels, 1)

    for detection, label in zip(detections, labels):
      x_min, y_min, x_max, y_max, confidence = detection

      if confidence < self.threshold:
        break

      self._autoDetectUnnormalized(x_min, y_min)

      bounding_box = self.recalculateBoundingBox([x_min, y_min, x_max, y_max],
                                                 result.save[0],
                                                 result.save[1])
      object = {
        'id': len(objects) + 1,
        'category': self.categories[label],
        'confidence': float(confidence),
        'bounding_box': bounding_box.asDict
      }
      objects.append(object)

    return objects

  def postprocess(self, result):
    objects = []

    if self.saveDict or \
        (isinstance(result.data, dict) and self.distributed == Distributed.OVMS):
      return self.postprocessAsDict(result)
    else:
      detections = self.squeeze_buffer(result.data, 2)

    if len(detections) == 0:
      return objects
    #print("POSTPROCESS", self.model, result.id, len(detections), self.threshold)
    conf = [x[self.idxConfidence] for x in detections]
    #print("CONFIDENCE", conf)

    # If the first result is empty, then skip processing the result list.
    if detections[0][self.idxConfidence] < self.threshold:
      return objects

    for obj in detections:
      # detections seem to be sorted by threshold descending, bail out
      # when threshold is too low or detection width or height is zero
      if obj[self.idxConfidence] < self.threshold \
          or obj[self.idxOriginX] == obj[self.idxOppositeX] \
          or obj[self.idxOriginY] == obj[self.idxOppositeY]:
        break

      self._autoDetectUnnormalized(obj[self.idxOriginX], obj[self.idxOriginY])

      # Allow the model to request fixed detection type.
      if self.idxCategory >= 0:
        cidx = int(obj[self.idxCategory])
      else:
        cidx = 0
      if cidx < len(self.categories):
        category = self.categories[cidx]
      else:
        category = "unknown:%i" % (cidx)

      # Skip blacklisted categories
      if category in self.blacklist:
        continue
      bounds = self.recalculateBoundingBox(obj[self.idxOriginX:self.idxOppositeY+1],
                                           result.save[0],
                                           result.save[1])
      comw = bounds.width / 3
      comh = bounds.height / 4
      center_of_mass = Rectangle(origin=Point(bounds.x + comw, bounds.y + comh),
                                 size=(comw, comh))
      odict = {'id': len(objects) + 1,
               'category': category,
               'confidence': float(obj[self.idxConfidence]),
               'bounding_box': bounds.asDict,
               'center_of_mass': center_of_mass.asDict}
      objects.append(odict)
    return objects

  def recalculateBoundingBox(self, bbox, image_width, image_height):
    x_min, y_min, x_max, y_max = bbox

    if not self.normalized_output:
      x_min, y_min, x_max, y_max = x_min / self.w, y_min / self.h, x_max / self.w, y_max / self.h

    x_scale, y_scale = image_width, image_height
    if self.keep_aspect:

      height_ratio = self.h / image_height
      width_ratio = self.w / image_width
      if height_ratio <= width_ratio:
        x_scale = self.w / height_ratio
      else:
        y_scale = self.h / width_ratio

    bounding_box = Rectangle(origin=Point(x_min * x_scale, y_min * y_scale),
                             opposite=Point(x_max * x_scale, y_max * y_scale))
    return bounding_box

  def serializeInput(self, data):
    enc_data = data.reshape((self.h, self.w, -1))
    enc_data = cv2.imencode(".jpg", enc_data)[1]
    enc_data = base64.b64encode(enc_data).decode("ASCII")
    return enc_data

  def deserializeInput(self, data):
    dec_data = np.fromstring(base64.b64decode(data), np.uint8)
    dec_data = cv2.imdecode(dec_data, 1)
    dec_data = dec_data.reshape((self.n, self.c, self.h, self.w))
    return dec_data

  def serializeOutput(self, data):
    enc_data = json.dumps(data, cls=NumpyEncoder)
    return enc_data

  def deserializeOutput(self, data):
    dec_data = json.loads(data)
    return dec_data

class REIDDetector(Detector):

  def postprocess(self, result):
    if isinstance(result.data, np.ndarray):
      return result.data
    else:
      return result.data.buffer

  def serializeInput(self, data):
    enc_data = []
    for d in data:
      d = d.transpose(1, 2, 0)
      e = cv2.imencode(".jpg", d)[1]
      e = base64.b64encode(e).decode("ASCII")
      enc_data.append(e)
    return enc_data

  def deserializeInput(self, data):
    dec_data = []
    for e in data:
      d = np.fromstring(base64.b64decode(e), np.uint8)
      d = cv2.imdecode(d, 1)
      d = d.transpose(2, 0, 1)
      dec_data.append(d)
    return dec_data

  def serializeOutput(self, data):
    enc_data = json.dumps(data, cls=NumpyEncoder)
    return enc_data

  def deserializeOutput(self, data):
    dec_data = json.loads(data)
    return np.array(dec_data)

def add_preload_options(parser):
  parser.add_argument("-d", "--device", default="CPU", help="Device to use")
  parser.add_argument("-m", "--model", help="Model to use")
