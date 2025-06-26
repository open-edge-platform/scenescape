// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <Eigen/Dense>
#include <algorithm>
#include <string>
#include <vector>
#include <cmath>
#include <tuple>
#include <stdexcept>
#include <rv/Utils.hpp>

namespace rv {
namespace tracking {

using Classification = Eigen::VectorXd;

namespace classification {
  double distance(const Classification & classificationA, const Classification & classificationB);
  Classification combine(const Classification & classificationA, const Classification & classificationB);
  double similarity(const Classification & classificationA, const Classification & classificationB);
}

class ClassificationData
{
public:
  ClassificationData()
  {
    classes = std::vector<std::string>({"unknown"});
  }

  ClassificationData(std::vector<std::string> classes_) :
  classes(classes_)
  {
    if (classes_.empty())
    {
      throw std::runtime_error("The classes vector is empty");
    }
  }

  inline std::size_t classIndex(std::string class_) const
  {
    auto it = std::find(classes.cbegin(), classes.cend(), class_);

    if (it == classes.end())
    {
      throw std::runtime_error("The class is not part of this classification.");
    }
    else
    {
      return std::distance(classes.cbegin(), it);
    }
  }

  inline std::string getClass(const Classification & classification) const
  {
    if (classes.size() != classification.size())
    {
      throw std::runtime_error("Invalid classification probability size");
    }

    Eigen::Index maxIndex;
    classification.maxCoeff(&maxIndex);
    return classes[maxIndex];
  }

  inline std::vector<std::string> getClasses() const
  {
    return classes;
  }

  void setClasses(std::vector<std::string> &classes_);

  Classification classification(const std::string & className, const double probability) const;

  Classification uniformPrior(double basePrior);
  Classification prior();

private:
  std::vector<std::string> classes;
};

} // namespace tracking
} // namespace rv
