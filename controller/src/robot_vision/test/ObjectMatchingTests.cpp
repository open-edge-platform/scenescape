// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <chrono>
#include <cmath>
#include <limits>
#include <utility>
#include <vector>

#include <gtest/gtest.h>
#include <opencv2/core.hpp>

#include <rv/Utils.hpp>
#include <rv/tracking/ObjectMatching.hpp>
#include <rv/tracking/OrientationAttributes.hpp>
#include <rv/tracking/PositionGate.hpp>
#include <rv/tracking/TrackManager.hpp>
#include <rv/tracking/TrackedObject.hpp>

#include "support/TestUtils.hpp"

TEST(ObjectMatchingTest, Chi2ThresholdMatchesExpectedQuantile)
{
  EXPECT_NEAR(rv::chi2Threshold(0.99, 2), 9.21034, 1e-3);
  EXPECT_NEAR(rv::chi2Threshold(0.99, 3), 11.3449, 1e-3);
  EXPECT_NEAR(rv::chi2Threshold(0.95, 3), 7.81473, 1e-3);
}

TEST(ObjectMatchingTest, PositionGateCentralizesXyVersusXyz)
{
  rv::tracking::TrackedObject planar;
  rv::tracking::TrackedObject measured;
  measured.z_measured = true;

  EXPECT_FALSE(rv::tracking::position_gate::gatesZ(planar, measured));
  EXPECT_FALSE(rv::tracking::position_gate::gatesZ(measured, planar));
  EXPECT_TRUE(rv::tracking::position_gate::gatesZ(measured, measured));
  EXPECT_FALSE(rv::tracking::position_gate::trackCanGateZ(planar));
  EXPECT_TRUE(rv::tracking::position_gate::trackCanGateZ(measured));
  EXPECT_EQ(rv::tracking::position_gate::positionDof(false), 2);
  EXPECT_EQ(rv::tracking::position_gate::positionDof(true), 3);
  EXPECT_NEAR(rv::tracking::position_gate::positionChi2(0.99, false), rv::chi2Threshold(0.99, 2), 1e-9);
  EXPECT_NEAR(rv::tracking::position_gate::positionChi2(0.99, true), rv::chi2Threshold(0.99, 3), 1e-9);

  std::vector<int> rows;
  rv::tracking::position_gate::appendPositionMeasurementRows(rows, false);
  EXPECT_EQ(rows, (std::vector<int>{rv::tracking::MeasurementIndex::X, rv::tracking::MeasurementIndex::Y}));
  rows.clear();
  rv::tracking::position_gate::appendPositionMeasurementRows(rows, true);
  EXPECT_EQ(rows, (std::vector<int>{rv::tracking::MeasurementIndex::X, rv::tracking::MeasurementIndex::Y,
                                    rv::tracking::MeasurementIndex::Z}));
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

  // predict() drops pending measurements, so measure after it. 2 s of measurements let the isotropic initial velocity
  // variance settle below the along-track process noise.
  for (int i = 0; i < 20; ++i)
  {
    timestamp += std::chrono::milliseconds(100);
    trackManager.predict(timestamp);
    seed.x += 0.5;
    trackManager.setMeasurement(trackId, seed);
    trackManager.correct();
    seed = trackManager.getTracks().front();
  }

  timestamp += std::chrono::milliseconds(1000);
  trackManager.predict(timestamp);
  auto track = trackManager.getTracks().front();

  const double s00 = track.predictedMeasurementCov(0, 0);
  const double s11 = track.predictedMeasurementCov(1, 1);
  EXPECT_GT(s00, 1.5 * s11) << "expected along-track (x) uncertainty to dominate after +x motion coast";

  const double pred_x = track.predictedMeasurementMean(0);
  const double pred_y = track.predictedMeasurementMean(1);

  rv::tracking::TrackedObject ahead = seed;
  ahead.x = pred_x + 2.0;
  ahead.y = pred_y;

  rv::tracking::TrackedObject lateral = seed;
  lateral.x = pred_x;
  lateral.y = pred_y + 2.0;

  const double chi2_gate = rv::chi2Threshold(0.99, 3);
  const double max_radius = 10.0;

  const std::vector<rv::tracking::TrackedObject> tracks = {track};
  auto assignedMeasurements = [&](const std::vector<rv::tracking::TrackedObject> &measurements, double threshold) {
    std::vector<std::pair<size_t, size_t>> assignments;
    std::vector<size_t> unassignedTracks;
    std::vector<size_t> unassignedMeasurements;
    rv::tracking::match(tracks,
                        measurements,
                        assignments,
                        unassignedTracks,
                        unassignedMeasurements,
                        rv::tracking::DistanceType::PositionMahalanobis,
                        threshold,
                        max_radius);
    std::vector<size_t> assigned;
    for (const auto &assignment : assignments)
    {
      assigned.push_back(assignment.second);
    }
    return assigned;
  };

  // Equal Euclidean distance, both inside a wide gate: the matcher takes the along-track detection, the lower cost.
  EXPECT_EQ(assignedMeasurements({lateral, ahead}, 100.0), std::vector<size_t>{1});
  // At chi2(0.99, 3) the along-track detection is inside the gate and the lateral one outside.
  EXPECT_EQ(assignedMeasurements({ahead}, chi2_gate), std::vector<size_t>{0});
  EXPECT_TRUE(assignedMeasurements({lateral}, chi2_gate).empty());
}

