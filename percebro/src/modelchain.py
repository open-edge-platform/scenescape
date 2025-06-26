# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import struct
import time
import base64

import numpy as np

from scene_common.geometry import Rectangle
from scene_common import log

from inferizer import Inferizer
from collections import OrderedDict

class ModelChain:
  class Stack:
    def __init__(self, spec):
      self.stack = []
      pos = 0
      while True:
        bidx = spec.find('[')
        eidx = spec.find(']')
        if bidx >= 0 and bidx < eidx:
          self.push(spec[:bidx])
          inner = self.__class__(spec[bidx+1:])
          self.stack.append(inner)
          eidx = inner.pos + 1 + bidx
          spec = spec[eidx:]
          pos += eidx
        elif eidx >= 0:
          self.push(spec[:eidx])
          pos += 1 + eidx
          break
        else:
          self.push(spec)
          pos += len(spec)
          break
      self.pos = pos
      return

    def push(self, spec):
      idx = spec.find('+')
      if idx >= 0 and idx < len(spec) - 1:
        self.push(spec[:idx+1])
        self.push(spec[idx+1:])
      else:
        idx = spec.find(',')
        if idx < 0:
          if len(spec):
            self.stack.append(spec)
        else:
          clist = spec.split(',')
          if len(clist[0]) == 0:
            clist = clist[1:]
          self.stack.extend(clist)
      return

    def groupDependencies(self, idx=0):
      while idx < len(self.stack):
        inner = self.stack[idx]
        idx += 1
        if isinstance(inner, ModelChain.Stack):
          inner.groupDependencies(0)
        elif isinstance(inner, str) and inner[-1] == '+':
          if isinstance(self.stack[idx], ModelChain.Stack) or idx+1 == len(self.stack):
            continue
          self.groupDependencies(idx)
          if self.stack[idx][-1] == '+':
            self.stack[idx] = self.stack[idx:idx+2]
            self.stack.pop(idx+1)
      return

    def setupModels(self, params, device="CPU"):
      models = {}
      idx = 0
      while idx < len(self.stack):
        p = self.stack[idx]
        if isinstance(p, str):
          isParent = False
          if p[-1] == '+':
            isParent = True
            p = p[:-1]
          chain = Inferizer(p, params, device)
          models[chain.modelID] = chain
          if isParent:
            children = self.stack[idx+1]
            if isinstance(children, str):
              children = Inferizer(children, params, device)
              childModels = {children.modelID: children}
            else:
              childModels = children.setupModels(params, chain.device)
            for cm in childModels:
              if childModels[cm].dependencies is None:
                childModels[cm].dependencies = chain.modelID
            models.update(childModels)
            idx += 1
        idx += 1
      return models

  def __init__(self, spec, params, device="CPU"):
    self.inputReady = []
    self.outputReady = []
    self.vcache = {}
    self.vorder = []
    self.knownTypes = []

    self.pending = 0
    self.orderedModels = {}
    if spec:
      parsed = ModelChain.Stack(spec)
      parsed.groupDependencies()
      models = parsed.setupModels(params, device)

      order = ModelChain.sortDependencies(models)
      self.orderedModels = OrderedDict([(x, models[x]) for x in order])
      log.info("Models:")
      for name in self.orderedModels:
        log.info("  ", name, self.orderedModels[name])
      log.info("Ordered:", order)
    return

  def terminate(self):
    while self.pending:
      for model in self.orderedModels:
        odata = self.orderedModels[model].engine.detect(None)
        if odata:
          self.pending -= 1
        else:
          time.sleep(0.01)
    return

  def detect(self, videoFrame):
    if videoFrame:
      self.vcache[videoFrame.id] = videoFrame
      self.vorder.append(videoFrame)
      self.prepareInput(videoFrame)
    self.detectObjects()
    self.addOutputResults()
    self.prepareNextInput()
    return

  def prepareInput(self, videoFrame):
    for modelID in self.orderedModels:
      model = self.orderedModels[modelID]
      if model.dependencies is None:
        idata = videoFrame.prepareData(None, modelID)
        if idata is not None:
          self.inputReady.append([modelID, idata])
    return

  def detectObjects(self):
    for input in self.inputReady:
      model = input[0]
      idata = input[1]
      odata = self.orderedModels[model].engine.detect(idata)
      self.pending += 1
      if odata is not None:
        self.outputReady.append([model, odata])
        self.pending -= 1
    self.inputReady = []
    return

  def addOutputResults(self):
    for model in self.orderedModels:
      while True:
        odata = self.orderedModels[model].engine.detect(None)
        if not odata:
          break
        self.pending -= 1
        self.outputReady.append([model, odata])

    for output in self.outputReady:
      model = output[0]
      odata = output[1]
      videoFrame = self.vcache[odata.id]
      videoFrame.addResults(model, self.orderedModels, odata)

    self.outputReady = []
    return

  def prepareNextInput(self):
    for v in self.vcache:
      videoFrame = self.vcache[v]
      for model in self.orderedModels:
        chain = self.orderedModels[model]
        dep = chain.dependencies
        if dep and videoFrame.modelComplete(dep) \
            and not videoFrame.modelComplete(model) \
            and not videoFrame.modelPending(model):
          idata = videoFrame.prepareData(dep, model)
          if idata is not None:
            self.inputReady.append([model, idata])

    return

  def available(self, now):
    if len(self.vorder) and self.vorder[0].allComplete(self):
      vdata = self.vorder.pop(0)
      vdata.end = now
      self.vcache.pop(vdata.id)
      vdata.mergeAll(self)
      return vdata
    return None

  def getAllObjects(self, videoFrame):
    """Annotates and returns all detected objects."""

    allObjects = {}

    for modelID in self.orderedModels:
      model = self.orderedModels[modelID]
      if model.dependencies is None:
        if modelID not in videoFrame.annotated:
          self.updateObjectsForModel(modelID, videoFrame)
          videoFrame.annotated[modelID] = True
        objects = self.getObjectsForModel(modelID, videoFrame)
        if objects:
          for oname, ogroup in objects.items():
            if oname not in allObjects:
              allObjects[oname] = []
            allObjects[oname].extend(ogroup)

    return allObjects

  def getObjectsForModel(self, modelID, videoFrame):
    objects = {}
    for otype in self.knownTypes:
      objects[otype] = []

    if modelID not in videoFrame.output or len(videoFrame.output[modelID].data) == 0:
      return
    data_len = len(videoFrame.output[modelID].data)
    if hasattr(videoFrame.input[modelID], 'virtual') and videoFrame.input[modelID].virtual:
      data_len -= len(videoFrame.input[modelID].virtual)
    for idx in range(data_len):
      data = videoFrame.output[modelID].data[idx]
      for obj in data:
        otype = obj['category']

        if otype not in objects:
          objects[otype] = []
        objects[otype].append(obj)
    return objects

  def updateObjectsForModel(self, modelID, videoFrame):
    if modelID not in videoFrame.output or len(videoFrame.output[modelID].data) == 0:
      return
    data_len = len(videoFrame.output[modelID].data)
    if hasattr(videoFrame.input[modelID], 'virtual') and videoFrame.input[modelID].virtual:
      data_len -= len(videoFrame.input[modelID].virtual)
    for idx in range(data_len):
      data = videoFrame.output[modelID].data[idx]
      invalid_objects = []
      for objidx, obj in enumerate(data):
        otype = obj['category']
        if otype == "vehicle" or otype == "bicycle":
          # When scene is too dark all vehicle detections are false positives
          obj['debug_brightness'] = videoFrame.brightness
          if obj['debug_brightness'] < 65:
            invalid_objects.append(objidx)
            continue
        bbox = None
        if 'bounding_box' in obj:
          bbox = obj['bounding_box']
        if 'parent_bounding_box' in obj:
          bbox = obj['parent_bounding_box']
        if bbox:
          bounds = Rectangle(bbox)
          agnostic = bounds
          if not bounds.is3D:
            agnostic = videoFrame.cam.intrinsics.infer3DCoordsFrom2DDetection(bounds)
            obj['bounding_box_px'] = bounds.asDict

          obj['bounding_box'] = agnostic.asDict
        if otype not in self.knownTypes:
          self.knownTypes.append(otype)
      for idx in sorted(invalid_objects, reverse=True):
        data.pop(idx)

    return

  @staticmethod
  def sortDependencies(models):
    ordered = []
    for m in models:
      chain = models[m]
      dep = chain.dependencies
      if dep is None:
        ordered.append(m)
      else:
        try:
          idx = ordered.index(dep)
        except ValueError:
          idx = -1
        if idx < 0:
          ordered.extend([m, dep])
        else:
          ordered.insert(idx, m)
    return ordered

  @staticmethod
  def flatten(objects):
    """Flattens nested list of objects, expand vectors to make them JSON compatible"""
    flatObjects = []

    for _, ogroup in objects.items():
      ModelChain.serializeVectors(ogroup, 'reid')
      flatObjects.extend(ogroup)

    for idx, obj in enumerate(flatObjects):
      obj['id'] = idx + 1

    return flatObjects

  @staticmethod
  def serializeVectors(objects, key):
    found = ModelChain.findResults(objects, key)
    for obj in found:
      if isinstance(obj[key], np.ndarray):
        vector = obj[key].flatten().tolist()
        vector = struct.pack("256f", *vector)
        vector = base64.b64encode(vector).decode('utf-8')
        obj[key] = vector
    return

  @staticmethod
  def findResults(olist, rname):
    found = []
    for obj in olist:
      if not isinstance(obj, dict):
        continue
      if rname in obj:
        found.append(obj)

      for key in obj:
        ll = obj[key]
        if isinstance(ll, list):
          o = ModelChain.findResults(ll, rname)
          if o is not None:
            found.extend(o)

    return found
