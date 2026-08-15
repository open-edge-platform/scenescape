# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

import time
from queue import Queue
from threading import Thread, current_thread

from controller.moving_object import (DEFAULT_EDGE_LENGTH,
                                      DEFAULT_TRACKING_RADIUS, ATagObject,
                                      MovingObject)
from controller.uuid_manager import UUIDManager
from scene_common import log
from scene_common.options import TYPE_1
import uuid
from controller.observability import metrics

object_classes = {
  # class
  'apriltag': {'class': ATagObject}
}

MAX_UNRELIABLE_TIME = 0.3333
NON_MEASUREMENT_TIME_DYNAMIC = 0.2666
NON_MEASUREMENT_TIME_STATIC = 0.5333
DEFAULT_SUSPENDED_TRACK_TIMEOUT_SECS = 60.0

# Queue mode constants for tracking operation
STREAMING_MODE = False  # (DEFAULT) Objects from one source (camera) at a time are put into the queue
BATCHED_MODE = True     # Objects from multiple sources are aggregated together and put into the queue

class Tracking(Thread):
  """Base tracker class. Each instance is a daemon thread that owns all mutable
  tracking state for one category. Worker threads enqueue work via self.queue;
  only this thread's run() loop mutates all_tracker_objects, curObjects, and
  uuid_manager. This ownership model is the foundation for future
  multiprocessing: each tracker can move to a dedicated process without
  sharing mutable state."""

  def __init__(self):
    super().__init__(daemon=True)
    self.trackers = {}
    self.all_tracker_objects = self.curObjects = []
    self.already_tracked_objects = []
    self.queue = Queue()
    self.uuid_manager = UUIDManager()
    # Thread identity recorded at run() start — used to assert ownership
    self._owner_thread_id = None
    return

  def getUniqueIDCount(self, category):
    tracker = self.trackers.get(category, None)
    if tracker:
      return tracker.uuid_manager.unique_id_count
    log.warning("No tracker for category", category)
    return 0

  def trackObjects(self, objects, already_tracked_objects, when, categories, \
                   ref_camera_frame_rate, \
                   max_unreliable_time, \
                   non_measurement_time_dynamic, \
                   non_measurement_time_static, \
                   use_tracker=True, camera_id=None):

    self._createTrackers(categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static)

    if not categories:
      categories = self.trackers.keys()
    for category in categories:
      self._updateRefCameraFrameRate(ref_camera_frame_rate, category)
      new_objects = [obj for obj in objects if obj.category == category]
      if not use_tracker:
        for obj in new_objects:
          obj.oid = str(uuid.uuid4())
          obj.setGID(obj.oid)
        # No threading when tracker is not used. Thus creating a copy is not required.
        self.trackers[category].all_tracker_objects = self.trackers[category].curObjects = new_objects
      else:
        queue = self.trackers[category].queue
        if not queue.empty():
          # Tracker specific to this category is still processing. Skip tracking objects for this category.
          log.debug("Tracker work queue is not empty", category, queue.qsize())
          metrics_attributes = {
            "category": category,
            "reason": "tracker_busy"
          }
          metrics.inc_dropped(metrics_attributes)
          continue
        queue.put((new_objects, when, already_tracked_objects, STREAMING_MODE))
    return

  def _updateRefCameraFrameRate(self, ref_camera_frame_rate, category):
    if ref_camera_frame_rate is not None and \
        self.trackers[category].ref_camera_frame_rate != ref_camera_frame_rate:
      self.trackers[category].ref_camera_frame_rate = ref_camera_frame_rate
      self.trackers[category].tracker.update_tracker_params(ref_camera_frame_rate)
    return

  def _createTrackers(self, categories, max_unreliable_time, non_measurement_time_dynamic, non_measurement_time_static):
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
    raise NotImplementedError

  def trackCategoryBatched(self, objects_per_camera, when, tracks):
    # You must implement in your subclass if batched mode is used
    raise NotImplementedError

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

  def _assert_owner_thread(self):
    """Assert that mutable tracker state is only accessed by the owning daemon thread."""
    tid = current_thread().ident
    if self._owner_thread_id is None:
      self._owner_thread_id = tid
      return
    if tid != self._owner_thread_id:
      raise RuntimeError(
        f"Tracker state accessed by thread {tid}, but owned by {self._owner_thread_id}"
      )

  def run(self):
    self._owner_thread_id = current_thread().ident
    self.uuid_manager.connectDatabase()
    last_heartbeat = time.time()
    items_processed = 0
    while True:
      queue_item = self.queue.get()

      # Queue items always have 4 elements: (objects, when, already_tracked_objects, mode)
      if len(queue_item) != 4:
        # Invalid queue item format
        self.queue.task_done()
        continue

      objects, when, already_tracked_objects, mode = queue_item

      if objects is None:
        self.queue.task_done()
        break

      # Determine category for metrics
      if mode == BATCHED_MODE and len(objects) > 0 and len(objects[0]) > 0:
        category = objects[0][0].category  # First object in first camera list
      elif mode == STREAMING_MODE and len(objects) > 0:
        category = objects[0].category
      else:
        category = "unknown"

      metrics_attributes = {
        "category": category,
      }
      try:
        with metrics.time_tracking(metrics_attributes):
          # Assert ownership: only this daemon thread should mutate tracker state
          self._assert_owner_thread()
          if mode == BATCHED_MODE:
            self.trackCategoryBatched(objects, when, already_tracked_objects)
          else:
            self.trackCategory(objects, when, already_tracked_objects)
          # curObjects are the results while all_tracker_objects
          # is used as a working collection inside the thread
          self.curObjects = (self.all_tracker_objects).copy()
      except Exception as e:
        log.error(f"[TRACKER_EXCEPTION] category={category}, mode={'batched' if mode == BATCHED_MODE else 'streaming'}, "
                  f"error={type(e).__name__}: {e}")
      finally:
        self.queue.task_done()
        items_processed += 1

      # Heartbeat logging every 30 seconds to confirm thread liveness
      now = time.time()
      if now - last_heartbeat > 30.0:
        log.info(f"[TRACKER_HEARTBEAT] thread={self.__str__()}, items_processed={items_processed}, queue_size={self.queue.qsize()}")
        last_heartbeat = now

    log.debug(f"Tracker thread {self.__str__()} exiting. Queue size: {self.queue.qsize()}")
    return

  def waitForComplete(self):
    if hasattr(self, 'queue'):
      log.debug(f"Waiting for tracker {self.__str__()} queue to complete. Queue size: {self.queue.qsize()}")
      self.queue.join()
    return

  def join(self):
    log.debug("Joining tracker threads. Trackers count: ", len(self.trackers))
    for category in self.trackers:
      tracker = self.trackers[category]
      tracker.queue.put((None, None, None, STREAMING_MODE))
      log.debug(f"Waiting for tracker thread category {category} to complete")
      tracker.waitForComplete()
      log.debug(f"Joining tracker thread category {category}")
      tracker.join()
      # Shutdown uuid_manager thread pool for this tracker
      if hasattr(tracker, 'uuid_manager'):
        tracker.uuid_manager.shutdown()
    return

  @staticmethod
  def createObject(sensorType, info, when, sensor, persist_attributes=None):
    if persist_attributes is None:
      persist_attributes = {}
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
      mobj.buffer_size = [oclass.get('x_buffer_size', 0.0),
                          oclass.get('y_buffer_size', 0.0),
                          oclass.get('z_buffer_size', 0.0)]
      tracking_radius = oclass.get('tracking_radius', tracking_radius)
      project_to_map = oclass.get('project_to_map', project_to_map)
      shift_type = oclass.get('shift_type', shift_type)
      rotation_from_velocity = oclass.get('rotation_from_velocity', rotation_from_velocity)
      mobj.setPersistentAttributes(info, persist_attributes)
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
    for key in self.all_tracker_objects:
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