TEST(ObjectMatchingTest, EuclideanSeparatesStackedFloors)
{
  rv::tracking::TrackedObject track;
  track.x = 1.0;
  track.y = 2.0;
  track.z = 0.0;
  track.z_measured = true; // floors are told apart by measured z only
  track.length = track.width = track.height = 0.5;

  rv::tracking::TrackedObject sameFloor = track;
  sameFloor.z = 0.1;

  rv::tracking::TrackedObject upperFloor = track;
  upperFloor.z = 3.0; // > 2 m birth / Euclidean gate

  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;

  rv::tracking::match({track}, {sameFloor, upperFloor}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::Euclidean, 2.0, 2.0);
  ASSERT_EQ(assignments.size(), 1U);
  EXPECT_EQ(assignments[0].second, 0U);

  assignments.clear();
  unassignedTracks.clear();
  unassignedMeasurements.clear();
  rv::tracking::match({track}, {upperFloor}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::Euclidean, 2.0, 2.0);
  EXPECT_TRUE(assignments.empty());
}

TEST(ObjectMatchingTest, EuclideanBirthUsesXyUnlessBothZMeasured)
{
  rv::tracking::TrackedObject planar;
  planar.x = 1.0;
  planar.y = 2.0;
  planar.z = 0.0;
  planar.z_measured = false;
  planar.length = planar.width = planar.height = 0.5;

  rv::tracking::TrackedObject measured = planar;
  measured.z = 1.5;
  measured.z_measured = true;

  rv::tracking::TrackedObject upperMeasured = planar;
  upperMeasured.z = 4.0; // Δz > kDefaultBirthClusterRadiusM
  upperMeasured.z_measured = true;

  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;

  // Mixed planar + measured Z: XY distance (~0) must match within 2 m.
  rv::tracking::match({planar}, {measured}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::EuclideanBirth, 2.0, 2.0);
  ASSERT_EQ(assignments.size(), 1U);

  assignments.clear();
  unassignedTracks.clear();
  unassignedMeasurements.clear();
  // Both measured, Δz = 4 m: reject.
  rv::tracking::match({measured}, {upperMeasured}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::EuclideanBirth, 2.0, 2.0);
  EXPECT_TRUE(assignments.empty());
}

