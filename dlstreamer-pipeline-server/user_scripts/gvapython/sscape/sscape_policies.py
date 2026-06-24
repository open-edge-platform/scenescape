# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
import struct
import base64

# PointPillars KITTI label mapping: index -> class name
_KITTI_LABELS = {0: 'Pedestrian', 1: 'Cyclist', 2: 'Car'}

## Policies to post process data

def _isDetection(item):
  """Check if item contains valid detection metadata."""
  detection = item.get('detection')
  return isinstance(detection, dict) and 'confidence' in detection

def _extractKeypointsFromGvametaconvert(item):
  """Extract keypoints from gvametaconvert format (yolo11-pose and similar)."""
  raw_keypoints = item.get('keypoints')
  if isinstance(raw_keypoints, list):
    for kp_group in raw_keypoints:
      points = kp_group.get('points', [])
      if points:
        keypoints = [
          {
            'name': p['name'],
            'x': p['x'],
            'y': p['y'],
            'confidence': p.get('confidence'),
          }
          for p in points
          if 'name' in p and 'x' in p and 'y' in p
        ]
        skeleton = kp_group.get('skeleton', [])
        point_names = [p.get('name', '') for p in points]
        connections = []
        for pair in skeleton:
          if (isinstance(pair, (list, tuple)) and len(pair) == 2
              and pair[0] < len(point_names) and pair[1] < len(point_names)):
            connections.append(point_names[pair[0]])
            connections.append(point_names[pair[1]])
        return {
          'keypoints': keypoints,
          'keypoint_connections': connections,
        }
  return {}

def _extractKeypoints(item):
  # Format 1: keypoints in tensors (older model-proc based pipelines)
  for tensor in item.get('tensors', []):
    if tensor.get('format') == 'keypoints':
      data = tensor.get('data', [])
      names = tensor.get('point_names', [])
      keypoints = [
        {'name': names[i], 'x': data[i * 2], 'y': data[i * 2 + 1]}
        for i in range(len(names))
        if i * 2 + 1 < len(data)
      ]
      return {
        'keypoints': keypoints,
        'keypoint_connections': tensor.get('point_connections', [])
      }

  # Format 2: keypoints from gvametaconvert (yolo11-pose and similar)
  return _extractKeypointsFromGvametaconvert(item)

def detectionPolicy(pobj, item, fw, fh):
  if not _isDetection(item):
    return
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
  pobj.update(_extractKeypoints(item))
  return

def detection3DPolicy(pobj, item, fw, fh):
  if not _isDetection(item):
    return
  pobj.update({
    'category': item['detection']['label'],
    'confidence': item['detection']['confidence'],
  })

  computeObjBoundingBoxParams3D(pobj, item)

  if not ('bounding_box_px' in pobj or 'rotation' in pobj):
    print(f"Warning: No bounding box or rotation data found in item {item}")
  return

def reidPolicy(pobj, item, fw, fh):
  if not _isDetection(item):
    return
  classificationPolicy(pobj, item, fw, fh)
  for tensor in item.get('tensors', [{}]):
    name = tensor.get('name','')
    if name and ('reid' in name or 'embedding' in name):
      reid_vector = tensor.get('data', [])
      # Handle variable-length re-id vectors from different models
      if not reid_vector:
        continue
      vector_len = len(reid_vector)
      # Pack vector with its actual dimensions
      format_string = f"{vector_len}f"
      try:
        v = struct.pack(format_string, *reid_vector)
      except struct.error as e:
        import sys
        print(f"Failed to pack reid vector of length {vector_len}: {e}", file=sys.stderr)
        continue
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
  if not _isDetection(item):
    return
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
  if not _isDetection(item):
    return
  detection3DPolicy(pobj, item, fw, fh)
  pobj['text'] = ''
  for key, value in item.items():
    if key.startswith('classification_layer') and isinstance(value, dict) and 'label' in value:
      pobj['text'] = value['label']
      break
  return

def lidarDetectionPolicy(pobj, item, fw, fh):
  """Handle LiDAR 3D detections from g3dinference/PointPillars.

  gvametaconvert converts pointpillars_3d tensors to JSON items with:
    bbox_3d: {x, y, z, w, l, h, theta}  (center + dimensions + yaw)
    confidence: float
    label_id: int  (KITTI: 0=Pedestrian, 1=Cyclist, 2=Car)
    label: str     (may be empty if no model-proc label map is loaded)
  """
  bbox_3d = item.get('bbox_3d')
  if bbox_3d is None:
    return

  label_id = item.get('label_id', -1)
  label = item.get('label') or _KITTI_LABELS.get(label_id, str(label_id))
  confidence = item.get('confidence', 0.0)

  theta = bbox_3d.get('theta', 0.0)
  half = theta / 2.0
  rotation_quat = [0.0, 0.0, math.sin(half), math.cos(half)]

  pobj.update({
    'category': label,
    'confidence': confidence,
    'translation': [bbox_3d['x'], bbox_3d['y'], bbox_3d['z']],
    'size': [bbox_3d['l'], bbox_3d['w'], bbox_3d['h']],
    'rotation': rotation_quat,
  })
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
