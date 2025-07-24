# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from robot_vision import tracking
import datetime
import numpy as np
from typing import List

# This example shows how a custom tracker can be created using the components from robot_vision.tracking


# Helper function to create an object with simplified interface
def create_object_at_location(x : float = 0., y: float= 0., z : float= 0., yaw : float = 0., classification=np.full((1,), 1.0)):
  object_ = tracking.TrackedObject()
  object_.x = x
  object_.y = y
  object_.z = z
  object_.length = 1
  object_.width = 1
  object_.height = 1
  object_.yaw = yaw
  object_.classification = classification

  return object_

class CustomTracker():
  def __init__(self, track_manager_config : tracking.TrackManagerConfig = None, distance_type : tracking.DistanceType = None, distance_threshold : float = 1.0):
    """
        Instantiate the custom tracker with given config and distance parameters
    """
    # For the custom tracker we will use the same match function and track_manager defined in robot vision
    self.distance_type = tracking.DistanceType.Euclidean if distance_type is None else distance_type
    self.distance_threshold = distance_threshold
    self.track_manager_config = tracking.TrackManagerConfig() if track_manager_config is None else track_manager_config
    self.track_manager = tracking.TrackManager(self.track_manager_config)

  def match_function(self, tracks, objects):
    """
        Here we have the possibility of writing our own match function, but will just simply
        default to tracking.match
    """
    return tracking.match(tracks, objects, self.distance_type, self.distance_threshold)

  def _zero_measurement_update(self, timestamp: datetime.datetime):
    """
        If there are no new objects jut do a prediction/correction step of the track manager.
        Tracks without measurements will not perform the correction step, in this case all tracks.
    """
    self.track_manager.predict(timestamp)
    self.track_manager.correct()

  def _update(self, objects : List[tracking.TrackedObject], timestamp : datetime.datetime):
    """
        Update the tracker with the new objects received, this function should be called only
        when there is at least one object
    """
    self.track_manager.predict(timestamp)
    tracks = self.track_manager.get_tracks()
    assignments, unassigned_tracks, unassigned_objects = self.match_function(tracks, objects)

    for track_index, object_index in assignments:
      self.track_manager.set_measurement(tracks[track_index].id, objects[object_index])

    self.track_manager.correct()

    for object_index in unassigned_objects:
      self.track_manager.create_track(objects[object_index], timestamp)

  def get_tracks(self):
    """
        Return all the current tracks contained in the track manager.
    """
    return self.track_manager.get_tracks()

  def get_reliable_tracks(self):
    """
        Return only those tracks classified as reliable by the track manager.
    """
    return self.track_manager.get_reliable_tracks()

  def track(self, objects : List[tracking.TrackedObject], timestamp : datetime.datetime):
    """
        execute a tracking step with the given object list.
    """
    if len(objects) == 0:
      self._zero_measurement_update(timestamp)
    else:
      self._update(objects, timestamp)

  def __repr__(self):
    return (f'{self.__class__.__name__}(config={self.track_manager_config})')


classification_data = tracking.ClassificationData(['class1', 'class2', 'class3'])

tracker_config = tracking.TrackManagerConfig()

tracker_config.max_number_of_unreliable_frames = 2
tracker_config.non_measurement_frames_dynamic = 3
tracker_config.non_measurement_frames_static = 4

tracker_config.default_process_noise = 0.001
tracker_config.default_measurement_noise = 0.01
tracker_config.motion_models = [tracking.MotionModel.CV, tracking.MotionModel.CA, tracking.MotionModel.CTRV]
distance_type = tracking.DistanceType.Euclidean
distance_threshold = 5.0

tracker = CustomTracker(tracker_config, distance_type, distance_threshold)

print(tracker)

initial_timestamp = datetime.datetime.now()
tracker.track([], initial_timestamp) # initialize tracker with zero objects
step = 0.1 # step time in seconds
total_time = 10.
vx = 2.0
vy = 1.0
x0 = 0.
y0 = 0.

mean = 0
std_dev = 0.01

print(f'Simulating an object starting at location ({x0}, {y0}) and moving with velocity ({vx}, {vy}) for {total_time} seconds.')


for t in np.arange(step, total_time + 1e-3, step): # initial time is step
  timestamp = initial_timestamp + datetime.timedelta(seconds = t)

  noise_x, noise_y = np.random.normal(mean, std_dev, 2)

  x = x0 + vx * t + noise_x
  y = y0 + vy * t + noise_y

  object_ = create_object_at_location(x=x, y=y, classification=classification_data.classification('class1', 0.6))
  tracker.track([object_], timestamp)

tracked_objects = tracker.get_reliable_tracks()

print('Number of tracks:', len(tracked_objects))

print('tracked object:', tracked_objects[0])
print('classification:', tracked_objects[0].classification.round(6))

# Create ground truth object, i.e. object location and velocity without noise
ground_truth_object = create_object_at_location(x=x0 + vx * t, y=y0 + vy * t, classification=classification_data.classification('class1', 1.0))
ground_truth_object.vx = vx
ground_truth_object.vy = vy

print('ground truth object:', ground_truth_object)
print('classification:', ground_truth_object.classification.round(6))
