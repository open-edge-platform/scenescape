// SPDX-FileCopyrightText: 2019 - 2026 Intel Corporation
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
#include "rv/tracking/OrientationAttributes.hpp"

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

namespace {

constexpr int kWithoutYaw = TrackedObject::MeasurementSize - 1;
constexpr int kYaw = TrackedObject::MeasurementSize - 1;

/// Per-track inverses for the Mahalanobis cost (S is fixed for the frame): S^-1, and the inverse of S without the yaw
/// row and column for pairs without yaw.
struct MahalanobisTrackCache
{
  TrackedObject::MeasurementMatrix covarianceInv;
  cv::Matx<double, kWithoutYaw, kWithoutYaw> covarianceWithoutYawInv;
  bool orientationObserved = false;
};

MahalanobisTrackCache buildMahalanobisTrackCache(const TrackedObject &track)
{
  MahalanobisTrackCache cache;
  cache.orientationObserved = orientation::orientationObserved(track);
  if (cache.orientationObserved)
  {
    cv::invert(track.predictedMeasurementCov, cache.covarianceInv, cv::DECOMP_SVD);
  }
  cv::invert(track.predictedMeasurementCov.get_minor<kWithoutYaw, kWithoutYaw>(0, 0),
             cache.covarianceWithoutYawInv,
             cv::DECOMP_SVD);
  return cache;
}

double mahalanobisCostFromCache(const TrackedObject &measurement,
                                const TrackedObject &track,
                                const MahalanobisTrackCache &cache)
{
  TrackedObject::MeasurementVector innovation = measurement.measurementVector() - track.predictedMeasurementMean;

  // Use yaw only when both sides have orientation and the update keeps it (the speed gate). Camera detections
  // and tracks that have never seen an orienting sensor leave yaw out — same
  // observed-row subset as the partial UKF update (inv of S without yaw), not
  // zeroing ν_yaw inside ν' S^-1 ν which still couples through off-diagonal S^-1.
  if (cache.orientationObserved && orientation::hasOrientation(measurement)
      && orientation::yawPassesSpeedGate(track, measurement.yaw))
  {
    // The detection yaw is in (-π, π] and the predicted yaw unwrapped; a box reads the same at yaw + π.
    innovation(kYaw) = -rv::deltaTheta(measurement.yaw, track.predictedMeasurementMean(kYaw));
    return 0.5 * std::sqrt(innovation.dot(cache.covarianceInv * innovation));
  }

  const auto reducedInnovation = innovation.get_minor<kWithoutYaw, 1>(0, 0);
  return 0.5 * std::sqrt(reducedInnovation.dot(cache.covarianceWithoutYawInv * reducedInnovation));
}

} // namespace

// One pair, for tests; match() builds the cache once per track.
double calculateMahalanobisDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  return mahalanobisCostFromCache(measurement, track, buildMahalanobisTrackCache(track));
}

double calculatePositionMahalanobisSquaredDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  const double pred_x = track.predictedMeasurementMean(0);
  const double pred_y = track.predictedMeasurementMean(1);
  const double dx = measurement.x - pred_x;
  const double dy = measurement.y - pred_y;

  const double s00 = track.predictedMeasurementCov(0, 0);
  const double s01 = track.predictedMeasurementCov(0, 1);
  const double s11 = track.predictedMeasurementCov(1, 1);

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
  cache.pred_x = track.predictedMeasurementMean(0);
  cache.pred_y = track.predictedMeasurementMean(1);

  const double s00 = track.predictedMeasurementCov(0, 0);
  const double s01 = track.predictedMeasurementCov(0, 1);
  const double s11 = track.predictedMeasurementCov(1, 1);
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
  else if (distanceType == DistanceType::Mahalanobis || distanceType == DistanceType::MCEMahalanobis)
  {
    std::vector<MahalanobisTrackCache> track_caches(tracks.size());
    for (size_t i = 0; i < tracks.size(); ++i)
    {
      track_caches[i] = buildMahalanobisTrackCache(tracks[i]);
    }

    const bool compound = distanceType == DistanceType::MCEMahalanobis;
    #pragma omp parallel for collapse(2)
    for (size_t i = 0; i < tracks.size(); ++i)
    {
      for (size_t j = 0; j < measurements.size(); ++j)
      {
        const double mahalanobis = mahalanobisCostFromCache(measurements[j], tracks[i], track_caches[i]);
        (*costMatrix)(i, j) = compound
          ? 0.5 * calculateMulticlassScaledDistance(measurements[j], tracks[i]) + 0.5 * mahalanobis
          : mahalanobis;
      }
    }
  }
  else
  {
    std::function<double(const TrackedObject &, const TrackedObject &)> distanceFunction;
    switch (distanceType)
    {
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