TEST(ObjectMatchingTest, PositionMahalanobisSeparatesStackedFloors)
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
  seed.z = 0.0;
  seed.z_measured = true; // floors are told apart by measured z only
  seed.length = seed.width = seed.height = 0.5;

  auto timestamp = std::chrono::system_clock::now();
  auto trackId = trackManager.createTrack(seed, timestamp);
  for (int i = 0; i < 5; ++i)
  {
    timestamp += std::chrono::milliseconds(100);
    trackManager.predict(timestamp); // predict() drops pending measurements, so measure after it
    trackManager.setMeasurement(trackId, seed);
    trackManager.correct();
  }
  timestamp += std::chrono::milliseconds(100);
  trackManager.predict(timestamp);
  auto track = trackManager.getTracks().front();

  rv::tracking::TrackedObject sameFloor = seed;
  sameFloor.z = 0.05;
  rv::tracking::TrackedObject upperFloor = seed;
  upperFloor.z = 4.0;

  const double chi2_gate = rv::chi2Threshold(0.99, 3);
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;

  rv::tracking::match({track}, {sameFloor, upperFloor}, assignments, unassignedTracks, unassignedMeasurements,
                      rv::tracking::DistanceType::PositionMahalanobis, chi2_gate, 10.0);
  ASSERT_EQ(assignments.size(), 1U);
  EXPECT_EQ(assignments[0].second, 0U);
}

// Defined in ObjectMatching.cpp, not declared in its header.
namespace rv::tracking {
double calculateMahalanobisDistance(const TrackedObject &measurement, const TrackedObject &track);
double calculateMulticlassScaledDistance(const TrackedObject &measurement, const TrackedObject &track);
} // namespace rv::tracking

