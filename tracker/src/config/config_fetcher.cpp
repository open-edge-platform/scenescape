#include "config/config_fetcher.h"
#include "logger.h"
#include <fstream>
#include <httplib.h>
#include <quill/LogMacros.h>
#include <rapidjson/document.h>
#include <rapidjson/prettywriter.h>
#include <rapidjson/stringbuffer.h>
#include <unordered_set>

ConfigFetcher::ConfigFetcher(const AuthConfig& auth_config) : config_(auth_config) {
    // Extract host and port from manager_url
    // Assuming format: https://localhost or https://localhost:443
    std::string host = config_.manager_url;

    // Remove protocol
    size_t pos = host.find("://");
    if (pos != std::string::npos) {
        host = host.substr(pos + 3);
    }

    // Extract port if present
    int port = 443; // Default HTTPS port
    pos = host.find(":");
    if (pos != std::string::npos) {
        port = std::stoi(host.substr(pos + 1));
        host = host.substr(0, pos);
    }

    // Create HTTPS client with full URL
    client_ = std::make_unique<httplib::Client>(config_.manager_url);

    // Configure SSL verification
    if (config_.skip_ssl_verification) {
        client_->enable_server_certificate_verification(false);
    }

    // Set timeout
    client_->set_connection_timeout(10); // 10 seconds
    client_->set_read_timeout(30);       // 30 seconds

    LOG_INFO(logger::get_logger(), "ConfigFetcher initialized for {}", config_.manager_url);
}

ConfigFetcher::~ConfigFetcher() = default;

bool ConfigFetcher::authenticate() {
    // Build JSON payload
    std::string post_data =
        "{\"username\":\"" + config_.username + "\",\"password\":\"" + config_.password + "\"}";

    LOG_INFO(logger::get_logger(), "Authenticating with Manager API");

    // POST request with content type parameter (not in headers to avoid duplication)
    auto res = client_->Post("/api/v1/auth", post_data, "application/json");

    if (!res) {
        LOG_ERROR(logger::get_logger(), "Authentication request failed: {}",
                  httplib::to_string(res.error()));
        return false;
    }

    if (res->status != 200) {
        LOG_ERROR(logger::get_logger(), "Authentication failed with HTTP {}: {}", res->status,
                  res->body);
        return false;
    }

    // Parse JSON response to get token
    rapidjson::Document doc;
    doc.Parse(res->body.c_str());

    if (doc.HasParseError() || !doc.IsObject() || !doc.HasMember("token")) {
        LOG_ERROR(logger::get_logger(), "Failed to parse auth response: {}", res->body);
        return false;
    }

    auth_token_ = doc["token"].GetString();
    LOG_INFO(logger::get_logger(), "Successfully authenticated, token: {}...",
             auth_token_.substr(0, 8));

    return true;
}

std::string ConfigFetcher::fetch_scenes() {
    if (auth_token_.empty()) {
        LOG_ERROR(logger::get_logger(), "Cannot fetch scenes: not authenticated");
        return "";
    }

    LOG_INFO(logger::get_logger(), "Fetching scenes from Manager API");

    // GET request with auth token
    httplib::Headers headers = {{"Authorization", "Token " + auth_token_}};

    auto res = client_->Get("/api/v1/scenes", headers);

    if (!res) {
        LOG_ERROR(logger::get_logger(), "Scenes request failed: {}",
                  httplib::to_string(res.error()));
        return "";
    }

    if (res->status != 200) {
        LOG_ERROR(logger::get_logger(), "Failed to fetch scenes, HTTP {}: {}", res->status,
                  res->body);
        return "";
    }

    LOG_INFO(logger::get_logger(), "Successfully fetched scenes ({} bytes)", res->body.size());

    return res->body;
}

