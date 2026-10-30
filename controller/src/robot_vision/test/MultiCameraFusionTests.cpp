// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <chrono>
#include <string>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include <rv/Utils.hpp>
#include <rv/tracking/MultipleObjectTracker.hpp>
#include <rv/tracking/OrientationAttributes.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "support/TestUtils.hpp"

namespace {

using rv::tracking::MeasurementIndex;
using rv::tracking::TrackedObject;
using rv::tracking::test::atMs;
using rv::tracking::test::diagonalMeasurementNoise;
using rv::tracking::test::makeDetection;
using Detections = std::vector<TrackedObject>;
using DetectionsPerCamera = std::vector<Detections>;

constexpr double kFusionGate = 2.0;

rv::tracking::MultipleObjectTracker makeFusionTracker()
{
  rv::tracking::TrackManagerConfig config;
  config.mMotionModels = {rv::tracking::MotionModel::CV};
  config.mDefaultProcessNoise = 1e-4;
  config.mDefaultMeasurementNoise = 0.2;
  config.mMaxNumberOfUnreliableFrames = 0;
  return rv::tracking::MultipleObjectTracker(config, rv::tracking::DistanceType::Euclidean, kFusionGate);
}

// Equal-weight average of every fused geometry field, without a camera_id so it is never fused again.
TrackedObject averageOf(const Detections &objects)
{
  TrackedObject average;
  for (const auto &object : objects)
  {
    average.x += object.x;
    average.y += object.y;
    average.z += object.z;
    average.length += object.length;
    average.width += object.width;
    average.height += object.height;
  }
  const double n = static_cast<double>(objects.size());
  average.x /= n;
  average.y /= n;
  average.z /= n;
  average.length /= n;
  average.width /= n;
  average.height /= n;
  return average;
}

void expectSameState(const TrackedObject &actual, const TrackedObject &expected)
{
  constexpr double kTolerance = 1e-9;
  EXPECT_NEAR(actual.x, expected.x, kTolerance);
  EXPECT_NEAR(actual.y, expected.y, kTolerance);
  EXPECT_NEAR(actual.z, expected.z, kTolerance);
  EXPECT_NEAR(actual.vx, expected.vx, kTolerance);
  EXPECT_NEAR(actual.vy, expected.vy, kTolerance);
  EXPECT_NEAR(actual.yaw, expected.yaw, kTolerance);
  EXPECT_NEAR(actual.length, expected.length, kTolerance);
  EXPECT_NEAR(actual.width, expected.width, kTolerance);
  EXPECT_NEAR(actual.height, expected.height, kTolerance);
}

// The twin is fed the expected fused detections directly, so equal states prove what fusion fed the filter.
void expectSameSingleTrack(rv::tracking::MultipleObjectTracker &tracker, rv::tracking::MultipleObjectTracker &twin)
{
  const auto tracks = tracker.getTracks();
  const auto twinTracks = twin.getTracks();
  ASSERT_EQ(tracks.size(), 1U);
  ASSERT_EQ(twinTracks.size(), 1U);
  expectSameState(tracks[0], twinTracks[0]);
}

std::vector<TrackedObject> tracksSortedByX(rv::tracking::MultipleObjectTracker &tracker)
{
  auto tracks = tracker.getTracks();
  std::sort(tracks.begin(), tracks.end(), [](const auto &a, const auto &b) { return a.x < b.x; });
  return tracks;
}

} // namespace

