/**
 * Unified Serialization Benchmark for Tracker Messages
 * 
 * Tests serialization/deserialization performance for:
 * - Detection messages (DetectionMessage)
 * - Regulated messages (RegulatedMessage)
 * 
 * With formats:
 * - JSON (RapidJSON for serialize, simdjson for deserialize)
 * - Protocol Buffers
 * - FlatBuffers
 */

#include <benchmark/benchmark.h>
#include <fstream>
#include <sstream>
#include <vector>
#include <stdexcept>

// JSON libraries
#include <rapidjson/document.h>
#include <rapidjson/writer.h>
#include <rapidjson/stringbuffer.h>
#include <simdjson.h>

// Protocol Buffers
#include "detection-message.pb.h"
#include "regulated-message.pb.h"

// FlatBuffers
#include "detection-message_generated.h"
#include "regulated-message_generated.h"

namespace pb_detection = scenescape::tracker;
namespace pb_regulated = scenescape::tracker::regulated;
namespace fb_detection = SceneScape::Tracker;
namespace fb_regulated = scenescape::tracker::regulated::fb;

//=============================================================================
// Global test data
//=============================================================================
struct TestData {
    std::string json_data;
    simdjson::dom::parser simdjson_parser;
    
    // Pre-built messages (built once from JSON)
    pb_detection::DetectionMessage detection_pb;
    pb_regulated::RegulatedMessage regulated_pb;
    flatbuffers::DetachedBuffer detection_fb;
    flatbuffers::DetachedBuffer regulated_fb;
    
    // Pre-serialized data for deserialization benchmarks
    std::string detection_pb_bytes;
    std::string regulated_pb_bytes;
    std::vector<uint8_t> detection_fb_bytes;
    std::vector<uint8_t> regulated_fb_bytes;
};

TestData g_detection_data;
TestData g_regulated_data;

//=============================================================================
// Helper: Load JSON file
//=============================================================================
std::string load_json_file(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open file: " + filepath);
    }
    
    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

//=============================================================================
// Detection Message Builders
//=============================================================================
void build_detection_protobuf(TestData& data) {
    rapidjson::Document doc;
    doc.Parse(data.json_data.c_str());
    
    data.detection_pb.set_id(doc["id"].GetString());
    data.detection_pb.set_debug_mac(doc["debug_mac"].GetString());
    data.detection_pb.set_timestamp(doc["timestamp"].GetString());
    data.detection_pb.set_debug_timestamp_end(doc["debug_timestamp_end"].GetString());
    data.detection_pb.set_debug_processing_time(doc["debug_processing_time"].GetDouble());
    data.detection_pb.set_rate(doc["rate"].GetDouble());
    
    const auto& persons = doc["objects"]["person"].GetArray();
    for (const auto& person : persons) {
        auto* obj = data.detection_pb.mutable_objects()->add_person();
        obj->set_category(person["category"].GetString());
        obj->set_confidence(person["confidence"].GetDouble());
        obj->set_id(person["id"].GetInt());
        
        auto* com = obj->mutable_center_of_mass();
        com->set_x(person["center_of_mass"]["x"].GetDouble());
        com->set_y(person["center_of_mass"]["y"].GetDouble());
        com->set_width(person["center_of_mass"]["width"].GetDouble());
        com->set_height(person["center_of_mass"]["height"].GetDouble());
        
        auto* bbox = obj->mutable_bounding_box_px();
        bbox->set_x(person["bounding_box_px"]["x"].GetDouble());
        bbox->set_y(person["bounding_box_px"]["y"].GetDouble());
        bbox->set_width(person["bounding_box_px"]["width"].GetDouble());
        bbox->set_height(person["bounding_box_px"]["height"].GetDouble());
    }
}

