// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <cmath>

#include <gtest/gtest.h>
#include <opencv2/core.hpp>

#include <rv/tracking/OrientationAttributes.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "support/TestUtils.hpp"

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