TEST(MultipleObjectTrackerTest, MultiCameraDetectionsFuseIntoOneTrack)
{
  // Same world object seen by two cameras with ~1.3 m projection disagreement.
  // Cross-camera birth clustering must fuse them into one track with averaged geometry.
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  trackerConfig.mMaxUnreliableTime = 0.0; // reliable immediately for assertion
  trackerConfig.mNonMeasurementTimeDynamic = 1.0;
  trackerConfig.mNonMeasurementTimeStatic = 1.6;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::Euclidean, 2.0);
  objectTracker.updateTrackerParams(10);

  rv::tracking::TrackedObject cam0;
  cam0.x = 7.11;
  cam0.y = 7.67;
  cam0.width = cam0.length = cam0.height = 0.5;

  rv::tracking::TrackedObject cam1 = cam0;
  cam1.x = 7.91;
  cam1.y = 6.69;

  auto timestamp = std::chrono::system_clock::now();
  objectTracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{cam0}, {cam1}},
                      timestamp,
                      rv::tracking::DistanceType::Euclidean,
                      2.0,
                      0.5);

  auto tracks = objectTracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U) << "cross-camera detections of one object must birth a single track";
  EXPECT_NEAR(tracks[0].x, 0.5 * (cam0.x + cam1.x), 1e-6);
  EXPECT_NEAR(tracks[0].y, 0.5 * (cam0.y + cam1.y), 1e-6);
}

TEST(MultipleObjectTrackerTest, MultiCameraBirthClusteringWeightsCamerasEqually)
{
  // Pairwise averaging would give the last camera weight 1/2 and earlier cameras 1/4.
  auto tracker = makeFusionTracker();
  const Detections cameras = {makeDetection(7.0, 7.0, 0.0, 0.5, 0.4, 1.5), makeDetection(7.6, 7.3, 0.1, 0.6, 0.5, 1.8),
                              makeDetection(8.2, 7.9, 0.3, 0.8, 0.6, 2.1)};

  tracker.track(DetectionsPerCamera{{cameras[0]}, {cameras[1]}, {cameras[2]}}, atMs(10));

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U);
  expectSameState(tracks[0], averageOf(cameras));
}

TEST(MultipleObjectTrackerTest, MultiCameraBirthKeepsDetectionsBeyondGateSeparate)
{
  auto tracker = makeFusionTracker();
  const auto near = makeDetection(7.0, 7.0, 0.0, 0.5, 0.5, 1.7);
  const auto far = makeDetection(7.0 + kFusionGate + 0.5, 7.0, 0.0, 0.5, 0.5, 1.7);

  tracker.track(DetectionsPerCamera{{near}, {far}}, atMs(10));

  const auto tracks = tracksSortedByX(tracker);
  ASSERT_EQ(tracks.size(), 2U);
  expectSameState(tracks[0], near);
  expectSameState(tracks[1], far);
}

TEST(MultipleObjectTrackerTest, MultiCameraBirthPairsDetectionsOfSeveralObjects)
{
  // Two objects seen by three cameras (listed in different orders): each track averages only its own detections.
  auto tracker = makeFusionTracker();
  const Detections left = {makeDetection(0.0, 0.0, 0.0, 0.5, 0.4, 1.6), makeDetection(0.4, 0.3, 0.1, 0.6, 0.5, 1.8),
                           makeDetection(-0.2, 0.4, 0.2, 0.7, 0.6, 1.7)};
  const Detections right = {makeDetection(4.0, 0.0, 0.0, 0.9, 0.8, 1.5), makeDetection(4.5, -0.2, 0.1, 1.0, 0.9, 1.6),
                            makeDetection(3.8, 0.3, 0.3, 1.1, 1.0, 1.4)};

  tracker.track(DetectionsPerCamera{{left[0], right[0]}, {right[1], left[1]}, {left[2], right[2]}}, atMs(10));

  const auto tracks = tracksSortedByX(tracker);
  ASSERT_EQ(tracks.size(), 2U);
  expectSameState(tracks[0], averageOf(left));
  expectSameState(tracks[1], averageOf(right));
}

