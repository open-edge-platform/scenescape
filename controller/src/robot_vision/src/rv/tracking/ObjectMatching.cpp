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

  double distance = std::sqrt(pow(measurement.x - track.x, 2) + pow(measurement.y - track.y, 2)
                              + pow(measurement.z - track.z, 2));

  return distance * (1.0 + conflict);
}

double calculateEuclideanDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  return std::sqrt(pow(measurement.x - track.x, 2) + pow(measurement.y - track.y, 2)
                   + pow(measurement.z - track.z, 2));
}

/// Birth clustering: XY when either detection is planar (no measured Z); full XYZ when both are.
double calculateEuclideanBirthDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  const double dx = measurement.x - track.x;
  const double dy = measurement.y - track.y;
  if (!(measurement.zMeasured && track.zMeasured))
  {
    return std::hypot(dx, dy);
  }
  const double dz = measurement.z - track.z;
  return std::sqrt(dx * dx + dy * dy + dz * dz);
}

double calculateMahalanobisDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  TrackedObject::MeasurementVector innovation = measurement.measurementVector() - track.predictedMeasurementMean;

  // Use yaw in the gate only when both sides have orientation. Camera detections
  // and tracks that have never seen an orienting sensor leave yaw out.
  if (!(orientation::hasOrientation(measurement) && orientation::orientationObserved(track)))
  {
    innovation(MeasurementIndex::YAW) = 0.;
  }

  // innovation' * S^-1 * innovation; S = H P H^T + R when the detection carries its own R
  const TrackedObject::MeasurementMatrix covarianceInv = measurement.measurementNoiseCov
    ? (track.predictedStateMeasurementCov + *measurement.measurementNoiseCov).inv(cv::DECOMP_SVD)
    : track.predictedMeasurementCovInv;
  const double squaredDistance = innovation.dot(covarianceInv * innovation);

  return 0.5 * std::sqrt(squaredDistance);
}

namespace {

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

} // namespace

double calculatePositionMahalanobisSquaredDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  const double pred_x = track.predictedMeasurementMean(MeasurementIndex::X);
  const double pred_y = track.predictedMeasurementMean(MeasurementIndex::Y);
  const double pred_z = track.predictedMeasurementMean(MeasurementIndex::Z);
  const double dx = measurement.x - pred_x;
  const double dy = measurement.y - pred_y;
  const double dz = measurement.z - pred_z;

  const cv::Matx33d S = positionCovariance(measurement, track);

  cv::Mat Sinv;
  if (cv::invert(S, Sinv, cv::DECOMP_LU) == 0)
  {
    return kDefaultClassBoundValue;
  }

  const double inv00 = Sinv.at<double>(0, 0);
  const double inv01 = Sinv.at<double>(0, 1);
  const double inv02 = Sinv.at<double>(0, 2);
  const double inv11 = Sinv.at<double>(1, 1);
  const double inv12 = Sinv.at<double>(1, 2);
  const double inv22 = Sinv.at<double>(2, 2);

  return dx * (inv00 * dx + inv01 * dy + inv02 * dz)
       + dy * (inv01 * dx + inv11 * dy + inv12 * dz)
       + dz * (inv02 * dx + inv12 * dy + inv22 * dz);
}

namespace {

/// Per-track constants for PositionMahalanobis cost fill (S^{-1} is fixed for the frame).
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
};

PositionMahalanobisTrackCache buildPositionMahalanobisTrackCache(const TrackedObject &track)
{
  PositionMahalanobisTrackCache cache;
  cache.pred_x = track.predictedMeasurementMean(MeasurementIndex::X);
  cache.pred_y = track.predictedMeasurementMean(MeasurementIndex::Y);
  cache.pred_z = track.predictedMeasurementMean(MeasurementIndex::Z);

  const cv::Matx33d S = positionBlock(track.predictedMeasurementCov);

  cv::Mat Sinv;
  if (cv::invert(S, Sinv, cv::DECOMP_LU) == 0)
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

double positionMahalanobisCostFromCache(double measurement_x, double measurement_y, double measurement_z,
                                        const PositionMahalanobisTrackCache &cache, double max_radius_m)
{
  const double dx = measurement_x - cache.pred_x;
  const double dy = measurement_y - cache.pred_y;
  const double dz = measurement_z - cache.pred_z;
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

/// Per-pair S = H P H^T + R_detection: the per-track cached S^-1 does not apply.
double positionMahalanobisCostWithMeasurementNoise(const TrackedObject &measurement,
                                                   const TrackedObject &track,
                                                   const PositionMahalanobisTrackCache &cache,
                                                   double max_radius_m)
{
  const double dx = measurement.x - cache.pred_x;
  const double dy = measurement.y - cache.pred_y;
  const double dz = measurement.z - cache.pred_z;
  if (std::sqrt(dx * dx + dy * dy + dz * dz) > max_radius_m)
  {
    return kDefaultClassBoundValue;
  }
  return calculatePositionMahalanobisSquaredDistance(measurement, track);
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
          ? positionMahalanobisCostWithMeasurementNoise(measurements[j], tracks[i], track_caches[i], max_radius_m)
          : positionMahalanobisCostFromCache(
              measurements[j].x, measurements[j].y, measurements[j].z, track_caches[i], max_radius_m);
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
      case DistanceType::EuclideanBirth:
        distanceFunction = [max_radius_m](const TrackedObject &measurement, const TrackedObject &track) {
          const double distance = calculateEuclideanBirthDistance(measurement, track);
          if (distance > max_radius_m)
          {
            return kDefaultClassBoundValue;
          }
          return distance;
        };
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
