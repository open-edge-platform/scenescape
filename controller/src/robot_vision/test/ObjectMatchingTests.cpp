// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <array>
#include <chrono>
#include <cmath>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include <rv/Utils.hpp>
#include <rv/tracking/ObjectMatching.hpp>
#include <rv/tracking/OrientationAttributes.hpp>
#include <rv/tracking/TrackManager.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "support/TestUtils.hpp"

TEST(ObjectMatchingTest, Chi2ThresholdMatchesExpectedQuantile)
{
  EXPECT_NEAR(rv::chi2Threshold(0.99, 2), 9.21034, 1e-3);
  EXPECT_NEAR(rv::chi2Threshold(0.99, 3), 11.3449, 1e-3);
  EXPECT_NEAR(rv::chi2Threshold(0.95, 3), 7.81473, 1e-3);
}

TEST(ObjectMatchingTest, PositionMahalanobisPrefersAlongTrackAxis)
{
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  rv::tracking::TrackManager trackManager(trackerConfig);

  rv::tracking::TrackedObject seed;
  seed.x = 0.0;
  seed.y = 0.0;
  seed.vx = 5.0;
  seed.vy = 0.0;
  seed.length = 0.5;
  seed.width = 0.5;
  seed.height = 0.5;

  auto timestamp = std::chrono::system_clock::now();
  auto trackId = trackManager.createTrack(seed, timestamp);

  for (int i = 0; i < 10; ++i)
  {
    timestamp += std::chrono::milliseconds(100);
    seed.x += 0.5;
    trackManager.setMeasurement(trackId, seed);
    trackManager.predict(timestamp);
    trackManager.correct();
    seed = trackManager.getTracks().front();
  }

  timestamp += std::chrono::milliseconds(1000);
  trackManager.predict(timestamp);
  auto track = trackManager.getTracks().front();

  const double s00 = track.predictedMeasurementCov(0, 0);
  const double s11 = track.predictedMeasurementCov(1, 1);
  EXPECT_GT(s00, 1.5 * s11) << "expected along-track (x) uncertainty to dominate after +x motion coast";

  const double pred_x = track.predictedMeasurementMean(0);
  const double pred_y = track.predictedMeasurementMean(1);

  rv::tracking::TrackedObject ahead = seed;
  ahead.x = pred_x + 2.0;
  ahead.y = pred_y;

  rv::tracking::TrackedObject lateral = seed;
  lateral.x = pred_x;
  lateral.y = pred_y + 2.0;

  const double chi2_gate = rv::chi2Threshold(0.99, 3);
  const double max_radius = 10.0;

  std::vector<rv::tracking::TrackedObject> tracks = {track};
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;

  // Equal Euclidean distance: matcher must prefer the along-track detection.
  rv::tracking::match(tracks, {ahead, lateral}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::PositionMahalanobis, chi2_gate, max_radius);
  ASSERT_EQ(assignments.size(), 1U);
  EXPECT_EQ(assignments[0].first, 0U);
  EXPECT_EQ(assignments[0].second, 0U);

  assignments.clear();
  unassignedTracks.clear();
  unassignedMeasurements.clear();
  rv::tracking::match(tracks, {lateral}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::PositionMahalanobis, chi2_gate, max_radius);
  // Lateral-only may still pass the chi2 gate; cost must still exceed along-track cost.
  const double dx = 2.0;
  const double dy = 2.0;
  const double det = s00 * s11;
  ASSERT_GT(det, 0.0);
  const double d2_ahead = (dx * dx) * s11 / det;
  const double d2_lateral = (dy * dy) * s00 / det;
  EXPECT_LT(d2_ahead, d2_lateral);
}

TEST(ObjectMatchingTest, EuclideanSeparatesStackedFloors)
{
  rv::tracking::TrackedObject track;
  track.x = 1.0;
  track.y = 2.0;
  track.z = 0.0;
  track.length = track.width = track.height = 0.5;

  rv::tracking::TrackedObject sameFloor = track;
  sameFloor.z = 0.1;

  rv::tracking::TrackedObject upperFloor = track;
  upperFloor.z = 3.0; // > 2 m birth / Euclidean gate

  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;

  rv::tracking::match({track}, {sameFloor, upperFloor}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::Euclidean, 2.0, 2.0);
  ASSERT_EQ(assignments.size(), 1U);
  EXPECT_EQ(assignments[0].second, 0U);

  assignments.clear();
  unassignedTracks.clear();
  unassignedMeasurements.clear();
  rv::tracking::match({track}, {upperFloor}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::Euclidean, 2.0, 2.0);
  EXPECT_TRUE(assignments.empty());
}

