// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "config_loader.hpp"
#include "logger.hpp"
#include "scene_loader.hpp"
#include "scene_parser.hpp"

#include "utils/mock_manager_rest_client.hpp"

#include <filesystem>
#include <fstream>
#include <gtest/gtest.h>

namespace tracker {
namespace {

using ::testing::_;
using ::testing::Return;

// ---------------------------------------------------------------------------
// RAII temp file helper
// ---------------------------------------------------------------------------
class TempFile {
public:
    TempFile(const std::string& content, const std::string& suffix = ".json") {
        path_ = std::filesystem::temp_directory_path() /
                ("api_test_" + std::to_string(counter_++) + suffix);
        std::ofstream ofs(path_);
        ofs << content;
    }

    ~TempFile() { std::filesystem::remove(path_); }

    const std::filesystem::path& path() const { return path_; }

private:
    std::filesystem::path path_;
    static inline int counter_ = 0;
};

// ---------------------------------------------------------------------------
// Helper: create a mock client factory returning a pre-configured mock
// ---------------------------------------------------------------------------
ManagerClientFactory make_mock_factory(const std::string& scenes_response) {
    return [scenes_response](const ManagerConfig&) -> std::unique_ptr<IManagerRestClient> {
        auto mock = std::make_unique<test::MockManagerRestClient>();
        EXPECT_CALL(*mock, authenticate(_, _)).Times(1);
        EXPECT_CALL(*mock, fetchScenes()).WillOnce(Return(scenes_response));
        return mock;
    };
}

// ---------------------------------------------------------------------------
// Factory-level tests for create_scene_loader with SceneSource::Api
// ---------------------------------------------------------------------------

TEST(ApiSceneLoaderTest, FactoryRequiresManagerConfig) {
    ScenesConfig config;
    config.source = SceneSource::Api;

    // No manager config provided -> should throw
    EXPECT_THROW(create_scene_loader(config, "/tmp", std::nullopt, "/tmp"), std::runtime_error);
}

TEST(ApiSceneLoaderTest, FactoryRequiresSchemaDir) {
    ScenesConfig config;
    config.source = SceneSource::Api;

    ManagerConfig mgr;
    mgr.url = "https://localhost:443";
    mgr.auth_path = "/tmp/nonexistent-auth.json";

    // Empty schema_dir -> should throw with clear message
    EXPECT_THROW(create_scene_loader(config, "/tmp", mgr, ""), std::runtime_error);
}

TEST(ApiSceneLoaderTest, FactoryCreatesLoaderWithManagerConfig) {
    ScenesConfig config;
    config.source = SceneSource::Api;

    ManagerConfig mgr;
    mgr.url = "https://localhost:443";
    mgr.auth_path = "/tmp/nonexistent-auth.json";

    // Should return a valid loader (auth file doesn't need to exist yet)
    auto loader = create_scene_loader(config, "/tmp", mgr, "/tmp");
    ASSERT_NE(loader, nullptr);
}

TEST(ApiSceneLoaderTest, LoadFailsWithInvalidAuthFile) {
    ScenesConfig config;
    config.source = SceneSource::Api;

    ManagerConfig mgr;
    mgr.url = "https://localhost:443";
    mgr.auth_path = "/tmp/nonexistent-auth-file.json";

    auto loader = create_scene_loader(config, "/tmp", mgr, "/tmp");
    EXPECT_THROW(loader->load(), std::runtime_error);
}

TEST(ApiSceneLoaderTest, LoadFailsWithMalformedAuthFile) {
    TempFile auth_file("not valid json");

    ScenesConfig config;
    config.source = SceneSource::Api;

    ManagerConfig mgr;
    mgr.url = "https://localhost:443";
    mgr.auth_path = auth_file.path().string();

    auto loader = create_scene_loader(config, "/tmp", mgr, "/tmp");
    EXPECT_THROW(loader->load(), std::runtime_error);
}

TEST(ApiSceneLoaderTest, LoadFailsWithMissingUserField) {
    TempFile auth_file(R"({"password": "pass123"})");

    ScenesConfig config;
    config.source = SceneSource::Api;

    ManagerConfig mgr;
    mgr.url = "https://localhost:443";
    mgr.auth_path = auth_file.path().string();

    auto loader = create_scene_loader(config, "/tmp", mgr, "/tmp");
    EXPECT_THROW(loader->load(), std::runtime_error);
}

TEST(ApiSceneLoaderTest, LoadFailsWithMissingPasswordField) {
    TempFile auth_file(R"({"user": "admin"})");

    ScenesConfig config;
    config.source = SceneSource::Api;

    ManagerConfig mgr;
    mgr.url = "https://localhost:443";
    mgr.auth_path = auth_file.path().string();

    auto loader = create_scene_loader(config, "/tmp", mgr, "/tmp");
    EXPECT_THROW(loader->load(), std::runtime_error);
}

// ---------------------------------------------------------------------------
// File-mode factory tests (regression)
// ---------------------------------------------------------------------------

TEST(ApiSceneLoaderTest, FileSourceStillWorksWithDefaultParams) {
    ScenesConfig config;
    config.source = SceneSource::File;
    config.file_path = "/nonexistent/scenes.json";

    auto loader = create_scene_loader(config, "/tmp");
    ASSERT_NE(loader, nullptr);
    // Should throw because file doesn't exist (not because of factory issues)
    EXPECT_THROW(loader->load(), std::runtime_error);
}

TEST(ApiSceneLoaderTest, FileSourceMissingFilePathThrows) {
    ScenesConfig config;
    config.source = SceneSource::File;

    EXPECT_THROW(create_scene_loader(config, "/tmp"), std::runtime_error);
}

// ---------------------------------------------------------------------------
// detail::read_auth_file tests
// ---------------------------------------------------------------------------

TEST(ReadAuthFileTest, ValidAuthFile) {
    TempFile auth_file(R"({"user": "admin", "password": "secret123"})");
    auto [user, pass] = detail::read_auth_file(auth_file.path().string());
    EXPECT_EQ(user, "admin");
    EXPECT_EQ(pass, "secret123");
}

TEST(ReadAuthFileTest, MissingFileThrows) {
    EXPECT_THROW(detail::read_auth_file("/nonexistent/auth.json"), std::runtime_error);
}

TEST(ReadAuthFileTest, InvalidJsonThrows) {
    TempFile auth_file("{not json");
    EXPECT_THROW(detail::read_auth_file(auth_file.path().string()), std::runtime_error);
}

TEST(ReadAuthFileTest, MissingUserFieldThrows) {
    TempFile auth_file(R"({"password": "pass"})");
    EXPECT_THROW(detail::read_auth_file(auth_file.path().string()), std::runtime_error);
}

TEST(ReadAuthFileTest, MissingPasswordFieldThrows) {
    TempFile auth_file(R"({"user": "admin"})");
    EXPECT_THROW(detail::read_auth_file(auth_file.path().string()), std::runtime_error);
}

TEST(ReadAuthFileTest, NonStringUserThrows) {
    TempFile auth_file(R"({"user": 123, "password": "pass"})");
    EXPECT_THROW(detail::read_auth_file(auth_file.path().string()), std::runtime_error);
}

TEST(ReadAuthFileTest, NonStringPasswordThrows) {
    TempFile auth_file(R"({"user": "admin", "password": true})");
    EXPECT_THROW(detail::read_auth_file(auth_file.path().string()), std::runtime_error);
}

TEST(ReadAuthFileTest, AuthFileWithWhitespace) {
    TempFile auth_file(R"({"user": "admin", "password": "pass123"}   
)");
    auto [user, pass] = detail::read_auth_file(auth_file.path().string());
    EXPECT_EQ(user, "admin");
    EXPECT_EQ(pass, "pass123");
}

// ---------------------------------------------------------------------------
// detail::transform_camera_to_schema tests
// ---------------------------------------------------------------------------

TEST(TransformCameraTest, FlatFieldsToNestedExtrinsics) {
    const char* json = R"({
        "uid": "cam1", "name": "cam1",
        "translation": [1.0, 2.0, 3.0],
        "rotation": [10.0, 20.0, 30.0],
        "scale": [1.0, 1.0, 1.0]
    })";
    rapidjson::Document doc;
    doc.Parse(json);
    auto& alloc = doc.GetAllocator();

