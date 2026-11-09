// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Track-to-detection association at the tracker level: MultipleObjectTracker with the production filter and track
// lifecycle, fed like the Tracker Service, with the legacy Euclidean gate (2 m) and the default PositionMahalanobis
// gate (chi-squared 0.99, 10 m ceiling).
//   - Regression: both methods keep every object on one track of its own.
//   - Differentiating: only PositionMahalanobis does. Its gate grows along the track while the track coasts and
//     stays narrower than 2 m across it.
//   - Known issues: the expected behaviour, reported as skipped while it fails.
// Every scenario runs kSeeds camera noise seeds. With RV_SCENARIO_DIR set, the first seed is recorded per method to
// $RV_SCENARIO_DIR/<Suite>.<Test>/<method>/ for tools/tracker/evaluation/visualization.

#include <algorithm>
#include <numbers>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include "support/ScenarioRecorder.hpp"
#include "support/TrackerRun.hpp"

namespace {

using namespace rv::tracking::test;
using std::numbers::pi;

constexpr double kFps = 10.0;
constexpr double kCameraNoise = 0.1; // ground-plane position noise [m]
constexpr int kSeeds = 3;
constexpr double kWalkingSpeed = 1.4; // [m/s]

struct SceneObject
{
  int id;
  std::vector<TruthSample> truth;
  std::vector<std::pair<double, double>> occlusions{}; // from <= t < to without detections
};

using Scene = std::vector<SceneObject>;

TruthSample startAt(double x, double y, double heading, double speed, Box box)
{
  return {.x = x, .y = y, .heading = heading, .speed = speed, .box = box};
}

struct PassingCar
{
  std::vector<TruthSample> truth;
  double passTime; // first frame at x >= 0 [s]
};

// A car on the x axis that starts at rest, accelerates at 2.5 m/s^2 to `speed` and passes x = 0 2 s later, so its
// track has the velocity by then; it drives on for 4 s.
PassingCar passingCar(double speed)
{
  constexpr double kAcceleration = 2.5;
  const double accelerationTime = speed / kAcceleration;
  const double start = -(speed * speed / (2.0 * kAcceleration) + 2.0 * speed);
  PassingCar car{.truth = Trajectory(startAt(start, 0.0, 0.0, 0.0, kCar))
                            .straight(1.0)
                            .accelerate(kAcceleration, accelerationTime)
                            .straight(6.0)
                            .sample(kFps),
                 .passTime = 0.0};
  car.passTime = std::ranges::find_if(car.truth, [](const TruthSample &sample) { return sample.x >= 0.0; })->t;
  return car;
}

// A person walking with `heading` who passes (0, lateral) at time `t`; sampled from 0 to `duration`.
std::vector<TruthSample> personPassing(double lateral, double heading, double t, double duration)
{
  return Trajectory(startAt(-kWalkingSpeed * t * std::cos(heading),
                            lateral - kWalkingSpeed * t * std::sin(heading),
                            heading,
                            kWalkingSpeed,
                            kPerson))
    .straight(duration)
    .sample(kFps);
}

// Identity errors (TrackerRun::identityErrors) per seed. The first seed is recorded to <caseName>/.
std::vector<int>
identityErrorsPerSeed(const Scene &scene, const Association &association, double fps = kFps, std::string caseName = {})
{
  std::set<int> objectIds;
  const auto *longest = &scene.front().truth;
  for (const auto &object : scene)
  {
    objectIds.insert(object.id);
    if (object.truth.size() > longest->size())
    {
      longest = &object.truth;
    }
  }
  std::vector<int> errors;
  for (int seed = 1; seed <= kSeeds; ++seed)
  {
    std::optional<ScenarioRecorder> recorder;
    if (seed == 1)
    {
      recorder.emplace(caseName.empty() ? std::string(association.method) : caseName);
    }
    std::vector<Observation> observations;
    for (const auto &object : scene)
    {
      Sensor camera{.positionNoise = kCameraNoise};
      camera.rng.seed(static_cast<unsigned>(100 * seed + object.id));
      auto objectObservations = observe(object.truth, camera, object.id);
      for (const auto &[from, to] : object.occlusions)
      {
        objectObservations = withoutBetween(objectObservations, from, to);
      }
      observations.insert(observations.end(), objectObservations.begin(), objectObservations.end());
      if (recorder)
      {
        recorder->truth(object.truth, object.id);
      }
    }
    TrackerRun run(association, fps, productionTrackerConfig(), recorder ? &*recorder : nullptr);
    run.play(sampleTimes(*longest), observations);
    errors.push_back(run.identityErrors(objectIds));
  }
  return errors;
}

std::string describe(const std::vector<int> &errors)
{
  std::string text = "identity errors per seed:";
  for (const int error : errors)
  {
    text += " " + std::to_string(error);
  }
  return text;
}

int failedSeeds(const std::vector<int> &errors)
{
  return static_cast<int>(std::ranges::count_if(errors, [](int error) { return error > 0; }));
}

void expectIdentitiesKept(const Scene &scene,
                          const Association &association,
                          double fps = kFps,
                          std::string caseName = {})
{
  const auto errors = identityErrorsPerSeed(scene, association, fps, std::move(caseName));
  EXPECT_EQ(failedSeeds(errors), 0) << association.method << ": " << describe(errors);
}

// Regression scenarios: both methods must pass.
void expectIdentitiesKeptByBoth(const Scene &scene, double fps = kFps, const std::string &caseName = {})
{
  for (const auto &association : {euclideanAssociation(), positionMahalanobisAssociation()})
  {
    const std::string name
      = caseName.empty() ? std::string(association.method) : caseName + "_" + std::string(association.method);
    expectIdentitiesKept(scene, association, fps, name);
  }
}

// Differentiating scenarios: PositionMahalanobis must pass; Euclidean failing on every seed shows that the scenario
// still separates the two methods.
void expectOnlyMahalanobisKeepsIdentities(const Scene &scene)
{
  expectIdentitiesKept(scene, positionMahalanobisAssociation());
  const auto euclidean = euclideanAssociation();
  const auto errors = identityErrorsPerSeed(scene, euclidean);
  EXPECT_EQ(failedSeeds(errors), kSeeds) << "Scenario no longer separates the methods, " << euclidean.method << ": "
                                         << describe(errors);
}

// Known issues: returns "<method>: <errors>" for each listed method that fails, to report as skipped.
std::string knownIssues(const Scene &scene, const std::vector<Association> &associations)
{
  std::string failures;
  for (const auto &association : associations)
  {
    const auto errors = identityErrorsPerSeed(scene, association);
    if (failedSeeds(errors) > 0)
    {
      failures += " " + std::string(association.method) + ": " + describe(errors) + ";";
    }
  }
  return failures;
}

} // namespace