TEST(ObjectMatchingTest, EuclideanBirthUsesXyUnlessBothZMeasured)
{
  rv::tracking::TrackedObject planar;
  planar.x = 1.0;
  planar.y = 2.0;
  planar.z = 0.0;
  planar.zMeasured = false;
  planar.length = planar.width = planar.height = 0.5;

  rv::tracking::TrackedObject measured = planar;
  measured.z = 1.5;
  measured.zMeasured = true;

  rv::tracking::TrackedObject upperMeasured = planar;
  upperMeasured.z = 4.0; // Δz > kDefaultBirthClusterRadiusM
  upperMeasured.zMeasured = true;

  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;

  // Mixed planar + measured Z: XY distance (~0) must match within 2 m.
  rv::tracking::match({planar}, {measured}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::EuclideanBirth, 2.0, 2.0);
  ASSERT_EQ(assignments.size(), 1U);

  assignments.clear();
  unassignedTracks.clear();
  unassignedMeasurements.clear();
  // Both measured, Δz = 4 m: reject.
  rv::tracking::match({measured}, {upperMeasured}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::EuclideanBirth, 2.0, 2.0);
  EXPECT_TRUE(assignments.empty());
}

TEST(ObjectMatchingTest, PositionMahalanobisSeparatesStackedFloors)
{
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  rv::tracking::TrackManager trackManager(trackerConfig);

  rv::tracking::TrackedObject seed;
  seed.x = 0.0;
  seed.y = 0.0;
  seed.z = 0.0;
  seed.length = seed.width = seed.height = 0.5;

  auto timestamp = std::chrono::system_clock::now();
  auto trackId = trackManager.createTrack(seed, timestamp);
  for (int i = 0; i < 5; ++i)
  {
    timestamp += std::chrono::milliseconds(100);
    trackManager.setMeasurement(trackId, seed);
    trackManager.predict(timestamp);
    trackManager.correct();
  }
  timestamp += std::chrono::milliseconds(100);
  trackManager.predict(timestamp);
  auto track = trackManager.getTracks().front();

  rv::tracking::TrackedObject sameFloor = seed;
  sameFloor.z = 0.05;
  rv::tracking::TrackedObject upperFloor = seed;
  upperFloor.z = 4.0;

  const double chi2_gate = rv::chi2Threshold(0.99, 3);
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;

  rv::tracking::match({track}, {sameFloor, upperFloor}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::PositionMahalanobis, chi2_gate, 10.0);
  ASSERT_EQ(assignments.size(), 1U);
  EXPECT_EQ(assignments[0].second, 0U);
}

// Defined in ObjectMatching.cpp, not declared in its header.
namespace rv::tracking {
double calculateMahalanobisDistance(const TrackedObject &measurement, const TrackedObject &track);
double calculatePositionMahalanobisSquaredDistance(const TrackedObject &measurement, const TrackedObject &track);
} // namespace rv::tracking

