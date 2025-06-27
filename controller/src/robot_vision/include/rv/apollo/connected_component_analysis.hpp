// Copyright 2018 The Apollo Authors. All Rights Reserved.
// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <cstdlib>
#include <queue>
#include <vector>

namespace apollo {
namespace perception {
namespace common {

/*
* @brief: bfs based connected component analysis
* @params[IN] graph: input graph for connected component analysis
* @params[OUT] components: connected components of input graph
* @return nothing
* */
void ConnectedComponentAnalysis(const std::vector<std::vector<int>> &graph, std::vector<std::vector<int>> *components);

} // namespace common
} // namespace perception
} // namespace apollo
