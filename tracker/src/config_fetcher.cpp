#include "config_fetcher.h"
#include "logger.h"
#include <fstream>
#include <httplib.h>
#include <quill/LogMacros.h>
#include <rapidjson/document.h>
#include <rapidjson/prettywriter.h>
#include <rapidjson/stringbuffer.h>

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

    // Step 3: Parse and write API response
    rapidjson::Document api_doc;
    api_doc.Parse(scenes_json.c_str());

    if (api_doc.HasParseError()) {
        LOG_ERROR(logger::get_logger(), "Failed to parse scenes JSON");
        return false;
    }

    // Step 4: Write full API response to file (keep original format)
    std::ofstream api_output(output_file);
    if (!api_output.is_open()) {
        LOG_ERROR(logger::get_logger(), "Failed to open output file: {}", output_file);
        return false;
    }

    rapidjson::StringBuffer api_buffer;
    rapidjson::PrettyWriter<rapidjson::StringBuffer> api_writer(api_buffer);
    api_writer.SetIndent(' ', 2);
    api_doc.Accept(api_writer);

    api_output << api_buffer.GetString();
    api_output.close();

    LOG_INFO(logger::get_logger(), "Successfully wrote API response to {}", output_file);

    // Log summary
    if (api_doc.IsObject() && api_doc.HasMember("count") && api_doc.HasMember("results")) {
        int count = api_doc["count"].GetInt();
        LOG_INFO(logger::get_logger(), "Fetched {} scene(s) from Manager API", count);

        const auto& results = api_doc["results"];
        if (results.IsArray()) {
            for (rapidjson::SizeType i = 0; i < results.Size(); i++) {
                const auto& scene = results[i];
                if (scene.HasMember("name") && scene.HasMember("cameras")) {
                    std::string scene_name = scene["name"].GetString();
                    int camera_count = scene["cameras"].GetArray().Size();
                    LOG_INFO(logger::get_logger(), "  Scene '{}': {} camera(s)", scene_name,
                             camera_count);
                }
            }
        }
    }

    return true;
}
