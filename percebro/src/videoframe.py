# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import math
import uuid

import numpy as np
from scipy.spatial.transform import Rotation

from detector import IAData
from detector_pose import PoseEstimator
from scene_common.geometry import Point, Rectangle
from scene_common.timestamp import get_epoch_time
from scene_common.transform import normalize, rotationToTarget
from scene_common import log

class VideoFrame:
  AVG_FRAMES = 100
  COLOR_VIRTUAL = (255,0,0)
  objColors = ((0, 0, 255), (255, 128, 128), (207, 83, 294), (31, 156, 238))

  def __init__(self, cam, frame, virtual, id=None, depth=None, \
               filtering=None, disable_3d_rotation=False, is_gray=False):
    self.input = {}
    self.output = {}

    self.cam = cam
    self.virtual = None
    self.initFrame(frame, depth, is_gray)
    self.initVirtual(frame, virtual)
    self.annotated = {}

    self.id = id
    if not self.id:
      self.id = uuid.uuid4()
    self.filtering_operations = {
      # Bottom finds the object with the max value using 'y' and 'height' (bottom row in pixels)
      'bottom': {'axis': 'y', 'attribute': 'height', 'operator': max},
      # Top finds the object with the min value, using 'y' (top row in pixels)
      'top': {'axis': 'y', 'attribute': None, 'operator': min},
    }
    self.filtering = filtering if filtering in self.filtering_operations else None
    self.disable_3d_rotation = disable_3d_rotation
    return

  def initFrame(self, frame, depth=None, is_gray=False):
    if is_gray:
      self.brightness = np.average(frame)
      frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    else:
      gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
      self.brightness = np.average(gray)
    self.frames = [frame]
    self.depth = depth
    return

  def initVirtual(self, frame, virtual):
    if virtual is not None and len(virtual):
      self.virtual = []
      for bounds in virtual:
        vrect = Rectangle(origin=Point(bounds[0], bounds[1]),
                          size=(bounds[2], bounds[3]))
        frect = Rectangle(origin=Point(0, 0), size=tuple(frame.shape[1::-1]))
        irect = vrect.intersection(frect)
        if irect is None or irect.size.width == 0 \
           or irect.size.width < vrect.size.width or irect.size.height < vrect.size.height:
          continue
        crop = frame[int(vrect.y):int(vrect.y2), int(vrect.x):int(vrect.x2)]
        self.frames.append(crop)
        self.virtual.append(bounds)
    return

  def modelComplete(self, modelID):
    return modelID in self.output

  def allComplete(self, chain):
    for modelID in chain.orderedModels:
      isDone = self.modelComplete(modelID)
      if not isDone:
        return False
    return True

  def modelPending(self, modelID):
    return modelID in self.input

  def adjustRectToFrame(self, frame, rect):
    x1, y1 = rect.topLeft.asNumpyCartesian
    x2, y2 = rect.bottomRight.asNumpyCartesian
    img_w, img_h = frame.shape[1::-1]
    if x1 < 0 or y1 < 0 or x2 >= img_w or y2 >= img_h:
      if x1 < 0:
        x1 = 0
      if y1 < 0:
        y1 = 0
      if x2 >= img_w:
        x2 = img_w - 1
      if y2 >= img_h:
        y2 = img_h - 1
      rect = Rectangle(origin=Point(x1, y1),
                       opposite=Point(x2, y2))
    return rect

  def calculateBounds(self, frame, rect):
    return self.adjustRectToFrame(frame, rect)

  def calculateBounds3D(self, frame, obj):
    """ Takes a 3d bounding box and generates a 2d bounding box
        from the pixels for the transformed vertices. """
    world_vertices = Rectangle(origin=Point(obj['translation']), size=tuple(obj['size']))
    transformed_vertices = self.compute2DVertices(world_vertices, obj['rotation'])
    if transformed_vertices is None:
      return None
    xmin, ymin = np.min(transformed_vertices, axis=0)
    xmax, ymax = np.max(transformed_vertices, axis=0)
    return self.adjustRectToFrame(frame, Rectangle(origin=Point(xmin, ymin), opposite=Point(xmax, ymax)))

  def cropBounds3D(self, frame, bounds):
    """ Takes 3D meter based bounding boxes and crops 2d sub-image
        from the corresponding vertices. """
    frames = []
    for obj in bounds:
      rect = self.calculateBounds3D(frame, obj)
      if rect is None:
        continue
      (left, top), (right, bottom) = rect.cv
      crop = frame[top:bottom, left:right]
      frames.append(crop)
    return frames

  def cropBounds3DRotate(self, frame, bounds):
    frames = []
    self.perspective_transforms = []
    invalid_bounds = []
    for idx, obj in enumerate(bounds):
      world_vertices = Rectangle(origin=Point(obj['translation']), size=tuple(obj['size']))
      out_frame, pixel_perspective_transform = \
              self.cropBounds3DClosestFaceObjectRotate(frame, world_vertices, obj)
      if out_frame is not None:
        frames.append(out_frame)
        self.perspective_transforms.append([world_vertices, pixel_perspective_transform])
      else:
        invalid_bounds.append(idx)
    for idx in sorted(invalid_bounds, reverse=True):
      bounds.pop(idx)
    return frames

  def cropBounds3DClosestFaceObjectRotate(self, frame, world_vertices, obj):
    # Get the object's vertices
    vertices = self.getCuboidVertices(world_vertices, rotation=obj['rotation'])

    # Find the 4 closest vertices - this is the closest face.
    closest_vertices = np.array(
                         [vertices[i] for i in np.argsort([np.linalg.norm(v) for v in vertices])],
                         dtype=np.float32
                       )[0:4]

    intrinsics = self.cam.intrinsics.intrinsics

    src_img_pts = cv2.projectPoints(
                    closest_vertices,
                    np.zeros(3), #vertices are in camera csys
                    np.zeros(3), #vertices are in camera csys
                    intrinsics,
                    np.zeros(4)
                  )[0][:, 0, :].round().astype(int)

    obj_transform = np.vstack([
      np.hstack([
        Rotation.from_quat(np.array(obj['rotation'])).as_matrix(),
        np.array(obj['translation']).reshape((3,1))
        ]),
      np.array([0, 0, 0, 1])
      ])
    obj_inv_transform = np.linalg.inv(obj_transform)

    # Unrotated and translated to origin
    xformed_vertices = np.array(
                        [(obj_inv_transform @ np.hstack([v,[1]]))[:3] for v in closest_vertices],
                         dtype = np.float32
                       )

    face_horizontal = xformed_vertices[0] - xformed_vertices[1]
    face_vertical = xformed_vertices[3] - xformed_vertices[1]
    if np.allclose(face_horizontal, [0,0,0], atol=0.5) \
        or np.allclose(face_vertical, [0,0,0], atol=0.5):
      log.warn("Invalid bounds detected: horizontal vector", face_horizontal, \
               "vertical vector", face_vertical, \
               "source pixels", src_img_pts)
      return None, None

    face_v1 = np.cross(face_horizontal,
                       face_vertical)
    min_stddev = np.argmin(np.std(xformed_vertices, 0))
    norm_v1 = abs(normalize(face_v1))
    needs_invert = True
    if xformed_vertices[0][min_stddev] < 0:
      norm_v1 = -norm_v1
      needs_invert = False

    xformed_vertices -= np.mean(xformed_vertices, 0)
    inv_face_rotation_raw = rotationToTarget(norm_v1, np.array([0, 0, 1]))
    if inv_face_rotation_raw is None:
      log.warn("Invalid Quat detected, xformed_vertices", xformed_vertices, "src_img_pts", src_img_pts, "norm_v1", norm_v1)
      return None, None
    inv_face_rotation = inv_face_rotation_raw.as_matrix()
    inv_face_transform = np.vstack([
                           np.hstack([
                             inv_face_rotation, np.zeros(3).reshape((3,1))
                           ]),
                           np.array([0, 0, 0, 1])
                         ])

    # Get face vertices in camera system
    vertices_face_csys = np.array(
                           [(inv_face_transform @ np.hstack([v,[1]]))[:3] for v in xformed_vertices],
                           dtype = np.float32
                         )
    # Obtain virtual camera rotation/translation vectors
    v_cam_rotation = Rotation.from_euler('XYZ', [0, np.pi, np.pi/2]).as_matrix()
    v_cam_translation = np.array([[0, 0, 1]], dtype=np.float32).T
    rvec = cv2.Rodrigues(np.linalg.inv(v_cam_rotation))[0]
    tvec = - v_cam_translation

    # Compute source and destination image areas
    src_img_bb_area = np.ptp(src_img_pts, 0).prod()
    dst_img_bb_area = np.ptp(vertices_face_csys[:,:2],0).prod()

    # Get virtual camera focal length to maintain same pixel area as original face
    ratio = np.sqrt(src_img_bb_area / dst_img_bb_area) * np.ptp(vertices_face_csys[:,:2], 0)
    fxy = np.divide(ratio, np.ptp(vertices_face_csys[:,:2], 0))[0]

    v_camera_matrix = np.array([
                        [fxy, 0, ratio[1]/2],
                        [0, fxy, ratio[0]/2],
                        [0, 0, 1]
                      ])
    dst_img_pts = cv2.projectPoints(
                    vertices_face_csys,
                    rvec,
                    tvec,
                    v_camera_matrix,
                    np.zeros(4)
                  )[0][:, 0, :].round().astype(int)

    if needs_invert:
      dst_img_pts = dst_img_pts[::-1]

    # Use 2d point pairs to getPerspectiveTransform()
    src_img_pts = np.array(src_img_pts, dtype=np.float32)
    dst_img_pts = np.array(dst_img_pts, dtype=np.float32)
    perspective_transform = cv2.getPerspectiveTransform(src_img_pts, dst_img_pts)

    # warpPerspective() to get adjusted subframe
    adjusted_frame = cv2.warpPerspective(
                       frame,
                       perspective_transform,
                       ratio[::-1].astype(int)
                     )
    return adjusted_frame, perspective_transform

  def cropBounds(self, frame, bounds):
    frames = []
    for obj in bounds:
      rect = self.calculateBounds(frame, Rectangle(obj['bounding_box']))
      (left, top), (right, bottom) = rect.cv
      crop = frame[top:bottom, left:right]
      frames.append(crop)
    return frames

  def prepareData(self, source, dest):
    if source is None:
      idata = IAData(self.frames, id=self.id)
      idata.cameraID = self.cam.mqttID
      idata.virtual = self.virtual
    else:
      if self.output[source] is None or len(self.output[source].data) == 0:
        self.output[dest] = None
        return None
      frames = []
      if len(self.input[source].data) != len(self.output[source].data):
        log.error("IO MISMATCH!", source,
              len(self.input[source].data), len(self.output[source].data))
        exit(1)
      virtual_len = 0
      if hasattr(self.input[source], 'virtual') and self.input[source].virtual:
        virtual_len = len(self.input[source].virtual)
      for idx in range(len(self.input[source].data) - virtual_len):
        fdata = self.output[source].data[idx]

        if isinstance(fdata, list) and len(fdata) > 0 and isinstance(fdata[0], dict):
          if 'bounding_box' in fdata[0]:
            bounds = Rectangle(fdata[0]['parent_bounding_box']) if 'parent_bounding_box' in fdata[0] else Rectangle(fdata[0]['bounding_box'])
            frames.extend(self.cropBounds(self.input[source].data[idx], fdata))
          else:
            if self.disable_3d_rotation:
              frames.extend(self.cropBounds3D(self.input[source].data[idx], fdata))
            else:
              frames.extend(self.cropBounds3DRotate(self.input[source].data[idx], fdata))

        else:
          frames.extend(fdata)
      if not len(frames):
        self.output[dest] = None
        return None
      idata = IAData(frames, id=self.id)
    idata.cam = self.cam.intrinsics.intrinsics
    idata.max_distance_squared = self.cam.max_distance_squared
    idata.begin = get_epoch_time()
    self.input[dest] = idata
    return idata

  def filterResults(self, fdata):
    if self.filtering and len(fdata) > 1:
      params = self.filtering_operations.get(self.filtering)
      return self.filterResultsBoundingBox(fdata, **params)
    return fdata

  def filterResultsBoundingBox(self, fdata, axis, attribute, operator):
    # Function to compute position of objects, based on axis ('x', 'y')
    # and offset when needed ('height' to get to the bottom-most pixel of the detection).
    def detection_position(item):
      return item['bounding_box'][axis] + item['bounding_box'].get(attribute, 0)

    # Find the detection of interest. operator max for bottom-most, min for top-most.
    filtered_detection = operator(fdata, key=detection_position)

    return [filtered_detection]

  def mergeResults(self, toModel, fromModel):
    if self.output[fromModel] is None:
      return

    data_from = self.output[fromModel].data
    if not len(data_from):
      return

    data_to = self.output[toModel].data
    fidx = 0
    virtual_len = 0
    if hasattr(self.input[toModel], 'virtual') and self.input[toModel].virtual:
      virtual_len = len(self.input[toModel].virtual)
    stop_idx = 0
    for obj_to in data_to:
      if isinstance(obj_to,list):
        stop_idx += len(obj_to)
      else:
        stop_idx += 1
    stop_idx -= virtual_len
    for tidx, tdata in enumerate(data_to):
      if fidx >= stop_idx:
        break
      for tobj in tdata:
        fdata = self.filterResults(data_from[fidx])
        if isinstance(fdata, list) and len(fdata) > 0 and isinstance(fdata[0], dict) \
           and 'bounding_box' in fdata[0]:
          frame = self.input[toModel].data[tidx]
          if 'bounding_box' in tobj:
            bounds = Rectangle(tobj['bounding_box'])
            rect = self.calculateBounds(frame, bounds)
          else:
            rect = self.calculateBounds3D(frame, tobj)
            if rect is None:
              continue
          oimg = self.input[fromModel].data[fidx]
          shape = oimg.shape
          for oidx in range(len(fdata)):

            fdata[oidx]['bounding_box_px'] = fdata[oidx]['bounding_box']
            fdata[oidx].pop('bounding_box')
            oe_bounds = self.getBoundsFromParent(rect, fdata[oidx])

            agnostic = oe_bounds
            if not oe_bounds.is3D:
              agnostic = self.cam.intrinsics.infer3DCoordsFrom2DDetection(oe_bounds)
            fdata[oidx]['parent_bounding_box'] = agnostic.asDict
        tobj[fromModel] = fdata
        fidx += 1

    return

  def mergeDistance(self, fromModel):
    if self.output[fromModel] is None:
      return

    data_from = self.output[fromModel].data
    for fidx, fdata in enumerate(data_from):
      if isinstance(fdata, list) and len(fdata) > 0:
        for fobj in fdata:
          if isinstance(fobj, dict) and 'bounding_box' in fobj:
            bounds = Rectangle(fobj['center_of_mass'])
            np_depth = self.depth
            com_depth = np_depth[int(bounds.y1):int(bounds.y2),
                                 int(bounds.x1):int(bounds.x2)]
            distance = np.average(com_depth.flatten())
            # Convert mm to meters
            distance /= 1000
            fobj['distance'] = distance
    return

  def mergeAll(self, chain):
    for fromModel in chain.orderedModels:
      toModel = chain.orderedModels[fromModel].dependencies
      if toModel is not None:
        self.mergeResults(toModel, fromModel)
      elif self.depth is not None:
        self.mergeDistance(fromModel)
    return

  def addResults(self, modelID, ordered, output):
    baseModel = ordered[modelID].dependencies
    if baseModel is None and self.virtual is not None:
      self.virtualDetect(self.virtual, output)

    self.output[modelID] = output
    return

  def virtualDetect(self, virtual, odata):
    """Walk through all the detections from virtual cameras and merge
      them into main detection list."""
    detections = odata.data[0]
    for idx, bounds in enumerate(virtual):
      vrect = Rectangle(origin=Point(bounds[0], bounds[1]),
                        size=(bounds[2], bounds[3]))
      more = odata.data[idx+1]
      if not more:
        continue

      m2 = more.copy()
      for obj in m2:
        bbox = Rectangle(obj['bounding_box'])
        bbox = bbox.offset(vrect.origin)
        if abs(bbox.x - vrect.x) < 2 \
          or abs(bbox.y - vrect.y) < 2 \
          or abs(bbox.x2 - vrect.x2) < 2 \
          or abs(bbox.y2 - vrect.y2) < 2:
          more.remove(obj)
          continue

        d2 = detections.copy()
        for obj2 in d2:
          r = Rectangle(obj2['bounding_box'])
          ri = r.intersection(bbox)
          if ri:
            percent = (ri.width * ri.height) / (r.width * r.height) * 100
            if percent >= 75:
              detections.remove(obj2)
        obj['bounding_box'] = bbox.asDict
      detections.extend(more)
    return

  def annotateFPS(self, frame):
    frameAvg = getattr(self.cam, 'frameAvg', None)
    if frameAvg is None:
      return
    fpsStr = "FPS %.1f" % (1 / self.cam.frameAvg)
    scale = int((frame.shape[0] + 479) / 480)
    cv2.putText(frame, fpsStr, (0, 30 * scale), cv2.FONT_HERSHEY_SIMPLEX,
                1 * scale, (0,0,0), 5 * scale)
    cv2.putText(frame, fpsStr, (0, 30 * scale), cv2.FONT_HERSHEY_SIMPLEX,
                1 * scale, (255,255,255), 2 * scale)
    return

  def annotateHPE(self, frame, obj):
    if 'pose' not in obj:
      return
    pose = obj['pose']
    for i in range(len(PoseEstimator.bodyPartKP)):
      pt1 = pose[i]
      if not pt1 or len(pt1) != 2:
        continue
      pt1_int = (int(pt1[0]), int(pt1[1]))
      cv2.circle(frame, pt1_int, 5, PoseEstimator.colors[i], -1, cv2.LINE_AA)

    for pose_pair in PoseEstimator.POSE_PAIRS:
      pt1 = pose[pose_pair[0]]
      pt2 = pose[pose_pair[1]]
      if not pt1 or len(pt1) != 2 or not pt2 or len(pt2) != 2:
        continue
      pt1_int = (int(pt1[0]), int(pt1[1]))
      pt2_int = (int(pt2[0]), int(pt2[1]))
      cv2.line(frame, pt1_int, pt2_int, PoseEstimator.colors[pose_pair[1]], 3)
    return

  def annotatePlate(self, frame, bounds, text):
    # Get an estimate of the size of the text with scale 1
    scale = 1
    lsize = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1*scale, 5*scale)[0]

    # Then adjust the scale so the text is about twice the length of the plate
    # (this makes it more or less readable in the annotation without taking it too much space)
    scale = scale * 2 * bounds.width / lsize[0]
    lsize = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1*scale, int(5*scale))[0]

    start_x = int(bounds.x - lsize[0])
    bottom_y = int(bounds.y + 10 + lsize[1])
    end_x = int(bounds.x)
    top_y = int(bounds.y + 10)
    if not self.pointsInsideImage(frame, [[start_x, top_y], [end_x, bottom_y]]):
      log.warn("Invalid text annotation", start_x, top_y, end_x, bottom_y)
      return

    cv2.putText(frame, text, (start_x, bottom_y),
                cv2.FONT_HERSHEY_SIMPLEX, 1 * scale, (0,0,0), int(5 * scale))
    cv2.putText(frame, text, (start_x, bottom_y),
                cv2.FONT_HERSHEY_SIMPLEX, 1 * scale, (255,255,255), int(2 * scale))
    return

  def getBoundsFromParent(self, parent_rect, obj):
    e_bounds = Rectangle(obj['bounding_box_px'])
    return e_bounds.offset(parent_rect.origin)

  def pointsInsideImage(self, frame, img_pts):
    frame_height, frame_width = frame.shape[:2]
    for point in img_pts:
      pt_x = int(point[0])
      pt_y = int(point[1])
      if pt_x < 0 or pt_x > frame_width \
          or pt_y < 0 or pt_y > frame_height:
        return False
    return True

  def findParentTransform(self, parent_obj):
    # Video frame should keep the perspective transform used to remove the rotation on the
    # 3d-object bounding box (closest face). We need to find which one was used for this specific bounding box.
    parent_size = parent_obj['size']
    parent_rect = Rectangle(origin=Point(parent_obj['translation']),
                            size=(parent_size[0], parent_size[1], parent_size[2]))

    for bbox_as_rect, pixel_transform in self.perspective_transforms:
      if bbox_as_rect.origin == parent_rect.origin \
          and np.allclose( bbox_as_rect.size.asNumpy[:2], parent_rect.size.asNumpy[:2] ):
        return pixel_transform

    log.warn('Failed to find perspective')
    return None

  def annotateRotatedSubobject(self, frame, parent_obj, obj_bounds, cindex):

    perspective_transform = self.findParentTransform(parent_obj)
    if perspective_transform is None:
      return None

    bbox_img_pts = np.array([ [obj_bounds.x, obj_bounds.y],
                              [obj_bounds.x + obj_bounds.width, obj_bounds.y],
                              [obj_bounds.x, obj_bounds.y + obj_bounds.height],
                              [obj_bounds.x + obj_bounds.width, obj_bounds.y + obj_bounds.height]] )
    # Get the inverse to map the detection pixels back to parent_object space:
    inv_perspective_xform = np.linalg.inv(perspective_transform)

    # Keep opencv happy
    bbox_img_pts = np.array([bbox_img_pts], dtype=np.float32)

    # Compute the 4 pixels back to parent_obj space
    src_img_pts_mapped_back = cv2.perspectiveTransform(bbox_img_pts, inv_perspective_xform)

    img_pts = np.squeeze(src_img_pts_mapped_back)

    if not self.pointsInsideImage(frame, img_pts):
      log.warn("Invalid lpdet annotation", img_pts)
      return None

    for i in range(2):
      cv2.line(frame,
               (int(img_pts[0][0]), int(img_pts[0][1])),
               (int(img_pts[1+i][0]), int(img_pts[1+i][1])),
               VideoFrame.objColors[cindex], thickness=4)
    for i in range(2):
      cv2.line(frame,
               (int(img_pts[3][0]), int(img_pts[3][1])),
               (int(img_pts[1+i][0]), int(img_pts[1+i][1])),
               VideoFrame.objColors[cindex], thickness=4)

    x_coords = [pt[0] for pt in img_pts]
    y_coords = [pt[1] for pt in img_pts]
    origin = (min(x_coords),min(y_coords))
    opposite = (max(x_coords),max(y_coords))
    return Rectangle(origin=Point(origin), opposite=Point(opposite))

  def annotateSubobjects(self, frame, parent_obj):
    rect = self.calculateBounds3D(frame, parent_obj)

    for model in self.output:
      if model in parent_obj:
        # Start at color index 2 since these are sub-detections
        cindex = 2

        #try and mark all of the objects in the sub-detection
        for obj in parent_obj[model]:

          if self.disable_3d_rotation:
            # Get the pixel space bounds directly
            bounds = self.getBoundsFromParent(rect, obj)
            cv2.rectangle(frame, *bounds.cv, VideoFrame.objColors[cindex], 4)
          else:
            # Get the pixel space bounds from inverse transform
            obj_bbox_bounds = Rectangle(obj['bounding_box_px'])
            bounds = self.annotateRotatedSubobject(frame, parent_obj, obj_bbox_bounds, cindex)
            if bounds is None:
              continue

          # Then try and find text (license plate) data in the sub-detection
          for submodel in self.output:
            if submodel != model and submodel in obj:
              for subobj in obj[submodel]:
                if isinstance(subobj, str) and len(subobj) > 0:
                  self.annotatePlate(frame, bounds, subobj)

    return

  def annotateObjects(self, frame, objects):
    for obj in objects:
      otype = obj['category']

      if otype == "person":
        cindex = 0
        self.annotateHPE(frame, obj)
      elif otype == "vehicle" or otype == "bicycle":
        cindex = 1
      else:
        cindex = 2

      if 'translation' in obj and 'rotation' in obj:
        world_vertices = Rectangle(origin=Point(obj['translation']), size=tuple(obj['size']))
        self.annotate3DObject(frame, world_vertices, obj['rotation'])
        self.annotateSubobjects(frame, obj)
        continue

      bounds = Rectangle(obj['bounding_box_px'])
      cv2.rectangle(frame, *bounds.cv, VideoFrame.objColors[cindex], 4)
      if 'distance' in obj:
        scale = int((frame.shape[0] + 479) / 480)
        label = "%0.2f" % (obj['distance'])
        lsize = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1*scale, 5*scale)[0]
        cv2.putText(frame, label, (int(bounds.x + 10), int(bounds.y + 10) + lsize[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 1 * scale, (0,0,0), 5 * scale)
        cv2.putText(frame, label, (int(bounds.x + 10), int(bounds.y + 10) + lsize[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 1 * scale, (255,255,255), 2 * scale)
    return

  def compute2DVertices(self, bbox3D, rotation):
    """ Computes vertices from a 3d bounding box using camera intrinsics. """
    vertices = self.getCuboidVertices(bbox3D, rotation)
    intrinsics = self.cam.intrinsics.intrinsics
    transformed_vertices = []
    pts_img = intrinsics @ vertices.T

    if np.all(np.absolute(pts_img[2]) > 1e-7) :
      pts_img = pts_img[:2] / pts_img[2]
      return pts_img.T.astype(np.int32)
    log.error("Division by zero: bbox", bbox3D,
              "image coords", pts_img)
    return None

  def annotate3DObject(self, frame, bbox3D, rotation, color=(66, 186, 150), thickness=2):
    """ Takes 3D meter based bounding boxes and draws the box in the frame. """

    vertex_idxs = [0, 1, 2, 3, 7, 6, 5, 4, 7, 3, 0, 4, 5, 1, 2, 6]
    rvecs, tvecs = np.array([0, 0, 0], np.float64), np.array([0, 0, 0], np.float64)

    transformed_vertices = self.compute2DVertices(bbox3D, rotation)
    if transformed_vertices is None:
      return

    for idx in range(len(vertex_idxs)-1):
      cv2.line( frame,
                transformed_vertices[vertex_idxs[idx]],
                transformed_vertices[vertex_idxs[idx+1]],
                color=(255,0,0) if idx == 0 else color,
                thickness=2 )
    return

  def getCuboidVertices(self, bbox3D, rotation=None):
    """ Creates vertices for cuboid based on (x, y, z) and (width, height, depth)."""

    width = bbox3D.width
    height = bbox3D.height
    depth = bbox3D.depth
    x = bbox3D.x
    y = bbox3D.y
    z = bbox3D.z

    vertices = np.zeros([3, 8])

    # Setup X, Y and Z respectively
    vertices[0, [0, 1, 4, 5]], vertices[0, [2, 3, 6, 7]] = width / 2, -width / 2
    vertices[1, [0, 3, 4, 7]], vertices[1, [1, 2, 5, 6]] = height / 2, -height / 2
    vertices[2, [0, 1, 2, 3]], vertices[2, [4, 5, 6, 7]] = 0, depth

    # Rotate
    if rotation is not None:
      if len(rotation) == 3:
        vertices = self.rotationAsMatrix(rotation) @ vertices
      elif len(rotation) == 4:
        vertices = Rotation.from_quat(rotation).as_matrix() @ vertices

    # Translate
    vertices[0, :] += x
    vertices[1, :] += y
    vertices[2, :] += z

    vertices = np.transpose(vertices)
    return vertices

  def rotationAsMatrix(self, rotation):
    rotation_x = np.array([
      [1, 0, 0],
      [0, math.cos(rotation[0]), -math.sin(rotation[0])],
      [0, math.sin(rotation[0]), math.cos(rotation[0])]
    ])

    rotation_y = np.array([
      [math.cos(rotation[1]), 0, math.sin(rotation[1])],
      [0, 1, 0],
      [-math.sin(rotation[1]), 0, math.cos(rotation[1])]
    ])

    rotation_z = np.array([
      [math.cos(rotation[2]), -math.sin(rotation[2]), 0],
      [math.sin(rotation[2]), math.cos(rotation[2]), 0],
      [0, 0, 1]
    ])

    rotation_as_matrix = np.dot(rotation_z, np.dot(rotation_y, rotation_x))
    return rotation_as_matrix

  def annotateVirtual(self, frame):
    if self.virtual is None or not len(self.virtual):
      return

    for bounds in self.virtual:
      cv2.rectangle(frame, (bounds[0], bounds[1]),
                    (bounds[0]+bounds[2], bounds[1]+bounds[3]),
                    VideoFrame.COLOR_VIRTUAL, 2)
    return

  def updateFrameAverage(self):
    frameNow = get_epoch_time()
    oldFrameAvg = getattr(self.cam, 'frameAvg', None)
    if getattr(self.cam, 'latencyAvg', None) is None:
      self.cam.latencyAvg = 1.0

    if oldFrameAvg is not None:
      frameDel = frameNow - self.cam.frameLast
      self.cam.frameAvg *= VideoFrame.AVG_FRAMES
      self.cam.frameAvg += frameDel
      self.cam.frameAvg /= VideoFrame.AVG_FRAMES + 1
      self.cam.frameLast = frameNow

      percent = abs(oldFrameAvg - self.cam.frameAvg) / self.cam.frameAvg
      if percent < 0.005 * 100 / VideoFrame.AVG_FRAMES:
        self.cam.averageStable = True
      else:
        self.cam.averageStable = False

      if getattr(self, 'begin', None) is not None:
        oldLatencyAvg = self.cam.latencyAvg
        frameNow = get_epoch_time()
        latencyDel = frameNow - self.begin
        self.cam.latencyAvg *= VideoFrame.AVG_FRAMES
        self.cam.latencyAvg += latencyDel
        self.cam.latencyAvg /= VideoFrame.AVG_FRAMES + 1
        percent = (abs(oldLatencyAvg - self.cam.latencyAvg) / self.cam.latencyAvg) * 1000
        if self.cam.averageStable and percent >= 0.6 * 100 / VideoFrame.AVG_FRAMES:
          self.cam.averageStable = False

    elif not hasattr(self.cam, 'frameFirst'):
      self.cam.frameFirst = frameNow

    elif self.cam.frameCount >= VideoFrame.AVG_FRAMES / 10:
      frameDel = frameNow - self.cam.frameFirst
      self.cam.frameAvg = frameDel / self.cam.frameCount

    return

  def annotatedFrame(self, chain):
    allObjects = chain.getAllObjects(self)
    flatObjects = chain.flatten(allObjects)
    frame = self.unannotatedFrame().copy()
    self.annotateObjects(frame, flatObjects)
    self.annotateVirtual(frame)
    frame = self.cam.intrinsics.pinholeUndistort(frame)
    return frame

  def unannotatedFrame(self):
    return self.frames[0]
