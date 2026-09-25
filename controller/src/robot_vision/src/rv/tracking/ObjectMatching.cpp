// SPDX-FileCopyrightText: 2019 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <functional>
#include <limits>
#include <numeric>
#include <opencv2/core.hpp>
#include <omp.h>

#include "rv/Utils.hpp"
#include "rv/tracking/ObjectMatching.hpp"
#include "rv/apollo/multi_hm_bipartite_graph_matcher.hpp"
#include "rv/apollo/secure_matrix.hpp"
#include "rv/tracking/Classification.hpp"

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

double calculatePositionMahalanobisSquaredDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  const double pred_x = track.predictedMeasurementMean.at<double>(0, 0);
  const double pred_y = track.predictedMeasurementMean.at<double>(1, 0);
  const double dx = measurement.x - pred_x;
  const double dy = measurement.y - pred_y;

  const double s00 = track.predictedMeasurementCov.at<double>(0, 0);
  const double s01 = track.predictedMeasurementCov.at<double>(0, 1);
  const double s11 = track.predictedMeasurementCov.at<double>(1, 1);

  const double det = s00 * s11 - s01 * s01;
  if (std::abs(det) < 1e-12)
  {
    return kDefaultClassBoundValue;
  }

  const double inv00 = s11 / det;
  const double inv01 = -s01 / det;
  const double inv11 = s00 / det;

  return dx * (inv00 * dx + inv01 * dy) + dy * (inv01 * dx + inv11 * dy);
}

namespace {

/// Per-track constants for PositionMahalanobis cost fill (S^{-1} is fixed for the frame).
struct PositionMahalanobisTrackCache
{
  double pred_x = 0.0;
  double pred_y = 0.0;
  double inv00 = 0.0;
  double inv01 = 0.0;
  double inv11 = 0.0;
  bool valid = false;
};

PositionMahalanobisTrackCache buildPositionMahalanobisTrackCache(const TrackedObject &track)
{
  PositionMahalanobisTrackCache cache;
  cache.pred_x = track.predictedMeasurementMean.at<double>(0, 0);
  cache.pred_y = track.predictedMeasurementMean.at<double>(1, 0);

  const double s00 = track.predictedMeasurementCov.at<double>(0, 0);
  const double s01 = track.predictedMeasurementCov.at<double>(0, 1);
  const double s11 = track.predictedMeasurementCov.at<double>(1, 1);
  const double det = s00 * s11 - s01 * s01;
  if (std::abs(det) < 1e-12)
  {
    return cache;
  }
  cache.inv00 = s11 / det;
  cache.inv01 = -s01 / det;
  cache.inv11 = s00 / det;
  cache.valid = true;
  return cache;
}

double positionMahalanobisCostFromCache(double measurement_x, double measurement_y,
                                        const PositionMahalanobisTrackCache &cache, double max_radius_m)
{
  const double dx = measurement_x - cache.pred_x;
  const double dy = measurement_y - cache.pred_y;
  if (std::hypot(dx, dy) > max_radius_m)
  {
    return kDefaultClassBoundValue;
  }
  if (!cache.valid)
  {
    return kDefaultClassBoundValue;
  }
  return dx * (cache.inv00 * dx + cache.inv01 * dy) + dy * (cache.inv01 * dx + cache.inv11 * dy);
}

} // namespace

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
                          const DistanceType &distanceType, double threshold, double max_radius_m)
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
  matcherOptions.cost_thresh = threshold;
  matcherOptions.bound_value = kDefaultClassBoundValue;

  apollo::perception::common::SecureMat<double> *costMatrix = matcher.cost_matrix();
  costMatrix->Resize(tracks.size(), measurements.size());

  if (distanceType == DistanceType::PositionMahalanobis)
  {
    // Invert the 2x2 position covariance once per track, not once per (track, detection).
    std::vector<PositionMahalanobisTrackCache> track_caches(tracks.size());
    for (size_t i = 0; i < tracks.size(); ++i)
    {
      track_caches[i] = buildPositionMahalanobisTrackCache(tracks[i]);
    }

    #pragma omp parallel for collapse(2)
    for (size_t i = 0; i < tracks.size(); ++i)
    {
      for (size_t j = 0; j < measurements.size(); ++j)
      {
        (*costMatrix)(i, j) = positionMahalanobisCostFromCache(
          measurements[j].x, measurements[j].y, track_caches[i], max_radius_m);
      }
    }
  }
  else
  {
    std::function<double(const TrackedObject &, const TrackedObject &)> distanceFunction;
    switch (distanceType)
    {
      case DistanceType::MCEMahalanobis:
        distanceFunction = std::bind(&calculateCompundDistance, std::placeholders::_1, std::placeholders::_2);
        break;
      case DistanceType::Mahalanobis:
        distanceFunction = std::bind(&calculateMahalanobisDistance, std::placeholders::_1, std::placeholders::_2);
        break;
      case DistanceType::MultiClassEuclidean:
        distanceFunction = std::bind(&calculateMulticlassScaledDistance, std::placeholders::_1, std::placeholders::_2);
        break;
      case DistanceType::Euclidean:
      default:
        distanceFunction = [max_radius_m](const TrackedObject &measurement, const TrackedObject &track) {
          const double distance = calculateEuclideanDistance(measurement, track);
          if (distance > max_radius_m)
          {
            return kDefaultClassBoundValue;
          }
          return distance;
        };
        break;
    }

    #pragma omp parallel for collapse(2)
    for (size_t i = 0; i < tracks.size(); ++i)
    {
      for (size_t j = 0; j < measurements.size(); ++j)
      {
        (*costMatrix)(i, j) = distanceFunction(measurements[j], tracks[i]);
      }
    }
  }

  matcher.Match(matcherOptions, &assignments, &unassignedTracks, &unassignedMeasurements);
}

} // namespace tracking
} // namespace rv
