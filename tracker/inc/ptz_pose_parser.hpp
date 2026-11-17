// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "ptz_dwell.hpp"

#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <string_view>

#include <rapidjson/fwd.h>

namespace tracker::ptz {

inline constexpr size_t kMaxPoseContextBytes = 4096;
inline constexpr size_t kMaxStatusBytes = 1024;
inline constexpr double kRigidTolerance = 1e-6;

inline constexpr const char* kPoseContextSchemaFile = "pose-context.schema.json";
inline constexpr const char* kPositioningStatusSchemaFile = "positioning-status.schema.json";

/// Bounded label values for tracker.ptz.pose_messages.rejected (same as the Controller).
enum class PoseRejectStage : uint8_t {
    Size,
    Json,
    Schema,
    Guard,
    Topic,
    Unmanaged
};

[[nodiscard]] const char* toString(PoseRejectStage stage);

struct ParsedStatus {
    std::string resolver_id;
    bool online = false;
    int64_t session_ns = 0;
};

struct PoseParseResult {
    PoseSnapshotPtr pose;                 ///< Set when the payload passed every check
    std::optional<PoseRejectStage> stage; ///< Set when the payload was rejected
};

struct StatusParseResult {
    std::optional<ParsedStatus> status;
    std::optional<PoseRejectStage> stage;
};

/**
 * @brief Validates untrusted PoseContext and resolver status payloads.
 *
 * Order: size bound → JSON parse → draft-04 schema → guards JSON Schema cannot express
 * (finite numbers, rigid row-major 4x4 matrix) → timestamp parsing. A valid pose gets its
 * PoseView precomputed here, once per PoseContext. Thread-safe (const, stateless).
 */
class PtzMessageParser {
public:
    /// @throws std::runtime_error when a schema file is missing or invalid
    explicit PtzMessageParser(const std::filesystem::path& schema_dir);

    [[nodiscard]] PoseParseResult parsePose(std::string_view payload) const;
    [[nodiscard]] StatusParseResult parseStatus(std::string_view payload) const;

private:
    std::shared_ptr<const rapidjson::SchemaDocument> pose_schema_;
    std::shared_ptr<const rapidjson::SchemaDocument> status_schema_;
};

} // namespace tracker::ptz
