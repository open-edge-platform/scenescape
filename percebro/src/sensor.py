# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
from modelchain import ModelChain
from videoframe import VideoFrame

from scene_common.geometry import Rectangle
from scene_common import log

class PercebroSensor:
  def __init__(self, sensorID, bounds, attrib, chainSpec, chainParams):
    self.mqttID = sensorID
    self.bounds = bounds
    self.attrib = attrib
    self.modelChain = ModelChain(chainSpec, chainParams)
    self.inputReady = []
    self.outputReady = []
    self.vcache = []
    return

  def detect(self, vdata):
    sensorFrame = None
    if vdata:
      crop = vdata.unannotatedFrame()
      if self.bounds:
        crop = crop[int(self.bounds.y):int(self.bounds.y2), int(self.bounds.x):int(self.bounds.x2)]
      sensorFrame = VideoFrame(vdata.cam, crop, None, None)
      sensorFrame.sensor = self
      sensorFrame.begin = vdata.begin
    self.modelChain.detect(sensorFrame)
    return

  def terminate(self):
    self.modelChain.terminate()
    return

  def available(self, now):
    return self.modelChain.available(now)

  @staticmethod
  def initializeSensors(sensorIDs, sensorAttribs, chainSpecs, chainParams):
    """Takes the sensorIDs and chainSpecs as passed from the command
    line and returns a list of instantiated sensors ready to run
    inference.
    """

    if len(sensorIDs) != len(chainSpecs):
      log.error("Must have sensor ID and model chain specs for each sensor")
      exit(1)

    sensors = []
    attribs = [None] * len(sensorIDs)
    attribs = sensorAttribs + attribs
    attribs = attribs[:len(sensorIDs)]
    for sensorID, attrib, chainSpec in zip(sensorIDs, attribs, chainSpecs):
      bsplit = sensorID.split("=")
      sensorID = bsplit[0]
      bounds = None
      if len(bsplit) > 2:
        log.error("Unknown bounds format must be formatted as <sensor_id>=[x,y,width,height]")
        exit(1)
      elif len(bsplit) == 2:
        bounds = Rectangle(json.loads(bsplit[1]))
      sensors.append(PercebroSensor(sensorID, bounds, attrib, chainSpec, chainParams))

    return sensors