TEST(MultipleObjectTrackerTest, MultiCameraBirthSeedsFromFirstMatchedCamera)
{
  // A new track keeps the non-geometry fields (e.g. the "info" detection id) of the first camera
  // in its cluster; track updates instead seed from the last matched camera.
  auto tracker = makeFusionTracker();
  Detections cameras = {makeDetection(7.0, 7.0, 0.0, 0.5, 0.5, 1.7), makeDetection(7.3, 7.1, 0.0, 0.5, 0.5, 1.7),
                        makeDetection(7.6, 6.9, 0.0, 0.5, 0.5, 1.7)};
  for (size_t camera = 0; camera < cameras.size(); ++camera)
  {
    cameras[camera].attributes["info"] = "detection-" + std::to_string(camera);
  }

  tracker.track(DetectionsPerCamera{{cameras[0]}, {cameras[1]}, {cameras[2]}}, atMs(10));

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U);
  ASSERT_EQ(tracks[0].attributes.count("info"), 1U);
  EXPECT_EQ(tracks[0].attributes.at("info"), "detection-0");
}

TEST(MultipleObjectTrackerTest, MultiCameraTrackUpdateAveragesWorldPosition)
{
  // Continuing tracks must average all cameras that matched, not keep last-camera geometry.
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const auto cam0 = makeDetection(7.11, 7.67, 0.0, 0.5, 0.5, 0.5);
  const auto cam1 = makeDetection(7.91, 6.69, 0.0, 0.5, 0.5, 0.5);

  for (int frame = 0; frame < 2; ++frame)
  {
    tracker.track(DetectionsPerCamera{{cam0}, {cam1}}, atMs(10 + 100 * frame));
    twin.track(DetectionsPerCamera{{averageOf({cam0, cam1})}}, atMs(10 + 100 * frame));
  }

  expectSameSingleTrack(tracker, twin);
}

TEST(MultipleObjectTrackerTest, MultiCameraMovingObjectMatchesPreAveragedSingleCamera)
{
  // Three cameras with a fixed per-camera bias on every geometry field, object moving diagonally.
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const Detections bias = {makeDetection(-0.3, 0.2, 0.0, 0.5, 0.4, 1.6), makeDetection(0.4, -0.1, 0.1, 0.6, 0.5, 1.8),
                           makeDetection(-0.1, -0.4, 0.2, 0.7, 0.6, 1.7)};

  for (int frame = 0; frame < 4; ++frame)
  {
    DetectionsPerCamera perCamera;
    Detections all;
    for (auto detection : bias)
    {
      detection.x += 7.0 + 0.15 * frame;
      detection.y += 7.0 + 0.1 * frame;
      perCamera.push_back({detection});
      all.push_back(detection);
    }
    tracker.track(perCamera, atMs(10 + 100 * frame));
    twin.track(DetectionsPerCamera{{averageOf(all)}}, atMs(10 + 100 * frame));
  }

  expectSameSingleTrack(tracker, twin);
}

TEST(MultipleObjectTrackerTest, MultiCameraTrackUpdateUsesOnlyMatchedCameras)
{
  // A detection outside the gate is not averaged into the track; it births its own track instead.
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  const auto camA = makeDetection(7.0, 7.0, 0.0, 0.5, 0.5, 1.7);
  const auto camB = makeDetection(7.6, 7.3, 0.0, 0.5, 0.5, 1.9);
  tracker.track(DetectionsPerCamera{{camA}, {camB}}, atMs(10));
  twin.track(DetectionsPerCamera{{averageOf({camA, camB})}}, atMs(10));

  auto movedA = camA;
  movedA.x += 0.1;
  auto farB = camB;
  farB.x += 3.0 * kFusionGate;
  tracker.track(DetectionsPerCamera{{movedA}, {farB}}, atMs(110));
  twin.track(DetectionsPerCamera{{movedA}}, atMs(110));

  const auto tracks = tracksSortedByX(tracker);
  const auto twinTracks = twin.getTracks();
  ASSERT_EQ(tracks.size(), 2U);
  ASSERT_EQ(twinTracks.size(), 1U);
  expectSameState(tracks[0], twinTracks[0]);
  expectSameState(tracks[1], farB);
}

