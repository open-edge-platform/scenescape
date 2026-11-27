// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

#include <gtest/gtest.h>
#include <opencv2/core.hpp>

#include <rv/tracking/TrackedObject.hpp>

namespace {

using rv::tracking::TrackedObject;
using rv::tracking::validatedMeasurementNoiseCov;
using rv::tracking::validMeasurementNoiseCov;

TrackedObject::MeasurementMatrix diagonalNoise(double variance = 0.2)
{
  return TrackedObject::MeasurementMatrix::eye() * variance;
}

// The std::invalid_argument message of validatedMeasurementNoiseCov, empty when it accepts noise.
std::string rejectionMessage(const TrackedObject::MeasurementMatrix &noise)
{
  try
  {
    (void)validatedMeasurementNoiseCov(noise);
    return {};
  }
  catch (const std::invalid_argument &error)
  {
    return error.what();
  }
}

} // namespace

TEST(TrackedObjectTest, IsDynamicIncludesVerticalVelocityOnlyWhenZMeasured)
{
  rv::tracking::TrackedObject obj;
  obj.vx = 0.0;
  obj.vy = 0.0;
  obj.vz = 0.0;
  obj.z_measured = false;
  EXPECT_FALSE(obj.isDynamic());

  obj.vz = 1.1; // filter vz alone must not age planar tracks on the dynamic coast
  EXPECT_FALSE(obj.isDynamic());

  obj.z_measured = true;
  EXPECT_TRUE(obj.isDynamic()) << "measured-z tracks count vz toward the dynamic threshold";

  obj.vx = 0.5;
  obj.vy = 0.0;
  obj.vz = 0.5; // 0.25 + 0.25 = 0.5
  EXPECT_FALSE(obj.isDynamic());

  obj.z_measured = false;
  obj.vx = 1.1;
  obj.vz = 0.0;
  EXPECT_TRUE(obj.isDynamic()) << "horizontal speed still marks planar tracks dynamic";
}

TEST(TrackedObjectTest, ValidatedMeasurementNoiseAcceptsSymmetricPositiveDefinite)
{
  auto noise = diagonalNoise(0.2);
  noise(0, 1) = noise(1, 0) = 0.05;
  const auto accepted = validatedMeasurementNoiseCov(noise);
  EXPECT_NEAR(accepted(0, 1), 0.05, 1e-15);
  EXPECT_NEAR(accepted(1, 0), 0.05, 1e-15);
  const auto valid = validMeasurementNoiseCov(noise);
  ASSERT_TRUE(valid);
  EXPECT_EQ(cv::norm(*valid, accepted, cv::NORM_INF), 0.0);
}

TEST(TrackedObjectTest, ValidatedMeasurementNoiseSymmetrizesNearSymmetric)
{
  auto noise = diagonalNoise(0.2);
  noise(0, 1) = 0.05;
  noise(1, 0) = 0.0;
  const auto accepted = validatedMeasurementNoiseCov(noise);
  EXPECT_NEAR(accepted(0, 1), 0.025, 1e-15);
  EXPECT_NEAR(accepted(1, 0), 0.025, 1e-15);
  const auto valid = validMeasurementNoiseCov(noise);
  ASSERT_TRUE(valid);
  EXPECT_EQ((*valid)(0, 1), (*valid)(1, 0));
}

TEST(TrackedObjectTest, ValidMeasurementNoiseDoesNotDependOnUnits)
{
  // No absolute pivot floor: a sharp R in m^2 (OpenCV's Cholesky rejects pivots below DBL_EPSILON) and a broad one are
  // both positive definite.
  for (const double variance : {1e-20, 1e-17, 1.0, 1e20})
  {
    SCOPED_TRACE(variance);
    EXPECT_TRUE(validMeasurementNoiseCov(diagonalNoise(variance)));
  }
}

