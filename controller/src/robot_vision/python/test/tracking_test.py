# SPDX-FileCopyrightText: 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from robot_vision import tracking
import numpy as np
import unittest
from datetime import datetime, timedelta

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


class TestTracking(unittest.TestCase):

  def test_constant_velocity_single_object(self):
    """
    Tests simple intersection
    """
    classification_data = tracking.ClassificationData(['Car', 'Bike', 'Pedestrian'])
    tracker_config = tracking.TrackManagerConfig()
    tracker_config.default_process_noise = 0.00001
    tracker_config.default_measurement_noise = 0.001
    tracker_config.motion_models = [tracking.MotionModel.CV]

    tracker = tracking.MultipleObjectTracker(tracker_config)
    initial_timestamp = datetime.now()
    tracker.track([], initial_timestamp) # initialize tracker with zero objects
    step = 0.1 # step time in seconds
    total_time = 10.
    vx = 2.0
    vy = 1.0
    x0 = 0.
    y0 = 0.

    for t in np.arange(step, total_time, step): # initial time is step
      timestamp = initial_timestamp + timedelta(seconds = t)

      x = x0 + vx * t
      y = y0 + vy * t

      object_ = create_object_at_location(x=x, y=y, classification=classification_data.classification('Car', 1.0))
      tracker.track([object_], timestamp)

    tracked_objects = tracker.get_reliable_tracks()

    self.assertEqual(len(tracked_objects), 1)
    tracked_object = tracked_objects[0]
    self.assertAlmostEqual(tracked_object.vx, vx, places=3)
    self.assertAlmostEqual(tracked_object.vy, vy, places=3)



  def test_constant_velocity_single_object_with_noise(self):
    """
    Tests simple intersection
    """
    classification_data = tracking.ClassificationData(['Person', 'Robot', 'Marker', 'Object'])

    tracker_config = tracking.TrackManagerConfig()
    tracker_config.max_number_of_unreliable_frames = 10
    tracker_config.non_measurement_frames_dynamic = 20
    tracker_config.non_measurement_frames_static = 30
    tracker_config.default_process_noise = 1e-5
    tracker_config.default_measurement_noise = 1e-2
    tracker_config.init_state_covariance = 1
    tracker_config.motion_models = [tracking.MotionModel.CV, tracking.MotionModel.CA, tracking.MotionModel.CTRV]
    gating_radius = 1.0 # in meters
    tracker = tracking.MultipleObjectTracker(tracker_config, tracking.DistanceType.MultiClassEuclidean, gating_radius)
    initial_timestamp = datetime.now()
    tracker.track([], initial_timestamp) # initialize tracker with zero objects
    step = 0.1 # step time in seconds
    total_time = 10.
    vx = 2.0
    vy = 1.0
    x0 = 0.
    y0 = 0.

    mean = 0
    std_dev = 0.01

    for t in np.arange(step, total_time, step): # initial time is step
      timestamp = initial_timestamp + timedelta(seconds = t)

      noise_x, noise_y = np.random.normal(mean, std_dev, 2)

      x = x0 + vx * t + noise_x
      y = y0 + vy * t + noise_y

      object_ = create_object_at_location(x=x, y=y, classification=classification_data.classification('Person', 1.0))
      tracker.track([object_], timestamp)

    tracked_objects = tracker.get_reliable_tracks()

    self.assertEqual(len(tracked_objects), 1)
    tracked_object = tracked_objects[0]
    self.assertAlmostEqual(tracked_object.vx, vx, places=2)
    self.assertAlmostEqual(tracked_object.vy, vy, places=2)

  def test_constant_velocity_single_object_with_noise_use_track_distance_overload(self):
    """
    Tests simple intersection
    """
    classification_data = tracking.ClassificationData(['Person', 'Robot', 'Marker', 'Object'])

    tracker_config = tracking.TrackManagerConfig()
    tracker_config.max_number_of_unreliable_frames = 10
    tracker_config.non_measurement_frames_dynamic = 20
    tracker_config.non_measurement_frames_static = 30
    tracker_config.default_process_noise = 1e-5
    tracker_config.default_measurement_noise = 1e-3
    tracker_config.init_state_covariance = 1
    tracker_config.motion_models = [tracking.MotionModel.CV, tracking.MotionModel.CA, tracking.MotionModel.CTRV]
    gating_radius = 1.0 # in meters
    tracker = tracking.MultipleObjectTracker(tracker_config)
    initial_timestamp = datetime.now()
    tracker.track([], initial_timestamp) # initialize tracker with zero objects
    step = 0.1 # step time in seconds
    total_time = 10.
    vx = 2.0
    vy = 1.0
    x0 = 0.
    y0 = 0.

    mean = 0
    std_dev = 0.01

    for t in np.arange(step, total_time, step): # initial time is step
      timestamp = initial_timestamp + timedelta(seconds = t)

      noise_x, noise_y = np.random.normal(mean, std_dev, 2)

      x = x0 + vx * t + noise_x
      y = y0 + vy * t + noise_y

      object_ = create_object_at_location(x=x, y=y, classification=classification_data.classification('Person', 1.0))
      tracker.track([object_], timestamp, tracking.DistanceType.MultiClassEuclidean, gating_radius)

    tracked_objects = tracker.get_reliable_tracks()

    self.assertEqual(len(tracked_objects), 1)
    tracked_object = tracked_objects[0]
    self.assertAlmostEqual(tracked_object.vx, vx, places=2)
    self.assertAlmostEqual(tracked_object.vy, vy, places=2)

