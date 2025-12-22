#pragma once

#include <atomic>
#include <mutex>
#include <string>
#include <thread>
#include <memory>

#include "config/config_source.h"
#include "config/scene_config.h"
#include "config.h"

// Forward declaration of global ConfigFetcher to avoid heavy header include
class ConfigFetcher;

namespace config {

// File-based configuration source with SIGHUP reload support
class FileConfigSource : public IConfigSource {
public:
    explicit FileConfigSource(std::string file_path);
    ~FileConfigSource() override;

    // Disable copy/move
    FileConfigSource(const FileConfigSource&) = delete;
    FileConfigSource& operator=(const FileConfigSource&) = delete;

    SceneConfiguration load() override;
    void startWatchingForUpdates(ConfigUpdateCallback callback) override;
    void stopWatching() override;
    ConfigSourceType getType() const override { return ConfigSourceType::FILE; }
    std::string getDescription() const override;

private:
    void watchLoop();

    std::string file_path_;
    ConfigUpdateCallback callback_;
    std::atomic<bool> stop_flag_{false};
    std::thread watch_thread_;
};

// API-based configuration source with MQTT event triggering
class ApiConfigSource : public IConfigSource {
public:
    struct ApiConfig {
        std::string manager_url;
        std::string username;
        std::string password;
        std::string output_file;
        std::string fallback_file;
        bool skip_ssl_verification;
        std::string reload_topic;
    };

    explicit ApiConfigSource(ApiConfig config);
    ~ApiConfigSource() override;

    // Disable copy/move
    ApiConfigSource(const ApiConfigSource&) = delete;
    ApiConfigSource& operator=(const ApiConfigSource&) = delete;

    SceneConfiguration load() override;
    void startWatchingForUpdates(ConfigUpdateCallback callback) override;
    void stopWatching() override;
    ConfigSourceType getType() const override { return ConfigSourceType::API; }
    std::string getDescription() const override;

private:
    void handleReloadTrigger();
    SceneConfiguration loadFromApiOrFallback();

    ApiConfig config_;
     std::unique_ptr<::ConfigFetcher> fetcher_;
    ConfigUpdateCallback callback_;
    std::mutex callback_mutex_;
};

// Factory function
std::unique_ptr<IConfigSource> createConfigSource(const Config& service_config);

} // namespace config
