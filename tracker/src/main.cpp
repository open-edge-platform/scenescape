// SPDX-FileCopyrightText: 2025-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Simple tracker hello world using RobotVision

#include <iostream>

#include "rv/tracking/TrackedObject.hpp"

int main()
{
  rv::tracking::TrackedObject obj;
  std::cout << "Hello from tracker with RobotVision integrated. Initial object id = "
            << obj.id << "\n";
  return 0;
}