void build_detection_flatbuffers(TestData& data) {
    rapidjson::Document doc;
    doc.Parse(data.json_data.c_str());
    
    flatbuffers::FlatBufferBuilder builder(1024);
    
    std::vector<flatbuffers::Offset<fb_detection::DetectedObject>> person_objects;
    const auto& persons = doc["objects"]["person"].GetArray();
    
    for (const auto& person : persons) {
        auto category = builder.CreateString(person["category"].GetString());
        
        auto com = fb_detection::CreatePoint(builder,
            person["center_of_mass"]["x"].GetDouble(),
            person["center_of_mass"]["y"].GetDouble(),
            person["center_of_mass"]["width"].GetDouble(),
            person["center_of_mass"]["height"].GetDouble());
        
        auto bbox = fb_detection::CreatePoint(builder,
            person["bounding_box_px"]["x"].GetDouble(),
            person["bounding_box_px"]["y"].GetDouble(),
            person["bounding_box_px"]["width"].GetDouble(),
            person["bounding_box_px"]["height"].GetDouble());
        
        auto obj = fb_detection::CreateDetectedObject(builder,
            category, person["confidence"].GetDouble(),
            com, bbox, person["id"].GetInt());
        
        person_objects.push_back(obj);
    }
    
    auto person_vector = builder.CreateVector(person_objects);
    auto objects = fb_detection::CreateDetectedObjects(builder, person_vector);
    
    auto id_str = builder.CreateString(doc["id"].GetString());
    auto debug_mac = builder.CreateString(doc["debug_mac"].GetString());
    auto timestamp = builder.CreateString(doc["timestamp"].GetString());
    auto debug_timestamp_end = builder.CreateString(doc["debug_timestamp_end"].GetString());
    
    auto msg = fb_detection::CreateDetectionMessage(builder,
        id_str, debug_mac, timestamp, debug_timestamp_end,
        doc["debug_processing_time"].GetDouble(),
        doc["rate"].GetDouble(), objects);
    
    builder.Finish(msg);
    data.detection_fb = builder.Release();
}

//=============================================================================
// Regulated Message Builders
//=============================================================================
void build_regulated_protobuf(TestData& data) {
    rapidjson::Document doc;
    doc.Parse(data.json_data.c_str());
    
    data.regulated_pb.set_timestamp(doc["timestamp"].GetString());
    data.regulated_pb.set_id(doc["id"].GetString());
    data.regulated_pb.set_name(doc["name"].GetString());
    data.regulated_pb.set_scene_rate(doc["scene_rate"].GetDouble());
    
    const auto& rate_obj = doc["rate"].GetObject();
    for (auto& m : rate_obj) {
        (*data.regulated_pb.mutable_rate())[m.name.GetString()] = m.value.GetDouble();
    }
    
    const auto& objects = doc["objects"].GetArray();
    for (const auto& obj : objects) {
        auto* reg_obj = data.regulated_pb.add_objects();
        
        reg_obj->set_category(obj["category"].GetString());
        reg_obj->set_confidence(obj["confidence"].GetDouble());
        reg_obj->set_id(obj["id"].GetString());
        reg_obj->set_type(obj["type"].GetString());
        reg_obj->set_first_seen(obj["first_seen"].GetString());
        
        auto* com = reg_obj->mutable_center_of_mass();
        com->set_x(obj["center_of_mass"]["x"].GetDouble());
        com->set_y(obj["center_of_mass"]["y"].GetDouble());
        com->set_width(obj["center_of_mass"]["width"].GetDouble());
        com->set_height(obj["center_of_mass"]["height"].GetDouble());
        
        auto* trans = reg_obj->mutable_translation();
        trans->set_x(obj["translation"][0].GetDouble());
        trans->set_y(obj["translation"][1].GetDouble());
        trans->set_z(obj["translation"][2].GetDouble());
        
        auto* size = reg_obj->mutable_size();
        size->set_x(obj["size"][0].GetDouble());
        size->set_y(obj["size"][1].GetDouble());
        size->set_z(obj["size"][2].GetDouble());
        
        auto* rot = reg_obj->mutable_rotation();
        rot->set_w(obj["rotation"][0].GetDouble());
        rot->set_x(obj["rotation"][1].GetDouble());
        rot->set_y(obj["rotation"][2].GetDouble());
        rot->set_z(obj["rotation"][3].GetDouble());
        
        auto* vel = reg_obj->mutable_velocity();
        vel->set_x(obj["velocity"][0].GetDouble());
        vel->set_y(obj["velocity"][1].GetDouble());
        vel->set_z(obj["velocity"][2].GetDouble());
        
        if (obj.HasMember("camera_bounds")) {
            const auto& bounds_obj = obj["camera_bounds"].GetObject();
            for (auto& b : bounds_obj) {
                auto& bound = (*reg_obj->mutable_camera_bounds())[b.name.GetString()];
                bound.set_x(b.value["x"].GetDouble());
                bound.set_y(b.value["y"].GetDouble());
                bound.set_width(b.value["width"].GetDouble());
                bound.set_height(b.value["height"].GetDouble());
            }
        }
    }
}

