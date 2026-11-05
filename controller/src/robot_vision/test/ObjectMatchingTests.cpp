// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <chrono>
#include <cmath>
#include <utility>
#include <vector>

#include <gtest/gtest.h>
#include <opencv2/core.hpp>

#include <rv/Utils.hpp>
#include <rv/tracking/ObjectMatching.hpp>
#include <rv/tracking/OrientationAttributes.hpp>
#include <rv/tracking/TrackManager.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "support/TestUtils.hpp"

TEST(ObjectMatchingTest, Chi2ThresholdMatchesExpectedQuantile)
{
  EXPECT_NEAR(rv::chi2Threshold(0.99, 2), 9.21034, 1e-3);
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

  const double chi2_gate = rv::chi2Threshold(0.99, 2);
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

// Defined in ObjectMatching.cpp, not declared in its header.
namespace rv::tracking {
double calculateMahalanobisDistance(const TrackedObject &measurement, const TrackedObject &track);
} // namespace rv::tracking

namespace {

using namespace rv::tracking;
using test::makeDetection;

constexpr int kYaw = TrackedObject::MeasurementSize - 1;
constexpr int kWithoutYaw = TrackedObject::MeasurementSize - 1;

// Symmetric positive definite S with strong yaw↔position coupling so zeroing ν_yaw ≠ marginalizing yaw.
TrackedObject makeTrack()
{
  TrackedObject track;
  track.predictedMeasurementMean = TrackedObject::MeasurementVector(2.5, -1.0, 0.4, 4.5, 1.8, 1.5, 0.2);
  TrackedObject::MeasurementMatrix covariance = TrackedObject::MeasurementMatrix::zeros();
  for (int i = 0; i < TrackedObject::MeasurementSize; ++i)
  {
    covariance(i, i) = 1.0;
  }
  // Correlate yaw with x and y; diagonally dominant so S stays SPD.
  covariance(0, kYaw) = covariance(kYaw, 0) = 0.6;
  covariance(1, kYaw) = covariance(kYaw, 1) = 0.5;
  track.predictedMeasurementCov = covariance;
  cv::Mat inverse;
  cv::invert(cv::Mat(covariance), inverse, cv::DECOMP_SVD);
  track.predictedMeasurementCovInv = inverse;
  return track;
}

TrackedObject makeMeasurement()
{
  auto measurement = makeDetection(3.0, -2.0, 0.5, 4.6, 1.9, 1.4);
  measurement.yaw = 1.2;
  return measurement;
}

// 0.5 * sqrt(d' * W * d): full S^-1 when useYaw, else inv of the leading 6x6 of S (UKF marginalization).
double expectedDistance(const TrackedObject &measurement, const TrackedObject &track, bool useYaw)
{
  TrackedObject::MeasurementVector innovation
    = measurement.measurementVector() - track.predictedMeasurementMean;
  if (useYaw)
  {
    return 0.5 * std::sqrt(innovation.dot(track.predictedMeasurementCovInv * innovation));
  }

  cv::Matx<double, kWithoutYaw, 1> reducedInnovation;
  cv::Matx<double, kWithoutYaw, kWithoutYaw> reducedCovariance;
  for (int i = 0; i < kWithoutYaw; ++i)
  {
    reducedInnovation(i) = innovation(i);
    for (int j = 0; j < kWithoutYaw; ++j)
    {
      reducedCovariance(i, j) = track.predictedMeasurementCov(i, j);
    }
  }
  cv::Matx<double, kWithoutYaw, kWithoutYaw> reducedCovarianceInv;
  cv::invert(reducedCovariance, reducedCovarianceInv, cv::DECOMP_SVD);
  return 0.5 * std::sqrt(reducedInnovation.dot(reducedCovarianceInv * reducedInnovation));
}

// Old gate: zero ν_yaw then use full S^-1 (wrong when yaw is correlated).
double zeroedYawDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  TrackedObject::MeasurementVector innovation
    = measurement.measurementVector() - track.predictedMeasurementMean;
  innovation(kYaw) = 0.0;
  return 0.5 * std::sqrt(innovation.dot(track.predictedMeasurementCovInv * innovation));
}

TEST(ObjectMatchingTest, MahalanobisDistanceUsesInverseCovarianceOfPredictedMeasurement)
{
  const auto track = makeTrack();
  const auto measurement = makeMeasurement();

  const double distance = calculateMahalanobisDistance(measurement, track);

  EXPECT_NEAR(distance, expectedDistance(measurement, track, false), 1e-12);
  EXPECT_GT(distance, 0.5);
  // Zeroing ν_yaw is not the same as marginalizing yaw when S couples yaw to position/size.
  EXPECT_GT(std::abs(distance - zeroedYawDistance(measurement, track)), 1e-3);

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

} // namespace