    detail::transform_camera_to_schema(doc, alloc);

    ASSERT_TRUE(doc.HasMember("extrinsics"));
    auto& ext = doc["extrinsics"];
    ASSERT_TRUE(ext.HasMember("translation"));
    EXPECT_DOUBLE_EQ(ext["translation"][0].GetDouble(), 1.0);
    EXPECT_DOUBLE_EQ(ext["translation"][1].GetDouble(), 2.0);
    EXPECT_DOUBLE_EQ(ext["translation"][2].GetDouble(), 3.0);
    ASSERT_TRUE(ext.HasMember("rotation"));
    ASSERT_TRUE(ext.HasMember("scale"));
}

TEST(TransformCameraTest, AlreadyNestedExtrinsicsUnchanged) {
    const char* json = R"({
        "uid": "cam1", "name": "cam1",
        "extrinsics": {
            "translation": [1.0, 2.0, 3.0],
            "rotation": [10.0, 20.0, 30.0],
            "scale": [1.0, 1.0, 1.0]
        }
    })";
    rapidjson::Document doc;
    doc.Parse(json);
    auto& alloc = doc.GetAllocator();

    detail::transform_camera_to_schema(doc, alloc);

    // extrinsics should be unchanged
    EXPECT_DOUBLE_EQ(doc["extrinsics"]["translation"][0].GetDouble(), 1.0);
}

