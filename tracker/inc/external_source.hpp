// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "scene_loader.hpp"
#include "tracking_types.hpp"

#include <chrono>
#include <list>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include <opencv2/core.hpp>

namespace tracker {

inline constexpr double kDefaultExternalSourceTtlSeconds = 30.0;
inline constexpr size_t kDefaultExternalSourceSweepChunkSize = 500;

inline constexpr const char* kReasonNoPoseAvailable = "no_pose_available";
inline constexpr const char* kReasonPoseExpired = "pose_expired";
inline constexpr const char* kReasonSceneGeoreferenceUnavailable = "scene_georeference_unavailable";
inline constexpr const char* kReasonUntrustedScenePose = "untrusted_scene_pose";
inline constexpr const char* kReasonUnsupportedReferenceFrame = "unsupported_reference_frame";
inline constexpr const char* kReasonInvalidPose = "invalid_pose";
inline constexpr const char* kReasonIdentityCollision = "identity_collision";

struct PoseResolution {
    std::optional<cv::Matx44d> source_to_scene;
    std::string reason;
};

std::array<double, 3> convertLlaToEcef(const std::array<double, 3>& lla);
TrsMatrix calculateTrsLocalToEcef(const std::array<std::array<double, 3>, 4>& map_corners,
                                  const std::array<std::array<double, 3>, 4>& lla_corners,
                                  double z_shift = 2.0);
std::array<double, 3> transformExternalPoint(const cv::Matx44d& source_to_scene,
                                             const std::array<double, 3>& point);

class ExternalSourcePoseCache {
public:
    explicit ExternalSourcePoseCache(double ttl_seconds = kDefaultExternalSourceTtlSeconds,
                                     size_t sweep_chunk_size = kDefaultExternalSourceSweepChunkSize,
                                     double sweep_grace_seconds = 0.0);

    PoseResolution resolve(const Scene& scene, const std::string& source_id,
                           const std::optional<ExternalPose>& pose,
                           std::chrono::system_clock::time_point when, bool trusted_scene_pose);

    std::vector<std::string> scenesWithLiveCache(const std::string& source_id,
                                                 std::chrono::system_clock::time_point when) const;

    size_t sweepExpired(std::chrono::system_clock::time_point now);

private:
    struct Key {
        std::string scene_id;
        std::string source_id;
        bool operator==(const Key&) const = default;
    };

    struct KeyHash {
        size_t operator()(const Key& key) const noexcept;
    };

    struct CachedPose {
        cv::Matx44d source_to_scene;
        std::chrono::system_clock::time_point when;
        std::chrono::system_clock::time_point expires_at;
    };

    using CacheEntries = std::list<std::pair<Key, CachedPose>>;
    using CacheIndex = std::unordered_map<Key, CacheEntries::iterator, KeyHash>;

    PoseResolution resolveFromCache(const Key& key,
                                    std::chrono::system_clock::time_point when) const;

    std::chrono::system_clock::duration ttl_;
    std::chrono::system_clock::duration sweep_grace_;
    size_t sweep_chunk_size_;
    mutable std::mutex mutex_;
    CacheEntries cache_entries_;
    CacheIndex cache_index_;
};

class IdentityClaimRegistry {
public:
    explicit IdentityClaimRegistry(double ttl_seconds = kDefaultExternalSourceTtlSeconds,
                                   size_t sweep_chunk_size = kDefaultExternalSourceSweepChunkSize,
                                   double sweep_grace_seconds = 0.0);

    std::pair<bool, std::string> claim(const std::string& scene_id, const std::string& category,
                                       const std::string& source_id, const std::string& object_id,
                                       std::chrono::system_clock::time_point when);

    size_t sweepExpired(std::chrono::system_clock::time_point now);

private:
    struct Key {
        std::string scene_id;
        std::string category;
        std::string object_id;
        bool operator==(const Key&) const = default;
    };

    struct KeyHash {
        size_t operator()(const Key& key) const noexcept;
    };

    struct Claim {
        std::string source_id;
        std::chrono::system_clock::time_point when;
        std::chrono::system_clock::time_point expires_at;
    };

    using ClaimEntries = std::list<std::pair<Key, Claim>>;
    using ClaimIndex = std::unordered_map<Key, ClaimEntries::iterator, KeyHash>;

    std::chrono::system_clock::duration ttl_;
    std::chrono::system_clock::duration sweep_grace_;
    size_t sweep_chunk_size_;
    std::mutex mutex_;
    ClaimEntries claim_entries_;
    ClaimIndex claim_index_;
};

} // namespace tracker