TEST(TrackedObjectTest, ValidatedMeasurementNoiseRejectsInvalidMatrices)
{
  struct Case
  {
    const char *name;
    TrackedObject::MeasurementMatrix noise;
  };
  const auto nan = std::numeric_limits<double>::quiet_NaN();
  const auto inf = std::numeric_limits<double>::infinity();
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
         Case{"indefinite after symmetrization",
              [] {
                auto noise = diagonalNoise(0.2);
                noise(0, 1) = 5.0;
                noise(1, 0) = 0.0;
                return noise;
              }()},
         Case{"symmetric part overflows",
              [] {
                auto noise = diagonalNoise(0.2);
                noise(0, 0) = std::numeric_limits<double>::max();
                return noise;
              }()},
         Case{"nan",
              [nan] {
                auto noise = diagonalNoise(0.2);
                noise(0, 0) = nan;
                return noise;
              }()},
         Case{"infinite off-diagonal",
              [inf] {
                auto noise = diagonalNoise(0.2);
                noise(0, 1) = inf;
                return noise;
              }()}})
  {
    SCOPED_TRACE(testCase.name);
    EXPECT_FALSE(validMeasurementNoiseCov(testCase.noise));
    EXPECT_THROW(validatedMeasurementNoiseCov(testCase.noise), std::invalid_argument);
  }
}

TEST(TrackedObjectTest, ValidatedMeasurementNoiseNamesTheReason)
{
  auto nonFinite = diagonalNoise(0.2);
  nonFinite(2, 2) = std::numeric_limits<double>::quiet_NaN();
  EXPECT_EQ(rejectionMessage(nonFinite), "measurement_noise_covariance must be finite");
  EXPECT_EQ(rejectionMessage(diagonalNoise(-0.2)), "measurement_noise_covariance must be positive definite");
  EXPECT_EQ(rejectionMessage(diagonalNoise(0.2)), "");
}

// Corner cases of the 73bd4a975 check (finite, symmetrized, positive definite), so asymmetric, singular or indefinite R
// cannot skew association or the Kalman gain.

TEST(TrackedObjectTest, ValidMeasurementNoiseRejectsEveryNonFiniteEntry)
{
  for (const double bad : {std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity(),
                           -std::numeric_limits<double>::infinity()})
  {
    for (int index = 0; index < TrackedObject::MeasurementSize * TrackedObject::MeasurementSize; ++index)
    {
      auto noise = diagonalNoise(0.2);
      noise.val[index] = bad; // one triangle only for off-diagonal entries
      SCOPED_TRACE(::testing::Message() << "entry " << index << " = " << bad);
      EXPECT_FALSE(validMeasurementNoiseCov(noise));
    }
  }
}

TEST(TrackedObjectTest, ValidMeasurementNoiseChecksEveryPivot)
{
  // A zero or negative variance, or a singular or indefinite 2x2 block, at any position of the 7x7 is rejected, so the
  // check covers the size and yaw rows, not only the position block. 0.25 is exact, so the singular block is exactly
  // singular.
  constexpr int n = TrackedObject::MeasurementSize;
  for (int row = 0; row < n; ++row)
  {
    SCOPED_TRACE(::testing::Message() << "row " << row);
    for (const double variance : {0.0, -0.2, -1e-300})
    {
      auto noise = diagonalNoise(0.2);
      noise(row, row) = variance;
      EXPECT_FALSE(validMeasurementNoiseCov(noise)) << "variance " << variance;
    }
    if (row + 1 < n)
    {
      for (const auto &[covariance, positiveDefinite] : {std::pair{0.2, true}, std::pair{0.25, false},
                                                         std::pair{0.3, false}, std::pair{-0.25, false}})
      {
        auto noise = diagonalNoise(0.25);
        noise(row, row + 1) = noise(row + 1, row) = covariance;
        EXPECT_EQ(validMeasurementNoiseCov(noise).has_value(), positiveDefinite) << "covariance " << covariance;
      }
    }
  }
}

TEST(TrackedObjectTest, ValidMeasurementNoiseRejectsIndefiniteMatrixWithPositiveLeadingMinors)
{
  // Every variance and every 2x2 principal minor is positive, but x, y and z cannot be pairwise correlated by -0.6:
  // det = 1 - 3 * 0.36 - 2 * 0.216 < 0.
  auto noise = diagonalNoise(1.0);
  noise(0, 1) = noise(1, 0) = noise(0, 2) = noise(2, 0) = noise(1, 2) = noise(2, 1) = -0.6;
  EXPECT_FALSE(validMeasurementNoiseCov(noise));
  noise(1, 2) = noise(2, 1) = 0.0;
  EXPECT_TRUE(validMeasurementNoiseCov(noise));
}

TEST(TrackedObjectTest, ValidMeasurementNoiseDropsTheSkewPart)
{
  // An antisymmetric part changes neither x^T R x nor validity: it is removed, not trusted.
  auto noise = diagonalNoise(0.2);
  noise(0, 1) = 5.0;
  noise(1, 0) = -5.0;
  noise(3, 6) = -1.0;
  noise(6, 3) = 1.0;
  const auto valid = validMeasurementNoiseCov(noise);
  ASSERT_TRUE(valid);
  EXPECT_EQ(cv::norm(*valid, diagonalNoise(0.2), cv::NORM_INF), 0.0);
}

