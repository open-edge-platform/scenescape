# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from queue import Queue
from threading import Thread

from controller.moving_object import (DEFAULT_EDGE_LENGTH,
                                      DEFAULT_TRACKING_RADIUS, ATagObject,
                                      MovingObject)
from controller.uuid_manager import UUIDManager
from scene_common import log
from scene_common.options import TYPE_1

object_classes = {
  # class
  'apriltag': {'class': ATagObject}
}

MAX_UNRELIABLE_TIME = 0.3333
NON_MEASUREMENT_TIME_DYNAMIC = 0.2666
NON_MEASUREMENT_TIME_STATIC = 0.5333

class Tracking(Thread):
  def __init__(self):
    super().__init__()
    self.trackers = {}
    self._objects = self.curObjects = []
    self.already_tracked_objects = []
    self.queue = Queue()
    self.uuid_manager = UUIDManager()
    return

  def getUniqueIDCount(self, category):
    tracker = self.trackers.get(category, None)
    if tracker:
      return tracker.uuid_manager.unique_id_count
    log.warn("No tracker for category", category)
    return 0

  def trackObjects(self, objects, already_tracked_objects, when, categories, \
                   ref_camera_frame_rate, \
                   max_unreliable_time, \
                   non_measurement_time_dynamic, \
                   non_measurement_time_static):
    self.createTrackers(categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static)

    if not categories:
      categories = self.trackers.keys()
    for category in categories:
      self.updateRefCameraFrameRate(ref_camera_frame_rate, category)
      queue = self.trackers[category].queue
      if not queue.empty():
        # Tracker specific to this category is still processing. Skip tracking objects for this category.
        log.info("Tracker work queue is not empty", category, queue.qsize())
        continue
      new_objects = [obj for obj in objects if obj.category == category]
      queue.put((new_objects, when, already_tracked_objects))
    return

  def updateRefCameraFrameRate(self, ref_camera_frame_rate, category):
    if ref_camera_frame_rate is not None and \
        self.trackers[category].ref_camera_frame_rate != ref_camera_frame_rate:
      self.trackers[category].ref_camera_frame_rate = ref_camera_frame_rate
      self.trackers[category].tracker.update_tracker_params(ref_camera_frame_rate)
    return

  def createTrackers(self, categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static):
    """Create a tracker object for each category"""
    for category in categories:
      if category not in self.trackers:
        tracker = self.__class__(max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static)
        self.trackers[category] = tracker
        tracker.start()
    return

  def updateObjectClasses(self, assets):
    remaining_object_class_names = list(object_classes.keys())
    for asset in assets:
      category = asset['name']

      if category not in object_classes:
        # Create a new subclass for new category
        category_class = MovingObject.createSubclass(category)
        object_classes[category] = {'class': category_class}
      else:
        remaining_object_class_names.remove(category)

      object_classes[category] = {'class': object_classes[category]['class']}
      for key in asset:
        if key == 'name':
          continue
        object_classes[category][key] = asset[key]

    for category in remaining_object_class_names:
      del object_classes[category]
    return

  def trackCategory(self, objects, when, tracks):
    # You must implement in your subclass
    raise NotImplemented
    return

  def currentObjects(self, category=None):
    categories = []
    if category is None:
      categories.extend(self.trackers.keys())
    else:
      categories.append(category)

    cur_objects = []
    for cat in categories:
      if cat in self.trackers:
        tracker = self.trackers[cat]
        cur_objects.extend(tracker.curObjects)
    if category is None:
      cur_objects = self.groupObjects(cur_objects)
    return cur_objects

  def run(self):
    self.uuid_manager.connectDatabase()
    while True:
      objects, when, already_tracked_objects = self.queue.get()
      if objects is None:
        self.queue.task_done()
        break
      self.trackCategory(objects, when, already_tracked_objects)
      self.curObjects = (self._objects + self.already_tracked_objects).copy()
      self.queue.task_done()
    return

  def waitForComplete(self):
    if hasattr(self, 'queue'):
      self.queue.join()
    return

  def join(self):
    for category in self.trackers:
      tracker = self.trackers[category]
      tracker.queue.put((None, None, None))
      tracker.waitForComplete()
      tracker.join()
    return

  @staticmethod
  def createObject(sensorType, info, when, sensor):
    tracking_radius = DEFAULT_TRACKING_RADIUS
    shift_type = TYPE_1
    project_to_map = False
    rotation_from_velocity = False

    if sensorType in object_classes:
      oclass = object_classes[sensorType]
      mobj = oclass['class'](info, when, sensor)
      if 'model_3d' in oclass:
        mobj.asset_scale = oclass['scale']
      mobj.size = [oclass.get('x_size', DEFAULT_EDGE_LENGTH),
                   oclass.get('y_size', DEFAULT_EDGE_LENGTH),
                   oclass.get('z_size', DEFAULT_EDGE_LENGTH)]
      tracking_radius = oclass.get('tracking_radius', tracking_radius)
      project_to_map = oclass.get('project_to_map', project_to_map)
      shift_type = oclass.get('shift_type', shift_type)
      rotation_from_velocity = oclass.get('rotation_from_velocity', rotation_from_velocity)
    else:
      mobj = MovingObject(info, when, sensor)

    mobj.project_to_map = project_to_map
    mobj.rotation_from_velocity = rotation_from_velocity
    mobj.shift_type = shift_type

    if tracking_radius > 0:
      mobj.tracking_radius = tracking_radius

    return mobj

  def groupObjects(self, objects):
    ogroups = {}
    for key in self._objects:
      ogroups[key] = []
    for obj in objects:
      if isinstance(obj, MovingObject):
        otype = obj.category
      else:
        otype = obj['category']
      if otype not in ogroups:
        ogroups[otype] = []
      ogroups[otype].append(obj)
    return ogroups
