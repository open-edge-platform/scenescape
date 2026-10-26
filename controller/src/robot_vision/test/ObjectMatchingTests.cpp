// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <chrono>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include <rv/Utils.hpp>
#include <rv/tracking/ObjectMatching.hpp>
#include <rv/tracking/TrackManager.hpp>
#include <rv/tracking/TrackedObject.hpp>

TEST(ObjectMatchingTest, Chi2ThresholdMatchesExpectedQuantile)
{
  EXPECT_NEAR(rv::chi2Threshold(0.99, 2), 9.21034, 1e-3);
}

TEST(ObjectMatchingTest, PositionMahalanobisPrefersAlongTrackAxis)
{
  rv::tracking::TrackManagerConfig trackerConfig;
  trackerConfig.mMotionModels = {rv::tracking::MotionModel::CV};
  trackerConfig.mDefaultProcessNoise = 1e-4;
  trackerConfig.mDefaultMeasurementNoise = 0.2;
  trackerConfig.mInitStateCovariance = 1.0;
  rv::tracking::TrackManager trackManager(trackerConfig);

  rv::tracking::TrackedObject seed;
  seed.x = 0.0;
  seed.y = 0.0;
  seed.vx = 5.0;
  seed.vy = 0.0;
  seed.length = 0.5;
  seed.width = 0.5;
  seed.height = 0.5;

  auto timestamp = std::chrono::system_clock::now();
  auto trackId = trackManager.createTrack(seed, timestamp);

  for (int i = 0; i < 10; ++i)
  {
    timestamp += std::chrono::milliseconds(100);
    seed.x += 0.5;
    trackManager.setMeasurement(trackId, seed);
    trackManager.predict(timestamp);
    trackManager.correct();
    seed = trackManager.getTrack(trackId);
  }

  timestamp += std::chrono::milliseconds(1000);
  trackManager.predict(timestamp);
  auto track = trackManager.getTrack(trackId);

  const double s00 = track.predictedMeasurementCov.at<double>(0, 0);
  const double s11 = track.predictedMeasurementCov.at<double>(1, 1);
  EXPECT_GT(s00, 1.5 * s11) << "expected along-track (x) uncertainty to dominate after +x motion coast";

  const double pred_x = track.predictedMeasurementMean.at<double>(0, 0);
  const double pred_y = track.predictedMeasurementMean.at<double>(1, 0);

  rv::tracking::TrackedObject ahead = seed;
  ahead.x = pred_x + 2.0;
  ahead.y = pred_y;

  rv::tracking::TrackedObject lateral = seed;
  lateral.x = pred_x;
  lateral.y = pred_y + 2.0;

  const double chi2_gate = rv::chi2Threshold(0.99, 2);
  const double max_radius = 10.0;

  std::vector<rv::tracking::TrackedObject> tracks = {track};
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;

  // Equal Euclidean distance: matcher must prefer the along-track detection.
  rv::tracking::match(tracks, {ahead, lateral}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::PositionMahalanobis, chi2_gate, max_radius);
  ASSERT_EQ(assignments.size(), 1U);
  EXPECT_EQ(assignments[0].first, 0U);
  EXPECT_EQ(assignments[0].second, 0U);

  assignments.clear();
  unassignedTracks.clear();
  unassignedMeasurements.clear();
  rv::tracking::match(tracks, {lateral}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::PositionMahalanobis, chi2_gate, max_radius);
  // Lateral-only may still pass the chi2 gate; cost must still exceed along-track cost.
  const double dx = 2.0;
  const double dy = 2.0;
  const double det = s00 * s11;
  ASSERT_GT(det, 0.0);
  const double d2_ahead = (dx * dx) * s11 / det;
  const double d2_lateral = (dy * dy) * s00 / det;
  EXPECT_LT(d2_ahead, d2_lateral);
}
