// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#include <functional>
#include <numeric>
#include <opencv2/core.hpp>

#include "rv/tracking/ObjectMatching.hpp"
#include "rv/apollo/multi_hm_bipartite_graph_matcher.hpp"
#include "rv/apollo/secure_matrix.hpp"
#include "rv/tracking/Classification.hpp"

#include <iostream>

namespace rv {
namespace tracking {

constexpr double kDefaultClassBoundValue = 1000.;

double calculateMulticlassScaledDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  auto conflict = rv::tracking::classification::distance(measurement.classification, track.classification);

  double distance = sqrt(pow(measurement.x - track.x, 2) + pow(measurement.y - track.y, 2));

  return distance * (1.0 + conflict);
}

double calculateEuclideanDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  return sqrt(pow(measurement.x - track.x, 2) + pow(measurement.y - track.y, 2));
}

double calculateMahalanobisDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  cv::Mat innovation = measurement.measurementVector() - (track.predictedMeasurementMean);

  // ignore yaw, 2D detectors cannot detect orientation
  innovation.at<double>(6, 0) = 0.;

  cv::Mat mahalanobisDistance = innovation.t() * (track.predictedMeasurementCovInv) * innovation;

  return 0.5 * std::sqrt(mahalanobisDistance.at<double>(0, 0));
}

double calculateCompundDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  double euclideanDist = calculateMulticlassScaledDistance(measurement, track);
  double mahalanobisDist = calculateMahalanobisDistance(measurement, track);

  return 0.5 * euclideanDist + 0.5 * mahalanobisDist;
}

void match(const std::vector<TrackedObject> &tracks,
                          const std::vector<TrackedObject> &measurements,
                          std::vector<std::pair<size_t, size_t>> &assignments,
                          std::vector<size_t> &unassignedTracks,
                          std::vector<size_t> &unassignedMeasurements,
                          const DistanceType &distanceType, double threshold)
{
  apollo::perception::lidar::MultiHmBipartiteGraphMatcher matcher;

  matcher.cost_matrix()->Reserve(tracks.size(), measurements.size());

  assignments.clear();
  unassignedTracks.clear();
  unassignedMeasurements.clear();
  if (measurements.empty() || tracks.empty())
  {
    unassignedMeasurements.resize(measurements.size());
    unassignedTracks.resize(tracks.size());

    std::iota(unassignedMeasurements.begin(), unassignedMeasurements.end(), 0);
    std::iota(unassignedTracks.begin(), unassignedTracks.end(), 0);
    return;
  }

  apollo::perception::lidar::BipartiteGraphMatcherOptions matcherOptions;
  std::function<double(const TrackedObject &, const TrackedObject &)> distanceFunction;
  switch (distanceType)
  {
    case DistanceType::MCEMahalanobis:
      distanceFunction = std::bind(&calculateCompundDistance, std::placeholders::_1, std::placeholders::_2);
      matcherOptions.cost_thresh = threshold;
      matcherOptions.bound_value = kDefaultClassBoundValue;
      break;
    case DistanceType::Mahalanobis:
      distanceFunction = std::bind(&calculateMahalanobisDistance, std::placeholders::_1, std::placeholders::_2);
      matcherOptions.cost_thresh = threshold;
      matcherOptions.bound_value = kDefaultClassBoundValue;
      break;
    case DistanceType::MultiClassEuclidean:
      distanceFunction = std::bind(&calculateMulticlassScaledDistance, std::placeholders::_1, std::placeholders::_2);
      matcherOptions.cost_thresh = threshold;
      matcherOptions.bound_value = kDefaultClassBoundValue;
      break;
    case DistanceType::Euclidean:
    default:
      distanceFunction = std::bind(&calculateEuclideanDistance, std::placeholders::_1, std::placeholders::_2);
      matcherOptions.cost_thresh = threshold;
      matcherOptions.bound_value = kDefaultClassBoundValue;
      break;
  }

  apollo::perception::common::SecureMat<double> *costMatrix = matcher.cost_matrix();
  costMatrix->Resize(tracks.size(), measurements.size());

  for (size_t i = 0; i < tracks.size(); ++i)
  {
    for (size_t j = 0; j < measurements.size(); ++j)
    {
      (*costMatrix)(i, j) = distanceFunction(measurements[j], tracks[i]);
    }
  }

  matcher.Match(matcherOptions, &assignments, &unassignedTracks, &unassignedMeasurements);
}

} // namespace tracking
} // namespace rv
