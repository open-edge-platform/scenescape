// Copyright 2018 The Apollo Authors. All Rights Reserved.
// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#include "rv/apollo/multi_hm_bipartite_graph_matcher.hpp"
#include "rv/apollo/gated_hungarian_bigraph_matcher.hpp"

namespace apollo {
namespace perception {
namespace lidar {

MultiHmBipartiteGraphMatcher::MultiHmBipartiteGraphMatcher()
{
  cost_matrix_ = optimizer_.mutable_global_costs();
}

MultiHmBipartiteGraphMatcher::~MultiHmBipartiteGraphMatcher()
{
  cost_matrix_ = nullptr;
}

void MultiHmBipartiteGraphMatcher::Match(const BipartiteGraphMatcherOptions &options,
                                         std::vector<NodeNodePair> *assignments,
                                         std::vector<size_t> *unassigned_rows,
                                         std::vector<size_t> *unassigned_cols)
{
  common::GatedHungarianMatcher<double>::OptimizeFlag opt_flag
    = common::GatedHungarianMatcher<double>::OptimizeFlag::OPTMIN;
  optimizer_.Match(options.cost_thresh, options.bound_value, opt_flag, assignments, unassigned_rows, unassigned_cols);
}

} // namespace lidar
} // namespace perception
} // namespace apollo
