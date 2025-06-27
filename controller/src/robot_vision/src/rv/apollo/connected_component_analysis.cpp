// Copyright 2018 The Apollo Authors. All Rights Reserved.
// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#include "rv/apollo/connected_component_analysis.hpp"

namespace apollo {
namespace perception {
namespace common {

void ConnectedComponentAnalysis(const std::vector<std::vector<int>> &graph, std::vector<std::vector<int>> *components)
{
  int num_item = static_cast<int>(graph.size());
  std::vector<int> visited;
  visited.resize(num_item, 0);
  std::queue<int> que;
  std::vector<int> component;
  component.reserve(num_item);
  components->clear();

  for (int index = 0; index < num_item; ++index)
  {
    if (visited[index])
    {
      continue;
    }
    component.push_back(index);
    que.push(index);
    visited[index] = 1;
    while (!que.empty())
    {
      int current_id = que.front();
      que.pop();
      for (size_t sub_index = 0; sub_index < graph[current_id].size(); ++sub_index)
      {
        int neighbor_id = graph[current_id][sub_index];
        if (visited[neighbor_id] == 0)
        {
          component.push_back(neighbor_id);
          que.push(neighbor_id);
          visited[neighbor_id] = 1;
        }
      }
    }
    components->push_back(component);
    component.clear();
  }
}

} // namespace common
} // namespace perception
} // namespace apollo
