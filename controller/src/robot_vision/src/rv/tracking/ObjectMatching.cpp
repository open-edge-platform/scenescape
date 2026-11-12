// SPDX-FileCopyrightText: 2019 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <algorithm>
#include <cmath>
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
#include "rv/tracking/PositionGate.hpp"

namespace rv {
namespace tracking {

constexpr double kDefaultClassBoundValue = 1000.;
// A track whose position covariance S has det S at or below this is never assigned.
constexpr double kMinPositionCovarianceDeterminant = 1e-12;

// Legacy (DistanceType::MultiClassEuclidean, MCEMahalanobis); the services do not use it.
double calculateMulticlassScaledDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  auto conflict = rv::tracking::classification::distance(measurement.classification, track.classification);

  double distance = std::sqrt(pow(measurement.x - track.x, 2) + pow(measurement.y - track.y, 2)
                              + pow(measurement.z - track.z, 2));

  return distance * (1.0 + conflict);
}

/// XY when either side is planar (no measured Z): a ground point and a box centre differ in z by the reference, not by
/// the motion. Full XYZ when both are, so measured stacked floors stay apart.
double calculateEuclideanDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  const double dx = measurement.x - track.x;
  const double dy = measurement.y - track.y;
  if (!position_gate::gatesZ(track, measurement))
  {
    return std::hypot(dx, dy);
  }
  const double dz = measurement.z - track.z;
  return std::sqrt(dx * dx + dy * dy + dz * dz);
}

// Legacy Mahalanobis cost (DistanceType::Mahalanobis, MCEMahalanobis); the services do not use it. It returns
// 0.5 * sqrt(d^2), so its threshold is no chi-squared confidence.
namespace {

constexpr int kWithoutYaw = TrackedObject::MeasurementSize - 1;
constexpr int kYaw = TrackedObject::MeasurementSize - 1;

/// Per-track inverses (S is fixed for the frame): S^-1, and the inverse of S without the yaw row and column for pairs
/// without yaw.
struct MahalanobisTrackCache
{
  TrackedObject::MeasurementMatrix covarianceInv;
  cv::Matx<double, kWithoutYaw, kWithoutYaw> covarianceWithoutYawInv;
  bool orientationObserved = false;
};

MahalanobisTrackCache buildMahalanobisCache(const TrackedObject::MeasurementMatrix &covariance, bool orientationObserved)
{
  MahalanobisTrackCache cache;
  cache.orientationObserved = orientationObserved;
  if (cache.orientationObserved)
  {
    cv::invert(covariance, cache.covarianceInv, cv::DECOMP_SVD);
  }
  cv::invert(covariance.get_minor<kWithoutYaw, kWithoutYaw>(0, 0), cache.covarianceWithoutYawInv, cv::DECOMP_SVD);
  return cache;
}

MahalanobisTrackCache buildMahalanobisTrackCache(const TrackedObject &track)
{
  return buildMahalanobisCache(track.predictedMeasurementCov, orientation::orientationObserved(track));
}

double mahalanobisCostFromCache(const TrackedObject &measurement,
                                const TrackedObject &track,
                                const MahalanobisTrackCache &trackCache)
{
  // S = H P H^T + R is per pair when the detection carries its own R, so the track's cached inverses do not apply.
  std::optional<MahalanobisTrackCache> pairCache;
  if (measurement.measurementNoiseCov)
  {
    pairCache = buildMahalanobisCache(track.predictedStateMeasurementCov + *measurement.measurementNoiseCov,
                                      trackCache.orientationObserved);
  }
  const MahalanobisTrackCache &cache = pairCache ? *pairCache : trackCache;

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

/// XYZ block of a measurement-space covariance.
cv::Matx33d positionBlock(const TrackedObject::MeasurementMatrix &covariance)
{
  static_assert(MeasurementIndex::Y == MeasurementIndex::X + 1 && MeasurementIndex::Z == MeasurementIndex::X + 2,
                "x, y, z must be adjacent in the measurement vector");
  return covariance.get_minor<3, 3>(MeasurementIndex::X, MeasurementIndex::X);
}

/// XYZ block of S: the track's predicted S, or H P H^T + R when the detection carries its own R.
cv::Matx33d positionCovariance(const TrackedObject &measurement, const TrackedObject &track)
{
  if (!measurement.measurementNoiseCov)
  {
    return positionBlock(track.predictedMeasurementCov);
  }
  return positionBlock(track.predictedStateMeasurementCov) + positionBlock(*measurement.measurementNoiseCov);
}

/// S^-1 of the position block when S is symmetric positive definite. A singular or indefinite S could give a negative
/// d^2 that passes any gate and wins the assignment; LU alone would still invert a near-singular one.
bool invertPositionCovariance(const cv::Matx33d &S, cv::Mat &Sinv)
{
  if (!cv::checkRange(S))
  {
    return false;
  }
  // Sylvester: SPD iff the leading principal minors are positive; the last one keeps the near-singular floor.
  const double minor2 = S(0, 0) * S(1, 1) - S(0, 1) * S(1, 0);
  if (S(0, 0) <= 0.0 || minor2 <= 0.0 || cv::determinant(S) <= kMinPositionCovarianceDeterminant)
  {
    return false;
  }
  return cv::invert(S, Sinv, cv::DECOMP_LU) != 0;
}

} // namespace

// One pair, for tests; match() builds the cache once per track.
double calculateMahalanobisDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  return mahalanobisCostFromCache(measurement, track, buildMahalanobisTrackCache(track));
}

