// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "ptz_pose_parser.hpp"

#include "ptz_time.hpp"

#include <array>
#include <cmath>
#include <fstream>
#include <stdexcept>

#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>
#include <rapidjson/schema.h>

namespace tracker::ptz {

namespace {

constexpr size_t kMatrixSize = 4;
constexpr std::array<const char*, 2> kFiniteScalars = {"sample_age_s", "timestamp_uncertainty_s"};
constexpr std::array<const char*, 4> kQualityFields = {"score", "temporal_score",
                                                       "calibration_score", "reprojection_rms_px"};

std::shared_ptr<const rapidjson::SchemaDocument> loadSchema(const std::filesystem::path& path) {
    std::ifstream ifs(path);
    if (!ifs.is_open()) {
        throw std::runtime_error("Failed to open PTZ schema: " + path.string());
    }
    rapidjson::IStreamWrapper isw(ifs);
    rapidjson::Document doc;
    doc.ParseStream(isw);
    if (doc.HasParseError()) {
        throw std::runtime_error("Failed to parse PTZ schema: " + path.string());
    }
    return std::make_shared<const rapidjson::SchemaDocument>(doc);
}

bool matchesSchema(const rapidjson::Document& doc, const rapidjson::SchemaDocument& schema) {
    rapidjson::SchemaValidator validator(schema);
    return doc.Accept(validator);
}

bool finiteFields(const rapidjson::Value& object, const auto& fields) {
    for (const char* key : fields) {
        auto it = object.FindMember(key);
        if (it != object.MemberEnd() &&
            (!it->value.IsNumber() || !std::isfinite(it->value.GetDouble()))) {
            return false;
        }
    }
    return true;
}

/// Rigid scene_from_camera matrix: finite, last row [0,0,0,1], orthonormal, det > 0.
std::optional<cv::Matx44d> rigidMatrix(const rapidjson::Value& rows) {
    if (!rows.IsArray() || rows.Size() != kMatrixSize) {
        return std::nullopt;
    }
    cv::Matx44d matrix;
    for (rapidjson::SizeType r = 0; r < kMatrixSize; ++r) {
        const auto& row = rows[r];
        if (!row.IsArray() || row.Size() != kMatrixSize) {
            return std::nullopt;
        }
        for (rapidjson::SizeType c = 0; c < kMatrixSize; ++c) {
            if (!row[c].IsNumber() || !std::isfinite(row[c].GetDouble())) {
                return std::nullopt;
            }
            matrix(r, c) = row[c].GetDouble();
        }
    }
    constexpr std::array<double, 4> kLastRow = {0.0, 0.0, 0.0, 1.0};
    for (int c = 0; c < 4; ++c) {
        if (std::abs(matrix(3, c) - kLastRow[c]) > kRigidTolerance) {
            return std::nullopt;
        }
    }
    const cv::Matx33d rotation(matrix(0, 0), matrix(0, 1), matrix(0, 2), matrix(1, 0), matrix(1, 1),
                               matrix(1, 2), matrix(2, 0), matrix(2, 1), matrix(2, 2));
    const cv::Matx33d gram = rotation * rotation.t();
    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 3; ++c) {
            if (std::abs(gram(r, c) - (r == c ? 1.0 : 0.0)) > kRigidTolerance) {
                return std::nullopt;
            }
        }
    }
    if (cv::determinant(rotation) <= 0.0) {
        return std::nullopt;
    }
    return matrix;
}

std::optional<std::string> optionalString(const rapidjson::Value& object, const char* key) {
    auto it = object.FindMember(key);
    if (it == object.MemberEnd() || !it->value.IsString()) {
        return std::nullopt;
    }
    return std::string(it->value.GetString(), it->value.GetStringLength());
}

std::optional<int64_t> timestampNs(const rapidjson::Value& object, const char* key) {
    auto it = object.FindMember(key);
    if (it == object.MemberEnd() || !it->value.IsString()) {
        return std::nullopt;
    }
    return parseIsoTimestampNs({it->value.GetString(), it->value.GetStringLength()});
}