class TestMultiModelKalmanEstimator(unittest.TestCase):
  def test_constant_velocity_single_object_with_noise(self):
    classification_data = tracking.ClassificationData(['Car', 'Bike', 'Pedestrian'])

    initial_timestamp = datetime.now()
    estimator = tracking.MultiModelKalmanEstimator()
    step = 0.1 # step time in seconds
    total_time = 10.
    vx = 2.0
    vy = 1.0
    x0 = 0.
    y0 = 0.

    initial_estimate = create_object_at_location(x=x0, y=y0, classification=classification_data.classification('Car', 1.0))
    estimator.initialize(initial_estimate, initial_timestamp, motion_models=[tracking.MotionModel.CV]) # initialize tracker with zero objects
    mean = 0
    std_dev = 0.01
    for t in np.arange(step, total_time, step): # initial time is step
      timestamp = initial_timestamp + timedelta(seconds = t)

      noise_x, noise_y = np.random.normal(mean, std_dev, 2)

      x = x0 + vx * t + noise_x
      y = y0 + vy * t + noise_y

      object_ = create_object_at_location(x=x, y=y, classification=classification_data.classification('Car', 1.0))
      estimator.track(object_, timestamp)
    tracked_object = estimator.current_state()
    self.assertAlmostEqual(tracked_object.vx, vx, places=2)
    self.assertAlmostEqual(tracked_object.vy, vy, places=2)

  def testPredictFunctionDoubleAndTimestamp(self):
    estimator_a = tracking.MultiModelKalmanEstimator()
    estimator_b = tracking.MultiModelKalmanEstimator()

    t = 0.123561 # only valid up to microseconds
    initial_timestamp = datetime.now()
    new_object = create_object_at_location()
    timestamp = initial_timestamp + timedelta(seconds = t)

    estimator_a.initialize(new_object, initial_timestamp)
    estimator_b.initialize(new_object, initial_timestamp)

    estimator_a.predict(timestamp)
    estimator_b.predict(t)

    self.assertEqual(estimator_a.timestamp().timestamp(), estimator_b.timestamp().timestamp())

class TestTrackManager(unittest.TestCase):
  def test_track_manager_with_one_track(self):
    initial_timestamp = datetime.now()
    classification_data = tracking.ClassificationData(['Car', 'Bike', 'Pedestrian'])
    tracker_config = tracking.TrackManagerConfig()
    tracker_config.default_process_noise = 1e-5
    tracker_config.default_measurement_noise = 1e-2
    tracker_config.motion_models = [tracking.MotionModel.CV]

    track_manager = tracking.TrackManager(tracker_config)
    initial_timestamp = datetime.now()

    step = 0.1 # step time in seconds
    total_time = 10.
    vx = 2.0
    vy = 1.0
    x0 = 0.
    y0 = 0.

    object_ = create_object_at_location(x=x0, y=y0, classification=classification_data.classification('Car', 1.0))
    track_id = track_manager.create_track(object_, initial_timestamp)

    mean = 0
    std_dev = 0.01

    for t in np.arange(step, total_time, step): # initial time is step
      timestamp = initial_timestamp + timedelta(seconds = t)

      noise_x, noise_y = np.random.normal(mean, std_dev, 2)

      x = x0 + vx * t + noise_x
      y = y0 + vy * t + noise_y

      object_ = create_object_at_location(x=x, y=y, classification=classification_data.classification('Car', 1.0))
      track_manager.predict(timestamp)
      track_manager.set_measurement(track_id, object_)
      track_manager.correct()

    tracked_objects = track_manager.get_reliable_tracks()

    self.assertEqual(len(tracked_objects), 1)
    tracked_object = tracked_objects[0]
    self.assertAlmostEqual(tracked_object.vx, vx, places=2)
    self.assertAlmostEqual(tracked_object.vy, vy, places=2)

    ## Test access methods
    current_track = track_manager.get_track(tracked_object.id)

    self.assertEqual(current_track.id, tracked_object.id)
    self.assertAlmostEqual(current_track.x, tracked_object.x, places=5)
    self.assertAlmostEqual(current_track.y, tracked_object.y, places=5)
    self.assertAlmostEqual(current_track.vx, tracked_object.vx, places=5)
    self.assertAlmostEqual(current_track.vy, tracked_object.vy, places=5)
    self.assertAlmostEqual(current_track.ax, tracked_object.ax, places=5)
    self.assertAlmostEqual(current_track.ay, tracked_object.ay, places=5)
    self.assertAlmostEqual(current_track.yaw, tracked_object.yaw, places=5)
    self.assertAlmostEqual(current_track.width, tracked_object.width, places=5)
    self.assertAlmostEqual(current_track.height, tracked_object.height, places=5)
    self.assertAlmostEqual(current_track.length, tracked_object.length, places=5)

    # set track as suspended, reliable tracks should be empty now
    track_manager.suspend_track(tracked_object.id)
    self.assertEqual(len(track_manager.get_reliable_tracks()), 0)

    # access function can retrieve the kalman estimator
    kalman_estimator = track_manager.get_kalman_estimator(tracked_object.id)

    self.assertEqual(kalman_estimator.current_state().id, tracked_object.id)
    self.assertAlmostEqual(kalman_estimator.current_state().x, tracked_object.x, places=5)
    self.assertAlmostEqual(kalman_estimator.current_state().y, tracked_object.y, places=5)
    self.assertAlmostEqual(kalman_estimator.current_state().vx, tracked_object.vx, places=5)
    self.assertAlmostEqual(kalman_estimator.current_state().vy, tracked_object.vy, places=5)
    self.assertAlmostEqual(kalman_estimator.current_state().ax, tracked_object.ax, places=5)
    self.assertAlmostEqual(kalman_estimator.current_state().ay, tracked_object.ay, places=5)
    self.assertAlmostEqual(kalman_estimator.current_state().yaw, tracked_object.yaw, places=5)
    self.assertAlmostEqual(kalman_estimator.current_state().width, tracked_object.width, places=5)
    self.assertAlmostEqual(kalman_estimator.current_state().height, tracked_object.height, places=5)
    self.assertAlmostEqual(kalman_estimator.current_state().length, tracked_object.length, places=5)

    track_manager.delete_track(tracked_object.id)

    # track is no longer part of the TrackManager
    with self.assertRaises(RuntimeError):
      track_manager.get_kalman_estimator(tracked_object.id)