TEST(TransformCameraTest, DistortionMovedInsideIntrinsics) {
    const char* json = R"({
        "uid": "cam1", "name": "cam1",
        "distortion": {"k1": 0.1, "k2": 0.2, "p1": 0.01, "p2": 0.02},
        "translation": [1.0, 2.0, 3.0],
        "rotation": [10.0, 20.0, 30.0],
        "scale": [1.0, 1.0, 1.0]
    })";
    rapidjson::Document doc;
    doc.Parse(json);
    auto& alloc = doc.GetAllocator();

    detail::transform_camera_to_schema(doc, alloc);

    ASSERT_TRUE(doc.HasMember("intrinsics"));
    ASSERT_TRUE(doc["intrinsics"].HasMember("distortion"));
    EXPECT_DOUBLE_EQ(doc["intrinsics"]["distortion"]["k1"].GetDouble(), 0.1);
}

TEST(TransformCameraTest, DistortionMergesIntoExistingIntrinsics) {
    const char* json = R"({
        "uid": "cam1", "name": "cam1",
        "intrinsics": {"fx": 500.0},
        "distortion": {"k1": 0.1, "k2": 0.2, "p1": 0.01, "p2": 0.02},
        "translation": [1.0, 2.0, 3.0],
        "rotation": [10.0, 20.0, 30.0],
        "scale": [1.0, 1.0, 1.0]
    })";
    rapidjson::Document doc;
    doc.Parse(json);
    auto& alloc = doc.GetAllocator();

    detail::transform_camera_to_schema(doc, alloc);

    ASSERT_TRUE(doc["intrinsics"].HasMember("distortion"));
    EXPECT_DOUBLE_EQ(doc["intrinsics"]["distortion"]["k1"].GetDouble(), 0.1);
    // Original fx should still be there
    EXPECT_DOUBLE_EQ(doc["intrinsics"]["fx"].GetDouble(), 500.0);
}

TEST(TransformCameraTest, DistortionAlreadyInsideIntrinsicsUnchanged) {
    const char* json = R"({
        "uid": "cam1", "name": "cam1",
        "intrinsics": {"distortion": {"k1": 0.5}},
        "distortion": {"k1": 0.9},
        "translation": [1.0, 2.0, 3.0],
        "rotation": [10.0, 20.0, 30.0],
        "scale": [1.0, 1.0, 1.0]
    })";
    rapidjson::Document doc;
    doc.Parse(json);
    auto& alloc = doc.GetAllocator();

    detail::transform_camera_to_schema(doc, alloc);

    // Should keep the existing intrinsics.distortion (not overwrite)
    EXPECT_DOUBLE_EQ(doc["intrinsics"]["distortion"]["k1"].GetDouble(), 0.5);
}

// ---------------------------------------------------------------------------
// detail::transform_api_scenes tests
// ---------------------------------------------------------------------------

