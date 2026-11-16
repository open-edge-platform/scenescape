// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <cmath>
#include <limits>
#include <stdexcept>

#include <gtest/gtest.h>
#include <opencv2/core.hpp>

#include <rv/tracking/TrackedObject.hpp>

namespace {

using rv::tracking::TrackedObject;
using rv::tracking::ensureValidMeasurementNoiseCov;
using rv::tracking::validatedMeasurementNoiseCov;

TrackedObject::MeasurementMatrix diagonalNoise(double variance = 0.2)
{
  return TrackedObject::MeasurementMatrix::eye() * variance;
}

bool isValidMeasurementNoiseCov(const TrackedObject::MeasurementMatrix &noise)
{
  try
  {
    (void)validatedMeasurementNoiseCov(noise);
    return true;
  }
  catch (const std::invalid_argument &)
  {
    return false;
  }
}

} // namespace

TEST(TrackedObjectTest, IsDynamicIncludesVerticalVelocity)
{
  rv::tracking::TrackedObject obj;
  obj.vx = 0.0;
  obj.vy = 0.0;
  obj.vz = 0.0;
  EXPECT_FALSE(obj.isDynamic());

  obj.vz = 1.1; // vz^2 > 1 alone
  EXPECT_TRUE(obj.isDynamic());

  obj.vx = 0.5;
  obj.vy = 0.0;
  obj.vz = 0.5; // 0.25 + 0.25 = 0.5
  EXPECT_FALSE(obj.isDynamic());
}

TEST(TrackedObjectTest, ValidatedMeasurementNoiseAcceptsSymmetricPositiveDefinite)
{
  auto noise = diagonalNoise(0.2);
  noise(0, 1) = noise(1, 0) = 0.05;
  const auto accepted = validatedMeasurementNoiseCov(noise);
  EXPECT_NEAR(accepted(0, 1), 0.05, 1e-15);
  EXPECT_NEAR(accepted(1, 0), 0.05, 1e-15);
  EXPECT_TRUE(isValidMeasurementNoiseCov(noise));
}

TEST(TrackedObjectTest, ValidatedMeasurementNoiseSymmetrizesNearSymmetric)
{
  auto noise = diagonalNoise(0.2);
  noise(0, 1) = 0.05;
  noise(1, 0) = 0.0;
  const auto accepted = validatedMeasurementNoiseCov(noise);
  EXPECT_NEAR(accepted(0, 1), 0.025, 1e-15);
  EXPECT_NEAR(accepted(1, 0), 0.025, 1e-15);
}

TEST(TrackedObjectTest, ValidatedMeasurementNoiseRejectsInvalidMatrices)
{
  struct Case
  {
    const char *name;
    TrackedObject::MeasurementMatrix noise;
  };
  const auto nan = std::numeric_limits<double>::quiet_NaN();
  for (const auto &testCase : {
         Case{"zero", TrackedObject::MeasurementMatrix::zeros()},
         Case{"singular", TrackedObject::MeasurementMatrix::eye() * 0.0},
         Case{"negative definite", TrackedObject::MeasurementMatrix::eye() * -0.2},
         Case{"indefinite",
              [] {
                auto noise = diagonalNoise(0.2);
                noise(0, 0) = 1.0;
                noise(1, 1) = 1.0;
                noise(0, 1) = noise(1, 0) = 2.0;
                return noise;
              }()},
         Case{"non-finite",
              [nan] {
                auto noise = diagonalNoise(0.2);
                noise(0, 0) = nan;
                return noise;
              }()}})
  {
    SCOPED_TRACE(testCase.name);
    EXPECT_FALSE(isValidMeasurementNoiseCov(testCase.noise));
    EXPECT_THROW(validatedMeasurementNoiseCov(testCase.noise), std::invalid_argument);
  }
}

TEST(TrackedObjectTest, EnsureValidMeasurementNoiseLeavesUnsetAndSymmetrizesSet)
{
  TrackedObject unset;
  ensureValidMeasurementNoiseCov(unset);
  EXPECT_FALSE(unset.measurementNoiseCov);

  TrackedObject object;
  auto noise = diagonalNoise(0.2);
  noise(0, 1) = 0.04;
  noise(1, 0) = 0.0;
  object.measurementNoiseCov = noise;
  ensureValidMeasurementNoiseCov(object);
  ASSERT_TRUE(object.measurementNoiseCov);
  EXPECT_NEAR((*object.measurementNoiseCov)(0, 1), 0.02, 1e-15);
  EXPECT_NEAR((*object.measurementNoiseCov)(1, 0), 0.02, 1e-15);

  object.measurementNoiseCov = TrackedObject::MeasurementMatrix::zeros();
  EXPECT_THROW(ensureValidMeasurementNoiseCov(object), std::invalid_argument);
}

TEST(TrackedObjectTest, ClearInvalidMeasurementNoiseDropsBadRWithoutThrowing)
{
  using rv::tracking::clearInvalidMeasurementNoiseCov;

  TrackedObject unset;
  clearInvalidMeasurementNoiseCov(unset);
  EXPECT_FALSE(unset.measurementNoiseCov);

  TrackedObject object;
  object.measurementNoiseCov = diagonalNoise(0.2);
  clearInvalidMeasurementNoiseCov(object);
  ASSERT_TRUE(object.measurementNoiseCov);
  EXPECT_NEAR((*object.measurementNoiseCov)(0, 0), 0.2, 1e-15);

  object.measurementNoiseCov = TrackedObject::MeasurementMatrix::zeros();
  clearInvalidMeasurementNoiseCov(object);
  EXPECT_FALSE(object.measurementNoiseCov);
}
