# SPDX-FileCopyrightText: 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from robot_vision import tracking
import numpy as np
import unittest
from datetime import datetime, timedelta
import cv2

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
    self.assertAlmostEqual(tracked_object.vx, vx, delta=0.05)
    self.assertAlmostEqual(tracked_object.vy, vy, delta=0.05)

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
    self.assertAlmostEqual(tracked_object.vx, vx, delta=0.05)
    self.assertAlmostEqual(tracked_object.vy, vy, delta=0.05)

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
    self.assertAlmostEqual(tracked_object.vx, vx, delta=0.05)
    self.assertAlmostEqual(tracked_object.vy, vy, delta=0.05)

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
    self.assertAlmostEqual(tracked_object.vx, vx, delta=0.05)
    self.assertAlmostEqual(tracked_object.vy, vy, delta=0.05)

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

  def test_chi2_threshold(self):
    self.assertAlmostEqual(tracking.chi2_threshold(0.99), 9.21034, places=3)

  def test_position_mahalanobis_prefers_motion_axis(self):
    tracker_config = tracking.TrackManagerConfig()
    tracker_config.motion_models = [tracking.MotionModel.CV]
    tracker_config.default_process_noise = 1e-4
    tracker_config.default_measurement_noise = 0.2
    tracker_config.init_state_covariance = 1.0

    manager = tracking.TrackManager(tracker_config)
    seed = create_object_at_location()
    seed.vx = 5.0
    seed.vy = 0.0

    timestamp = datetime.now()
    track_id = manager.create_track(seed, timestamp)

    for _ in range(10):
      timestamp += timedelta(milliseconds=100)
      seed.x += 0.5
      manager.set_measurement(track_id, seed)
      manager.predict(timestamp)
      manager.correct()
      seed = manager.get_track(track_id)

    timestamp += timedelta(milliseconds=1000)
    manager.predict(timestamp)
    track = manager.get_track(track_id)

    cov = np.array(track.measurement_covariance, dtype=float)
    s00 = float(cov[0, 0])
    s11 = float(cov[1, 1])
    self.assertGreater(s00, 1.5 * s11)

    mean = np.array(track.measurement_mean, dtype=float).ravel()
    pred_x = float(mean[0])
    pred_y = float(mean[1])
    chi2_gate = tracking.chi2_threshold(0.99)

    ahead = create_object_at_location(x=pred_x + 2.0, y=pred_y)
    lateral = create_object_at_location(x=pred_x, y=pred_y + 2.0)

    # Equal Euclidean distance: Hungarian must pick the along-track detection.
    assignments, _, _ = tracking.match(
      [track],
      [ahead, lateral],
      tracking.DistanceType.PositionMahalanobis,
      chi2_gate,
      10.0,
    )
    self.assertEqual(len(assignments), 1)
    self.assertEqual(assignments[0], (0, 0))

    d2_ahead = (2.0 ** 2) * s11 / (s00 * s11)
    d2_lateral = (2.0 ** 2) * s00 / (s00 * s11)
    self.assertLess(d2_ahead, d2_lateral)

  def test_position_mahalanobis_fuses_multi_camera_detections(self):
    """Cross-camera birth clustering must fuse in meters under PositionMahalanobis.

    Raw detections lack track predictedMeasurementCov; Mahalanobis on detection-
    detection matching would treat them as near-delta and fail to merge the same
    object seen ~1.3 m apart by two cameras (duplicate frozen tracks).

    Birth clustering uses a fixed ~2 m Euclidean radius (legacy scale), not the
    Mahalanobis max_radius_m ceiling, so a 10 m association ceiling does not
    over-merge nearby people at birth.
    """
    tracker_config = tracking.TrackManagerConfig()
    tracker_config.motion_models = [tracking.MotionModel.CV]
    tracker_config.default_process_noise = 1e-4
    tracker_config.default_measurement_noise = 0.2
    tracker_config.init_state_covariance = 1.0

    chi2_gate = tracking.chi2_threshold(0.99)
    tracker = tracking.MultipleObjectTracker(
      tracker_config, tracking.DistanceType.PositionMahalanobis, chi2_gate)
    tracker.update_tracker_params(10)

    cam0 = create_object_at_location(x=7.11, y=7.67)
    cam0.length = cam0.width = cam0.height = 0.5
    cam1 = create_object_at_location(x=7.91, y=6.69)
    cam1.length = cam1.width = cam1.height = 0.5

    tracker.track(
      [[cam0], [cam1]],
      datetime.now(),
      tracking.DistanceType.PositionMahalanobis,
      chi2_gate,
      0.5,
      10.0,
    )
    self.assertEqual(
      len(tracker.get_tracks()),
      1,
      'cross-camera detections of one object must birth a single track',
    )
    track = tracker.get_tracks()[0]
    self.assertAlmostEqual(track.x, 0.5 * (cam0.x + cam1.x), places=5)
    self.assertAlmostEqual(track.y, 0.5 * (cam0.y + cam1.y), places=5)

    # Beyond the fixed birth radius (~2 m) must not fuse even when max_radius_m
    # is a wide Mahalanobis ceiling (10 m).
    tracker2 = tracking.MultipleObjectTracker(
      tracker_config, tracking.DistanceType.PositionMahalanobis, chi2_gate)
    tracker2.update_tracker_params(10)
    beyond_birth = create_object_at_location(x=7.11 + 3.0, y=7.67)
    beyond_birth.length = beyond_birth.width = beyond_birth.height = 0.5
    tracker2.track(
      [[cam0], [beyond_birth]],
      datetime.now(),
      tracking.DistanceType.PositionMahalanobis,
      chi2_gate,
      0.5,
      10.0,
    )
    self.assertEqual(
      len(tracker2.get_tracks()),
      2,
      'birth clustering must stay at ~2 m, not follow max_radius_m=10',
    )

  def test_multi_camera_track_update_averages_world_position(self):
    """Track updates must average geometry across cameras, not last-camera wins."""
    tracker_config = tracking.TrackManagerConfig()
    tracker_config.motion_models = [tracking.MotionModel.CV]
    tracker_config.default_process_noise = 1e-4
    tracker_config.default_measurement_noise = 0.2
    tracker_config.init_state_covariance = 1.0
    tracker_config.max_number_of_unreliable_frames = 0

    tracker = tracking.MultipleObjectTracker(
      tracker_config, tracking.DistanceType.Euclidean, 5.0)
    tracker.update_tracker_params(10)

    cam0 = create_object_at_location(x=7.11, y=7.67)
    cam0.length = cam0.width = cam0.height = 0.5
    cam1 = create_object_at_location(x=7.91, y=6.69)
    cam1.length = cam1.width = cam1.height = 0.5
    mid_x = 0.5 * (cam0.x + cam1.x)
    mid_y = 0.5 * (cam0.y + cam1.y)

    ts = datetime.now()
    tracker.track([[cam0], [cam1]], ts, tracking.DistanceType.Euclidean, 5.0, 0.5, 10.0)
    ts += timedelta(milliseconds=100)
    tracker.track([[cam0], [cam1]], ts, tracking.DistanceType.Euclidean, 5.0, 0.5, 10.0)

    track = tracker.get_tracks()[0]
    self.assertAlmostEqual(track.x, mid_x, delta=0.15)
    self.assertAlmostEqual(track.y, mid_y, delta=0.15)

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