TEST(TransformApiScenesTest, TransformsArrayOfScenes) {
    const char* json = R"([{
        "uid": "scene1", "name": "Scene 1",
        "cameras": [{
            "uid": "cam1", "name": "cam1",
            "translation": [1.0, 2.0, 3.0],
            "rotation": [10.0, 20.0, 30.0],
            "scale": [1.0, 1.0, 1.0]
        }]
    }])";
    rapidjson::Document doc;
    doc.Parse(json);

    detail::transform_api_scenes(doc);

    ASSERT_TRUE(doc[0]["cameras"][0].HasMember("extrinsics"));
    EXPECT_DOUBLE_EQ(doc[0]["cameras"][0]["extrinsics"]["translation"][0].GetDouble(), 1.0);
}

TEST(TransformApiScenesTest, NonArrayInputIsNoOp) {
    rapidjson::Document doc;
    doc.SetObject();
    detail::transform_api_scenes(doc);
    EXPECT_TRUE(doc.IsObject());
}

TEST(TransformApiScenesTest, SceneWithNoCamerasIsSkipped) {
    const char* json = R"([{"uid": "scene1", "name": "Scene 1"}])";
    rapidjson::Document doc;
    doc.Parse(json);

    detail::transform_api_scenes(doc);
    // No crash, no cameras added
    EXPECT_FALSE(doc[0].HasMember("cameras"));
}

// ---------------------------------------------------------------------------
// detail::validate_scenes tests
// ---------------------------------------------------------------------------

class ValidateScenesTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }

    std::filesystem::path schema_path_ =
        std::filesystem::path(TRACKER_SCHEMA_DIR) / "scene.schema.json";
};

TEST_F(ValidateScenesTest, ValidScenePasses) {
    const char* json = R"([{
        "uid": "3bc091c7-e449-46a0-9540-29c499bca18c",
        "name": "Retail",
        "cameras": [{
            "uid": "camera1", "name": "camera1",
            "intrinsics": {
                "fx": 571.26, "fy": 571.26, "cx": 320.0, "cy": 240.0,
                "distortion": {"k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0}
            },
            "extrinsics": {
                "translation": [2.665, 1.008, 2.604],
                "rotation": [-137.859, -19.441, -15.385],
                "scale": [1.0, 1.0, 1.0]
            }
        }]
    }])";
    rapidjson::Document doc;
    doc.Parse(json);

    auto result = detail::validate_scenes(doc, schema_path_);
    EXPECT_EQ(result.GetArray().Size(), 1);
}

TEST_F(ValidateScenesTest, InvalidSceneSkipped) {
    // Missing required "uid" field — scene should be skipped, not throw
    const char* json = R"([{"name": "Bad Scene", "cameras": []}])";
    rapidjson::Document doc;
    doc.Parse(json);

    auto result = detail::validate_scenes(doc, schema_path_);
    EXPECT_EQ(result.GetArray().Size(), 0);
}

TEST_F(ValidateScenesTest, MixOfValidAndInvalidScenes) {
    // First scene is invalid (missing uid), second is valid
    const char* json = R"([
        {"name": "Bad Scene"},
        {
            "uid": "valid-uid",
            "name": "Good Scene",
            "cameras": [{
                "uid": "cam1", "name": "cam1",
                "intrinsics": {
                    "fx": 571.26, "fy": 571.26, "cx": 320.0, "cy": 240.0,
                    "distortion": {"k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0}
                },
                "extrinsics": {
                    "translation": [2.665, 1.008, 2.604],
                    "rotation": [-137.859, -19.441, -15.385],
                    "scale": [1.0, 1.0, 1.0]
                }
            }]
        }
    ])";
    rapidjson::Document doc;
    doc.Parse(json);

    auto result = detail::validate_scenes(doc, schema_path_);
    EXPECT_EQ(result.GetArray().Size(), 1);
    EXPECT_STREQ(result[0]["name"].GetString(), "Good Scene");
}

TEST_F(ValidateScenesTest, EmptyArrayReturnsEmpty) {
    rapidjson::Document doc;
    doc.SetArray();

    auto result = detail::validate_scenes(doc, schema_path_);
    EXPECT_EQ(result.GetArray().Size(), 0);
}