TEST(MultipleObjectTrackerTest, PositionMahalanobisFusesMultiCameraDetectionsIntoOneTrack)
{
  // Same world object seen by two cameras with ~1.3 m projection disagreement.
  // Track association uses PositionMahalanobis; cross-camera birth clustering
  // must still fuse in meters so we do not create duplicate frozen tracks.
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  trackerConfig.mMaxUnreliableTime = 0.0; // reliable immediately for assertion
  trackerConfig.mNonMeasurementTimeDynamic = 1.0;
  trackerConfig.mNonMeasurementTimeStatic = 1.6;

  const double chi2_gate = rv::chi2Threshold(0.99, 3);
  rv::tracking::MultipleObjectTracker objectTracker(
    trackerConfig, rv::tracking::DistanceType::PositionMahalanobis, chi2_gate);
  objectTracker.updateTrackerParams(10);

  rv::tracking::TrackedObject cam0;
  cam0.x = 7.11;
  cam0.y = 7.67;
  cam0.width = cam0.length = cam0.height = 0.5;

  rv::tracking::TrackedObject cam1 = cam0;
  cam1.x = 7.91;
  cam1.y = 6.69;

  auto timestamp = std::chrono::system_clock::now();
  objectTracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{cam0}, {cam1}},
                      timestamp,
                      rv::tracking::DistanceType::PositionMahalanobis,
                      chi2_gate,
                      0.5,
                      10.0);

  auto tracks = objectTracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U) << "cross-camera detections of one object must birth a single track";
  EXPECT_NEAR(tracks[0].x, 0.5 * (cam0.x + cam1.x), 1e-6);
  EXPECT_NEAR(tracks[0].y, 0.5 * (cam0.y + cam1.y), 1e-6);
}


TEST(MultipleObjectTrackerTest, BirthClusteringDoesNotFuseStackedFloors)
{
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  trackerConfig.mMaxUnreliableTime = 0.0;
  trackerConfig.mNonMeasurementTimeDynamic = 1.0;
  trackerConfig.mNonMeasurementTimeStatic = 1.6;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::Euclidean, 2.0);
  objectTracker.updateTrackerParams(10);

  rv::tracking::TrackedObject floor0;
  floor0.x = 5.0;
  floor0.y = 5.0;
  floor0.z = 0.0;
  floor0.zMeasured = true;
  floor0.width = floor0.length = floor0.height = 0.5;

  rv::tracking::TrackedObject floor1 = floor0;
  floor1.z = 3.0; // beyond kDefaultBirthClusterRadiusM (2 m)

  auto timestamp = std::chrono::system_clock::now();
  objectTracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{floor0}, {floor1}},
                      timestamp, rv::tracking::DistanceType::Euclidean, 2.0, 0.5);

  auto tracks = objectTracker.getTracks();
  ASSERT_EQ(tracks.size(), 2U) << "measured-Z detections stacked in Z must not birth-cluster into one track";
}

TEST(MultipleObjectTrackerTest, BirthClusteringFusesMixedPlanarAndMeasuredZ)
{
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  trackerConfig.mMaxUnreliableTime = 0.0;
  trackerConfig.mNonMeasurementTimeDynamic = 1.0;
  trackerConfig.mNonMeasurementTimeStatic = 1.6;

  rv::tracking::MultipleObjectTracker objectTracker(trackerConfig, rv::tracking::DistanceType::Euclidean, 2.0);
  objectTracker.updateTrackerParams(10);

  rv::tracking::TrackedObject planar;
  planar.x = 5.0;
  planar.y = 5.0;
  planar.z = 0.0;
  planar.zMeasured = false;
  planar.width = planar.length = planar.height = 0.5;

  rv::tracking::TrackedObject measured = planar;
  measured.z = 1.5;
  measured.zMeasured = true;

  auto timestamp = std::chrono::system_clock::now();
  objectTracker.track(std::vector<std::vector<rv::tracking::TrackedObject>>{{planar}, {measured}},
                      timestamp, rv::tracking::DistanceType::Euclidean, 2.0, 0.5);

  auto tracks = objectTracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U) << "planar + measured-Z at same XY should birth-cluster via XY distance";
}

