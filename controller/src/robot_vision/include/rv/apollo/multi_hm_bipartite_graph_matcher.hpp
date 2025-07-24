// Copyright 2018 The Apollo Authors. All Rights Reserved.
// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <string>
#include <vector>

#include "rv/apollo/base_bipartite_graph_matcher.hpp"
#include "rv/apollo/gated_hungarian_bigraph_matcher.hpp"
#include "rv/apollo/secure_matrix.hpp"

namespace apollo {
namespace perception {
namespace lidar {

class MultiHmBipartiteGraphMatcher : public BaseBipartiteGraphMatcher
{
public:
  MultiHmBipartiteGraphMatcher();
  ~MultiHmBipartiteGraphMatcher();

  // @brief: match interface
  // @params [in]: match params
  // @params [out]: matched pair of objects & tracks
  // @params [out]: unmatched rows
  // @params [out]: unmatched cols
  void Match(const BipartiteGraphMatcherOptions &options,
             std::vector<NodeNodePair> *assignments,
             std::vector<size_t> *unassigned_rows,
             std::vector<size_t> *unassigned_cols);
  std::string Name() const
  {
    return "MultiHmBipartiteGraphMatcher";
  }

protected:
  common::GatedHungarianMatcher<double> optimizer_;
}; // class MultiHmObjectMatcher

} // namespace lidar
} // namespace perception
} // namespace apollo