void build_regulated_flatbuffers(TestData& data) {
    rapidjson::Document doc;
    doc.Parse(data.json_data.c_str());
    
    flatbuffers::FlatBufferBuilder builder(4096);
    
    // Build rate map
    std::vector<flatbuffers::Offset<fb_regulated::CameraRate>> rate_entries;
    const auto& rate_obj = doc["rate"].GetObject();
    for (auto& m : rate_obj) {
        auto camera = builder.CreateString(m.name.GetString());
        rate_entries.push_back(fb_regulated::CreateCameraRate(builder, camera, m.value.GetDouble()));
    }
    auto rate_vector = builder.CreateVector(rate_entries);
    
    // Build objects
    std::vector<flatbuffers::Offset<fb_regulated::RegulatedObject>> objects;
    const auto& objects_array = doc["objects"].GetArray();
    
    for (const auto& obj : objects_array) {
        auto category = builder.CreateString(obj["category"].GetString());
        auto id = builder.CreateString(obj["id"].GetString());
        auto type = builder.CreateString(obj["type"].GetString());
        auto first_seen = builder.CreateString(obj["first_seen"].GetString());
        
        auto com = fb_regulated::CreateBox(builder,
            obj["center_of_mass"]["x"].GetDouble(),
            obj["center_of_mass"]["y"].GetDouble(),
            obj["center_of_mass"]["width"].GetDouble(),
            obj["center_of_mass"]["height"].GetDouble());
        
        fb_regulated::Vector3 trans(
            obj["translation"][0].GetDouble(),
            obj["translation"][1].GetDouble(),
            obj["translation"][2].GetDouble());
        
        fb_regulated::Vector3 size(
            obj["size"][0].GetDouble(),
            obj["size"][1].GetDouble(),
            obj["size"][2].GetDouble());
        
        fb_regulated::Quaternion rot(
            obj["rotation"][1].GetDouble(),  // x
            obj["rotation"][2].GetDouble(),  // y
            obj["rotation"][3].GetDouble(),  // z
            obj["rotation"][0].GetDouble()); // w
        
        fb_regulated::Vector3 vel(
            obj["velocity"][0].GetDouble(),
            obj["velocity"][1].GetDouble(),
            obj["velocity"][2].GetDouble());
        
        flatbuffers::Offset<flatbuffers::Vector<flatbuffers::Offset<fb_regulated::CameraBound>>> camera_bounds = 0;
        if (obj.HasMember("camera_bounds")) {
            std::vector<flatbuffers::Offset<fb_regulated::CameraBound>> bounds;
            const auto& bounds_obj = obj["camera_bounds"].GetObject();
            for (auto& b : bounds_obj) {
                auto camera = builder.CreateString(b.name.GetString());
                auto box = fb_regulated::CreateBox(builder,
                    b.value["x"].GetDouble(),
                    b.value["y"].GetDouble(),
                    b.value["width"].GetDouble(),
                    b.value["height"].GetDouble());
                bounds.push_back(fb_regulated::CreateCameraBound(builder, camera, box));
            }
            camera_bounds = builder.CreateVector(bounds);
        }
        
        objects.push_back(fb_regulated::CreateRegulatedObject(builder,
            category, obj["confidence"].GetDouble(), com, id, type,
            &trans, &size, &vel, &rot, 0, 0.0, first_seen, camera_bounds));
    }
    
    auto objects_vector = builder.CreateVector(objects);
    auto timestamp = builder.CreateString(doc["timestamp"].GetString());
    auto id_str = builder.CreateString(doc["id"].GetString());
    auto name = builder.CreateString(doc["name"].GetString());
    
    auto msg = fb_regulated::CreateRegulatedMessage(builder,
        timestamp, objects_vector, id_str, name, doc["scene_rate"].GetDouble(),
        rate_vector);
    
    builder.Finish(msg);
    data.regulated_fb = builder.Release();
}