class TestMatchFunction(unittest.TestCase):
  def test_match_single_objects(self):
    classification_data = tracking.ClassificationData(['Car', 'Bike', 'Pedestrian'])

    track_00 = create_object_at_location(x=0, y=0, classification=classification_data.classification('Car', 0.9))
    track_01 = create_object_at_location(x=10, y=10, classification=classification_data.classification('Car', 0.9))

    # distance greater than 1
    measurement_00 = create_object_at_location(x=-1, y=1, classification=classification_data.classification('Car', 0.9))
    # distance is less than 1
    measurement_01 = create_object_at_location(x=10.5, y=9.5, classification=classification_data.classification('Car', 0.9))
    # invalid measurement
    measurement_02 = create_object_at_location(x=5.0, y=5.0, classification=classification_data.classification('Car', 0.9))

    # test first with a threshold greater than 1.0
    assignments, unassigned_tracks, unanssigend_objects = tracking.match([track_00, track_01], [measurement_00, measurement_01, measurement_02], threshold=10.0)

    # all objects should be assigned
    for k, (track_idx, measurement_idx) in enumerate(assignments):
      self.assertTrue(track_idx == k)
      self.assertTrue(measurement_idx == k)
    self.assertTrue(len(unassigned_tracks) == 0)
    self.assertTrue(len(unanssigend_objects) == 1)

    # test with a threshold less or equal than 1.0
    assignments, unassigned_tracks, unanssigend_objects = tracking.match([track_00, track_01], [measurement_00, measurement_01, measurement_02], threshold=1.0)

    # Only the second object will be matched
    self.assertTrue(assignments[0][0] == 1)
    self.assertTrue(assignments[0][1] == 1)
    self.assertTrue(len(unassigned_tracks) == 1)
    self.assertTrue(len(unanssigend_objects) == 2)

class TestClassification(unittest.TestCase):
  def test_classification_functions(self):
    classification_data = tracking.ClassificationData(['Car', 'Bike', 'Pedestrian'])

    self.assertEqual(classification_data.get_class(classification_data.classification('Car')), 'Car')
    self.assertEqual(classification_data.get_class(classification_data.classification('Bike')), 'Bike')
    self.assertEqual(classification_data.get_class(classification_data.classification('Pedestrian')), 'Pedestrian')

    self.assertAlmostEqual(tracking.classification.similarity([1,0,0], [1,0,0]), 1.0)
    self.assertAlmostEqual(tracking.classification.similarity([1,0,0], [0,0,1]), 0.0)

    car_measurement = np.array([0.8,0.1,0.1])
    bike_measurement = np.array([0.1,0.8,0.1])
    pedestrian_measurement = np.array([0.1,0.1,0.8])

    self.assertEqual(classification_data.get_class(car_measurement), "Car")
    self.assertEqual(classification_data.get_class(bike_measurement), "Bike")
    self.assertEqual(classification_data.get_class(pedestrian_measurement), "Pedestrian")

    classification = classification_data.classification('Car', 0.8)
    self.assertAlmostEqual(classification[0], 0.8)
    self.assertAlmostEqual(classification[1], 0.1)
    self.assertAlmostEqual(classification[2], 0.1)
