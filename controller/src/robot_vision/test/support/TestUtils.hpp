// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <chrono>
#include <string>

#include <rv/tracking/TrackedObject.hpp>

namespace rv::tracking::test {

inline std::chrono::system_clock::time_point atMs(int milliseconds)
{
  return std::chrono::system_clock::time_point(std::chrono::milliseconds(milliseconds));
}

inline TrackedObject
makeBox(double x, double y, double z, double length, double width, double height, const std::string &cameraId = {})
{
  TrackedObject object;
  object.x = x;
  object.y = y;
  object.z = z;
  object.length = length;
  object.width = width;
  object.height = height;
  if (!cameraId.empty())
  {
    object.attributes["camera_id"] = cameraId;
  }
  return object;
}

} // namespace rv::tracking::test
