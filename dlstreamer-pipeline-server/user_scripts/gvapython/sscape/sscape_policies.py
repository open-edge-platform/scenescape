# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import struct
import base64

## Policies to post process data

def detectionPolicy(pobj, item, fw, fh):
  detection = item['detection']
  # If label is missing use label_id to avoid KeyError exception.
  category = detection.get('label') or str(detection['label_id'])
  pobj.update({
    'category': category,
    'confidence': detection['confidence']
  })
  pobj.update({
    'bounding_box_px': {'x': item['x'], 'y': item['y'], 'width': item['w'], 'height': item['h']}
  })
  return

def detection3DPolicy(pobj, item, fw, fh):
  pobj.update({
    'category': item['detection']['label'],
    'confidence': item['detection']['confidence'],
  })

  computeObjBoundingBoxParams3D(pobj, item)

  if not ('bounding_box_px' in pobj or 'rotation' in pobj):
    print(f"Warning: No bounding box or rotation data found in item {item}")
  return

def reidPolicy(pobj, item, fw, fh):
  classificationPolicy(pobj, item, fw, fh)
  for tensor in item.get('tensors', [{}]):
    name = tensor.get('name','')
    if name and ('reid' in name or 'embedding' in name):
      reid_vector = tensor.get('data', [])
      v = struct.pack("256f",*reid_vector)
      # Move reid under metadata key
      if 'metadata' not in pobj:
        pobj['metadata'] = {}
      pobj['metadata']['reid'] = {
        'embedding_vector': base64.b64encode(v).decode('utf-8'),
        'model_name': tensor.get('model_name', '')
      }
      break
  return

def classificationPolicy(pobj, item, fw, fh):
  """Extract detection and classification metadata from tensors and update pobj"""
  detectionPolicy(pobj, item, fw, fh)

  # Initialize metadata dict if it doesn't exist
  if 'metadata' not in pobj:
    pobj['metadata'] = {}

  categories = {}
  for tensor in item.get('tensors', [{}]):
    name = tensor.get('name','')
    if name and name != 'detection' and ('reid' not in name and 'embedding' not in name):
      metadata_dict = {
        'label': tensor.get('label', ''),
        'model_name': tensor.get('model_name', '')
      }
      if 'confidence' in tensor:
        metadata_dict['confidence'] = tensor.get('confidence')
      categories[name] = metadata_dict

  # Move all semantic metadata under metadata key
  pobj['metadata'].update(categories)
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

def computeObjBoundingBoxParams3D(pobj, item):
  if 'extra_params' in item and all(k in item['extra_params'] for k in ['translation', 'rotation', 'dimension']):
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

    pobj['bounding_box_3D'] = {
      'x': x_min,
      'y': y_min,
      'z': z_min,
      'width': bbox_width,
      'height': bbox_height,
      'depth': bbox_depth
    }

  return
