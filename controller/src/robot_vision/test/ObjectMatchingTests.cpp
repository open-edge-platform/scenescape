// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <array>
#include <cmath>

#include <gtest/gtest.h>

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
using Vector = std::array<double, TrackedObject::MeasurementSize>;

constexpr int kYaw = 6;

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

} // namespace