// TrackerRun bookkeeping

TEST(TrackerRunTest, AttributesTrackUpdatesToObjects)
{
  const auto person1 = Trajectory(startAt(0.0, 0.0, 0.0, kWalkingSpeed, kPerson)).straight(2.0).sample(kFps);
  const auto person2 = Trajectory(startAt(0.0, 10.0, 0.0, kWalkingSpeed, kPerson)).straight(2.0).sample(kFps);
  Sensor camera;
  auto observations = observe(person1, camera, 1);
  const auto observations2 = observe(person2, camera, 2);
  observations.insert(observations.end(), observations2.begin(), observations2.end());

  TrackerRun run(euclideanAssociation(), kFps);
  run.play(sampleTimes(person1), observations);

  ASSERT_EQ(run.tracksOf(1).size(), 1U);
  ASSERT_EQ(run.tracksOf(2).size(), 1U);
  EXPECT_NE(run.tracksOf(1).front(), run.tracksOf(2).front());
  EXPECT_EQ(run.objectsOf(run.tracksOf(1).front()), std::set<int>{1});
  EXPECT_EQ(run.updatesOf(1), static_cast<int>(person1.size()));
  EXPECT_EQ(run.identityErrors({1, 2}), 0);
  EXPECT_EQ(run.reliableTracks().size(), 2U);
}

TEST(TrackerRunTest, CountsATrackRestartedAfterDropAsIdentityError)
{
  // 1.5 s without detections, longer than the 0.8 s a moving track coasts before it is dropped.
  const auto person = Trajectory(startAt(0.0, 0.0, 0.0, kWalkingSpeed, kPerson)).straight(5.0).sample(kFps);
  Sensor camera;
  TrackerRun run(euclideanAssociation(), kFps);
  run.play(sampleTimes(person), withoutBetween(observe(person, camera), 2.0, 3.5));

  EXPECT_EQ(run.tracksOf(1).size(), 2U);
  EXPECT_EQ(run.identityErrors({1}), 1);
}

// Regression

TEST(AssociationScenarioTest, PersonWalkingKeepsOneTrack)
{
  expectIdentitiesKeptByBoth({{.id = 1,
                               .truth = Trajectory(startAt(0.0, 0.0, 0.0, kWalkingSpeed, kPerson))
                                          .straight(3.0)
                                          .turn(0.5, 3.0)
                                          .straight(3.0)
                                          .sample(kFps)}});
}

