// Copyright 2018 The Apollo Authors. All Rights Reserved.
// SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <Eigen/Core>
#include <string>
#include <utility>
#include <vector>

#include "rv/apollo/secure_matrix.hpp"

namespace apollo {
namespace perception {
namespace lidar {

struct BipartiteGraphMatcherInitOptions
{
};

struct BipartiteGraphMatcherOptions
{
  double cost_thresh = 4.0f;
  double bound_value = 100.0f;
};

class BaseBipartiteGraphMatcher
{
public:
  typedef std::pair<size_t, size_t> NodeNodePair;
  BaseBipartiteGraphMatcher() = default;
  virtual ~BaseBipartiteGraphMatcher() = default;

  // @params[OUT] assignments: matched pair of objects & tracks
  // @params[OUT] unassigned_rows: unmatched rows
  // @params[OUT] unassigned_cols: unmatched cols
  // @return nothing
  virtual void Match(const BipartiteGraphMatcherOptions &options,
                     std::vector<NodeNodePair> *assignments,
                     std::vector<size_t> *unassigned_rows,
                     std::vector<size_t> *unassigned_cols)
    = 0;
  virtual std::string Name() const = 0;

  virtual common::SecureMat<double> *cost_matrix()
  {
    return cost_matrix_;
  }

protected:
  common::SecureMat<double> *cost_matrix_ = nullptr;
  double max_match_distance_ = 0.0f;

private:
  BaseBipartiteGraphMatcher(const BaseBipartiteGraphMatcher &) = delete;
  BaseBipartiteGraphMatcher &operator=(const BaseBipartiteGraphMatcher &) = delete;
}; // class BaseBipartiteGraphMatcher

} // namespace lidar
} // namespace perception
} // namespace apollo
