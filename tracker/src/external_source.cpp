// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "external_source.hpp"

#include "scene_geospatial.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

#include <opencv2/calib3d.hpp>

namespace tracker {

namespace {

constexpr double kMatrixEpsilon = 1e-12;

std::chrono::system_clock::duration secondsToClockDuration(double seconds) {
    if (!std::isfinite(seconds) || seconds <= 0.0) {
        throw std::invalid_argument("External-source duration must be finite and greater than 0");
    }
    return std::chrono::duration_cast<std::chrono::system_clock::duration>(
        std::chrono::duration<double>(seconds));
}

cv::Matx44d toMatrix(const std::array<std::array<double, 4>, 4>& values) {
    cv::Matx44d matrix;
    for (int row = 0; row < 4; ++row) {
        for (int column = 0; column < 4; ++column) {
            const double value = values[static_cast<size_t>(row)][static_cast<size_t>(column)];
            if (!std::isfinite(value)) {
                throw std::invalid_argument("TRS matrix contains a non-finite value");
            }
            matrix(row, column) = value;
        }
    }
    return matrix;
}

bool finite(const std::array<double, 3>& values) {
    return std::all_of(values.begin(), values.end(),
                       [](double value) { return std::isfinite(value); });
}

bool finiteMatrix(const cv::Matx44d& matrix) {
    return std::all_of(matrix.val, matrix.val + 16,
                       [](double value) { return std::isfinite(value); });
}

std::optional<cv::Matx33d> quaternionToRotation(const std::array<double, 4>& quaternion) {
    if (!std::all_of(quaternion.begin(), quaternion.end(),
                     [](double value) { return std::isfinite(value); })) {
        return std::nullopt;
    }
    const double norm = std::sqrt(quaternion[0] * quaternion[0] + quaternion[1] * quaternion[1] +
                                  quaternion[2] * quaternion[2] + quaternion[3] * quaternion[3]);
    if (norm <= kMatrixEpsilon) {
        return std::nullopt;
    }

    const double x = quaternion[0] / norm;
    const double y = quaternion[1] / norm;
    const double z = quaternion[2] / norm;
    const double w = quaternion[3] / norm;
    return cv::Matx33d(1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w),
                       2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w),
                       2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y));
}

std::optional<cv::Matx44d> makePoseMatrix(const std::array<double, 3>& translation,
                                          const std::array<double, 4>& quaternion) {
    if (!finite(translation)) {
        return std::nullopt;
    }
    const auto rotation = quaternionToRotation(quaternion);
    if (!rotation.has_value()) {
        return std::nullopt;
    }
    return cv::Matx44d((*rotation)(0, 0), (*rotation)(0, 1), (*rotation)(0, 2), translation[0],
                       (*rotation)(1, 0), (*rotation)(1, 1), (*rotation)(1, 2), translation[1],
                       (*rotation)(2, 0), (*rotation)(2, 1), (*rotation)(2, 2), translation[2], 0.0,
                       0.0, 0.0, 1.0);
}

size_t combineHash(size_t left, size_t right) {
    return left ^ (right + 0x9e3779b97f4a7c15ULL + (left << 6U) + (left >> 2U));
}

} // namespace

std::array<double, 3> transformExternalPoint(const cv::Matx44d& source_to_scene,
                                             const std::array<double, 3>& point) {
    const cv::Vec4d transformed = source_to_scene * cv::Vec4d(point[0], point[1], point[2], 1.0);
    return {transformed[0], transformed[1], transformed[2]};
}

ExternalSourcePoseCache::ExternalSourcePoseCache(double ttl_seconds, size_t sweep_chunk_size,
                                                 double sweep_grace_seconds)
    : ttl_(secondsToClockDuration(ttl_seconds)),
      sweep_grace_(
          secondsToClockDuration(sweep_grace_seconds > 0.0 ? sweep_grace_seconds : kMatrixEpsilon)),
      sweep_chunk_size_(sweep_chunk_size) {
    if (sweep_chunk_size_ == 0) {
        throw std::invalid_argument("External-source sweep chunk size must be greater than 0");
    }
    if (sweep_grace_seconds == 0.0) {
        sweep_grace_ = std::chrono::system_clock::duration::zero();
    }
}

