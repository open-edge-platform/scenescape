// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * @file detection_projector_test.cpp
 * @brief Unit tests for CameraModelProjector and toTrackerInputs().
 */

#include "detection_projector.hpp"
#include "reid_sighting.hpp"
#include "tracking_types.hpp"

#include <gtest/gtest.h>
#include <rapidjson/document.h>
#include <rv/tracking/OrientationAttributes.hpp>

#include <array>
#include <cmath>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace tracker {
namespace {

// atag-qcam1 from tracker/config/scenes.json
Camera make_camera(const std::string& uid = "atag-qcam1") {
    Camera camera;
    camera.uid = uid;
    camera.name = uid;
    camera.intrinsics = {905.0, 905.0, 640.0, 360.0, {0.0, 0.0, 0.0, 0.0}};
    camera.extrinsics.translation = {2.985857104493509, 0.2054078898442529, 2.7150546825598902};
    camera.extrinsics.rotation = {-135.08718965001765, 12.682032394455131, 19.24508172546946};
    return camera;
}

CoordinateTransformer make_transformer(const Camera& camera = make_camera(),
                                       const ObjectClassConfig& object_class = {}) {
    return CoordinateTransformer(camera.intrinsics, camera.extrinsics, object_class.shift_type,
                                 object_class.footprint_half);
}

Detection make_detection(float x, float y, float w, float h, int32_t id = 1) {
    return Detection{.id = id, .bounding_box_px = cv::Rect2f(x, y, w, h)};
}

// Camera-model projection followed by the detection data, as in TrackingWorker.
std::vector<rv::tracking::TrackedObject>
project(const CoordinateTransformer& transformer, std::span<const Detection> detections,
        const std::optional<ReidSightingContext>& sightings = std::nullopt) {
    return toTrackerInputs(detections, transformer.transformDetections(detections), sightings);
}

// Geometry per detection; std::nullopt for a detection without a measurement.
ProjectedDetections
make_projected(const std::vector<std::optional<rv::tracking::TrackedObject>>& objects) {
    ProjectedDetections projected;
    for (const auto& object : objects) {
        projected.objects.push_back(object.value_or(rv::tracking::TrackedObject{}));
        projected.has_geometry.push_back(object.has_value() ? 1 : 0);
    }
    return projected;
}

rv::tracking::TrackedObject make_geometry(double x, double y) {
    rv::tracking::TrackedObject object;
    object.x = x;
    object.y = y;
    object.length = object.width = 0.5;
    object.height = 1.7;
    return object;
}

//
// CameraModelProjector
//

TEST(CameraModelProjectorTest, ProjectsEachBatchWithItsCameraCalibration) {
    auto other_camera = make_camera("cam-2");
    other_camera.extrinsics.translation = {-1.0, 4.0, 3.5};
    other_camera.extrinsics.rotation = {-150.6, 42.35, 52.3};
    CameraModelProjector projector({{"atag-qcam1", make_camera()}, {"cam-2", other_camera}}, {});
    Detection world_detection;
    world_detection.translation = std::array<double, 3>{1.0, 2.0, 3.0};
    world_detection.size = std::array<double, 3>{4.0, 5.0, 6.0};
    std::vector<DetectionBatch> batches(2);
    batches[0].camera_id = "cam-2";
    batches[0].detections = {make_detection(590.0f, 260.0f, 100.0f, 200.0f), world_detection};
    batches[1].camera_id = "atag-qcam1";
    batches[1].detections = {make_detection(10.0f, 10.0f, 80.0f, 160.0f)};

    const auto projected = projector.project(batches);

    ASSERT_EQ(projected.size(), 2u);
    for (size_t i = 0; i < batches.size(); ++i) {
        const auto camera = batches[i].camera_id == "cam-2" ? other_camera : make_camera();
        const auto expected = make_transformer(camera).transformDetections(batches[i].detections);
        ASSERT_TRUE(projected[i]) << "batch " << i;
        ASSERT_TRUE(projected[i]->covers(batches[i].detections.size())) << "batch " << i;
        EXPECT_EQ(projected[i]->has_geometry, expected.has_geometry) << "batch " << i;
        for (size_t j = 0; j < expected.objects.size(); ++j) {
            const auto& actual = projected[i]->objects[j];
            EXPECT_DOUBLE_EQ(actual.x, expected.objects[j].x);
            EXPECT_DOUBLE_EQ(actual.y, expected.objects[j].y);
            EXPECT_DOUBLE_EQ(actual.z, expected.objects[j].z);
            EXPECT_DOUBLE_EQ(actual.height, expected.objects[j].height);
            EXPECT_EQ(actual.zMeasured, expected.objects[j].zMeasured);
        }
    }
}

TEST(CameraModelProjectorTest, UnknownCameraHasNoResult) {
    CameraModelProjector projector({{"atag-qcam1", make_camera()}}, {});
    std::vector<DetectionBatch> batches(3);
    batches[0].camera_id = "unknown";
    batches[0].detections = {make_detection(590.0f, 260.0f, 100.0f, 200.0f)};
    batches[1].camera_id = "atag-qcam1";
    batches[1].detections = {make_detection(590.0f, 260.0f, 100.0f, 200.0f)};
    batches[2].camera_id = "atag-qcam1"; // empty frame

    const auto projected = projector.project(batches);

    ASSERT_EQ(projected.size(), 3u);
    EXPECT_FALSE(projected[0]);
    ASSERT_TRUE(projected[1]);
    EXPECT_TRUE(projected[1]->covers(1));
    ASSERT_TRUE(projected[2]);
    EXPECT_TRUE(projected[2]->covers(0));
    EXPECT_TRUE(projector.project({}).empty());
}

TEST(CameraModelProjectorTest, AppliesObjectClassProjectionSettings) {
    const ObjectClassConfig object_class{.shift_type = ObjectClassConfig::kShiftType2,
                                         .footprint_half = 0.25};
    CameraModelProjector projector({{"atag-qcam1", make_camera()}}, object_class);
    std::vector<DetectionBatch> batches(1);
    batches[0].camera_id = "atag-qcam1";
    batches[0].detections = {make_detection(900.0f, 350.0f, 300.0f, 300.0f)};

    const auto projected = projector.project(batches);
    const auto expected =
        make_transformer(make_camera(), object_class).transformDetections(batches[0].detections);
    const auto type1 = make_transformer().transformDetections(batches[0].detections);

    ASSERT_TRUE(projected.at(0) && projected[0]->covers(1));
    const auto& actual = projected[0]->objects[0];
    EXPECT_DOUBLE_EQ(actual.x, expected.objects.at(0).x);
    EXPECT_DOUBLE_EQ(actual.y, expected.objects.at(0).y);
    EXPECT_GT(std::hypot(actual.x - type1.objects.at(0).x, actual.y - type1.objects.at(0).y), 0.01);
}

//
// toTrackerInputs
//

TEST(ToTrackerInputsTest, KeepsProjectedGeometry) {
    Detection detection = make_detection(590.0f, 260.0f, 100.0f, 200.0f, 5);
    detection.metadata_json = R"({"age":{"label":"adult"}})";
    detection.confidence = 0.9;
    auto geometry = make_geometry(1.5, -2.5);
    geometry.z = 0.85;
    geometry.zMeasured = true;
    geometry.yaw = 0.4;
    rv::tracking::orientation::setHasOrientation(geometry, true);
    geometry.measurementNoiseCov = rv::tracking::TrackedObject::MeasurementMatrix::eye() * 0.3;
    const auto inputs = toTrackerInputs(std::array{detection}, make_projected({geometry}));

    ASSERT_EQ(inputs.size(), 1u);
    EXPECT_EQ(inputs[0].id, 5);
    EXPECT_DOUBLE_EQ(inputs[0].x, 1.5);
    EXPECT_DOUBLE_EQ(inputs[0].y, -2.5);
    EXPECT_DOUBLE_EQ(inputs[0].z, 0.85);
    EXPECT_TRUE(inputs[0].zMeasured);
    EXPECT_DOUBLE_EQ(inputs[0].height, 1.7);
    EXPECT_DOUBLE_EQ(inputs[0].yaw, 0.4);
    EXPECT_TRUE(rv::tracking::orientation::hasOrientation(inputs[0]));
    ASSERT_TRUE(inputs[0].measurementNoiseCov);
    EXPECT_DOUBLE_EQ((*inputs[0].measurementNoiseCov)(0, 0), 0.3);
    EXPECT_EQ(inputs[0].attributes.at("metadata.age"), R"({"label":"adult"})");
    EXPECT_NEAR(std::stod(inputs[0].attributes.at("confidence")), 0.9, 1e-9);
}

TEST(ToTrackerInputsTest, DropsDetectionsWithoutGeometryAndKeepsTheirOrder) {
    DetectionBatch batch;
    batch.camera_id = "cam-1";
    batch.timestamp_iso = "2026-01-27T12:00:00Z";
    for (int32_t id = 0; id < 4; ++id) {
        Detection detection = make_detection(100.0f * static_cast<float>(id), 50.0f,
                                             10.0f + static_cast<float>(id), 20.0f, id);
        detection.reid_json = R"({"embedding_vector":[[1,2]]})";
        batch.detections.push_back(detection);
    }
    const auto projected = make_projected(
        {std::nullopt, make_geometry(1.0, 0.0), std::nullopt, make_geometry(3.0, 0.0)});
    ReidSightingIndex sightings;
    sightings.reset("chunk-1");
    const auto context = sightings.add_batch(batch);

    const auto inputs = toTrackerInputs(batch.detections, projected, context);

    ASSERT_EQ(inputs.size(), 2u);
    EXPECT_EQ(inputs[0].id, 1);
    EXPECT_DOUBLE_EQ(inputs[0].x, 1.0);
    EXPECT_EQ(inputs[1].id, 3);
    EXPECT_DOUBLE_EQ(inputs[1].x, 3.0);
    // Sighting tokens keep the index of the detection in its batch.
    EXPECT_EQ(inputs[0].attributes.at("metadata.reid"), "chunk-1:1");
    EXPECT_EQ(inputs[1].attributes.at("metadata.reid"), "chunk-1:3");
    rapidjson::Document sighting;
    ASSERT_FALSE(sighting.Parse(sightings.take(inputs[1].attributes).c_str()).HasParseError());
    EXPECT_DOUBLE_EQ(sighting["bounding_box_px"]["width"].GetDouble(), 13.0);
}

TEST(ToTrackerInputsTest, LargeBatchKeepsDetectionDataInOrder) {
    // Above the OpenMP threshold; every third detection has no geometry.
    std::vector<Detection> detections;
    std::vector<std::optional<rv::tracking::TrackedObject>> geometry;
    for (int32_t id = 0; id < 100; ++id) {
        Detection detection = make_detection(0.0f, 0.0f, 10.0f, 20.0f, id);
        detection.confidence = id / 100.0;
        detection.metadata_json = R"({"index":)" + std::to_string(id) + "}";
        detections.push_back(detection);
        geometry.push_back(id % 3 == 0
                               ? std::nullopt
                               : std::optional(make_geometry(static_cast<double>(id), 0.0)));
    }

    const auto inputs = toTrackerInputs(detections, make_projected(geometry));

    ASSERT_EQ(inputs.size(), 66u);
    size_t next = 0;
    for (int32_t id = 0; id < 100; ++id) {
        if (id % 3 == 0) {
            continue;
        }
        const auto& input = inputs.at(next++);
        EXPECT_EQ(input.id, id);
        EXPECT_DOUBLE_EQ(input.x, static_cast<double>(id));
        EXPECT_NEAR(std::stod(input.attributes.at("confidence")), id / 100.0, 1e-12);
        EXPECT_EQ(input.attributes.at("metadata.index"), std::to_string(id));
    }
}

TEST(ToTrackerInputsTest, RejectsGeometryCountMismatch) {
    const std::vector<Detection> detections = {make_detection(0.0f, 0.0f, 10.0f, 20.0f)};

    auto without_mask = make_projected({make_geometry(0.0, 0.0)});
    without_mask.has_geometry.clear();

    EXPECT_THROW(toTrackerInputs(detections, ProjectedDetections{}), std::invalid_argument);
    EXPECT_THROW(toTrackerInputs(detections, make_projected({std::nullopt, std::nullopt})),
                 std::invalid_argument);
    EXPECT_THROW(toTrackerInputs(detections, without_mask), std::invalid_argument);
    EXPECT_TRUE(toTrackerInputs({}, ProjectedDetections{}).empty());
}

TEST(ToTrackerInputsTest, PreservesDetectionId) {
    const auto transformer = make_transformer();

    std::vector<Detection> detections = {
        make_detection(590.0f, 260.0f, 100.0f, 200.0f, 42),
        make_detection(10.0f, 10.0f, 80.0f, 160.0f, 7),
    };

    auto result = project(transformer, detections);
    ASSERT_EQ(result.size(), 2u);
    EXPECT_EQ(result[0].id, 42);
    EXPECT_EQ(result[1].id, 7);
}

TEST(ToTrackerInputsTest, MissingIdUsesInvalidObjectId) {
    const auto transformer = make_transformer();

    Detection det;
    det.id = std::nullopt;
    det.bounding_box_px = cv::Rect2f(590.0f, 260.0f, 100.0f, 200.0f);

    std::vector<Detection> detections = {det};
    auto result = project(transformer, detections);
    ASSERT_EQ(result.size(), 1u);
    EXPECT_EQ(result[0].id, rv::tracking::InvalidObjectId);
}

TEST(ToTrackerInputsTest, MissingSightingContextPreservesOnlyNonReidFields) {
    const auto transformer = make_transformer();

    Detection det = make_detection(590.0f, 260.0f, 100.0f, 200.0f, 1);
    det.metadata_json = R"({"age":{"label":"adult"}})";
    det.reid_json = R"({"model_name":"test"})";

    auto result = project(transformer, std::vector<Detection>{det});

    ASSERT_EQ(result.size(), 1u);
    EXPECT_EQ(result[0].attributes.count("metadata_json"), 0u);
    EXPECT_EQ(result[0].attributes.count("metadata.reid"), 0u);
    EXPECT_EQ(result[0].attributes.count("metadata_provenance.reid"), 0u);
    EXPECT_EQ(result[0].attributes.at("metadata.age"), R"({"label":"adult"})");
}

TEST(ToTrackerInputsTest, MetadataAndSightingShareDetectionPayload) {
    const auto transformer = make_transformer();
    Detection detection = make_detection(590.0f, 260.0f, 100.0f, 200.0f, 1);
    detection.metadata_json = R"({"age":{"label":"adult"}})";
    detection.reid_json = R"({"embedding_vector":[[1.25,2.5]],"confidence":0.8})";
    detection.reid_confidence = 0.8;
    DetectionBatch batch;
    batch.camera_id = "cam-1";
    batch.timestamp_iso = "2026-01-27T12:00:00Z";
    batch.detections.push_back(detection);
    ReidSightingIndex reid_sightings;
    reid_sightings.reset("chunk-1");
    const auto context = reid_sightings.add_batch(batch);

    auto result = project(transformer, batch.detections, context);

    ASSERT_EQ(result.size(), 1u);
    const auto& attributes = result[0].attributes;
    rapidjson::Document sighting;
    EXPECT_EQ(attributes.at("metadata.reid"), "chunk-1:0");
    ASSERT_FALSE(sighting.Parse(reid_sightings.take(attributes).c_str()).HasParseError());
    EXPECT_DOUBLE_EQ(sighting["reid"]["embedding_vector"][0][0].GetDouble(), 1.25);
    EXPECT_STREQ(sighting["camera_id"].GetString(), "cam-1");
    EXPECT_STREQ(sighting["timestamp"].GetString(), "2026-01-27T12:00:00Z");
    EXPECT_FALSE(sighting.HasMember("chunk_id"));
    EXPECT_EQ(attributes.at("metadata_provenance.reid"), "chunk-1");
    EXPECT_EQ(attributes.at("metadata_transient.reid"), "1");
    EXPECT_DOUBLE_EQ(sighting["bounding_box_px"]["width"].GetDouble(), 100.0);
    EXPECT_DOUBLE_EQ(std::stod(attributes.at("metadata_confidence.reid")), 0.8);
    EXPECT_EQ(attributes.count("metadata_json"), 0u);
    EXPECT_EQ(attributes.count("reid_sighting"), 0u);
}

TEST(ToTrackerInputsTest, SensorFrameReidWithoutPixelBoxDoesNotCreateSighting) {
    const auto transformer = make_transformer();
    Detection detection;
    detection.translation = std::array<double, 3>{1.0, 2.0, 3.0};
    detection.size = std::array<double, 3>{4.0, 5.0, 6.0};
    detection.reid_json = R"({"embedding_vector":[[1,2]]})";
    DetectionBatch batch;
    batch.camera_id = "cam-1";
    batch.timestamp_iso = "2026-01-27T12:00:00Z";
    batch.detections.push_back(detection);
    ReidSightingIndex reid_sightings;
    reid_sightings.reset("chunk-1");
    const auto context = reid_sightings.add_batch(batch);

    const auto result = project(transformer, batch.detections, context);

    ASSERT_EQ(result.size(), 1u);
    EXPECT_TRUE(reid_sightings.take(result[0].attributes).empty());
    EXPECT_EQ(result[0].attributes.count("metadata.reid"), 0u);
    EXPECT_EQ(result[0].attributes.count("metadata_provenance.reid"), 0u);
}

TEST(ToTrackerInputsTest, MismatchedSightingSpanIsRejectedBeforeParallelWork) {
    const auto transformer = make_transformer();
    DetectionBatch batch;
    batch.detections.resize(64);
    ReidSightingIndex index;
    index.reset("chunk");
    const auto context = index.add_batch(batch);
    const auto detections = std::span<const Detection>(batch.detections);
    const auto other_detections = batch.detections;

    EXPECT_THROW(project(transformer, detections.first(32), context), std::invalid_argument);
    EXPECT_THROW(project(transformer, other_detections, context), std::invalid_argument);
    EXPECT_THROW(project(transformer, detections.subspan(1), context), std::invalid_argument);
}

TEST(ToTrackerInputsTest, LegacyReidEncodingsAreWrappedWithoutDroppingTheVector) {
    const auto transformer = make_transformer();
    for (const auto& payload : {R"({"reid":[[1.25,2.5]]})", R"({"reid":"AACAPwAAAEA="})"}) {
        Detection detection = make_detection(590.0f, 260.0f, 100.0f, 200.0f, 1);
        rapidjson::Document original;
        ASSERT_FALSE(original.Parse(payload).HasParseError());
        parse_detection_metadata(original, detection);
        DetectionBatch batch;
        batch.camera_id = "cam-1";
        batch.timestamp_iso = "2026-01-27T12:00:00Z";
        batch.detections.push_back(detection);
        ReidSightingIndex reid_sightings;
        reid_sightings.reset("chunk-1");
        const auto context = reid_sightings.add_batch(batch);
        auto result = project(transformer, batch.detections, context);
        ASSERT_EQ(result.size(), 1u);
        rapidjson::Document sighting;
        ASSERT_FALSE(
            sighting.Parse(reid_sightings.take(result[0].attributes).c_str()).HasParseError());
        EXPECT_EQ(sighting["reid"]["embedding_vector"], original["reid"]);
        EXPECT_EQ(result[0].attributes.count("metadata_json"), 0u);
        EXPECT_EQ(result[0].attributes.count("reid_sighting"), 0u);
    }
}

TEST(ToTrackerInputsTest, EmbeddedNullSuffixIsRejectedAsInvalidJson) {
    const auto transformer = make_transformer();
    Detection detection = make_detection(590.0f, 260.0f, 100.0f, 200.0f, 1);
    detection.metadata_json = R"({"age":{"label":"adult"}})" + std::string("\0junk", 5);

    const auto result = project(transformer, std::vector<Detection>{detection});

    ASSERT_EQ(result.size(), 1u);
    EXPECT_EQ(result[0].attributes.count("metadata.age"), 0u);
}

TEST(ToTrackerInputsTest, IncompleteSightingContextDoesNotProduceInvalidSightings) {
    const auto transformer = make_transformer();
    Detection detection = make_detection(590.0f, 260.0f, 100.0f, 200.0f, 1);
    detection.reid_json = R"({"embedding_vector":[[1,2]]})";
    const std::vector<std::array<std::string, 3>> contexts = {
        {"", "2026-01-27T12:00:00Z", "chunk-1"},
        {"cam-1", "", "chunk-1"},
        {"cam-1", "2026-01-27T12:00:00Z", ""}};
    for (const auto& context : contexts) {
        DetectionBatch batch;
        batch.camera_id = context[0];
        batch.timestamp_iso = context[1];
        batch.detections.push_back(detection);
        ReidSightingIndex index;
        index.reset(context[2]);
        const auto sightings = index.add_batch(batch);
        auto result = project(transformer, batch.detections, sightings);
        ASSERT_EQ(result.size(), 1u);
        EXPECT_EQ(result[0].attributes.count("metadata.reid"), 0u);
        EXPECT_EQ(result[0].attributes.count("metadata_provenance.reid"), 0u);
    }
}

TEST(ToTrackerInputsTest, Confidence_PreservedThroughProjection) {
    const auto transformer = make_transformer();

    Detection det = make_detection(590.0f, 260.0f, 100.0f, 200.0f, 1);
    det.confidence = 0.95;

    auto result = project(transformer, std::vector<Detection>{det});

    ASSERT_EQ(result.size(), 1u);
    ASSERT_TRUE(result[0].attributes.count("confidence"));
    EXPECT_NEAR(std::stod(result[0].attributes.at("confidence")), 0.95, 1e-9);
}

TEST(ToTrackerInputsTest, Confidence_AbsentWhenNotProvided) {
    const auto transformer = make_transformer();

    auto result = project(transformer,
                          std::vector<Detection>{make_detection(590.0f, 260.0f, 100.0f, 200.0f)});

    ASSERT_EQ(result.size(), 1u);
    EXPECT_FALSE(result[0].attributes.count("confidence"));
}

TEST(ToTrackerInputsTest, Confidence_MultipleDetectionsPreservedInOrder) {
    const auto transformer = make_transformer();

    Detection det0 = make_detection(590.0f, 260.0f, 100.0f, 200.0f, 0);
    det0.confidence = 0.8;

    Detection det1 = make_detection(10.0f, 10.0f, 80.0f, 160.0f, 1);
    // No confidence on det1

    Detection det2 = make_detection(1190.0f, 550.0f, 80.0f, 160.0f, 2);
    det2.confidence = 0.6;

    auto result = project(transformer, std::vector<Detection>{det0, det1, det2});

    ASSERT_EQ(result.size(), 3u);
    EXPECT_NEAR(std::stod(result[0].attributes.at("confidence")), 0.8, 1e-9);
    EXPECT_FALSE(result[1].attributes.count("confidence"));
    EXPECT_NEAR(std::stod(result[2].attributes.at("confidence")), 0.6, 1e-9);
}

} // namespace
} // namespace tracker