class TestComputePixelsToMeterPlane(unittest.TestCase):
  @staticmethod
  def reference_computePixelsToMeterPlane(x: float, y: float, width: float, height: float,
                              cameraintrinsicsmatrix: np.ndarray, distortionmatrix: np.ndarray) -> tuple[float, float, float, float]:
    """
    ! Convert pixel coordinates to undistorted normalized image coordinates using camera intrinsics and distortion matrices.
      Compute the undistorted coordinates for the given pixel point and its opposite corner.

    @param   x                        X-coordinate of the top-left corner of the pixel region (in pixels).
    @param   y                        Y-coordinate of the top-left corner of the pixel region (in pixels).
    @param   width                    Width of the pixel region (in pixels).
    @param   height                   Height of the pixel region (in pixels).
    @param   cameraintrinsicsmatrix   Camera intrinsics matrix as a numpy array.
    @param   distortionmatrix         Distortion coefficients matrix as a numpy array.

    @return  Tuple containing:
         - X-coordinate of the undistorted point (in normalized image coordinates).
         - Y-coordinate of the undistorted point (in normalized image coordinates).
         - Width of the undistorted region (in normalized image coordinates).
         - Height of the undistorted region (in normalized image coordinates).
    """
    pxpoint = np.array([x, y], dtype='float64').reshape(-1, 1, 2)
    pt = cv2.undistortPoints(pxpoint, cameraintrinsicsmatrix, distortionmatrix)
    oppositepxpoint = np.array([x + width, y + height], dtype='float64').reshape(-1, 1, 2)
    opppt = cv2.undistortPoints(oppositepxpoint, cameraintrinsicsmatrix, distortionmatrix)
    return pt[0][0][0], pt[0][0][1], opppt[0][0][0] - pt[0][0][0], opppt[0][0][1] - pt[0][0][1]

  def test_reference_vs_cpp_implementation(self):
    """
    Test that the reference Python implementation and the C++ implementation
    produce the same results for pixel to meter plane conversion.
    """
    # Test camera intrinsics matrix (3x3)
    intrinsics = np.array([[800.0, 0.0, 320.0],
                          [0.0, 800.0, 240.0],
                          [0.0, 0.0, 1.0]], dtype=np.float64)

    # Test distortion coefficients (k1, k2, p1, p2, k3)
    distortion = np.array([0.1, -0.2, 0.01, -0.005, 0.05], dtype=np.float64)

    # Test cases with different pixel coordinates and bounding box sizes
    test_cases = [
      # (x, y, width, height)
      (100, 150, 50, 100),
      (0, 0, 1, 1),
      (320, 240, 100, 80),  # Center of image
      (50.5, 75.3, 25.7, 30.2),  # Fractional coordinates
      (600, 400, 20, 40),
      (10, 10, 200, 300),
      (250, 300, 80, 60)
    ]

    for x, y, width, height in test_cases:
      with self.subTest(x=x, y=y, width=width, height=height):
        # Get results from reference Python implementation
        ref_result = self.reference_computePixelsToMeterPlane(
          x, y, width, height, intrinsics, distortion
        )

        # Get results from C++ implementation
        cpp_result = tracking.compute_pixels_to_meter_plane(
          x, y, width, height, intrinsics, distortion
        )

        # Compare results with small tolerance for floating point precision
        tolerance = 1e-6
        self.assertAlmostEqual(ref_result[0], cpp_result[0], delta=tolerance,
                              msg=f"X coordinate mismatch for ({x}, {y}, {width}, {height})")
        self.assertAlmostEqual(ref_result[1], cpp_result[1], delta=tolerance,
                              msg=f"Y coordinate mismatch for ({x}, {y}, {width}, {height})")
        self.assertAlmostEqual(ref_result[2], cpp_result[2], delta=tolerance,
                              msg=f"Width mismatch for ({x}, {y}, {width}, {height})")
        self.assertAlmostEqual(ref_result[3], cpp_result[3], delta=tolerance,
                              msg=f"Height mismatch for ({x}, {y}, {width}, {height})")

  def test_batch_vs_single_implementation(self):
    """
    Test that the batch processing function produces the same results as
    calling the single function multiple times.
    """
    # Test camera intrinsics matrix (3x3)
    intrinsics = np.array([[800.0, 0.0, 320.0],
                          [0.0, 800.0, 240.0],
                          [0.0, 0.0, 1.0]], dtype=np.float64)

    # Test distortion coefficients (k1, k2, p1, p2, k3)
    distortion = np.array([0.1, -0.2, 0.01, -0.005, 0.05], dtype=np.float64)

    # Test cases with different pixel coordinates and bounding box sizes
    test_bboxes = [
      (100, 150, 50, 100),
      (0, 0, 1, 1),
      (320, 240, 100, 80),  # Center of image
      (50.5, 75.3, 25.7, 30.2),  # Fractional coordinates
      (600, 400, 20, 40),
      (10, 10, 200, 300),
      (250, 300, 80, 60)
    ]

    # Get results from single function calls
    single_results = []
    for x, y, width, height in test_bboxes:
      result = tracking.compute_pixels_to_meter_plane(
        x, y, width, height, intrinsics, distortion
      )
      single_results.append(result)

    # Get results from batch function
    batch_results = tracking.compute_pixels_to_meter_plane_batch(
      test_bboxes, intrinsics, distortion
    )

    # Compare results
    self.assertEqual(len(single_results), len(batch_results),
                     "Batch and single results should have same length")

    tolerance = 1e-6
    for i, (single_result, batch_result) in enumerate(zip(single_results, batch_results)):
      x, y, width, height = test_bboxes[i]
      with self.subTest(bbox_index=i, bbox=(x, y, width, height)):
        self.assertAlmostEqual(single_result[0], batch_result[0], delta=tolerance,
                              msg=f"X coordinate mismatch for bbox {i}: ({x}, {y}, {width}, {height})")
        self.assertAlmostEqual(single_result[1], batch_result[1], delta=tolerance,
                              msg=f"Y coordinate mismatch for bbox {i}: ({x}, {y}, {width}, {height})")
        self.assertAlmostEqual(single_result[2], batch_result[2], delta=tolerance,
                              msg=f"Width mismatch for bbox {i}: ({x}, {y}, {width}, {height})")
        self.assertAlmostEqual(single_result[3], batch_result[3], delta=tolerance,
                              msg=f"Height mismatch for bbox {i}: ({x}, {y}, {width}, {height})")

  def test_batch_empty_list(self):
    """
    Test that the batch function handles empty input correctly.
    """
    # Test camera intrinsics matrix (3x3)
    intrinsics = np.array([[800.0, 0.0, 320.0],
                          [0.0, 800.0, 240.0],
                          [0.0, 0.0, 1.0]], dtype=np.float64)

    # Test distortion coefficients (k1, k2, p1, p2, k3)
    distortion = np.array([0.1, -0.2, 0.01, -0.005, 0.05], dtype=np.float64)

    # Test with empty list
    empty_bboxes = []
    results = tracking.compute_pixels_to_meter_plane_batch(
      empty_bboxes, intrinsics, distortion
    )

    self.assertEqual(len(results), 0, "Empty input should return empty results")
    self.assertIsInstance(results, list, "Result should be a list")
