#pragma once

#include "config/config_source.h"
#include "config_fetcher.h"
#include <atomic>
#include <chrono>
#include <memory>
#include <optional>
#include <string>
#include <thread>

namespace config {

/**
 * @brief API-based configuration source with MQTT event triggering
 * 
 * Loads scene configuration from Manager REST API and watches for updates via
 * MQTT reload topic subscription. ConfigFetcher writes API response to file
 * in the correct format, then SceneConfig::from_file() loads it to maintain
 * consistent internal file format.
 * 
 * Update trigger:
 * - MQTT message on scene_config.api.reload_topic
 * 
 * Graceful degradation:
 * - On API fetch failure: Falls back to last-known-good file
 * - On parse failure: Keeps previous config, logs error
 * - Empty reload_topic: Logs warning, no runtime updates
 * 
 * Thread-safety:
 * - MQTT event handler invokes callback from MQTT thread
 * - Callback invocation is serialized via mutex
 */
class ApiConfigSource : public IConfigSource {
public:
    /**
     * @brief Configuration for API source
     */
    struct ApiConfig {
        std::string manager_url;           ///< Manager API URL
        std::string username;              ///< Auth username
        std::string password;              ///< Auth password
        std::string output_file;           ///< File path to write fetched config
        std::string fallback_file;         ///< Fallback file path if API fetch fails
        bool skip_ssl_verification;        ///< Skip SSL cert verification (dev only)
        std::string reload_topic;          ///< MQTT topic for reload events (required)
    };

    /**
     * @brief Construct an API-based config source
     * 
     * @param config API configuration
     */
    explicit ApiConfigSource(ApiConfig config);

    /**
     * @brief Destructor - stops MQTT subscription if active
     */
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
    std::unique_ptr<ConfigFetcher> fetcher_;
    ConfigUpdateCallback callback_;
    std::mutex callback_mutex_; ///< Serializes callback invocation from MQTT thread
    // TODO: Add MqttClient member when MQTT subscription is implemented
};

} // namespace config
