// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Deterministic replay of a scripted scene through TrackingWorker, with every published track
// written as exact text (hexfloat), to compare two tracker configurations bit for bit. With
// TRACKER_REPLAY_GOLDEN=<file> the default configuration's replay is also written to <file>, to be
// compared with `cmp` across a change.

#include <gtest/gtest.h>

#include "logger.hpp"
#include "time_utils.hpp"
#include "tracking_worker.hpp"

#include <rv/tracking/MultipleObjectTracker.hpp>
#include <rv/tracking/TrackManager.hpp>

#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <format>
#include <fstream>
#include <map>
#include <mutex>
#include <random>
#include <string>
#include <thread>
#include <vector>

namespace tracker {
namespace {

constexpr int kFrames = 80;
constexpr double kFrameS = 0.1;
constexpr double kCameraHeightM = 12.0; // the whole scene stays inside the image
constexpr double kFx = 905.0;
constexpr double kCx = 640.0;
constexpr double kCy = 360.0;
constexpr int kCameras = 2;

std::unordered_map<std::string, Camera> make_cameras() {
    std::unordered_map<std::string, Camera> cameras;
    for (int index = 1; index <= kCameras; ++index) {
        Camera camera;
        camera.uid = std::format("cam-{}", index);
        camera.name = camera.uid;
        camera.intrinsics = {kFx, kFx, kCx, kCy, {0.0, 0.0, 0.0, 0.0}};
        camera.extrinsics.translation = {0.0, 0.0, kCameraHeightM};
        camera.extrinsics.rotation = {180.0, 0.0, 0.0}; // straight down
        camera.extrinsics.scale = {1.0, 1.0, 1.0};
        cameras.emplace(camera.uid, camera);
    }
    return cameras;
}

// The foot point of a person at (x, y) metres from the camera axis as the bottom centre of a pixel
// box.
Detection person_at(double x, double y, int id, std::mt19937& rng) {
    std::normal_distribution<double> noise(0.0, 1.5);
    const double u = kCx + kFx * x / kCameraHeightM + noise(rng);
    const double v = kCy + kFx * y / kCameraHeightM + noise(rng);
    constexpr float kWidthPx = 40.0F;
    constexpr float kHeightPx = 100.0F;
    return Detection{.id = id,
                     .bounding_box_px = {static_cast<float>(u) - kWidthPx / 2.0F,
                                         static_cast<float>(v) - kHeightPx, kWidthPx, kHeightPx},
                     .confidence = 0.9};
}

int wait_processed(const TrackingWorker& worker, int expected) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(30);
    while (worker.processed_count() < expected && std::chrono::steady_clock::now() < deadline) {
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    return worker.processed_count();
}

std::string exact(double value) {
    return std::format("{:a}", value);
}

// Two people crossing seen by two cameras; the first is occluded for a second. Published tracks,
// one line each, with track ids replaced by their order of first appearance (they are random
// UUIDs).
std::vector<std::string> replay(const TrackingConfig& config) {
    std::mutex mutex;
    std::vector<std::string> lines;
    std::map<std::string, int> ids;
    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mutex);
        for (const auto& track : tracks) {
            const int id = ids.emplace(track.id, static_cast<int>(ids.size())).first->second;
            std::string line = std::format("id={}", id);
            for (const double value : track.translation) {
                line += " " + exact(value);
            }
            for (const double value : track.velocity) {
                line += " " + exact(value);
            }
            for (const double value : track.size) {
                line += " " + exact(value);
            }
            for (const double value : track.rotation) {
                line += " " + exact(value);
            }
            if (track.association_window) {
                const auto& window = *track.association_window;
                line += " " + window.method + " " + window.shape;
                for (const auto& value : {window.radius_m, window.semi_major_m, window.semi_minor_m,
                                          window.angle_rad}) {
                    line += " " + (value ? exact(*value) : std::string("-"));
                }
            }
            lines.push_back(std::move(line));
        }
        lines.push_back("frame");
    };

    TrackingScope scope{"scene-1", "person"};
    {
        TrackingWorker worker(scope, "Replay Scene", kFrames + 1, callback, config, make_cameras());
        std::mt19937 rng(7);
        const auto start =
            std::chrono::system_clock::time_point{} + std::chrono::hours(24 * 365 * 56);
        for (int frame = 0; frame < kFrames; ++frame) {
            const double t = (frame + 1) * kFrameS;
            const auto timestamp = start + std::chrono::milliseconds(static_cast<long>(t * 1000.0));
            Chunk chunk;
            chunk.scene_id = scope.scene_id;
            chunk.category = scope.category;
            chunk.chunk_time = std::chrono::steady_clock::now();
            for (int camera = 1; camera <= kCameras; ++camera) {
                DetectionBatch batch;
                batch.camera_id = std::format("cam-{}", camera);
                batch.timestamp = timestamp;
                batch.timestamp_iso = formatTimestamp(timestamp);
                const bool occluded = t >= 3.0 && t < 4.0;
                if (!occluded) {
                    batch.detections.push_back(person_at(-4.0 + 0.9 * t, 0.0, 1, rng));
                }
                batch.detections.push_back(person_at(0.5, -3.0 + 0.75 * t, 2, rng));
                chunk.camera_batches.push_back(std::move(batch));
            }
            EXPECT_TRUE(worker.try_enqueue(std::move(chunk)));
        }
        EXPECT_EQ(wait_processed(worker, kFrames), kFrames);
    }
    return lines;
}