size_t ExternalSourcePoseCache::KeyHash::operator()(const Key& key) const noexcept {
    return combineHash(std::hash<std::string>{}(key.scene_id),
                       std::hash<std::string>{}(key.source_id));
}

PoseResolution
ExternalSourcePoseCache::resolveFromCache(const Key& key,
                                          std::chrono::system_clock::time_point when) const {
    const auto cached = cache_index_.find(key);
    if (cached == cache_index_.end()) {
        return {.reason = kReasonNoPoseAvailable};
    }
    if (when > cached->second->second.expires_at) {
        return {.reason = kReasonPoseExpired};
    }
    return {.source_to_scene = cached->second->second.source_to_scene};
}

PoseResolution ExternalSourcePoseCache::resolve(const Scene& scene, const std::string& source_id,
                                                const std::optional<ExternalPose>& pose,
                                                std::chrono::system_clock::time_point when,
                                                bool trusted_scene_pose) {
    const Key key{scene.uid, source_id};
    std::lock_guard lock(mutex_);
    if (!pose.has_value()) {
        return resolveFromCache(key, when);
    }

    auto existing = cache_index_.find(key);
    if (existing != cache_index_.end() && when < existing->second->second.when) {
        return resolveFromCache(key, when);
    }

    std::array<double, 3> translation{};
    if (pose->reference_frame == "scene") {
        if (!trusted_scene_pose) {
            return {.reason = kReasonUntrustedScenePose};
        }
        translation = pose->position;
    } else if (pose->reference_frame == "wgs84") {
        if (!scene.trs_matrix.has_value()) {
            return {.reason = kReasonSceneGeoreferenceUnavailable};
        }
        try {
            const auto scene_to_ecef = toMatrix(*scene.trs_matrix);
            cv::Matx44d ecef_to_scene;
                if (std::abs(cv::invert(scene_to_ecef, ecef_to_scene, cv::DECOMP_LU)) <=
                    kMatrixEpsilon ||
                !finiteMatrix(ecef_to_scene)) {
                return {.reason = kReasonSceneGeoreferenceUnavailable};
            }
            const auto ecef = convertLlaToEcef(pose->position);
            translation = transformExternalPoint(ecef_to_scene, ecef);
        } catch (const std::invalid_argument&) {
            return {.reason = kReasonInvalidPose};
        }
    } else {
        return {.reason = kReasonUnsupportedReferenceFrame};
    }

    const auto source_to_scene = makePoseMatrix(translation, pose->rotation);
    if (!source_to_scene.has_value()) {
        return {.reason = kReasonInvalidPose};
    }
    if (existing != cache_index_.end()) {
        existing->second->second = CachedPose{*source_to_scene, when, when + ttl_};
        cache_entries_.splice(cache_entries_.end(), cache_entries_, existing->second);
    } else {
        cache_entries_.emplace_back(key, CachedPose{*source_to_scene, when, when + ttl_});
        auto entry = std::prev(cache_entries_.end());
        try {
            cache_index_.emplace(key, entry);
        } catch (...) {
            cache_entries_.erase(entry);
            throw;
        }
    }
    return {.source_to_scene = source_to_scene};
}

std::vector<std::string>
ExternalSourcePoseCache::scenesWithLiveCache(const std::string& source_id,
                                             std::chrono::system_clock::time_point when) const {
    std::vector<std::string> scene_ids;
    std::lock_guard lock(mutex_);
    for (const auto& [key, cached] : cache_entries_) {
        if (key.source_id == source_id && when <= cached.expires_at) {
            scene_ids.push_back(key.scene_id);
        }
    }
    return scene_ids;
}