TEST(TrackedObjectTest, ValidMeasurementNoiseAgreesWithTheEigenvalueCheck)
{
  // The check of 73bd4a975 (smallest eigenvalue of the symmetric part > 0) as the oracle, on random matrices whose
  // smallest eigenvalue is placed on either side of 0, from 1e-10 to 1 relative to the largest, at scales 1e-6 to 1e6.
  // Closer to 0 both are rounding noise (they disagree only below about 1e-15 relative).
  constexpr int n = TrackedObject::MeasurementSize;
  cv::RNG rng(20261117);
  int accepted = 0;
  constexpr int kCases = 4000;
  for (int testCase = 0; testCase < kCases; ++testCase)
  {
    TrackedObject::MeasurementMatrix factor;
    for (double &value : factor.val)
    {
      value = rng.uniform(-1.0, 1.0);
    }
    TrackedObject::MeasurementMatrix symmetric = factor * factor.t();
    cv::Mat eigenvalues;
    cv::eigen(symmetric, eigenvalues);
    double smallest = 0.0;
    double largest = 0.0;
    cv::minMaxLoc(eigenvalues, &smallest, &largest);
    const double sign = rng.uniform(0, 2) == 0 ? -1.0 : 1.0;
    const double margin = sign * std::pow(10.0, rng.uniform(-10.0, 0.0)) * largest;
    const double scale = std::pow(10.0, rng.uniform(-6.0, 6.0));
    symmetric = (symmetric + TrackedObject::MeasurementMatrix::eye() * (margin - smallest)) * scale;
    symmetric = 0.5 * (symmetric + symmetric.t());

    // An asymmetric input with this symmetric part.
    TrackedObject::MeasurementMatrix noise = symmetric;
    for (int row = 0; row < n; ++row)
    {
      for (int col = row + 1; col < n; ++col)
      {
        const double skew = rng.uniform(-1.0, 1.0) * scale;
        noise(row, col) += skew;
        noise(col, row) -= skew;
      }
    }

    const TrackedObject::MeasurementMatrix expectedSymmetric = 0.5 * (noise + noise.t());
    cv::eigen(expectedSymmetric, eigenvalues);
    cv::minMaxLoc(eigenvalues, &smallest);
    const bool oracle = smallest > 0.0;
    const auto valid = validMeasurementNoiseCov(noise);
    ASSERT_EQ(valid.has_value(), oracle) << "case " << testCase << ", smallest eigenvalue " << smallest << ", margin "
                                         << margin * scale;
    if (valid)
    {
      // Bit-identical to what 73bd4a975 stored.
      ASSERT_EQ(cv::norm(*valid, expectedSymmetric, cv::NORM_INF), 0.0) << "case " << testCase;
      ++accepted;
    }
  }
  // Both sides of the boundary are exercised.
  EXPECT_GT(accepted, kCases / 4);
  EXPECT_LT(accepted, 3 * kCases / 4);
}

TEST(TrackedObjectTest, ClearInvalidMeasurementNoiseKeepsValidRAndClearsInvalidRWithoutThrowing)
{
  using rv::tracking::clearInvalidMeasurementNoiseCov;

  TrackedObject unset;
  clearInvalidMeasurementNoiseCov(unset);
  EXPECT_FALSE(unset.measurementNoiseCov);

  TrackedObject object;
  auto noise = diagonalNoise(0.2);
  noise(0, 1) = 0.04;
  noise(1, 0) = 0.0;
  object.measurementNoiseCov = noise;
  clearInvalidMeasurementNoiseCov(object);
  ASSERT_TRUE(object.measurementNoiseCov);
  EXPECT_EQ((*object.measurementNoiseCov)(0, 1), 0.02);
  EXPECT_EQ((*object.measurementNoiseCov)(1, 0), 0.02);

  for (const auto &invalid : {TrackedObject::MeasurementMatrix::zeros(), diagonalNoise(-0.2)})
  {
    object.measurementNoiseCov = invalid;
    clearInvalidMeasurementNoiseCov(object);
    EXPECT_FALSE(object.measurementNoiseCov);
  }
  static_assert(noexcept(clearInvalidMeasurementNoiseCov(object)));
}