/// Fill the snapshot from schema-valid fields; false when a field cannot be interpreted.
bool fillSnapshot(const rapidjson::Document& doc, PoseSnapshot& pose) {
    auto timestamp = timestampNs(doc, "timestamp");
    auto valid_until = timestampNs(doc, "valid_until");
    auto motion = parseMotionState(doc["motion_state"].GetString());
    if (!timestamp || !valid_until || !motion || !doc["sequence"].IsInt64()) {
        return false;
    }
    pose.source_id = doc["source_id"].GetString();
    pose.sequence = doc["sequence"].GetInt64();
    pose.timestamp_ns = *timestamp;
    pose.valid_until_ns = *valid_until;
    pose.timestamp_uncertainty_ns = secondsToNs(doc["timestamp_uncertainty_s"].GetDouble());
    pose.valid = doc["valid"].GetBool();
    pose.motion_state = *motion;
    pose.calibration_version = doc["calibration_version"].GetString();
    if (auto reason = optionalString(doc, "invalid_reason")) {
        pose.invalid_reason = parseInvalidReason(*reason).value_or(InvalidReason::InvalidPose);
    }
    if (auto detail = optionalString(doc, "reason_detail")) {
        auto parsed = parseReasonDetail(*detail);
        if (!parsed) {
            return false;
        }
        pose.reason_detail = *parsed;
    }
    auto pose_it = doc.FindMember("pose");
    if (pose_it != doc.MemberEnd() && pose_it->value.IsObject()) {
        pose.frame_id = optionalString(pose_it->value, "frame_id");
    }
    return true;
}

} // namespace

const char* toString(PoseRejectStage stage) {
    switch (stage) {
        case PoseRejectStage::Size:
            return "size";
        case PoseRejectStage::Json:
            return "json";
        case PoseRejectStage::Schema:
            return "schema";
        case PoseRejectStage::Guard:
            return "guard";
        case PoseRejectStage::Topic:
            return "topic";
        case PoseRejectStage::Unmanaged:
            return "unmanaged";
    }
    return "unknown";
}

PtzMessageParser::PtzMessageParser(const std::filesystem::path& schema_dir)
    : pose_schema_(loadSchema(schema_dir / kPoseContextSchemaFile)),
      status_schema_(loadSchema(schema_dir / kPositioningStatusSchemaFile)) {}

PoseParseResult PtzMessageParser::parsePose(std::string_view payload) const {
    if (payload.size() > kMaxPoseContextBytes) {
        return {nullptr, PoseRejectStage::Size};
    }
    rapidjson::Document doc;
    if (doc.Parse(payload.data(), payload.size()).HasParseError()) {
        return {nullptr, PoseRejectStage::Json};
    }
    if (!matchesSchema(doc, *pose_schema_)) {
        return {nullptr, PoseRejectStage::Schema};
    }

    std::optional<cv::Matx44d> matrix;
    bool guards_pass = finiteFields(doc, kFiniteScalars);
    auto quality = doc.FindMember("quality");
    if (guards_pass && quality != doc.MemberEnd() && quality->value.IsObject()) {
        guards_pass = finiteFields(quality->value, kQualityFields);
    }
    if (guards_pass && doc["valid"].GetBool()) {
        matrix = rigidMatrix(doc["pose"]["matrix_4x4"]);
        guards_pass = matrix.has_value();
    }
    if (!guards_pass) {
        return {nullptr, PoseRejectStage::Guard};
    }

    auto pose = std::make_shared<PoseSnapshot>();
    if (!fillSnapshot(doc, *pose)) {
        return {nullptr, PoseRejectStage::Schema};
    }
    if (matrix) {
        pose->view = PoseView::fromRigidMatrix(*matrix);
    }
    return {std::move(pose), std::nullopt};
}

StatusParseResult PtzMessageParser::parseStatus(std::string_view payload) const {
    if (payload.size() > kMaxStatusBytes) {
        return {std::nullopt, PoseRejectStage::Size};
    }
    rapidjson::Document doc;
    if (doc.Parse(payload.data(), payload.size()).HasParseError()) {
        return {std::nullopt, PoseRejectStage::Json};
    }
    if (!matchesSchema(doc, *status_schema_)) {
        return {std::nullopt, PoseRejectStage::Schema};
    }
    auto session = timestampNs(doc, "timestamp");
    if (!session) {
        return {std::nullopt, PoseRejectStage::Schema};
    }
    return {ParsedStatus{doc["resolver_id"].GetString(),
                         std::string_view(doc["status"].GetString()) == "online", *session},
            std::nullopt};
}

} // namespace tracker::ptz