namespace {

using namespace rv::tracking;
using test::makeDetection;
using Vector = std::array<double, TrackedObject::MeasurementSize>;

constexpr int kYaw = MeasurementIndex::YAW;

// Symmetric positive definite, with every measurement coupled to every other, yaw included.
TrackedObject makeTrack()
{
  TrackedObject track;
  track.predictedMeasurementMean = TrackedObject::MeasurementVector(2.5, -1.0, 0.4, 4.5, 1.8, 1.5, 0.2);
  for (int i = 0; i < TrackedObject::MeasurementSize; ++i)
  {
    for (int j = 0; j < TrackedObject::MeasurementSize; ++j)
    {
      track.predictedMeasurementCovInv(i, j) = i == j ? 4.0 + i : 0.3 / (1.0 + std::abs(i - j));
    }
  }
  return track;
}

TrackedObject makeMeasurement()
{
  auto measurement = makeDetection(3.0, -2.0, 0.5, 4.6, 1.9, 1.4);
  measurement.yaw = 1.2;
  return measurement;
}

// 0.5 * sqrt(d' * S^-1 * d), written with plain loops.
double expectedDistance(const TrackedObject &measurement, const TrackedObject &track, bool useYaw)
{
  const Vector observed{measurement.x,
                        measurement.y,
                        measurement.z,
                        measurement.length,
                        measurement.width,
                        measurement.height,
                        measurement.yaw};
  Vector innovation{};
  for (int i = 0; i < TrackedObject::MeasurementSize; ++i)
  {
    innovation[i] = observed[i] - track.predictedMeasurementMean(i);
  }
  if (!useYaw)
  {
    innovation[kYaw] = 0.0;
  }
  double squared = 0.0;
  for (int i = 0; i < TrackedObject::MeasurementSize; ++i)
  {
    for (int j = 0; j < TrackedObject::MeasurementSize; ++j)
    {
      squared += innovation[i] * track.predictedMeasurementCovInv(i, j) * innovation[j];
    }
  }
  return 0.5 * std::sqrt(squared);
}

TEST(ObjectMatchingTest, MahalanobisDistanceUsesInverseCovarianceOfPredictedMeasurement)
{
  const auto track = makeTrack();
  const auto measurement = makeMeasurement();

  const double distance = calculateMahalanobisDistance(measurement, track);

  EXPECT_NEAR(distance, expectedDistance(measurement, track, false), 1e-12);
  EXPECT_GT(distance, 0.5);

  const auto onTrack = makeDetection(2.5, -1.0, 0.4, 4.5, 1.8, 1.5);
  EXPECT_DOUBLE_EQ(calculateMahalanobisDistance(onTrack, track), 0.0);
}

TEST(ObjectMatchingTest, MahalanobisDistanceUsesYawOnlyWhenBothSidesHaveOrientation)
{
  const struct
  {
    const char *name;
    bool measurementOriented;
    bool trackHasOrientation; // the latest update came from an orienting sensor
    bool trackObservedOrientation;
    bool expectYaw;
  } cases[] = {
    {.name = "camera detection, camera track",
     .measurementOriented = false,
     .trackHasOrientation = false,
     .trackObservedOrientation = false,
     .expectYaw = false},
    {.name = "orienting detection, camera track",
     .measurementOriented = true,
     .trackHasOrientation = false,
     .trackObservedOrientation = false,
     .expectYaw = false},
    {.name = "camera detection, orienting track",
     .measurementOriented = false,
     .trackHasOrientation = true,
     .trackObservedOrientation = true,
     .expectYaw = false},
    {.name = "orienting detection, track that observed orientation earlier",
     .measurementOriented = true,
     .trackHasOrientation = false,
     .trackObservedOrientation = true,
     .expectYaw = true},
    {.name = "orienting detection, orienting track",
     .measurementOriented = true,
     .trackHasOrientation = true,
     .trackObservedOrientation = false,
     .expectYaw = true},
  };

  auto measurement = makeMeasurement();
  const auto reference = makeTrack();
  // The yaw innovation is large and coupled to the other measurements, so using it must change the distance.
  ASSERT_GT(std::abs(expectedDistance(measurement, reference, true) - expectedDistance(measurement, reference, false)),
            0.1);

  for (const auto &scenario : cases)
  {
    SCOPED_TRACE(scenario.name);
    auto track = makeTrack();
    measurement.attributes.clear();
    if (scenario.measurementOriented)
    {
      orientation::setHasOrientation(measurement, true);
    }
    orientation::setHasOrientation(track, scenario.trackHasOrientation);
    if (scenario.trackObservedOrientation)
    {
      track.attributes[orientation::ORIENTATION_OBSERVED] = orientation::TRUE_VALUE;
    }

    EXPECT_NEAR(calculateMahalanobisDistance(measurement, track),
                expectedDistance(measurement, track, scenario.expectYaw),
                1e-12);
  }
}

TEST(ObjectMatchingTest, MahalanobisDistanceUsesMeasurementNoise)
{
  // With R on the detection, S = H P H^T + R replaces the track's cached S^-1 for this pair.
  auto track = makeTrack();
  track.predictedStateMeasurementCov = TrackedObject::MeasurementMatrix::eye() * 0.5;
  auto measurement = makeMeasurement();
  measurement.measurementNoiseCov
    = TrackedObject::MeasurementMatrix::diag(TrackedObject::MeasurementVector(0.5, 1.5, 3.5, 0.5, 0.5, 0.5, 0.5));
  const Vector variance{1.0, 2.0, 4.0, 1.0, 1.0, 1.0, 1.0};

  const auto innovation = measurement.measurementVector() - track.predictedMeasurementMean;
  double squared = 0.0;
  for (int i = 0; i < TrackedObject::MeasurementSize; ++i)
  {
    if (i != kYaw) // neither side has orientation
    {
      squared += innovation(i) * innovation(i) / variance[i];
    }
  }
  EXPECT_NEAR(calculateMahalanobisDistance(measurement, track), 0.5 * std::sqrt(squared), 1e-12);

  measurement.measurementNoiseCov.reset();
  EXPECT_NEAR(calculateMahalanobisDistance(measurement, track), expectedDistance(measurement, track, false), 1e-12);
}

TrackedObject predictedStaticTrack()
{
  TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  TrackManager trackManager(trackerConfig);

  const auto seed = makeDetection(0.0, 0.0, 0.0, 0.5, 0.5, 0.5);
  auto timestamp = std::chrono::system_clock::now();
  const auto trackId = trackManager.createTrack(seed, timestamp);
  for (int i = 0; i < 5; ++i)
  {
    timestamp += std::chrono::milliseconds(100);
    trackManager.setMeasurement(trackId, seed);
    trackManager.predict(timestamp);
    trackManager.correct();
  }
  timestamp += std::chrono::milliseconds(100);
  trackManager.predict(timestamp);
  return trackManager.getTracks().front();
}

bool isGated(const TrackedObject &track, const TrackedObject &detection, double maxRadius = 10.0)
{
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;
  match({track},
        {detection},
        assignments,
        unassignedTracks,
        unassignedMeasurements,
        DistanceType::PositionMahalanobis,
        rv::chi2Threshold(0.99, 3),
        maxRadius);
  return assignments.size() == 1U;
}

TEST(ObjectMatchingTest, PositionMahalanobisGateUsesMeasurementNoise)
{
  const auto track = predictedStaticTrack();
  // Predict publishes H P H^T next to S = H P H^T + R_default.
  ASSERT_NEAR(track.predictedStateMeasurementCov(MeasurementIndex::X, MeasurementIndex::X),
              track.predictedMeasurementCov(MeasurementIndex::X, MeasurementIndex::X) - 0.2,
              1e-12);
  ASSERT_GT(track.predictedStateMeasurementCov(MeasurementIndex::X, MeasurementIndex::X), 0.0);

  // 3 m off along x: outside the default-R gate, inside when the detection's own R is wide along x.
  const auto defaultR = makeDetection(3.0, 0.0, 0.0, 0.5, 0.5, 0.5);
  auto wideAlongX = defaultR;
  wideAlongX.measurementNoiseCov = test::diagonalMeasurementNoise(25.0, 0.2, 0.2);
  auto wideAlongY = defaultR;
  wideAlongY.measurementNoiseCov = test::diagonalMeasurementNoise(0.2, 25.0, 0.2);

  EXPECT_FALSE(isGated(track, defaultR));
  EXPECT_TRUE(isGated(track, wideAlongX));
  EXPECT_FALSE(isGated(track, wideAlongY)) << "R must act along its own axes, not inflate the gate isotropically";
  EXPECT_NEAR(calculatePositionMahalanobisSquaredDistance(wideAlongX, track),
              9.0 / (track.predictedStateMeasurementCov(MeasurementIndex::X, MeasurementIndex::X) + 25.0),
              1e-9);
}

TEST(ObjectMatchingTest, PositionMahalanobisGateWithMeasurementNoiseKeepsRadiusCeiling)
{
  const auto track = predictedStaticTrack();
  auto farButVague = makeDetection(12.0, 0.0, 0.0, 0.5, 0.5, 0.5);
  farButVague.measurementNoiseCov = test::diagonalMeasurementNoise(1000.0, 0.2, 0.2);

  EXPECT_TRUE(isGated(track, farButVague, 20.0));
  EXPECT_FALSE(isGated(track, farButVague, 10.0)) << "max_radius_m must still cap a wide R";
}

} // namespace
