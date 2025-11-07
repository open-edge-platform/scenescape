#include "config/file_config_source.h"
#include "logger.h"
#include <quill/LogMacros.h>
#include <csignal>
#include <chrono>

namespace config {

namespace {
// Global signal flag for SIGHUP (async-signal-safe)
std::atomic<bool> g_reload_config{false};

void sighandler([[maybe_unused]] int signum) {
    g_reload_config.store(true);
}
} // anonymous namespace

FileConfigSource::FileConfigSource(std::string file_path) : file_path_(std::move(file_path)) {
    // Register SIGHUP handler
    std::signal(SIGHUP, sighandler);
}

FileConfigSource::~FileConfigSource() {
    stopWatching();
}

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
    if (!watch_thread_.joinable()) {
        return;
    }

    stop_flag_.store(true);
    if (watch_thread_.joinable()) {
        watch_thread_.join();
    }
    
    LOG_INFO(logger::get_logger(), "Stopped watching for config updates");
}

void FileConfigSource::watchLoop() {
    using namespace std::chrono_literals;

    while (!stop_flag_.load()) {
        // Check reload flag every second
        std::this_thread::sleep_for(1s);

        if (g_reload_config.exchange(false)) {
            LOG_INFO(logger::get_logger(), "SIGHUP received, reloading config from {}", file_path_);

            try {
                SceneConfiguration new_config = load_scene_config_from_json(file_path_);
                
                if (callback_ && !callback_(new_config)) {
                    LOG_ERROR(logger::get_logger(), "Config update callback failed");
                    // Continue watching despite callback failure
                }
            } catch (const std::exception& e) {
                LOG_ERROR(logger::get_logger(), "Failed to reload config: {}", e.what());
                // Continue watching despite load failure (resilient to transient errors)
            }
        }
    }
}

std::string FileConfigSource::getDescription() const {
    return "file: " + file_path_;
}

} // namespace config