//=============================================================================
// Setup function (called once before benchmarks)
//=============================================================================
void setup_test_data(const std::string& detection_file, const std::string& regulated_file) {
    // Load JSON files
    g_detection_data.json_data = load_json_file(detection_file);
    g_regulated_data.json_data = load_json_file(regulated_file);
    
    // Build detection messages
    build_detection_protobuf(g_detection_data);
    build_detection_flatbuffers(g_detection_data);
    g_detection_data.detection_pb_bytes = g_detection_data.detection_pb.SerializeAsString();
    g_detection_data.detection_fb_bytes.assign(
        g_detection_data.detection_fb.data(),
        g_detection_data.detection_fb.data() + g_detection_data.detection_fb.size());
    
    // Build regulated messages
    build_regulated_protobuf(g_regulated_data);
    build_regulated_flatbuffers(g_regulated_data);
    g_regulated_data.regulated_pb_bytes = g_regulated_data.regulated_pb.SerializeAsString();
    g_regulated_data.regulated_fb_bytes.assign(
        g_regulated_data.regulated_fb.data(),
        g_regulated_data.regulated_fb.data() + g_regulated_data.regulated_fb.size());
}

//=============================================================================
// Detection Message Benchmarks
//=============================================================================

// JSON Serialize (RapidJSON)
static void BM_Detection_JSON_Serialize_RapidJSON(benchmark::State& state) {
    rapidjson::Document doc;
    doc.Parse(g_detection_data.json_data.c_str());
    
    for (auto _ : state) {
        rapidjson::StringBuffer buffer;
        rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
        doc.Accept(writer);
        benchmark::DoNotOptimize(buffer.GetString());
    }
}
BENCHMARK(BM_Detection_JSON_Serialize_RapidJSON);

// JSON Deserialize (simdjson)
static void BM_Detection_JSON_Deserialize_simdjson(benchmark::State& state) {
    simdjson::dom::parser parser;
    
    for (auto _ : state) {
        auto doc = parser.parse(g_detection_data.json_data);
        benchmark::DoNotOptimize(doc);
    }
}
BENCHMARK(BM_Detection_JSON_Deserialize_simdjson);

// JSON Deserialize (RapidJSON) - for comparison
static void BM_Detection_JSON_Deserialize_RapidJSON(benchmark::State& state) {
    for (auto _ : state) {
        rapidjson::Document doc;
        doc.Parse(g_detection_data.json_data.c_str());
        benchmark::DoNotOptimize(doc);
    }
}
BENCHMARK(BM_Detection_JSON_Deserialize_RapidJSON);

// Protobuf Serialize
static void BM_Detection_Protobuf_Serialize(benchmark::State& state) {
    for (auto _ : state) {
        std::string output;
        g_detection_data.detection_pb.SerializeToString(&output);
        benchmark::DoNotOptimize(output);
    }
}
BENCHMARK(BM_Detection_Protobuf_Serialize);

// Protobuf Deserialize
static void BM_Detection_Protobuf_Deserialize(benchmark::State& state) {
    for (auto _ : state) {
        pb_detection::DetectionMessage msg;
        msg.ParseFromString(g_detection_data.detection_pb_bytes);
        benchmark::DoNotOptimize(msg);
    }
}
BENCHMARK(BM_Detection_Protobuf_Deserialize);