namespace {

/// Per-track constants for PositionMahalanobis cost fill (S^{-1} is fixed for the frame): the inverse of the x/y/z
/// block for pairs that both measured z, and of the x/y block for the others.
struct PositionMahalanobisTrackCache
{
  double pred_x = 0.0;
  double pred_y = 0.0;
  double pred_z = 0.0;
  double inv00 = 0.0;
  double inv01 = 0.0;
  double inv02 = 0.0;
  double inv11 = 0.0;
  double inv12 = 0.0;
  double inv22 = 0.0;
  bool valid = false;
  double invXy00 = 0.0;
  double invXy01 = 0.0;
  double invXy11 = 0.0;
  bool validXy = false;
  bool z_measured = false;
};

/// Cache for one S: the track's predicted S, or a pair's H P H^T + R_detection.
PositionMahalanobisTrackCache buildPositionMahalanobisCache(const TrackedObject &track, const cv::Matx33d &S)
{
  PositionMahalanobisTrackCache cache;
  cache.pred_x = track.predictedMeasurementMean(MeasurementIndex::X);
  cache.pred_y = track.predictedMeasurementMean(MeasurementIndex::Y);
  cache.pred_z = track.predictedMeasurementMean(MeasurementIndex::Z);
  cache.z_measured = track.z_measured;

  // x/y block: SPD with det S_xy above the floor, as the 2x2 gate before z tracking.
  const double detXy = S(0, 0) * S(1, 1) - S(0, 1) * S(1, 0);
  if (std::isfinite(S(0, 0)) && std::isfinite(S(0, 1)) && std::isfinite(S(1, 1)) && S(0, 0) > 0.0
      && detXy > kMinPositionCovarianceDeterminant)
  {
    cache.invXy00 = S(1, 1) / detXy;
    cache.invXy01 = -S(0, 1) / detXy;
    cache.invXy11 = S(0, 0) / detXy;
    cache.validXy = true;
  }

  cv::Mat Sinv;
  if (!invertPositionCovariance(S, Sinv))
  {
    return cache;
  }
  cache.inv00 = Sinv.at<double>(0, 0);
  cache.inv01 = Sinv.at<double>(0, 1);
  cache.inv02 = Sinv.at<double>(0, 2);
  cache.inv11 = Sinv.at<double>(1, 1);
  cache.inv12 = Sinv.at<double>(1, 2);
  cache.inv22 = Sinv.at<double>(2, 2);
  cache.valid = true;
  return cache;
}

PositionMahalanobisTrackCache buildPositionMahalanobisTrackCache(const TrackedObject &track)
{
  return buildPositionMahalanobisCache(track, positionBlock(track.predictedMeasurementCov));
}

/// Cost against match()'s single threshold chi2(p, 3). When position_gate::gatesZ is false, d² is on x/y only and
/// scaled by xy_scale so both subspaces pass at the same p (see position_gate::xyCostScaleForChi2Threshold3).
double positionMahalanobisCostFromCache(const TrackedObject &measurement, const PositionMahalanobisTrackCache &cache,
                                        double max_radius_m, double xy_scale)
{
  const double dx = measurement.x - cache.pred_x;
  const double dy = measurement.y - cache.pred_y;
  if (!position_gate::gatesZ(cache.z_measured, measurement.z_measured))
  {
    if (std::hypot(dx, dy) > max_radius_m || !cache.validXy)
    {
      return kDefaultClassBoundValue;
    }
    return xy_scale * (cache.invXy00 * dx * dx + 2.0 * cache.invXy01 * dx * dy + cache.invXy11 * dy * dy);
  }
  const double dz = measurement.z - cache.pred_z;
  if (std::sqrt(dx * dx + dy * dy + dz * dz) > max_radius_m)
  {
    return kDefaultClassBoundValue;
  }
  if (!cache.valid)
  {
    return kDefaultClassBoundValue;
  }
  return dx * (cache.inv00 * dx + cache.inv01 * dy + cache.inv02 * dz)
       + dy * (cache.inv01 * dx + cache.inv11 * dy + cache.inv12 * dz)
       + dz * (cache.inv02 * dx + cache.inv12 * dy + cache.inv22 * dz);
}

/// Cost of one pair from its own S: with R on the detection S = H P H^T + R is per pair, so the track's cached inverses
/// do not apply; the per-pair z gate does.
double positionMahalanobisPairCost(const TrackedObject &measurement,
                                   const TrackedObject &track,
                                   double max_radius_m,
                                   double xy_scale)
{
  const auto pairCache = buildPositionMahalanobisCache(track, positionCovariance(measurement, track));
  return positionMahalanobisCostFromCache(measurement, pairCache, max_radius_m, xy_scale);
}

} // namespace

