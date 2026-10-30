// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <gtest/gtest.h>

#include <rv/tracking/TrackedObject.hpp>

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