// FlatBuffers Serialize
static void BM_Detection_FlatBuffers_Serialize(benchmark::State& state) {
    for (auto _ : state) {
        flatbuffers::FlatBufferBuilder builder(1024);
        
        std::vector<flatbuffers::Offset<fb_detection::DetectedObject>> person_objects;
        auto persons = g_detection_data.detection_pb.objects().person();
        
        for (const auto& person : persons) {
            auto category = builder.CreateString(person.category());
            auto com = fb_detection::CreatePoint(builder,
                person.center_of_mass().x(), person.center_of_mass().y(),
                person.center_of_mass().width(), person.center_of_mass().height());
            auto bbox = fb_detection::CreatePoint(builder,
                person.bounding_box_px().x(), person.bounding_box_px().y(),
                person.bounding_box_px().width(), person.bounding_box_px().height());
            
            person_objects.push_back(fb_detection::CreateDetectedObject(builder,
                category, person.confidence(), com, bbox, person.id()));
        }
        
        auto person_vector = builder.CreateVector(person_objects);
        auto objects = fb_detection::CreateDetectedObjects(builder, person_vector);
        auto id_str = builder.CreateString(g_detection_data.detection_pb.id());
        auto debug_mac = builder.CreateString(g_detection_data.detection_pb.debug_mac());
        auto timestamp = builder.CreateString(g_detection_data.detection_pb.timestamp());
        auto debug_timestamp_end = builder.CreateString(g_detection_data.detection_pb.debug_timestamp_end());
        
        auto msg = fb_detection::CreateDetectionMessage(builder,
            id_str, debug_mac, timestamp, debug_timestamp_end,
            g_detection_data.detection_pb.debug_processing_time(),
            g_detection_data.detection_pb.rate(), objects);
        
        builder.Finish(msg);
        benchmark::DoNotOptimize(builder.GetBufferPointer());
    }
}
BENCHMARK(BM_Detection_FlatBuffers_Serialize);

// FlatBuffers Deserialize (zero-copy access)
static void BM_Detection_FlatBuffers_Deserialize(benchmark::State& state) {
    for (auto _ : state) {
        auto msg = fb_detection::GetDetectionMessage(g_detection_data.detection_fb_bytes.data());
        benchmark::DoNotOptimize(msg->id());
    }
}
BENCHMARK(BM_Detection_FlatBuffers_Deserialize);

//=============================================================================
// Regulated Message Benchmarks
//=============================================================================

// JSON Serialize (RapidJSON)
static void BM_Regulated_JSON_Serialize_RapidJSON(benchmark::State& state) {
    rapidjson::Document doc;
    doc.Parse(g_regulated_data.json_data.c_str());
    
    for (auto _ : state) {
        rapidjson::StringBuffer buffer;
        rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
        doc.Accept(writer);
        benchmark::DoNotOptimize(buffer.GetString());
    }
}
BENCHMARK(BM_Regulated_JSON_Serialize_RapidJSON);

// JSON Deserialize (simdjson)
static void BM_Regulated_JSON_Deserialize_simdjson(benchmark::State& state) {
    simdjson::dom::parser parser;
    
    for (auto _ : state) {
        auto doc = parser.parse(g_regulated_data.json_data);
        benchmark::DoNotOptimize(doc);
    }
}
BENCHMARK(BM_Regulated_JSON_Deserialize_simdjson);

// JSON Deserialize (RapidJSON) - for comparison
static void BM_Regulated_JSON_Deserialize_RapidJSON(benchmark::State& state) {
    for (auto _ : state) {
        rapidjson::Document doc;
        doc.Parse(g_regulated_data.json_data.c_str());
        benchmark::DoNotOptimize(doc);
    }
}
BENCHMARK(BM_Regulated_JSON_Deserialize_RapidJSON);

// Protobuf Serialize
static void BM_Regulated_Protobuf_Serialize(benchmark::State& state) {
    for (auto _ : state) {
        std::string output;
        g_regulated_data.regulated_pb.SerializeToString(&output);
        benchmark::DoNotOptimize(output);
    }
}
BENCHMARK(BM_Regulated_Protobuf_Serialize);

// Protobuf Deserialize
static void BM_Regulated_Protobuf_Deserialize(benchmark::State& state) {
    for (auto _ : state) {
        pb_regulated::RegulatedMessage msg;
        msg.ParseFromString(g_regulated_data.regulated_pb_bytes);
        benchmark::DoNotOptimize(msg);
    }
}
BENCHMARK(BM_Regulated_Protobuf_Deserialize);

