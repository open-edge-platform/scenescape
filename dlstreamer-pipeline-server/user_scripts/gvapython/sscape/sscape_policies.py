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

def reidPolicy(pobj, item, fw, fh, _cache={}):
  # First apply classification policy (handles detection + classification metadata)
  classificationPolicy(pobj, item, fw, fh)

  # Then add REID embedding to metadata
  if 'reid_index' not in _cache:
    for idx, tensor in enumerate(item.get('tensors', [])):
      if tensor.get('layer_name') == 'reid_embedding':
        _cache['reid_index'] = idx
        break
    else:
      # No REID tensor found - cache None to avoid repeated searches
      _cache['reid_index'] = None

  reid_idx = _cache.get('reid_index')
  if reid_idx is None:
    return

  tensors = item.get('tensors', [])
  if reid_idx >= len(tensors):
    return

  reid_tensor = tensors[reid_idx]
  reid_vector = reid_tensor.get('data', [])
  if not reid_vector:
    return

  v = struct.pack(f"{len(reid_vector)}f", *reid_vector)

  # Ensure metadata exists
  if 'metadata' not in pobj:
    pobj['metadata'] = {}

  pobj['metadata']['reid'] = {
    'embedding': base64.b64encode(v).decode('utf-8')
  }

  # Add model info if available
  model_name = reid_tensor.get('model_name')
  if model_name:
    pobj['metadata']['reid']['model'] = model_name

  return


def classificationPolicy(pobj, item, fw, fh):
  """Extract detection and classification metadata from tensors."""
  detectionPolicy(pobj, item, fw, fh)

  metadata = {}

  for tensor in item.get('tensors', []):
    name = tensor.get('name', '')
    if not name or name == 'detection' or tensor.get('layer_name') == 'reid_embedding':
      continue

    # Build metadata entry
    meta_entry = {'label': tensor.get('label', '')}

    confidence = tensor.get('confidence')
    if confidence is not None:
      meta_entry['confidence'] = confidence

    model_name = tensor.get('model_name')
    if model_name:
      meta_entry['model'] = model_name
    metadata[name] = meta_entry

  if metadata:
    pobj['metadata'] = metadata

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
