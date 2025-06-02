/*
 * ----------------- BEGIN LICENSE BLOCK ---------------------------------
 *
 * INTEL CONFIDENTIAL
 *
 * Copyright (c) 2019-2023 Intel Corporation
 *
 * This software and the related documents are Intel copyrighted materials, and
 * your use of them is governed by the express license under which they were
 * provided to you (License). Unless the License provides otherwise, you may not
 * use, modify, copy, publish, distribute, disclose or transmit this software or
 * the related documents without Intel's prior written permission.
 *
 * This software and the related documents are provided as is, with no express or
 * implied warranties, other than those that are expressly stated in the License.
 *
 * ----------------- END LICENSE BLOCK -----------------------------------
 */
#include "rv/tracking/Classification.hpp"

namespace rv {
namespace tracking {

namespace classification {
  Classification combine(const Classification & classificationA, const Classification & classificationB)
  {
    if (classificationA.size() != classificationB.size())
    {
      throw std::runtime_error("The classification sizes are different");
    }

    // If classification probabilities are well defined these terms should be zero
    double unknownA = rv::clamp<double>(1.0 - classificationA.sum(), 0., 1.0);
    double unknownB = rv::clamp<double>(1.0 - classificationB.sum(), 0., 1.0);

    auto elementCombination = classificationA.array() * classificationB.array();

    return ((elementCombination) / (elementCombination.sum() + unknownA * unknownB + 1e-6)).matrix();
  }


  double distance(const Classification & classificationA, const Classification & classificationB)
  {
    if (classificationA.size() != classificationB.size())
    {
      throw std::runtime_error("The vectors should be of the same size");
    }

    Classification residual = (classificationA - classificationB);

    return std::sqrt(0.5 * residual.transpose() * residual);
  }


  double similarity(const Classification & classificationA, const Classification & classificationB)
  {
    return 1.0 - distance(classificationA, classificationB);
  }
} // enf of namespace classification

  Classification ClassificationData::classification(const std::string & className, const double probability) const
  {
    std::size_t j = classIndex(className);
    auto unknown = rv::clamp(1.0 - probability, 0.0, 1.0);
    Classification probabilities = Classification::Constant(classes.size(), unknown / std::max(static_cast<double>(classes.size() - 1), 1.0));
    probabilities(j) = probability;
    return probabilities;
  }

  void ClassificationData::setClasses(std::vector<std::string> &classes_)
  {
    classes = classes_;
  }

  Classification ClassificationData::uniformPrior(double basePrior)
  {
    return Classification::Constant(classes.size(), basePrior);
  }

  Classification ClassificationData::prior()
  {
    double basePrior = static_cast<double>(classes.size());
    return uniformPrior(1 / basePrior);
  }

} // namespace tracking
} // namespace rv