// One pair, for tests: d^2 on x/y/z when position_gate::gatesZ, else on x/y (df 2, not scaled to chi2(p, 3)); S is
// H P H^T + R when the detection carries R. match() costs the pairs without R with the per-track cache.
double calculatePositionMahalanobisSquaredDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  return positionMahalanobisPairCost(measurement, track, std::numeric_limits<double>::infinity(), 1.0);
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
  // Rejected pairs cost kDefaultClassBoundValue; a threshold above it would make them valid matches.
  matcherOptions.cost_thresh = std::min(threshold, kDefaultClassBoundValue);
  matcherOptions.bound_value = kDefaultClassBoundValue;

  apollo::perception::common::SecureMat<double> *costMatrix = matcher.cost_matrix();
  costMatrix->Resize(tracks.size(), measurements.size());

  if (distanceType == DistanceType::PositionMahalanobis)
  {
    // threshold is chi2(p, 3); x/y-only pairs are scaled to the same p.
    const double xy_scale = position_gate::xyCostScaleForChi2Threshold3(threshold);

    // Invert the 3x3 position covariance once per track, not once per (track, detection).
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
        (*costMatrix)(i, j) = measurements[j].measurementNoiseCov
          ? positionMahalanobisPairCost(measurements[j], tracks[i], max_radius_m, xy_scale)
          : positionMahalanobisCostFromCache(measurements[j], track_caches[i], max_radius_m, xy_scale);
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
      case DistanceType::EuclideanBirth:
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
