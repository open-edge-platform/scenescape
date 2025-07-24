#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json

def loadJsonData(fileName):
  """Loads Tracker data from JSON file in established format."""
  with open(fileName, "r") as f:
    return [json.loads(l.strip()) for l in f.readlines()]

def loadData(fileName, convertJson=False):
  """! Load ground truth or predictions data
  @param   fileName      ground truth or predictions file.
  @param   convertJson   convert json outputted by tracker debugger to metrics tool format.
  @return  jsonData      input file data converted to json format.
  @return  m_objects     dict object that has objects location and gid, keyed by frame number.
  @return  info          dict object that has cam ID and objName.
  """
  jsonData = []
  m_objects = {}
  info = {'id': None}

  jsonData = loadJsonData(fileName)
  if convertJson:
    jsonData = convertEventJsonToMetricsJson(jsonData)

  for frame, item in enumerate(jsonData):
    objects = item['objects']
    parseObjects(m_objects, info, frame, objects)

  return jsonData, m_objects, info

def parseObjects(m_objects, info, frame, objects):
  """! Parse json data to populate object, info dicts
  @param   m_objects    dict object that has objects location and gid, keyed by frame number.
  @param   info         dict object that has cam ID and objName.
  @param   frame        frame id
  @param   objects      json objects
  """
  for category in objects:
    for object in objects[category]:
      if category not in m_objects:
        m_objects[category] = {}
      if info['id'] is None:
        info['id'] = category
      m_objects[category][frame] = object

  return

def convertEventJsonToMetricsJson(raw):
  """! Convert events json to metrics json format
  @param   raw             raw events json
  @return  convertedData   metrics friendly json format
  """
  convertedData = []
  for i in range(len(raw)):
    posData = {}
    timestamp = raw[i]['input']['timestamp']
    posData[timestamp] = {}
    posData[timestamp]['objects'] = []
    objects = raw[i]['output']['objects']
    for category in objects:
      objs = objects[category]
      for obj in objs:
        od = {
          'category': obj['category'],
          'id': obj['gid'],
          'translation': obj['location'][0]['point']
        }
        posData[timestamp]['objects'].append(od)
    for d in posData:
      line = {'timestamp': d, 'objects': posData[d]['objects']}
      convertedData.append(line)
  return convertedData
