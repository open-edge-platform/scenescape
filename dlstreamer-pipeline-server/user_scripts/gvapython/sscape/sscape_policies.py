# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import struct
import base64

## Policies to post process data

def detectionPolicy(pobj, item, fw, fh):
  pobj.update({
    'category': item['detection']['label'],
    'confidence': item['detection']['confidence']
  })
  computeObjBoundingBoxParams(pobj, fw, fh, item['x'], item['y'], item['w'],item['h'],
                              item['detection']['bounding_box']['x_min'],
                              item['detection']['bounding_box']['y_min'],
                              item['detection']['bounding_box']['x_max'],
                              item['detection']['bounding_box']['y_max'])
  return

def detection3DPolicy(pobj, item, fw, fh):
  pobj.update({
    'category': item['detection']['label'],
    'confidence': item['detection']['confidence'],
  })

  if 'extra_params' in item:
    computeObjBoundingBoxParams3D(pobj, item)
  else:
    computeObjBoundingBoxParams(pobj, fw, fh, item['x'], item['y'], item['w'],item['h'],
                            item['detection']['bounding_box']['x_min'],
                            item['detection']['bounding_box']['y_min'],
                            item['detection']['bounding_box']['x_max'],
                            item['detection']['bounding_box']['y_max'])
  if not ('bounding_box_px' in pobj or 'rotation' in pobj):
    print(f"Warning: No bounding box or rotation data found in item {item}")
  return

def reidPolicy(pobj, item, fw, fh):
  detectionPolicy(pobj, item, fw, fh)
  reid_vector = item['tensors'][1]['data']
  v = struct.pack("256f",*reid_vector)
  pobj['reid'] = base64.b64encode(v).decode('utf-8')
  return

def classificationPolicy(pobj, item, fw, fh):
  detectionPolicy(pobj, item, fw, fh)
  # todo: add configurable parameters(set tensor name)
  pobj['category'] = item['classification_layer_name:efficientnet-b0/model/head/dense/BiasAdd:0']['label']
  return

def ocrPolicy(pobj, item, fw, fh):
  detection3DPolicy(pobj, item, fw, fh)
  pobj['text'] = ''
  for key, value in item.items():
    if key.startswith('classification_layer') and isinstance(value, dict) and 'label' in value:
      pobj['text'] = value['label']
      break
  return

## Utility functions

def computeObjBoundingBoxParams(pobj, fw, fh, x, y, w, h, xminnorm=None, yminnorm=None, xmaxnorm=None, ymaxnorm=None):
  # use normalized bounding box for calculating center of mass
  xmax, xmin = int(xmaxnorm * fw), int(xminnorm * fw)
  ymax, ymin = int(ymaxnorm * fh), int(yminnorm * fh)
  comw, comh = (xmax - xmin) / 3, (ymax - ymin) / 4

  pobj.update({
    'center_of_mass': {'x': int(xmin + comw), 'y': int(ymin + comh), 'width': comw, 'height': comh},
    'bounding_box_px': {'x': x, 'y': y, 'width': w, 'height': h}
  })
  return

def computeObjBoundingBoxParams3D(pobj, item):
  pobj.update({
    'translation': item['extra_params']['translation'],
    'rotation': item['extra_params']['rotation'],
    'size': item['extra_params']['dimension']
  })

  x_min, y_min, z_min = pobj['translation']
  x_size, y_size, z_size = pobj['size']
  x_max, y_max, z_max = x_min + x_size, y_min + y_size, z_min + z_size
  
  bbox_width = x_max - x_min
  bbox_height = y_max - y_min
  bbox_depth = z_max - z_min
  
  com_w, com_h, com_d = bbox_width / 3, bbox_height / 4, bbox_depth / 3
  
  com_x = int(x_min + com_w)
  com_y = int(y_min + com_h) 
  com_z = int(z_min + com_d)

  pobj['bounding_box_3D'] = {
    'x': x_min,
    'y': y_min,
    'z': z_min,
    'width': bbox_width,
    'height': bbox_height,
    'depth': bbox_depth
  }
  pobj['center_of_mass'] = {
    'x': com_x,
    'y': com_y, 
    'z': com_z,
    'width': com_w,
    'height': com_h,
    'depth': com_d
  }
  return