TEST(ValidateScenesTest_NoFixture, MissingSchemaFileThrows) {
    rapidjson::Document doc;
    doc.SetArray();
    EXPECT_THROW(detail::validate_scenes(doc, "/nonexistent/schema.json"), std::runtime_error);
}

TEST(ValidateScenesTest_NoFixture, MalformedSchemaFileThrows) {
    TempFile bad_schema("this is not valid json {{{");
    rapidjson::Document doc;
    doc.SetArray();
    EXPECT_THROW(detail::validate_scenes(doc, bad_schema.path()), std::runtime_error);
}

// ---------------------------------------------------------------------------
// detail::read_file_trimmed tests
// ---------------------------------------------------------------------------

TEST(ReadFileTrimmedTest, ReadsAndTrimsTrailingWhitespace) {
    TempFile f("hello world  \n\n");
    EXPECT_EQ(detail::read_file_trimmed(f.path()), "hello world");
}

TEST(ReadFileTrimmedTest, MissingFileThrows) {
    EXPECT_THROW(detail::read_file_trimmed("/nonexistent/file.txt"), std::runtime_error);
}

// ---------------------------------------------------------------------------
// Full ApiSceneLoader pipeline via mock
// ---------------------------------------------------------------------------

class ApiSceneLoaderPipelineTest : public ::testing::Test {
protected:
    void SetUp() override { Logger::init("warn"); }
    void TearDown() override { Logger::shutdown(); }

    std::filesystem::path schema_dir_ = std::filesystem::path(TRACKER_SCHEMA_DIR);

    // Minimal valid Manager API response with one scene and one camera
    std::string make_api_response() {
        return R"({
            "results": [{
                "uid": "scene-001",
                "name": "TestScene",
                "cameras": [{
                    "uid": "cam1",
                    "name": "Camera 1",
                    "translation": [1.0, 2.0, 3.0],
                    "rotation": [-90.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                    "distortion": {"k1": 0.1, "k2": 0.0, "p1": 0.0, "p2": 0.0},
                    "intrinsics": {
                        "fx": 500.0, "fy": 500.0,
                        "cx": 320.0, "cy": 240.0
                    }
                }]
            }]
        })";
    }
};

TEST_F(ApiSceneLoaderPipelineTest, FullPipelineReturnsScenes) {
    TempFile auth_file(R"({"user": "admin", "password": "pass123"})");

    ManagerConfig mgr;
    mgr.url = "https://localhost:443";
    mgr.auth_path = auth_file.path().string();

    auto factory = make_mock_factory(make_api_response());
    auto loader = create_api_scene_loader(mgr, schema_dir_, factory);

    auto scenes = loader->load();
    ASSERT_EQ(scenes.size(), 1);
    EXPECT_EQ(scenes[0].uid, "scene-001");
    EXPECT_EQ(scenes[0].name, "TestScene");
    ASSERT_EQ(scenes[0].cameras.size(), 1);
    EXPECT_EQ(scenes[0].cameras[0].uid, "cam1");
    EXPECT_DOUBLE_EQ(scenes[0].cameras[0].extrinsics.translation[0], 1.0);
    EXPECT_DOUBLE_EQ(scenes[0].cameras[0].extrinsics.translation[1], 2.0);
    EXPECT_DOUBLE_EQ(scenes[0].cameras[0].extrinsics.translation[2], 3.0);
    EXPECT_DOUBLE_EQ(scenes[0].cameras[0].intrinsics.fx, 500.0);
    EXPECT_DOUBLE_EQ(scenes[0].cameras[0].intrinsics.distortion.k1, 0.1);
}

