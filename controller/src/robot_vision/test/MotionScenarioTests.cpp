// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <cmath>
#include <numbers>

#include <gtest/gtest.h>

#include "support/Scenario.hpp"

namespace {

using namespace rv::tracking::test;

} // namespace

TEST(ScenarioSupportTest, TrajectoryKinematics)
{
  // One full circle at 2 m/s ends where it started.
  const double turnRate = std::numbers::pi / 5.0;
  const auto circle = Trajectory(0.0, 0.0, 0.0, 2.0).turn(turnRate, 10.0).sample(10.0);
  ASSERT_EQ(circle.size(), 101U);
  EXPECT_NEAR(circle.back().t, 10.0, 1e-9);
  EXPECT_NEAR(circle.back().x, 0.0, 1e-6);
  EXPECT_NEAR(circle.back().y, 0.0, 1e-6);
  EXPECT_NEAR(circle.back().heading, 2.0 * std::numbers::pi, 1e-9);
  const double radius = 2.0 / turnRate;
  EXPECT_NEAR(std::hypot(circle[25].x, circle[25].y - radius), radius, 1e-6);

  // Braking at 10 m/s^2 from 5 m/s stops after 0.5 s and 1.25 m, then stays put.
  const auto braking = Trajectory(0.0, 0.0, 0.0, 5.0).accelerate(-10.0, 1.0).sample(10.0);
  EXPECT_DOUBLE_EQ(braking.back().speed, 0.0);
  EXPECT_NEAR(braking.back().x, 1.25, 1e-3);
  EXPECT_EQ(between(braking, 0.5, 1.0).size(), 5U);
}