TEST(MultipleObjectTrackerTest, MultiCameraBirthFusionWeightsByMeasurementNoise)
{
  // cam0 is sharp along x and blurry along y, cam1 the opposite: the track takes x from cam0 and y from cam1.
  auto tracker = makeFusionTracker();
  auto cam0 = makeDetection(7.11, 7.67, 0.0, 0.5, 0.5, 0.5);
  cam0.measurementNoiseCov = diagonalMeasurementNoise(0.01, 4.0, 0.2);
  auto cam1 = makeDetection(7.91, 6.69, 0.0, 0.5, 0.5, 0.5);
  cam1.measurementNoiseCov = diagonalMeasurementNoise(4.0, 0.01, 0.2);

  tracker.track(DetectionsPerCamera{{cam0}, {cam1}}, atMs(10));

  const auto tracks = tracker.getTracks();
  ASSERT_EQ(tracks.size(), 1U);
  EXPECT_NEAR(tracks[0].x, (7.11 / 0.01 + 7.91 / 4.0) / (1.0 / 0.01 + 1.0 / 4.0), 1e-9);
  EXPECT_NEAR(tracks[0].y, (7.67 / 4.0 + 6.69 / 0.01) / (1.0 / 4.0 + 1.0 / 0.01), 1e-9);
  EXPECT_FALSE(tracks[0].measurementNoiseCov) << "tracks must not carry a detection R";

  // The birth P on the measured states starts from the fused R.
  const cv::Mat P = tracker.mTrackManager.mKalmanEstimators.begin()->second.getKalmanFilterErrorCovariance(0);
  EXPECT_NEAR(
    P.at<double>(rv::tracking::StateIndex::X, rv::tracking::StateIndex::X), 1.0 / (1.0 / 0.01 + 1.0 / 4.0), 1e-12);
  EXPECT_NEAR(
    P.at<double>(rv::tracking::StateIndex::Y, rv::tracking::StateIndex::Y), 1.0 / (1.0 / 4.0 + 1.0 / 0.01), 1e-12);
}

TEST(MultipleObjectTrackerTest, MultiCameraTrackUpdateFusesByMeasurementNoise)
{
  // The twin gets the information-weighted point and its fused R, so equal states prove both reached the filter.
  auto tracker = makeFusionTracker();
  auto twin = makeFusionTracker();
  auto cam0 = makeDetection(7.11, 7.67, 0.0, 0.5, 0.5, 0.5);
  cam0.measurementNoiseCov = diagonalMeasurementNoise(0.01, 4.0, 0.2);
  auto cam1 = makeDetection(7.91, 6.69, 0.0, 0.5, 0.5, 0.5);
  cam1.measurementNoiseCov = diagonalMeasurementNoise(4.0, 0.01, 0.2);

  const double varX = 1.0 / (1.0 / 0.01 + 1.0 / 4.0);
  const double varY = 1.0 / (1.0 / 4.0 + 1.0 / 0.01);
  auto fused = makeDetection(varX * (7.11 / 0.01 + 7.91 / 4.0), varY * (7.67 / 4.0 + 6.69 / 0.01), 0.0, 0.5, 0.5, 0.5);
  // z, length, width and height: two equal 0.2 variances fuse to 0.1; yaw keeps the seed's 0.2.
  fused.measurementNoiseCov = diagonalMeasurementNoise(varX, varY, 0.1, 0.1);
  (*fused.measurementNoiseCov)(MeasurementIndex::YAW, MeasurementIndex::YAW) = 0.2;

  for (int frame = 0; frame < 3; ++frame)
  {
    tracker.track(DetectionsPerCamera{{cam0}, {cam1}}, atMs(10 + 100 * frame));
    twin.track(DetectionsPerCamera{{fused}}, atMs(10 + 100 * frame));
  }

  expectSameSingleTrack(tracker, twin);
}