// FlatBuffers Serialize
static void BM_Regulated_FlatBuffers_Serialize(benchmark::State& state) {
    for (auto _ : state) {
        flatbuffers::FlatBufferBuilder builder(4096);
        
        // Build rate map
        std::vector<flatbuffers::Offset<fb_regulated::CameraRate>> rate_entries;
        for (const auto& r : g_regulated_data.regulated_pb.rate()) {
            auto camera = builder.CreateString(r.first);
            rate_entries.push_back(fb_regulated::CreateCameraRate(builder, camera, r.second));
        }
        auto rate_vector = builder.CreateVector(rate_entries);
        
        // Build objects
        std::vector<flatbuffers::Offset<fb_regulated::RegulatedObject>> objects;
        for (const auto& obj : g_regulated_data.regulated_pb.objects()) {
            auto category = builder.CreateString(obj.category());
            auto id = builder.CreateString(obj.id());
            auto type = builder.CreateString(obj.type());
            auto first_seen = builder.CreateString(obj.first_seen());
            
            auto com = fb_regulated::CreateBox(builder,
                obj.center_of_mass().x(), obj.center_of_mass().y(),
                obj.center_of_mass().width(), obj.center_of_mass().height());
            
            fb_regulated::Vector3 trans(
                obj.translation().x(), obj.translation().y(), obj.translation().z());
            fb_regulated::Vector3 size(
                obj.size().x(), obj.size().y(), obj.size().z());
            fb_regulated::Quaternion rot(
                obj.rotation().x(), obj.rotation().y(), obj.rotation().z(), obj.rotation().w());
            fb_regulated::Vector3 vel(
                obj.velocity().x(), obj.velocity().y(), obj.velocity().z());
            
            flatbuffers::Offset<flatbuffers::Vector<flatbuffers::Offset<fb_regulated::CameraBound>>> camera_bounds = 0;
            if (!obj.camera_bounds().empty()) {
                std::vector<flatbuffers::Offset<fb_regulated::CameraBound>> bounds;
                for (const auto& b : obj.camera_bounds()) {
                    auto camera = builder.CreateString(b.first);
                    auto box = fb_regulated::CreateBox(builder,
                        b.second.x(), b.second.y(),
                        b.second.width(), b.second.height());
                    bounds.push_back(fb_regulated::CreateCameraBound(builder, camera, box));
                }
                camera_bounds = builder.CreateVector(bounds);
            }
            
            objects.push_back(fb_regulated::CreateRegulatedObject(builder,
                category, obj.confidence(), com, id, type,
                &trans, &size, &vel, &rot, 0, 0.0, first_seen, camera_bounds));
        }
        
        auto objects_vector = builder.CreateVector(objects);
        auto timestamp = builder.CreateString(g_regulated_data.regulated_pb.timestamp());
        auto id_str = builder.CreateString(g_regulated_data.regulated_pb.id());
        auto name = builder.CreateString(g_regulated_data.regulated_pb.name());
        
        auto msg = fb_regulated::CreateRegulatedMessage(builder,
            timestamp, objects_vector, id_str, name, g_regulated_data.regulated_pb.scene_rate(),
            rate_vector);
        
        builder.Finish(msg);
        benchmark::DoNotOptimize(builder.GetBufferPointer());
    }
}
BENCHMARK(BM_Regulated_FlatBuffers_Serialize);

// FlatBuffers Deserialize (zero-copy access)
static void BM_Regulated_FlatBuffers_Deserialize(benchmark::State& state) {
    for (auto _ : state) {
        auto msg = fb_regulated::GetRegulatedMessage(g_regulated_data.regulated_fb_bytes.data());
        benchmark::DoNotOptimize(msg->id());
    }
}
BENCHMARK(BM_Regulated_FlatBuffers_Deserialize);

//=============================================================================
// Main
//=============================================================================
int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <detection-json-file> <regulated-json-file> [benchmark args...]\n";
        return 1;
    }
    
    // Load test data
    setup_test_data(argv[1], argv[2]);
    
    // Remove our custom args and pass the rest to benchmark
    char** benchmark_argv = new char*[argc - 1];
    benchmark_argv[0] = argv[0];
    for (int i = 3; i < argc; ++i) {
        benchmark_argv[i - 2] = argv[i];
    }
    int benchmark_argc = argc - 2;
    
    ::benchmark::Initialize(&benchmark_argc, benchmark_argv);
    ::benchmark::RunSpecifiedBenchmarks();
    ::benchmark::Shutdown();
    
    delete[] benchmark_argv;
    return 0;
}