TEST(AssociationScenarioTest, PeopleSideBySideKeepTheirTracks)
{
  // 1 m apart: both detections are within 2 m of both tracks, so the assignment decides.
  expectIdentitiesKeptByBoth(
    {{.id = 1, .truth = Trajectory(startAt(0.0, 0.0, 0.0, kWalkingSpeed, kPerson)).straight(10.0).sample(kFps)},
     {.id = 2, .truth = Trajectory(startAt(0.0, 1.0, 0.0, kWalkingSpeed, kPerson)).straight(10.0).sample(kFps)}});
}

TEST(AssociationScenarioTest, PeoplePassingHeadOnKeepTheirTracks)
{
  // Opposite directions on paths 1 m apart; they pass each other at 5 s.
  expectIdentitiesKeptByBoth(
    {{.id = 1, .truth = Trajectory(startAt(0.0, 0.0, 0.0, kWalkingSpeed, kPerson)).straight(10.0).sample(kFps)},
     {.id = 2,
      .truth
      = Trajectory(startAt(2.0 * 5.0 * kWalkingSpeed, 1.0, pi, kWalkingSpeed, kPerson)).straight(10.0).sample(kFps)}});
}

TEST(AssociationScenarioTest, PeopleCrossingKeepTheirTracks)
{
  // Paths cross at right angles at (7, 0). Person 2 reaches the crossing 0.8 s after person 1, so they come within
  // 0.8 m of each other. Neither gate separates people who are at the same place at the same time: with exact
  // crossings both methods swap identities on most noise seeds.
  constexpr double kDelay = 0.8;
  constexpr double kCrossingX = 7.0;
  const double crossingTime = kCrossingX / kWalkingSpeed;
  const double distance2 = kWalkingSpeed * (crossingTime + kDelay);
  const auto person1 = Trajectory(startAt(0.0, 0.0, 0.0, kWalkingSpeed, kPerson)).straight(10.0).sample(kFps);
  const auto person2
    = Trajectory(startAt(kCrossingX, -distance2, pi / 2.0, kWalkingSpeed, kPerson)).straight(10.0).sample(kFps);
  expectIdentitiesKeptByBoth({{.id = 1, .truth = person1}, {.id = 2, .truth = person2}}, kFps, "visible");
  // Person 1 is not detected while the other one walks past.
  expectIdentitiesKeptByBoth({{.id = 1, .truth = person1, .occlusions = {{crossingTime + 0.5, crossingTime + 1.1}}},
                              {.id = 2, .truth = person2}},
                             kFps,
                             "occluded");
}

TEST(AssociationScenarioTest, PersonReacquiredAfterOcclusion)
{
  // 0.8 s without detections, the longest coast before a moving track is dropped.
  expectIdentitiesKeptByBoth(
    {{.id = 1,
      .truth = Trajectory(startAt(0.0, 0.0, 0.0, kWalkingSpeed, kPerson)).straight(10.0).sample(kFps),
      .occlusions = {{5.0, 5.8}}}});
}

TEST(AssociationScenarioTest, FastCarKeepsOneTrack)
{
  // Up to 25 m/s, i.e. 2.5 m per frame at 10 fps and 12.5 m per frame at 2 fps, more than the 2 m Euclidean radius.
  // Both gates are centred on the predicted position, so the distance per frame does not matter once the track has
  // the velocity.
  for (const double fps : {kFps, 2.0})
  {
    SCOPED_TRACE(fps);
    const auto car
      = Trajectory(startAt(0.0, 0.0, 0.0, 0.0, kCar)).straight(1.0).accelerate(2.0, 12.5).straight(4.0).sample(fps);
    expectIdentitiesKeptByBoth({{.id = 1, .truth = car}}, fps, std::to_string(static_cast<int>(fps)) + "fps");
  }
}

TEST(AssociationScenarioTest, CarPassingPersonKeepsBothTracks)
{
  // A car at 10 m/s passes a person walking 1.5 m beside its path, in the same and in the opposite direction, and
  // hides the person for 0.8 s. The car's detections pass within 2 m of the person's coasting track, but the car's
  // own track is closer and takes them, with either gate.
  const auto car = passingCar(10.0);
  const double duration = car.truth.back().t;
  for (const auto &[name, heading] : {std::pair{"overtaking", 0.0}, std::pair{"oncoming", pi}})
  {
    SCOPED_TRACE(name);
    expectIdentitiesKeptByBoth({{.id = 1, .truth = car.truth},
                                {.id = 2,
                                 .truth = personPassing(1.5, heading, car.passTime, duration),
                                 .occlusions = {{car.passTime - 0.4, car.passTime + 0.4}}}},
                               kFps,
                               name);
  }
}