TEST(MultipleObjectTrackerTest, MultiCameraFusionUsesDefaultNoiseForDetectionsWithoutR)
{
  auto tracker = makeFusionTracker(); // default R = 0.2 I
  auto withR = makeDetection(1.0, 0.0, 0.0, 0.5, 0.5, 0.5);
  withR.measurementNoiseCov = diagonalMeasurementNoise(0.01, 0.2, 0.2);
  const auto withoutR = makeDetection(1.2, 0.0, 0.0, 0.5, 0.5, 0.5);

  for (int frame = 0; frame < 2; ++frame)
  {
    tracker.track(DetectionsPerCamera{{withR}, {withoutR}}, atMs(10 + 100 * frame));
  }

  const auto &measurements = tracker.mTrackManager.mMeasurementMap;
  ASSERT_EQ(measurements.size(), 1U);
  const auto &fused = measurements.begin()->second;
  ASSERT_TRUE(fused.measurementNoiseCov);
  EXPECT_NEAR(fused.x, (1.0 / 0.01 + 1.2 / 0.2) / (1.0 / 0.01 + 1.0 / 0.2), 1e-9);
  EXPECT_NEAR(
    (*fused.measurementNoiseCov)(MeasurementIndex::X, MeasurementIndex::X), 1.0 / (1.0 / 0.01 + 1.0 / 0.2), 1e-12);
}

TEST(MultipleObjectTrackerTest, MultiCameraFusionWithoutMeasurementNoiseLeavesRUnset)
{
  // Legacy path: no detection carries R, so the fused measurement is the plain average with the default R.
  auto tracker = makeFusionTracker();
  const auto cam0 = makeDetection(1.0, 0.0, 0.0, 0.5, 0.5, 0.5);
  const auto cam1 = makeDetection(1.2, 0.0, 0.0, 0.5, 0.5, 0.5);

  for (int frame = 0; frame < 2; ++frame)
  {
    tracker.track(DetectionsPerCamera{{cam0}, {cam1}}, atMs(10 + 100 * frame));
  }

  const auto &measurements = tracker.mTrackManager.mMeasurementMap;
  ASSERT_EQ(measurements.size(), 1U);
  const auto &fused = measurements.begin()->second;
  EXPECT_FALSE(fused.measurementNoiseCov);
  EXPECT_NEAR(fused.x, 1.1, 1e-12);
}

TEST(MultipleObjectTrackerTest, MultiCameraFusedYawVarianceFollowsSelectedOrientingDetection)
{
  auto tracker = makeFusionTracker();
  auto orienting = makeDetection(1.0, 0.0, 0.0, 0.5, 0.5, 0.5);
  orienting.measurementNoiseCov = diagonalMeasurementNoise(0.2, 0.2, 0.2);
  (*orienting.measurementNoiseCov)(MeasurementIndex::YAW, MeasurementIndex::YAW) = 0.01;
  rv::tracking::orientation::setHasOrientation(orienting, true);

  // The last camera seeds the fused measurement; its yaw variance (5.0) must not follow the selected yaw.
  auto cameraOnly = makeDetection(1.2, 0.0, 0.0, 0.5, 0.5, 0.5);
  cameraOnly.measurementNoiseCov = diagonalMeasurementNoise(0.2, 0.2, 0.2, 5.0);
  rv::tracking::orientation::setHasOrientation(cameraOnly, false);

  for (int frame = 0; frame < 2; ++frame)
  {
    tracker.track(DetectionsPerCamera{{orienting}, {cameraOnly}}, atMs(10 + 100 * frame));
  }

  const auto &measurements = tracker.mTrackManager.mMeasurementMap;
  ASSERT_EQ(measurements.size(), 1U);
  const auto &fused = measurements.begin()->second;
  ASSERT_TRUE(fused.measurementNoiseCov);
  EXPECT_DOUBLE_EQ((*fused.measurementNoiseCov)(MeasurementIndex::YAW, MeasurementIndex::YAW), 0.01);
}