TrackingConfig euclidean_config() {
    TrackingConfig config;
    config.association.method = AssociationMethod::Euclidean;
    config.association.max_radius_m = 2.0;
    return config;
}

TrackingConfig mahalanobis_config() {
    TrackingConfig config;
    config.association.method = AssociationMethod::PositionMahalanobis;
    config.association.gate_probability = 0.99;
    config.association.max_radius_m = 10.0;
    return config;
}

class TrackingReplayTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init(std::getenv("TRACKER_REPLAY_LOG") ? "debug" : "warn"); }
    void TearDown() override { Logger::shutdown(); }
};

FilterConfig production_filter() {
    return {.process_noise = rv::tracking::kProductionProcessNoise,
            .base_measurement_noise = rv::tracking::kProductionMeasurementNoise,
            .init_state_covariance = rv::tracking::kProductionInitStateCovariance};
}

// The production values written out give the very same tracks, to the last bit, as the defaults.
TEST_F(TrackingReplayTest, ProductionFilterWrittenOutIsBitIdenticalToTheDefaults) {
    for (const auto& config : {euclidean_config(), mahalanobis_config()}) {
        auto explicit_config = config;
        explicit_config.filter = production_filter();
        explicit_config.association.birth_cluster_radius_m =
            rv::tracking::kDefaultBirthClusterRadiusM;
        const auto defaults = replay(config);
        EXPECT_GT(defaults.size(), static_cast<size_t>(kFrames));
        EXPECT_EQ(replay(explicit_config), defaults);
    }
}

// Not only plumbing: every setting changes the tracks.
TEST_F(TrackingReplayTest, OtherFilterValuesChangeTheTracks) {
    const auto defaults = replay(mahalanobis_config());
    for (const auto& filter :
         {FilterConfig{.process_noise = 1e-3}, FilterConfig{.base_measurement_noise = 1.0},
          FilterConfig{.init_state_covariance = 16.0}}) {
        auto config = mahalanobis_config();
        config.filter = filter;
        EXPECT_NE(replay(config), defaults);
    }
}

// Two cameras see one new object 3 m apart: the birth radius decides whether it is one track or
// two.
size_t tracks_born_from_two_cameras(double birth_cluster_radius_m, bool set) {
    std::mutex mutex;
    size_t track_count = 0;
    PublishCallback callback = [&](const std::string&, const std::string&, const std::string&,
                                   const std::string&, const std::vector<Track>& tracks) {
        std::lock_guard lock(mutex);
        track_count = tracks.size();
    };
    auto config = euclidean_config();
    config.max_unreliable_time_s = 0.0; // reliable at once
    if (set) {
        config.association.birth_cluster_radius_m = birth_cluster_radius_m;
    }
    TrackingScope scope{"scene-1", "person"};
    {
        TrackingWorker worker(scope, "Birth Scene", 2, callback, config, make_cameras());
        std::mt19937 rng(7);
        const auto timestamp =
            std::chrono::system_clock::time_point{} + std::chrono::hours(24 * 365 * 56);
        Chunk chunk;
        chunk.scene_id = scope.scene_id;
        chunk.category = scope.category;
        chunk.chunk_time = std::chrono::steady_clock::now();
        for (int camera = 1; camera <= kCameras; ++camera) {
            DetectionBatch batch;
            batch.camera_id = std::format("cam-{}", camera);
            batch.timestamp = timestamp;
            batch.timestamp_iso = formatTimestamp(timestamp);
            batch.detections.push_back(person_at(camera == 1 ? 0.0 : 3.0, 0.0, camera, rng));
            chunk.camera_batches.push_back(std::move(batch));
        }
        EXPECT_TRUE(worker.try_enqueue(std::move(chunk)));
        EXPECT_EQ(wait_processed(worker, 1), 1);
    }
    return track_count;
}

TEST_F(TrackingReplayTest, BirthClusterRadiusDecidesWhetherCamerasShareATrack) {
    EXPECT_EQ(tracks_born_from_two_cameras(0.0, false), 2U) << "default: 2 m";
    EXPECT_EQ(tracks_born_from_two_cameras(2.0, true), 2U);
    EXPECT_EQ(tracks_born_from_two_cameras(3.5, true), 1U);
    EXPECT_EQ(tracks_born_from_two_cameras(0.0, true), 2U);
}

TEST_F(TrackingReplayTest, WritesGoldenWhenRequested) {
    const char* path = std::getenv("TRACKER_REPLAY_GOLDEN");
    if (path == nullptr) {
        GTEST_SKIP() << "TRACKER_REPLAY_GOLDEN not set";
    }
    std::ofstream golden(path);
    ASSERT_TRUE(golden.is_open()) << "cannot open " << path;
    for (const auto& [name, config] : {std::pair{"euclidean", euclidean_config()},
                                       std::pair{"position_mahalanobis", mahalanobis_config()}}) {
        for (const auto& line : replay(config)) {
            golden << name << ' ' << line << '\n';
        }
    }
    golden.close();
    EXPECT_FALSE(golden.fail()) << "incomplete write to " << path;
}

} // namespace
} // namespace tracker