namespace {

using namespace rv::tracking;
using test::makeDetection;

constexpr int kYaw = MeasurementIndex::YAW;
constexpr int kWithoutYaw = TrackedObject::MeasurementSize - 1;
static_assert(kYaw == kWithoutYaw, "yaw must be the last measurement");

// Symmetric positive definite S with strong yaw↔position coupling so zeroing ν_yaw ≠ marginalizing yaw.
TrackedObject makeTrack()
{
  TrackedObject track;
  track.predictedMeasurementMean = TrackedObject::MeasurementVector(2.5, -1.0, 0.4, 4.5, 1.8, 1.5, 0.2);
  TrackedObject::MeasurementMatrix covariance = TrackedObject::MeasurementMatrix::zeros();
  for (int i = 0; i < TrackedObject::MeasurementSize; ++i)
  {
    covariance(i, i) = 1.0;
  }
  // Correlate yaw with x and y; diagonally dominant so S stays SPD.
  covariance(0, kYaw) = covariance(kYaw, 0) = 0.6;
  covariance(1, kYaw) = covariance(kYaw, 1) = 0.5;
  track.predictedMeasurementCov = covariance;
  return track;
}

TrackedObject::MeasurementMatrix inverseCovariance(const TrackedObject &track)
{
  TrackedObject::MeasurementMatrix inverse;
  cv::invert(track.predictedMeasurementCov, inverse, cv::DECOMP_SVD);
  return inverse;
}

TrackedObject makeMeasurement()
{
  auto measurement = makeDetection(3.0, -2.0, 0.5, 4.6, 1.9, 1.4);
  measurement.yaw = 1.2;
  return measurement;
}

// 0.5 * sqrt(d' * W * d): full S^-1 when useYaw, else inv of the leading 6x6 of S (UKF marginalization).
double expectedDistance(const TrackedObject &measurement, const TrackedObject &track, bool useYaw)
{
  TrackedObject::MeasurementVector innovation
    = measurement.measurementVector() - track.predictedMeasurementMean;
  if (useYaw)
  {
    return 0.5 * std::sqrt(innovation.dot(inverseCovariance(track) * innovation));
  }

  cv::Matx<double, kWithoutYaw, 1> reducedInnovation;
  cv::Matx<double, kWithoutYaw, kWithoutYaw> reducedCovariance;
  for (int i = 0; i < kWithoutYaw; ++i)
  {
    reducedInnovation(i) = innovation(i);
    for (int j = 0; j < kWithoutYaw; ++j)
    {
      reducedCovariance(i, j) = track.predictedMeasurementCov(i, j);
    }
  }
  cv::Matx<double, kWithoutYaw, kWithoutYaw> reducedCovarianceInv;
  cv::invert(reducedCovariance, reducedCovarianceInv, cv::DECOMP_SVD);
  return 0.5 * std::sqrt(reducedInnovation.dot(reducedCovarianceInv * reducedInnovation));
}

// Old gate: zero ν_yaw then use full S^-1 (wrong when yaw is correlated).
double zeroedYawDistance(const TrackedObject &measurement, const TrackedObject &track)
{
  TrackedObject::MeasurementVector innovation
    = measurement.measurementVector() - track.predictedMeasurementMean;
  innovation(kYaw) = 0.0;
  return 0.5 * std::sqrt(innovation.dot(inverseCovariance(track) * innovation));
}

// Legacy DistanceType::Mahalanobis, not used by the services.
TEST(ObjectMatchingTest, MahalanobisDistanceUsesInverseCovarianceOfPredictedMeasurement)
{
  const auto track = makeTrack();
  const auto measurement = makeMeasurement();

  const double distance = calculateMahalanobisDistance(measurement, track);

  EXPECT_NEAR(distance, expectedDistance(measurement, track, false), 1e-12);
  EXPECT_GT(distance, 0.5);
  // Zeroing ν_yaw is not the same as marginalizing yaw when S couples yaw to position/size.
  EXPECT_GT(std::abs(distance - zeroedYawDistance(measurement, track)), 1e-3);

  const auto onTrack = makeDetection(2.5, -1.0, 0.4, 4.5, 1.8, 1.5);
  EXPECT_DOUBLE_EQ(calculateMahalanobisDistance(onTrack, track), 0.0);
}

// Legacy DistanceType::Mahalanobis, not used by the services.
TEST(ObjectMatchingTest, MahalanobisDistanceUsesYawOnlyWhenBothSidesHaveOrientation)
{
  const struct
  {
    const char *name;
    bool measurementOriented;
    bool trackHasOrientation; // the latest update came from an orienting sensor
    bool trackObservedOrientation;
    bool expectYaw;
  } cases[] = {
    {.name = "camera detection, camera track",
     .measurementOriented = false,
     .trackHasOrientation = false,
     .trackObservedOrientation = false,
     .expectYaw = false},
    {.name = "orienting detection, camera track",
     .measurementOriented = true,
     .trackHasOrientation = false,
     .trackObservedOrientation = false,
     .expectYaw = false},
    {.name = "camera detection, orienting track",
     .measurementOriented = false,
     .trackHasOrientation = true,
     .trackObservedOrientation = true,
     .expectYaw = false},
    {.name = "orienting detection, track that observed orientation earlier",
     .measurementOriented = true,
     .trackHasOrientation = false,
     .trackObservedOrientation = true,
     .expectYaw = true},
    {.name = "orienting detection, orienting track",
     .measurementOriented = true,
     .trackHasOrientation = true,
     .trackObservedOrientation = false,
     .expectYaw = true},
  };

  auto measurement = makeMeasurement();
  const auto reference = makeTrack();
  // The yaw innovation is large and coupled to the other measurements, so using it must change the distance.
  ASSERT_GT(std::abs(expectedDistance(measurement, reference, true) - expectedDistance(measurement, reference, false)),
            0.1);

  for (const auto &scenario : cases)
  {
    SCOPED_TRACE(scenario.name);
    auto track = makeTrack();
    measurement.attributes.clear();
    if (scenario.measurementOriented)
    {
      orientation::setHasOrientation(measurement, true);
    }
    orientation::setHasOrientation(track, scenario.trackHasOrientation);
    if (scenario.trackObservedOrientation)
    {
      track.attributes[orientation::ORIENTATION_OBSERVED] = orientation::TRUE_VALUE;
    }

    EXPECT_NEAR(calculateMahalanobisDistance(measurement, track),
                expectedDistance(measurement, track, scenario.expectYaw),
                1e-12);
  }
}

// A track predicted at (0, 0) with position covariance s00, s01, s11 and unit variance in the other measurement rows.
TrackedObject makePositionTrack(double s00, double s01, double s11)
{
  TrackedObject track;
  track.predictedMeasurementMean = TrackedObject::MeasurementVector::zeros();
  TrackedObject::MeasurementMatrix covariance = TrackedObject::MeasurementMatrix::eye();
  covariance(0, 0) = s00;
  covariance(0, 1) = covariance(1, 0) = s01;
  covariance(1, 1) = s11;
  track.predictedMeasurementCov = covariance;
  return track;
}

TrackedObject makePerson(double x, double y)
{
  return makeDetection(x, y, 0.0, 0.5, 0.5, 1.8);
}

std::vector<std::pair<size_t, size_t>> matchedPairs(const std::vector<TrackedObject> &tracks,
                                                    const std::vector<TrackedObject> &measurements,
                                                    DistanceType distanceType,
                                                    double threshold,
                                                    double maxRadiusM = std::numeric_limits<double>::infinity())
{
  std::vector<std::pair<size_t, size_t>> assignments;
  std::vector<size_t> unassignedTracks;
  std::vector<size_t> unassignedMeasurements;
  match(tracks, measurements, assignments, unassignedTracks, unassignedMeasurements, distanceType, threshold, maxRadiusM);
  return assignments;
}

size_t assignedCount(const TrackedObject &track,
                     const TrackedObject &measurement,
                     DistanceType distanceType,
                     double threshold,
                     double maxRadiusM = std::numeric_limits<double>::infinity())
{
  return matchedPairs({track}, {measurement}, distanceType, threshold, maxRadiusM).size();
}

// Legacy DistanceType::Mahalanobis, not used by the services.
TEST(ObjectMatchingTest, MahalanobisMatchUsesTheDistanceCost)
{
  // match() costs each pair with calculateMahalanobisDistance (MCEMahalanobis: its average with the multi-class
  // Euclidean distance), with the track's own S: a farther track with another S comes first, so mixing up tracks
  // changes the cost.
  auto farTrack = makePositionTrack(4.0, 0.5, 2.0);
  farTrack.predictedMeasurementMean(0) = 20.0;

  auto orientingTrack = makeTrack();
  orientation::markOrientationObserved(orientingTrack);
  auto orientedMeasurement = makeMeasurement();
  orientation::setHasOrientation(orientedMeasurement, true);

  const struct
  {
    const char *name;
    TrackedObject track;
    TrackedObject measurement;
  } cases[] = {
    {.name = "without yaw", .track = makeTrack(), .measurement = makeMeasurement()},
    {.name = "with yaw", .track = orientingTrack, .measurement = orientedMeasurement},
  };
  for (const auto &scenario : cases)
  {
    SCOPED_TRACE(scenario.name);
    const double mahalanobis = calculateMahalanobisDistance(scenario.measurement, scenario.track);
    const double compound
      = 0.5 * calculateMulticlassScaledDistance(scenario.measurement, scenario.track) + 0.5 * mahalanobis;
    ASSERT_LT(mahalanobis, calculateMahalanobisDistance(scenario.measurement, farTrack));

    for (const auto &[distanceType, cost] :
         {std::pair{DistanceType::Mahalanobis, mahalanobis}, std::pair{DistanceType::MCEMahalanobis, compound}})
    {
      SCOPED_TRACE(distanceType == DistanceType::Mahalanobis ? "Mahalanobis" : "MCEMahalanobis");
      const std::vector<TrackedObject> tracks = {farTrack, scenario.track};
      using Pairs = std::vector<std::pair<size_t, size_t>>;
      EXPECT_EQ(matchedPairs(tracks, {scenario.measurement}, distanceType, cost * (1.0 + 1e-12)), (Pairs{{1, 0}}));
      EXPECT_EQ(matchedPairs(tracks, {scenario.measurement}, distanceType, cost * (1.0 - 1e-12)), Pairs{});
    }
  }
}

constexpr double kPi = orientation::kPi;

// A car track predicted on the detection's position and size with unit S and orientation observed: with yaw in the
// gate the cost is 0.5 * |yaw innovation|, without it 0.
TrackedObject makeOrientedTrack(double predictedYaw, double vx = 0.0, double vy = 0.0)
{
  TrackedObject track;
  track.vx = vx;
  track.vy = vy;
  track.yaw = predictedYaw;
  track.predictedMeasurementMean = TrackedObject::MeasurementVector(0.0, 0.0, 0.0, 4.5, 1.8, 1.5, predictedYaw);
  track.predictedMeasurementCov = TrackedObject::MeasurementMatrix::eye();
  orientation::markOrientationObserved(track);
  return track;
}

TrackedObject makeOrientedCar(double yaw)
{
  auto car = makeDetection(0.0, 0.0, 0.0, 4.5, 1.8, 1.5);
  car.yaw = yaw;
  orientation::setHasOrientation(car, true);
  return car;
}

// Legacy DistanceType::Mahalanobis, not used by the services.
TEST(ObjectMatchingTest, MahalanobisDistanceWrapsYaw)
{
  // Detection yaw is in (-pi, pi], the predicted yaw is unwrapped, and a box reads the same at yaw + pi: the innovation
  // is the smallest of those differences, so none of them blocks the match.
  struct Case
  {
    const char *name;
    double predictedYaw;
    double detectionYaw;
    double innovation;
  };
  for (const auto &[name, predictedYaw, detectionYaw, innovation] :
       {Case{"across +-pi", kPi - 0.05, -kPi + 0.05, 0.1},
        Case{"unwrapped track yaw", 4.0 * kPi + 0.3, 0.2, -0.1},
        Case{"box read backwards", 0.1, 0.15 - kPi, 0.05}})
  {
    SCOPED_TRACE(name);
    const auto track = makeOrientedTrack(predictedYaw);
    const auto car = makeOrientedCar(detectionYaw);
    EXPECT_NEAR(calculateMahalanobisDistance(car, track), 0.5 * std::abs(innovation), 1e-9);
    EXPECT_EQ(assignedCount(track, car, DistanceType::Mahalanobis, 1.0), 1U);
  }
}

// Legacy DistanceType::Mahalanobis, not used by the services.
TEST(ObjectMatchingTest, MahalanobisDistanceAppliesTheYawSpeedGate)
{
  // At 1 m/s or more the update turns the detection yaw by pi toward the direction of travel and drops it when it is
  // still more than 0.6 rad off; the gate leaves out the yaw the update drops.
  struct Case
  {
    const char *name;
    double vx, vy;
    double predictedYaw;
    double detectionYaw;
    double distance;
  };
  for (const auto &[name, vx, vy, predictedYaw, detectionYaw, distance] :
       {Case{"read backwards, 0.3 rad off the travel", 2.0, 0.0, 0.1, -kPi + 0.3, 0.1},
        Case{"read backwards along -y", 0.0, -2.0, -kPi / 2.0, kPi / 2.0, 0.0},
        Case{"across the travel: dropped", 2.0, 0.0, 0.1, kPi / 2.0, 0.0},
        Case{"across the travel at 1 m/s: dropped", 1.0, 0.0, 0.1, kPi / 2.0, 0.0},
        Case{"across the travel below 1 m/s: kept", 0.5, 0.0, 0.1, kPi / 2.0, 0.5 * (kPi / 2.0 - 0.1)}})
  {
    SCOPED_TRACE(name);
    EXPECT_NEAR(
      calculateMahalanobisDistance(makeOrientedCar(detectionYaw), makeOrientedTrack(predictedYaw, vx, vy)), distance, 1e-9);
  }
}

TEST(ObjectMatchingTest, PositionMahalanobisRejectsPairsBeyondMaxRadius)
{
  // With S_xy = 100 m^2 the chi-squared 0.99 gate reaches about 30 m: a detection 12 m away passes it (d^2 = 1.44),
  // and only the max_radius_m ceiling rejects it.
  const auto track = makePositionTrack(100.0, 0.0, 100.0);
  const double gate = rv::chi2Threshold(0.99, 2);
  EXPECT_EQ(assignedCount(track, makePerson(12.0, 0.0), DistanceType::PositionMahalanobis, gate, 10.0), 0U);
  EXPECT_EQ(assignedCount(track, makePerson(12.0, 0.0), DistanceType::PositionMahalanobis, gate, 15.0), 1U);
  // Without a ceiling (the default) the gate alone decides.
  EXPECT_EQ(assignedCount(track, makePerson(12.0, 0.0), DistanceType::PositionMahalanobis, gate), 1U);
  // A zero ceiling rejects every offset.
  EXPECT_EQ(assignedCount(track, makePerson(0.1, 0.0), DistanceType::PositionMahalanobis, gate, 0.0), 0U);
}

TEST(ObjectMatchingTest, EuclideanRejectsPairsBeyondMaxRadius)
{
  // A cost threshold of 100 m leaves the rejection to max_radius_m; the services pass max_radius_m as both.
  const auto track = makePerson(0.0, 0.0);
  EXPECT_EQ(assignedCount(track, makePerson(3.0, 0.0), DistanceType::Euclidean, 100.0, 2.0), 0U);
  EXPECT_EQ(assignedCount(track, makePerson(3.0, 0.0), DistanceType::Euclidean, 100.0, 5.0), 1U);
  EXPECT_EQ(assignedCount(track, makePerson(3.0, 0.0), DistanceType::Euclidean, 100.0), 1U);
}

TEST(ObjectMatchingTest, MaxRadiusRejectsPairsAtThresholdsAboveTheBoundCost)
{
  // A pair beyond max_radius_m costs 1000: a threshold above that is capped, so the pair stays rejected.
  EXPECT_EQ(assignedCount(makePerson(0.0, 0.0), makePerson(3.0, 0.0), DistanceType::Euclidean, 2000.0, 2.0), 0U);
  EXPECT_EQ(assignedCount(makePositionTrack(100.0, 0.0, 100.0), makePerson(12.0, 0.0),
                          DistanceType::PositionMahalanobis, 2000.0, 10.0),
            0U);
}

TEST(ObjectMatchingTest, PositionMahalanobisGatesZOnlyWhenBothSidesMeasuredIt)
{
  // S = I. A detection 5 m above the prediction: z is gated only when the detection and the track both have measured
  // z; otherwise only x and y are, and the max_radius_m ceiling uses the XY distance too.
  const double chi2 = rv::chi2Threshold(0.99, 3);
  auto track = makePositionTrack(1.0, 0.0, 1.0);
  auto above = makePerson(0.0, 0.0);
  above.z = 5.0;
  auto farAbove = above;
  farAbove.z = 20.0;

  const struct
  {
    const char *name;
    bool trackZ, detectionZ;
    size_t expected;
  } cases[] = {{"planar track and detection", false, false, 1U},
               {"planar track", false, true, 1U},
               {"planar detection", true, false, 1U},
               {"both measured", true, true, 0U}};
  for (const auto &testCase : cases)
  {
    SCOPED_TRACE(testCase.name);
    track.z_measured = testCase.trackZ;
    above.z_measured = farAbove.z_measured = testCase.detectionZ;
    EXPECT_EQ(assignedCount(track, above, DistanceType::PositionMahalanobis, chi2, 10.0), testCase.expected);
    EXPECT_EQ(assignedCount(track, farAbove, DistanceType::PositionMahalanobis, chi2, 10.0), testCase.expected)
      << "20 m above, ceiling 10 m";
  }
}

TEST(ObjectMatchingTest, PositionMahalanobisGatesXyPairsAtTwoDegreesOfFreedom)
{
  // The services pass chi2(p, 3). A pair gated on x and y only is a 2-DOF test, so it gets chi2(p, 2) (9.21 at 0.99),
  // the gate before z tracking; a pair gated on x, y and z keeps chi2(p, 3) (11.34). S = I, d^2 = 10 between the two.
  const double chi2 = rv::chi2Threshold(0.99, 3);
  auto track = makePositionTrack(1.0, 0.0, 1.0);
  const auto between = makePerson(std::sqrt(10.0), 0.0);
  const auto inside = makePerson(std::sqrt(9.0), 0.0);

  EXPECT_EQ(assignedCount(track, between, DistanceType::PositionMahalanobis, chi2, 10.0), 0U) << "planar";
  EXPECT_EQ(assignedCount(track, inside, DistanceType::PositionMahalanobis, chi2, 10.0), 1U) << "planar";

  track.z_measured = true;
  auto measuredBetween = between;
  measuredBetween.z_measured = true;
  EXPECT_EQ(assignedCount(track, measuredBetween, DistanceType::PositionMahalanobis, chi2, 10.0), 1U) << "measured z";
}

TEST(ObjectMatchingTest, EuclideanGatesZOnlyWhenBothSidesMeasuredIt)
{
  // A detection 3 m above the track at the same x, y, with a 2 m gate: rejected only when both have measured z.
  rv::tracking::TrackedObject track = makePerson(1.0, 2.0);
  rv::tracking::TrackedObject above = track;
  above.z = 3.0;

  const struct
  {
    const char *name;
    bool trackZ, detectionZ;
    size_t expected;
  } cases[] = {{"planar track and detection", false, false, 1U},
               {"planar track", false, true, 1U},
               {"planar detection", true, false, 1U},
               {"both measured", true, true, 0U}};
  for (const auto &testCase : cases)
  {
    SCOPED_TRACE(testCase.name);
    track.z_measured = testCase.trackZ;
    above.z_measured = testCase.detectionZ;
    EXPECT_EQ(assignedCount(track, above, DistanceType::Euclidean, 2.0, 2.0), testCase.expected);
  }
}

TEST(ObjectMatchingTest, PositionMahalanobisNeverAssignsTrackWithDegenerateCovariance)
{
  // |det S| < 1e-12 on the x/y/z block (S_zz = 1 here, so det S_xy) gives the bound cost (1000), so the track is
  // not assigned below that threshold, not even a detection exactly at the prediction.
  struct Case
  {
    const char *name;
    double s00, s01, s11;
    size_t expected;
  };
  for (const auto &[name, s00, s01, s11, expected] : {Case{"zero", 0.0, 0.0, 0.0, 0U},
                                                      Case{"rank one", 1.0, 1.0, 1.0, 0U},
                                                      Case{"det 1e-14", 1e-7, 0.0, 1e-7, 0U},
                                                      Case{"det 1e-10", 1e-5, 0.0, 1e-5, 1U}})
  {
    SCOPED_TRACE(name);
    EXPECT_EQ(
      assignedCount(makePositionTrack(s00, s01, s11), makePerson(0.0, 0.0), DistanceType::PositionMahalanobis, 100.0),
      expected);
  }
}

TEST(ObjectMatchingTest, PositionMahalanobisNeverAssignsTrackWithNonSpdCovariance)
{
  // Indefinite / negative-definite S_xy used to invert and yield negative d^2 (always under any chi^2 gate, preferred
  // by Hungarian). Reject them the same way as a singular covariance.
  const double chi2 = rv::chi2Threshold(0.99, 2);
  struct Case
  {
    const char *name;
    double s00, s01, s11;
  };
  for (const auto &[name, s00, s01, s11] : {Case{"negative definite", -1.0, 0.0, -1.0},
                                            Case{"indefinite", 1.0, 2.0, 1.0},
                                            Case{"s00 negative", -0.2, 0.0, 0.2},
                                            Case{"non-finite", std::numeric_limits<double>::quiet_NaN(), 0.0, 1.0}})
  {
    SCOPED_TRACE(name);
    EXPECT_EQ(assignedCount(makePositionTrack(s00, s01, s11), makePerson(0.0, 0.0), DistanceType::PositionMahalanobis,
                            chi2),
              0U);
  }

  // ND track must not steal a far detection from a PSD track: before the fix, d^2 = -25 beat the PSD near cost.
  auto badTrack = makePositionTrack(-1.0, 0.0, -1.0);
  auto goodTrack = makePositionTrack(0.2, 0.0, 0.2);
  const auto assignments =
    matchedPairs({badTrack, goodTrack}, {makePerson(0.1, 0.0), makePerson(5.0, 0.0)}, DistanceType::PositionMahalanobis,
                 chi2, 10.0);
  EXPECT_EQ(assignments.size(), 1U);
  EXPECT_EQ(assignments.front().first, 1U);  // PSD track
  EXPECT_EQ(assignments.front().second, 0U); // near detection
}

} // namespace