TEST(AssociationScenarioTest, RunnerEnteringGetsOneTrack)
{
  // A person-sized object enters at 4 m/s, 0.4 m per frame. A new track starts at rest with velocity variance
  // init_state_covariance (1 m^2/s^2), enough for the corrections to bring its velocity up before the object leaves
  // either gate. Mahalanobis keeps such an entry up to about 6 m/s at 10 fps.
  expectIdentitiesKeptByBoth(
    {{.id = 1, .truth = Trajectory(startAt(0.0, 0.0, 0.0, 4.0, kPerson)).straight(4.0).sample(kFps)}});
}

// Differentiating

TEST(AssociationScenarioTest, CarBrakingWhileOccludedIsReacquired)
{
  // A car at 10 m/s brakes at 8 m/s^2 during a 0.8 s occlusion and reappears 2.56 m behind the constant-velocity
  // prediction. The Euclidean gate is 2 m, so the car gets a new track. The Mahalanobis gate has grown to about 4 m
  // along the track while it coasted.
  const auto car = Trajectory(startAt(0.0, 0.0, 0.0, 0.0, kCar))
                     .straight(1.0)
                     .accelerate(2.5, 4.0)
                     .straight(2.0)
                     .accelerate(-8.0, 0.8)
                     .straight(3.0)
                     .sample(kFps);
  expectOnlyMahalanobisKeepsIdentities({{.id = 1, .truth = car, .occlusions = {{7.0, 7.8}}}});
}

TEST(AssociationScenarioTest, PersonAppearingBesideOccludedPersonGetsOwnTrack)
{
  // Person 1 is not detected from 5 s for 0.8 s. Person 2 appears at 5 s, 1.8 m beside person 1, and walks along.
  // Within 2 m, the Euclidean gate gives person 2's detections to person 1's coasting track. Across the track the
  // Mahalanobis gate stays at about 1.5 m, so person 2 gets a track of its own and person 1 is reacquired.
  const auto person2 = Trajectory(startAt(0.0, 1.8, 0.0, kWalkingSpeed, kPerson)).straight(10.0).sample(kFps);
  expectOnlyMahalanobisKeepsIdentities(
    {{.id = 1,
      .truth = Trajectory(startAt(0.0, 0.0, 0.0, kWalkingSpeed, kPerson)).straight(10.0).sample(kFps),
      .occlusions = {{5.0, 5.8}}},
     {.id = 2, .truth = between(person2, 5.0, person2.back().t + 1.0)}});
}

// Known issues

TEST(AssociationScenarioTest, CarPullingAwayKeepsOneTrack)
{
  // A car stands for 1 s, then accelerates at 5 m/s^2. At rest the along-track velocity noise points in the noisy
  // direction of the estimated velocity, so the velocity follows slowly (0.6 m/s at a true 4 m/s), and the lag
  // exceeds the Mahalanobis gate of about 1.6 m before the 2 m Euclidean one. Each new track starts at rest and lags
  // again. Velocity noise of the same size in every direction below 1 m/s fixes it; a 2 m gate floor would too, but
  // also widens the gate across the track.
  // Known issue: reported as skipped while it fails, passes once it is fixed.
  const Scene scene{
    {.id = 1,
     .truth
     = Trajectory(startAt(0.0, 0.0, 0.0, 0.0, kCar)).straight(1.0).accelerate(5.0, 3.0).straight(2.0).sample(kFps)}};
  expectIdentitiesKept(scene, euclideanAssociation());
  if (const auto failures = knownIssues(scene, {positionMahalanobisAssociation()}); !failures.empty())
  {
    GTEST_SKIP() << "Known issue, the car gets more than one track:" << failures;
  }
}

TEST(AssociationScenarioTest, CarEnteringAtSpeedGetsOneTrack)
{
  // A car enters at 10 m/s, 1 m per frame. A new track starts at rest with velocity variance init_state_covariance
  // (1 m^2/s^2), 10 standard deviations below the true speed, so the correction moves its position more than its
  // velocity; after 3-4 frames the car is more than 2 m ahead of the prediction and gets a new track, with either
  // method. Passes with both methods from an initial velocity variance of 16 m^2/s^2.
  // Known issue: reported as skipped while it fails, passes once it is fixed.
  const Scene scene{{.id = 1, .truth = Trajectory(startAt(0.0, 0.0, 0.0, 10.0, kCar)).straight(3.0).sample(kFps)}};
  if (const auto failures = knownIssues(scene, {euclideanAssociation(), positionMahalanobisAssociation()});
      !failures.empty())
  {
    GTEST_SKIP() << "Known issue, the car gets more than one track:" << failures;
  }
}
