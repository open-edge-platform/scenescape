#include "config/api_config_source.h"
#include "logger.h"
#include <quill/LogMacros.h>
#include <stdexcept>

namespace config {

ApiConfigSource::ApiConfigSource(ApiConfig config) : config_(std::move(config)) {
    // Create ConfigFetcher with auth settings
    ConfigFetcher::AuthConfig auth_config{
        .manager_url = config_.manager_url,
        .username = config_.username,
        .password = config_.password,
        .skip_ssl_verification = config_.skip_ssl_verification
    };
    fetcher_ = std::make_unique<ConfigFetcher>(auth_config);
}

ApiConfigSource::~ApiConfigSource() {
    stopWatching();
}

SceneConfiguration ApiConfigSource::load() {
    return loadFromApiOrFallback();
}

SceneConfiguration ApiConfigSource::loadFromApiOrFallback() {
    LOG_INFO(logger::get_logger(), "Loading scene config from API: {}", config_.manager_url);

    // Attempt to fetch from API and save to file (ConfigFetcher writes in correct file format)
    if (!fetcher_->fetch_and_save(config_.output_file)) {
        LOG_WARNING(logger::get_logger(), "API fetch failed, attempting graceful fallback");
        
        // Try to load from previous API output file first
        try {
            LOG_INFO(logger::get_logger(), "Loading previous API output: {}", config_.output_file);
            return load_scene_config_from_json(config_.output_file);
        } catch (const std::exception& e1) {
            LOG_WARNING(logger::get_logger(), "Previous API output invalid: {}", e1.what());
            
            // Fall back to fallback_file if configured
            if (!config_.fallback_file.empty()) {
                try {
                    LOG_INFO(logger::get_logger(), "Loading fallback file: {}", config_.fallback_file);
                    return load_scene_config_from_json(config_.fallback_file);
                } catch (const std::exception& e2) {
                    LOG_ERROR(logger::get_logger(), "Fallback file invalid: {}", e2.what());
                }
            }
            
            throw std::runtime_error("Failed to load scene config from API and all fallbacks exhausted");
        }
    }

    // Load the freshly fetched config (maintains consistent file format internally)
    return load_scene_config_from_json(config_.output_file);
}

void ApiConfigSource::startWatchingForUpdates(ConfigUpdateCallback callback) {
    if (callback_) {
        LOG_WARNING(logger::get_logger(), "API config source already watching");
        return;
    }

    callback_ = std::move(callback);

    // Validate reload_topic is configured
    if (config_.reload_topic.empty()) {
        LOG_WARNING(logger::get_logger(), 
                   "No reload_topic configured - API config will not update at runtime");
        return;
    }

    // TODO: Subscribe to MQTT reload topic
    // When MqttClient is available, create subscription that calls handleReloadTrigger()
    LOG_INFO(logger::get_logger(), 
            "API config source will reload on MQTT topic: {} (TODO: implement subscription)",
            config_.reload_topic);
}

void ApiConfigSource::stopWatching() {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    
    // TODO: Unsubscribe from MQTT topic and disconnect client
    
    callback_ = nullptr;
    LOG_INFO(logger::get_logger(), "Stopped watching for API config updates");
}

void ApiConfigSource::handleReloadTrigger() {
    LOG_INFO(logger::get_logger(), "API reload triggered via MQTT, fetching updated config");

    std::lock_guard<std::mutex> lock(callback_mutex_);

    if (!callback_) {
        return;
    }

    try {
        // Fetch and load new config (graceful fallback handled inside)
        SceneConfiguration new_config = loadFromApiOrFallback();

        // Invoke callback with new config
        if (!callback_(new_config)) {
            LOG_ERROR(logger::get_logger(), "Config update callback returned false");
        } else {
            LOG_INFO(logger::get_logger(), "Successfully reloaded config from API");
        }
    } catch (const std::exception& e) {
        // Graceful degradation: Log error but keep existing config
        LOG_ERROR(logger::get_logger(), "Failed to reload config from API: {}", e.what());
    }
}

std::string ApiConfigSource::getDescription() const {
    std::string desc = "api: " + config_.manager_url;
    if (!config_.reload_topic.empty()) {
        desc += " (mqtt: " + config_.reload_topic + ")";
    } else {
        desc += " (no runtime updates)";
    }
    return desc;
}

} // namespace config
