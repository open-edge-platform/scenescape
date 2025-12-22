#include "config/config_sources.hpp"
#include "config.h"
#include "config/config_fetcher.h"
#include "logger.h"
#include <quill/LogMacros.h>
#include <memory>
#include <stdexcept>
#include <csignal>
#include <chrono>

namespace config {

// ===== FileConfigSource implementation =====
namespace {
std::atomic<bool> g_reload_config{false};
void sighandler([[maybe_unused]] int signum) { g_reload_config.store(true); }
}

FileConfigSource::FileConfigSource(std::string file_path) : file_path_(std::move(file_path)) {
    std::signal(SIGHUP, sighandler);
}

FileConfigSource::~FileConfigSource() { stopWatching(); }

SceneConfiguration FileConfigSource::load() {
    LOG_INFO(logger::get_logger(), "Loading scene config from file: {}", file_path_);
    return load_scene_config_from_json(file_path_);
}

void FileConfigSource::startWatchingForUpdates(ConfigUpdateCallback callback) {
    if (watch_thread_.joinable()) {
        LOG_WARNING(logger::get_logger(), "File config source already watching");
        return;
    }
    callback_ = std::move(callback);
    stop_flag_.store(false);
    watch_thread_ = std::thread(&FileConfigSource::watchLoop, this);
    LOG_INFO(logger::get_logger(), "Started watching for SIGHUP signals on {}", file_path_);
}

void FileConfigSource::stopWatching() {
    if (!watch_thread_.joinable()) { return; }
    stop_flag_.store(true);
    if (watch_thread_.joinable()) { watch_thread_.join(); }
    LOG_INFO(logger::get_logger(), "Stopped watching for config updates");
}

void FileConfigSource::watchLoop() {
    using namespace std::chrono_literals;
    while (!stop_flag_.load()) {
        std::this_thread::sleep_for(1s);
        if (g_reload_config.exchange(false)) {
            LOG_INFO(logger::get_logger(), "SIGHUP received, reloading config from {}", file_path_);
            try {
                SceneConfiguration new_config = load_scene_config_from_json(file_path_);
                if (callback_ && !callback_(new_config)) {
                    LOG_ERROR(logger::get_logger(), "Config update callback failed");
                }
            } catch (const std::exception& e) {
                LOG_ERROR(logger::get_logger(), "Failed to reload config: {}", e.what());
            }
        }
    }
}

std::string FileConfigSource::getDescription() const { return "file: " + file_path_; }

// ===== ApiConfigSource implementation =====
ApiConfigSource::ApiConfigSource(ApiConfig config) : config_(std::move(config)) {
    ConfigFetcher::AuthConfig auth_config{.manager_url = config_.manager_url,
                                         .username = config_.username,
                                         .password = config_.password,
                                         .skip_ssl_verification = config_.skip_ssl_verification};
    fetcher_ = std::make_unique<ConfigFetcher>(auth_config);
}

ApiConfigSource::~ApiConfigSource() { stopWatching(); }

SceneConfiguration ApiConfigSource::load() { return loadFromApiOrFallback(); }

SceneConfiguration ApiConfigSource::loadFromApiOrFallback() {
    LOG_INFO(logger::get_logger(), "Loading scene config from API: {}", config_.manager_url);
    if (!fetcher_->fetch_and_save(config_.output_file)) {
        LOG_WARNING(logger::get_logger(), "API fetch failed, attempting graceful fallback");
        try {
            LOG_INFO(logger::get_logger(), "Loading previous API output: {}", config_.output_file);
            return load_scene_config_from_json(config_.output_file);
        } catch (const std::exception& e1) {
            LOG_WARNING(logger::get_logger(), "Previous API output invalid: {}", e1.what());
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
    return load_scene_config_from_json(config_.output_file);
}

void ApiConfigSource::startWatchingForUpdates(ConfigUpdateCallback callback) {
    if (callback_) {
        LOG_WARNING(logger::get_logger(), "API config source already watching");
        return;
    }
    callback_ = std::move(callback);
    if (config_.reload_topic.empty()) {
        LOG_WARNING(logger::get_logger(), "No reload_topic configured - API config will not update at runtime");
        return;
    }
    // TODO: Subscribe to MQTT reload topic and invoke handleReloadTrigger()
    LOG_INFO(logger::get_logger(), "API config source will reload on MQTT topic: {} (TODO)", config_.reload_topic);
}

void ApiConfigSource::stopWatching() {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    // TODO: Unsubscribe from MQTT topic
    callback_ = nullptr;
    LOG_INFO(logger::get_logger(), "Stopped watching for API config updates");
}

void ApiConfigSource::handleReloadTrigger() {
    LOG_INFO(logger::get_logger(), "API reload triggered via MQTT, fetching updated config");
    std::lock_guard<std::mutex> lock(callback_mutex_);
    if (!callback_) { return; }
    try {
        SceneConfiguration new_config = loadFromApiOrFallback();
        if (!callback_(new_config)) {
            LOG_ERROR(logger::get_logger(), "Config update callback returned false");
        } else {
            LOG_INFO(logger::get_logger(), "Successfully reloaded config from API");
        }
    } catch (const std::exception& e) {
        LOG_ERROR(logger::get_logger(), "Failed to reload config from API: {}", e.what());
    }
}

std::string ApiConfigSource::getDescription() const {
    std::string desc = "api: " + config_.manager_url;
    desc += config_.reload_topic.empty() ? " (no runtime updates)" : (" (mqtt: " + config_.reload_topic + ")");
    return desc;
}

// ===== Factory function =====
std::unique_ptr<IConfigSource> createConfigSource(const Config& service_config) {
    const auto& scenes_config = service_config.scenes;
    if (scenes_config.source == "file") {
        if (scenes_config.file_path.empty()) {
            throw std::runtime_error("scene_config.file_path is required when source='file'");
        }
        LOG_INFO(logger::get_logger(), "Creating file-based config source: {}", scenes_config.file_path);
        return std::make_unique<FileConfigSource>(scenes_config.file_path);
    } else if (scenes_config.source == "api") {
        if (scenes_config.api_endpoint.url.empty()) {
            throw std::runtime_error("scene_config.api_endpoint.url is required when source='api'");
        }
        if (scenes_config.api_endpoint.output_file.empty()) {
            throw std::runtime_error("scene_config.api_endpoint.output_file is required when source='api'");
        }
        if (scenes_config.api_endpoint.reload_topic.empty()) {
            LOG_WARNING(logger::get_logger(), "scene_config.api_endpoint.reload_topic is empty - API config will not update at runtime");
        }
        ApiConfigSource::ApiConfig api_config{.manager_url = scenes_config.api_endpoint.url,
                                              .username = scenes_config.api_endpoint.username,
                                              .password = scenes_config.api_endpoint.password,
                                              .output_file = scenes_config.api_endpoint.output_file,
                                              .fallback_file = scenes_config.file_path,
                                              .skip_ssl_verification = scenes_config.api_endpoint.skip_ssl_verification,
                                              .reload_topic = scenes_config.api_endpoint.reload_topic};
        LOG_INFO(logger::get_logger(), "Creating API-based config source: {} (reload topic: {})", scenes_config.api_endpoint.url,
                 api_config.reload_topic.empty() ? "none" : api_config.reload_topic);
        return std::make_unique<ApiConfigSource>(std::move(api_config));
    } else {
        throw std::runtime_error("Invalid scene_config.source: '" + scenes_config.source + "' (must be 'file' or 'api')");
    }
}

} // namespace config
