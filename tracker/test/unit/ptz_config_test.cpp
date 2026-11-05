// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "config_loader.hpp"
#include "env_vars.hpp"
#include "ptz_config.hpp"
#include "utils/scoped_env.hpp"

#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <string>
#include <unistd.h>

namespace tracker {
namespace {

using test::ScopedEnv;

constexpr const char* kBounds = R"("max_pose_age_s": 0.5, "max_clock_offset_s": 0.05,
    "max_detection_pipeline_latency_s": 1.0, "max_detection_timestamp_uncertainty_s": 0.05)";

class TempJson {
public:
    explicit TempJson(const std::string& content) {
        path_ = std::filesystem::temp_directory_path() /
                ("tracker_ptz_test_" + std::to_string(::getpid()) + "_" +
                 std::to_string(counter_++) + ".json");
        std::ofstream(path_) << content;
    }
    ~TempJson() { std::filesystem::remove(path_); }
    [[nodiscard]] const std::filesystem::path& path() const { return path_; }

private:
    std::filesystem::path path_;
    static inline int counter_ = 0;
};

std::string serviceConfig(const std::string& ptz_block, bool with_ntp = true) {
    return std::string(R"({"infrastructure": {"mqtt": {"host": "broker", "port": 1883})") +
           (with_ntp ? R"(, "ntp": {"server": "ntpserv"})" : "") +
           R"(}, "scenes": {"source": "file", "file_path": "scenes.json"})" +
           (ptz_block.empty() ? "" : ", \"ptz\": " + ptz_block) + "}";
}

ServiceConfig load(const std::string& content) {
    TempJson file(content);
    return load_config(file.path(), std::string(TRACKER_SCHEMA_DIR) + "/config.schema.json");
}

TEST(PtzConfigTest, OffByDefaultWithoutRequiredValues) {
    const auto config = load(serviceConfig(""));
    EXPECT_EQ(config.ptz.mode(), PtzMode::Off);
    EXPECT_FALSE(config.ptz.max_pose_age_s.has_value());
    EXPECT_EQ(config.ptz.assignments_path, kDefaultPtzAssignmentsPath);
    EXPECT_EQ(config.ptz.shadow.sample_every_n, kDefaultPtzShadowSampleEveryN);
    EXPECT_EQ(config.ptz.shadow.run_id, kDefaultPtzShadowRunId);
    EXPECT_FALSE(config.ptz.shadow.per_decision);
}

TEST(PtzConfigTest, DefaultTrackerJsonKeepsPtzOff) {
    const auto config = load_config(std::string(TRACKER_CONFIG_DIR) + "/tracker.json",
                                    std::string(TRACKER_SCHEMA_DIR) + "/config.schema.json");
    EXPECT_EQ(config.ptz.mode(), PtzMode::Off);
}

TEST(PtzConfigTest, ParsesEnforcingConfiguration) {
    const auto config = load(serviceConfig(std::string(R"({"enabled": true, )") + kBounds +
                                           R"(, "assignments_path": "/a.json",
              "shadow": {"run_id": "run-1", "sample_every_n": 3, "per_decision": true}})"));
    EXPECT_EQ(config.ptz.mode(), PtzMode::Enforce);
    EXPECT_DOUBLE_EQ(config.ptz.max_pose_age_s.value(), 0.5);
    EXPECT_DOUBLE_EQ(config.ptz.max_clock_offset_s.value(), 0.05);
    EXPECT_DOUBLE_EQ(config.ptz.max_detection_pipeline_latency_s.value(), 1.0);
    EXPECT_DOUBLE_EQ(config.ptz.max_detection_timestamp_uncertainty_s.value(), 0.05);
    EXPECT_EQ(config.ptz.assignments_path, "/a.json");
    EXPECT_EQ(config.ptz.shadow.run_id, "run-1");
    EXPECT_EQ(config.ptz.shadow.sample_every_n, 3);
    EXPECT_TRUE(config.ptz.shadow.per_decision);
}

TEST(PtzConfigTest, EnvironmentOverridesEveryValue) {
    ScopedEnv shadow(env::PTZ_SHADOW_MODE, "true");
    ScopedEnv age(env::PTZ_MAX_POSE_AGE_S, "0.7");
    ScopedEnv offset(env::PTZ_MAX_CLOCK_OFFSET_S, "0.1");
    ScopedEnv latency(env::PTZ_MAX_DETECTION_PIPELINE_LATENCY_S, "2");
    ScopedEnv uncertainty(env::PTZ_MAX_DETECTION_TIMESTAMP_UNCERTAINTY_S, "0");
    ScopedEnv path(env::PTZ_ASSIGNMENTS_PATH, "/env.json");
    ScopedEnv run(env::PTZ_SHADOW_RUN_ID, "env.run");
    ScopedEnv every(env::PTZ_SHADOW_SAMPLE_EVERY_N, "1");
    ScopedEnv per(env::PTZ_SHADOW_PER_DECISION, "yes");
    const auto config = load(serviceConfig(""));
    EXPECT_EQ(config.ptz.mode(), PtzMode::Shadow);
    EXPECT_DOUBLE_EQ(config.ptz.max_pose_age_s.value(), 0.7);
    EXPECT_DOUBLE_EQ(config.ptz.max_clock_offset_s.value(), 0.1);
    EXPECT_DOUBLE_EQ(config.ptz.max_detection_pipeline_latency_s.value(), 2.0);
    EXPECT_DOUBLE_EQ(config.ptz.max_detection_timestamp_uncertainty_s.value(), 0.0);
    EXPECT_EQ(config.ptz.assignments_path, "/env.json");
    EXPECT_EQ(config.ptz.shadow.run_id, "env.run");
    EXPECT_EQ(config.ptz.shadow.sample_every_n, 1);
    EXPECT_TRUE(config.ptz.shadow.per_decision);
}

TEST(PtzConfigTest, EnvironmentCanDisableAJsonEnabledMode) {
    ScopedEnv enabled(env::PTZ_ENABLED, "false");
    const auto config = load(serviceConfig(R"({"enabled": true})"));
    EXPECT_EQ(config.ptz.mode(), PtzMode::Off);
}

TEST(PtzConfigTest, ModesAreMutuallyExclusive) {
    EXPECT_THROW(load(serviceConfig(std::string(R"({"enabled": true, "shadow_mode": true, )") +
                                    kBounds + "}")),
                 std::runtime_error);
}

TEST(PtzConfigTest, ActiveModeRequiresEveryBound) {
    for (const char* missing :
         {"max_pose_age_s", "max_clock_offset_s", "max_detection_pipeline_latency_s",
          "max_detection_timestamp_uncertainty_s"}) {
        std::string bounds = kBounds;
        const auto at = bounds.find(std::string("\"") + missing + "\"");
        const auto end = bounds.find_first_of(",", at);
        bounds.erase(at, end == std::string::npos ? std::string::npos : end - at + 1);
        while (!bounds.empty() && (bounds.back() == ',' || bounds.back() == ' ')) {
            bounds.pop_back();
        }
        EXPECT_THROW(load(serviceConfig("{\"enabled\": true, " + bounds + "}")), std::runtime_error)
            << missing;
    }
}

TEST(PtzConfigTest, RejectsNonPositiveBounds) {
    ScopedEnv age(env::PTZ_MAX_POSE_AGE_S, "0");
    EXPECT_THROW(load(serviceConfig(std::string(R"({"enabled": true, )") + kBounds + "}")),
                 std::runtime_error);
}

TEST(PtzConfigTest, RequiresNtpWhenActive) {
    ScopedEnv ntp(env::NTP_SERVER, std::nullopt);
    EXPECT_THROW(
        load(serviceConfig(std::string(R"({"shadow_mode": true, )") + kBounds + "}", false)),
        std::runtime_error);
}

TEST(PtzConfigTest, RejectsInvalidEnvironmentValues) {
    {
        ScopedEnv bad(env::PTZ_MAX_POSE_AGE_S, "abc");
        EXPECT_THROW(load(serviceConfig("")), std::runtime_error);
    }
    {
        ScopedEnv bad(env::PTZ_MAX_POSE_AGE_S, "inf");
        EXPECT_THROW(load(serviceConfig("")), std::runtime_error);
    }
    {
        ScopedEnv bad(env::PTZ_ENABLED, "maybe");
        EXPECT_THROW(load(serviceConfig("")), std::runtime_error);
    }
    {
        ScopedEnv bad(env::PTZ_SHADOW_SAMPLE_EVERY_N, "2x");
        EXPECT_THROW(load(serviceConfig("")), std::runtime_error);
    }
    {
        ScopedEnv bad(env::PTZ_SHADOW_SAMPLE_EVERY_N, "notanumber");
        EXPECT_THROW(load(serviceConfig("")), std::runtime_error);
    }
}

TEST(PtzConfigTest, ValidatesShadowSettingsWhenActive) {
    const std::string active = std::string(R"({"enabled": true, )") + kBounds + "}";
    {
        ScopedEnv run(env::PTZ_SHADOW_RUN_ID, "bad id!");
        EXPECT_THROW(load(serviceConfig(active)), std::runtime_error);
    }
    {
        ScopedEnv every(env::PTZ_SHADOW_SAMPLE_EVERY_N, "0");
        EXPECT_THROW(load(serviceConfig(active)), std::runtime_error);
    }
    {
        ScopedEnv path(env::PTZ_ASSIGNMENTS_PATH, std::nullopt);
        EXPECT_THROW(
            load(serviceConfig(std::string(R"({"enabled": true, "assignments_path": "", )") +
                               kBounds + "}")),
            std::runtime_error);
    }
}

TEST(PtzConfigTest, SchemaRejectsUnknownPtzKeys) {
    EXPECT_THROW(load(serviceConfig(R"({"enabled": false, "unknown": 1})")), std::runtime_error);
}

// --- Assignment manifest ---

TEST(PtzAssignmentsTest, ParsesManifestAndIgnoresComments) {
    const auto assignments =
        ptz::parseAssignments(R"({"$comment": "x", "cam-a": "positioning", "cam-b": "r2"})");
    EXPECT_EQ(assignments.size(), 2u);
    EXPECT_EQ(assignments.at("cam-a"), "positioning");
    EXPECT_EQ(assignments.at("cam-b"), "r2");
}

TEST(PtzAssignmentsTest, RejectsInvalidManifests) {
    for (const char* text : {"[]", "{", R"({"cam": 1})", R"({"cam/x": "r"})", R"({"cam": "r+"})",
                             R"({"": "r"})", R"({"cam": "#"})"}) {
        EXPECT_THROW(ptz::parseAssignments(text), std::runtime_error) << text;
    }
    EXPECT_THROW(ptz::parseAssignments(R"({"cam": ")" + std::string(257, 'r') + "\"}"),
                 std::runtime_error);
}

TEST(PtzAssignmentsTest, LoadsFromFileAndReportsUnreadableFiles) {
    TempJson file(R"({"cam": "positioning"})");
    EXPECT_EQ(ptz::loadAssignments(file.path()).at("cam"), "positioning");
    EXPECT_THROW(ptz::loadAssignments("/nonexistent/assignments.json"), std::runtime_error);
    TempJson bad("not json");
    EXPECT_THROW(ptz::loadAssignments(bad.path()), std::runtime_error);
}

TEST(PtzAssignmentsTest, RepositoryManifestIsValid) {
    EXPECT_NO_THROW(ptz::loadAssignments(std::string(TRACKER_CONFIG_DIR) +
                                         "/../../deployment/positioning-assignments.json"));
}

} // namespace
} // namespace tracker