size_t ExternalSourcePoseCache::sweepExpired(std::chrono::system_clock::time_point now) {
    std::vector<Key> snapshot;
    {
        std::lock_guard lock(mutex_);
        snapshot.reserve(cache_entries_.size());
        for (const auto& entry : cache_entries_) {
            snapshot.push_back(entry.first);
        }
    }

    size_t evicted = 0;
    for (size_t begin = 0; begin < snapshot.size();) {
        const size_t end = begin + std::min(sweep_chunk_size_, snapshot.size() - begin);
        {
            std::lock_guard lock(mutex_);
            for (size_t index = begin; index < end; ++index) {
                const auto indexed = cache_index_.find(snapshot[index]);
                if (indexed == cache_index_.end()) {
                    continue;
                }
                const auto entry = indexed->second;
                if (now > entry->second.expires_at + sweep_grace_) {
                    cache_index_.erase(indexed);
                    cache_entries_.erase(entry);
                    ++evicted;
                }
            }
        }
        begin = end;
    }
    return evicted;
}

IdentityClaimRegistry::IdentityClaimRegistry(double ttl_seconds, size_t sweep_chunk_size,
                                             double sweep_grace_seconds)
    : ttl_(secondsToClockDuration(ttl_seconds)),
      sweep_grace_(
          secondsToClockDuration(sweep_grace_seconds > 0.0 ? sweep_grace_seconds : kMatrixEpsilon)),
      sweep_chunk_size_(sweep_chunk_size) {
    if (sweep_chunk_size_ == 0) {
        throw std::invalid_argument("Identity sweep chunk size must be greater than 0");
    }
    if (sweep_grace_seconds == 0.0) {
        sweep_grace_ = std::chrono::system_clock::duration::zero();
    }
}

size_t IdentityClaimRegistry::KeyHash::operator()(const Key& key) const noexcept {
    size_t result = std::hash<std::string>{}(key.scene_id);
    result = combineHash(result, std::hash<std::string>{}(key.category));
    return combineHash(result, std::hash<std::string>{}(key.object_id));
}

std::pair<bool, std::string>
IdentityClaimRegistry::claim(const std::string& scene_id, const std::string& category,
                             const std::string& source_id, const std::string& object_id,
                             std::chrono::system_clock::time_point when) {
    const Key key{scene_id, category, object_id};
    std::lock_guard lock(mutex_);
    auto existing = claim_index_.find(key);
    if (existing != claim_index_.end() && existing->second->second.source_id != source_id &&
        when <= existing->second->second.expires_at) {
        return {false, kReasonIdentityCollision};
    }
    if (existing != claim_index_.end() && existing->second->second.source_id == source_id &&
        when < existing->second->second.when) {
        return {true, {}};
    }
    if (existing != claim_index_.end()) {
        existing->second->second = Claim{source_id, when, when + ttl_};
        claim_entries_.splice(claim_entries_.end(), claim_entries_, existing->second);
    } else {
        claim_entries_.emplace_back(key, Claim{source_id, when, when + ttl_});
        auto entry = std::prev(claim_entries_.end());
        try {
            claim_index_.emplace(key, entry);
        } catch (...) {
            claim_entries_.erase(entry);
            throw;
        }
    }
    return {true, {}};
}

size_t IdentityClaimRegistry::sweepExpired(std::chrono::system_clock::time_point now) {
    std::vector<Key> snapshot;
    {
        std::lock_guard lock(mutex_);
        snapshot.reserve(claim_entries_.size());
        for (const auto& entry : claim_entries_) {
            snapshot.push_back(entry.first);
        }
    }

    size_t evicted = 0;
    for (size_t begin = 0; begin < snapshot.size();) {
        const size_t end = begin + std::min(sweep_chunk_size_, snapshot.size() - begin);
        {
            std::lock_guard lock(mutex_);
            for (size_t index = begin; index < end; ++index) {
                const auto indexed = claim_index_.find(snapshot[index]);
                if (indexed == claim_index_.end()) {
                    continue;
                }
                const auto entry = indexed->second;
                if (now > entry->second.expires_at + sweep_grace_) {
                    claim_index_.erase(indexed);
                    claim_entries_.erase(entry);
                    ++evicted;
                }
            }
        }
        begin = end;
    }
    return evicted;
}

} // namespace tracker