TEST_F(ApiSceneLoaderPipelineTest, MultipleScenesAndCameras) {
    TempFile auth_file(R"({"user": "admin", "password": "pass"})");
    std::string response = R"({
        "results": [
            {
                "uid": "scene-1", "name": "Scene One",
                "cameras": [
                    {
                        "uid": "cam1", "name": "Cam 1",
                        "translation": [1.0, 0.0, 0.0],
                        "rotation": [0.0, 0.0, 0.0],
                        "scale": [1.0, 1.0, 1.0]
                    },
                    {
                        "uid": "cam2", "name": "Cam 2",
                        "translation": [2.0, 0.0, 0.0],
                        "rotation": [0.0, 0.0, 0.0],
                        "scale": [1.0, 1.0, 1.0]
                    }
                ]
            },
            {
                "uid": "scene-2", "name": "Scene Two",
                "cameras": [{
                    "uid": "cam3", "name": "Cam 3",
                    "translation": [3.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0]
                }]
            }
        ]
    })";

    ManagerConfig mgr;
    mgr.url = "https://localhost";
    mgr.auth_path = auth_file.path().string();

    auto factory = make_mock_factory(response);
    auto loader = create_api_scene_loader(mgr, schema_dir_, factory);

    auto scenes = loader->load();
    ASSERT_EQ(scenes.size(), 2);
    EXPECT_EQ(scenes[0].cameras.size(), 2);
    EXPECT_EQ(scenes[1].cameras.size(), 1);
    EXPECT_EQ(scenes[1].cameras[0].uid, "cam3");
}

TEST_F(ApiSceneLoaderPipelineTest, InvalidJsonResponseThrows) {
    TempFile auth_file(R"({"user": "admin", "password": "pass"})");

    ManagerConfig mgr;
    mgr.url = "https://localhost";
    mgr.auth_path = auth_file.path().string();

    auto factory = make_mock_factory("not json at all");
    auto loader = create_api_scene_loader(mgr, schema_dir_, factory);

    EXPECT_THROW(loader->load(), std::runtime_error);
}

TEST_F(ApiSceneLoaderPipelineTest, MissingResultsArrayThrows) {
    TempFile auth_file(R"({"user": "admin", "password": "pass"})");

    ManagerConfig mgr;
    mgr.url = "https://localhost";
    mgr.auth_path = auth_file.path().string();

    auto factory = make_mock_factory(R"({"data": []})");
    auto loader = create_api_scene_loader(mgr, schema_dir_, factory);

    EXPECT_THROW(loader->load(), std::runtime_error);
}

TEST_F(ApiSceneLoaderPipelineTest, ResultsNotArrayThrows) {
    TempFile auth_file(R"({"user": "admin", "password": "pass"})");

    ManagerConfig mgr;
    mgr.url = "https://localhost";
    mgr.auth_path = auth_file.path().string();

    auto factory = make_mock_factory(R"({"results": "not an array"})");
    auto loader = create_api_scene_loader(mgr, schema_dir_, factory);

    EXPECT_THROW(loader->load(), std::runtime_error);
}

TEST_F(ApiSceneLoaderPipelineTest, EmptyResultsReturnsNoScenes) {
    TempFile auth_file(R"({"user": "admin", "password": "pass"})");

    ManagerConfig mgr;
    mgr.url = "https://localhost";
    mgr.auth_path = auth_file.path().string();

    auto factory = make_mock_factory(R"({"results": []})");
    auto loader = create_api_scene_loader(mgr, schema_dir_, factory);

    auto scenes = loader->load();
    EXPECT_TRUE(scenes.empty());
}

TEST_F(ApiSceneLoaderPipelineTest, SchemaValidationFailureSkipsInvalidScenes) {
    TempFile auth_file(R"({"user": "admin", "password": "pass"})");
    // Scene missing required "uid" field — should be skipped, not throw
    std::string response = R"({"results": [{"name": "Bad", "cameras": []}]})";

    ManagerConfig mgr;
    mgr.url = "https://localhost";
    mgr.auth_path = auth_file.path().string();

    auto factory = make_mock_factory(response);
    auto loader = create_api_scene_loader(mgr, schema_dir_, factory);

    auto scenes = loader->load();
    EXPECT_TRUE(scenes.empty());
}

// ---------------------------------------------------------------------------
// scene_parser.hpp coverage: require_array3 non-number element (lines 45-46)
// ---------------------------------------------------------------------------

TEST(SceneParserTest, RequireArray3NonNumberElementThrows) {
    // Translation array with string instead of number
    const char* json = R"({
        "uid": "scene1", "name": "Scene",
        "cameras": [{
            "uid": "cam1", "name": "cam1",
            "extrinsics": {
                "translation": [1.0, "not-a-number", 3.0],
                "rotation": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0]
            }
        }]
    })";
    rapidjson::Document doc;
    doc.Parse(json);

    EXPECT_THROW(detail::parse_scene(doc), std::runtime_error);
}

} // namespace
} // namespace tracker