bool ConfigFetcher::fetch_and_save(const std::string& output_file) {
    LOG_INFO(logger::get_logger(), "Starting configuration fetch from Manager API");

    // Step 1: Authenticate
    if (!authenticate()) {
        LOG_ERROR(logger::get_logger(), "Authentication failed, aborting");
        return false;
    }

    // Step 2: Fetch scenes
    std::string scenes_json = fetch_scenes();
    if (scenes_json.empty()) {
        LOG_ERROR(logger::get_logger(), "Failed to fetch scenes, aborting");
        return false;
    }

    // Step 3: Parse API response
    rapidjson::Document api_doc;
    api_doc.Parse(scenes_json.c_str());

    if (api_doc.HasParseError()) {
        LOG_ERROR(logger::get_logger(), "Failed to parse scenes JSON");
        return false;
    }

    // Step 4: Transform API response into internal scenes.json unified format
    // Internal schema: { cameras: [...], scenes: [...] }
    rapidjson::Document scenes_doc;
    scenes_doc.SetObject();

    rapidjson::Value cameras(rapidjson::kArrayType);
    rapidjson::Value scenes(rapidjson::kArrayType);

    // Temporary map to avoid duplicate cameras across scenes
    std::unordered_set<std::string> camera_ids_seen;

    if (api_doc.IsObject() && api_doc.HasMember("results") && api_doc["results"].IsArray()) {
        const auto& results = api_doc["results"].GetArray();
        for (rapidjson::SizeType i = 0; i < results.Size(); ++i) {
            const auto& scene = results[i];

            // Build scene entry
            rapidjson::Value scene_obj(rapidjson::kObjectType);
            if (scene.HasMember("id") && scene["id"].IsString()) {
                scene_obj.AddMember("id", rapidjson::Value(scene["id"].GetString(), scenes_doc.GetAllocator()), scenes_doc.GetAllocator());
            } else {
                // Fallback to index-based id if missing
                std::string sid = "scene_" + std::to_string(i + 1);
                scene_obj.AddMember("id", rapidjson::Value(sid.c_str(), scenes_doc.GetAllocator()), scenes_doc.GetAllocator());
            }

            if (scene.HasMember("name") && scene["name"].IsString()) {
                scene_obj.AddMember("name", rapidjson::Value(scene["name"].GetString(), scenes_doc.GetAllocator()), scenes_doc.GetAllocator());
            } else {
                std::string sname = "Scene " + std::to_string(i + 1);
                scene_obj.AddMember("name", rapidjson::Value(sname.c_str(), scenes_doc.GetAllocator()), scenes_doc.GetAllocator());
            }

            rapidjson::Value scene_cameras(rapidjson::kArrayType);

            // Extract cameras from scene entry
            if (scene.HasMember("cameras") && scene["cameras"].IsArray()) {
                const auto& cams = scene["cameras"].GetArray();
                for (rapidjson::SizeType j = 0; j < cams.Size(); ++j) {
                    const auto& cam = cams[j];

                    // Determine camera id and name
                    std::string cam_id;
                    std::string cam_name;
                    if (cam.HasMember("id")) {
                        if (cam["id"].IsString()) cam_id = cam["id"].GetString();
                        else if (cam["id"].IsInt()) cam_id = std::to_string(cam["id"].GetInt());
                    }
                    if (cam_id.empty() && cam.HasMember("name") && cam["name"].IsString()) {
                        cam_id = cam["name"].GetString();
                    }
                    if (cam.HasMember("name") && cam["name"].IsString()) {
                        cam_name = cam["name"].GetString();
                    } else if (!cam_id.empty()) {
                        cam_name = cam_id;
                    } else {
                        cam_name = "Camera";
                    }

                    if (cam_id.empty()) {
                        // Skip cameras without identifiable id
                        continue;
                    }

                    // Add camera id to scene cameras
                    scene_cameras.PushBack(rapidjson::Value(cam_id.c_str(), scenes_doc.GetAllocator()), scenes_doc.GetAllocator());

                    // Add camera to global cameras array if first time seen
                    if (camera_ids_seen.insert(cam_id).second) {
                        rapidjson::Value cam_obj(rapidjson::kObjectType);
                        cam_obj.AddMember("id", rapidjson::Value(cam_id.c_str(), scenes_doc.GetAllocator()), scenes_doc.GetAllocator());
                        cam_obj.AddMember("name", rapidjson::Value(cam_name.c_str(), scenes_doc.GetAllocator()), scenes_doc.GetAllocator());

                        // Intrinsics/distortion defaults (dummy values as per current design)
                        rapidjson::Value intr(rapidjson::kObjectType);
                        intr.AddMember("fx", 0.0, scenes_doc.GetAllocator());
                        intr.AddMember("fy", 0.0, scenes_doc.GetAllocator());
                        intr.AddMember("cx", 0.0, scenes_doc.GetAllocator());
                        intr.AddMember("cy", 0.0, scenes_doc.GetAllocator());
                        cam_obj.AddMember("intrinsics", intr, scenes_doc.GetAllocator());

                        rapidjson::Value dist(rapidjson::kObjectType);
                        dist.AddMember("k1", 0.0, scenes_doc.GetAllocator());
                        dist.AddMember("k2", 0.0, scenes_doc.GetAllocator());
                        dist.AddMember("p1", 0.0, scenes_doc.GetAllocator());
                        dist.AddMember("p2", 0.0, scenes_doc.GetAllocator());
                        cam_obj.AddMember("distortion", dist, scenes_doc.GetAllocator());

                        cameras.PushBack(cam_obj, scenes_doc.GetAllocator());
                    }
                }
            }

            // Attach cameras list to scene and push
            scene_obj.AddMember("cameras", scene_cameras, scenes_doc.GetAllocator());
            scenes.PushBack(scene_obj, scenes_doc.GetAllocator());
        }
    } else {
        LOG_ERROR(logger::get_logger(), "Unexpected API response format: missing 'results' array");
        return false;
    }

    // Build final document
    scenes_doc.AddMember("cameras", cameras, scenes_doc.GetAllocator());
    scenes_doc.AddMember("scenes", scenes, scenes_doc.GetAllocator());

    // Pretty-write unified scenes.json to output file
    std::ofstream out(output_file);
    if (!out.is_open()) {
        LOG_ERROR(logger::get_logger(), "Failed to open output file: {}", output_file);
        return false;
    }
    rapidjson::StringBuffer buffer;
    rapidjson::PrettyWriter<rapidjson::StringBuffer> writer(buffer);
    writer.SetIndent(' ', 2);
    scenes_doc.Accept(writer);
    out << buffer.GetString();
    out.close();

    LOG_INFO(logger::get_logger(), "Wrote unified scenes config to {}", output_file);

    // Log summary
    LOG_INFO(logger::get_logger(), "Unified scenes: {} camera(s), {} scene(s)",
             cameras.Size(), scenes.Size());

    return true;
}
