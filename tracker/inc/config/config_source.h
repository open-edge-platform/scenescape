#pragma once

#include "scene_config.h"
#include <functional>
#include <memory>
#include <string>

namespace config {

/**
 * @brief Callback invoked when scene configuration updates are detected
 * 
 * @param new_config The newly loaded scene configuration
 * @return true if update was successfully applied, false on error
 */
using ConfigUpdateCallback = std::function<bool(const SceneConfiguration& new_config)>;

/**
 * @brief Type of configuration source
 */
enum class ConfigSourceType {
    FILE, ///< File-based config with SIGHUP reload
    API   ///< API-based config with MQTT event triggering
};

/**
 * @brief Abstract interface for scene configuration sources
 * 
 * Decouples the mechanism for loading and monitoring scene configuration
 * from the actual update logic. Implementations handle different update
 * triggers (SIGHUP signals, MQTT events) while providing a uniform interface.
 * 
 * Thread-safety: Implementations must ensure thread-safe callback invocation
 * and safe concurrent access to watch/stop operations.
 */
class IConfigSource {
public:
    virtual ~IConfigSource() = default;

    /**
     * @brief Load the initial scene configuration
     * 
     * Called once at startup to fetch the initial config state.
     * May block on I/O (file read, network request).
     * 
     * @return SceneConfiguration The loaded configuration
     * @throws std::runtime_error if loading fails (validation error, I/O error)
     */
    virtual SceneConfiguration load() = 0;

    /**
     * @brief Start watching for configuration updates
     * 
     * Registers a callback to be invoked when the configuration changes.
     * The implementation decides how to detect changes (signals, MQTT events).
     * 
     * For file sources: Sets up signal handler for SIGHUP
     * For API sources: Subscribes to MQTT reload topic
     * 
     * @param callback Function to call when updates are detected
     *                 Receives new SceneConfiguration, returns true on success
     */
    virtual void startWatchingForUpdates(ConfigUpdateCallback callback) = 0;

    /**
     * @brief Stop watching for configuration updates
     * 
     * Unregisters callback and stops any background threads/timers.
     * Implementations must ensure clean shutdown without blocking indefinitely.
     */
    virtual void stopWatching() = 0;

    /**
     * @brief Get the configuration source type
     * 
     * @return ConfigSourceType The type of this config source
     */
    virtual ConfigSourceType getType() const = 0;

    /**
     * @brief Get human-readable description of this config source
     * 
     * @return std::string Description (e.g., "file: /path/to/scenes.json")
     */
    virtual std::string getDescription() const = 0;
};

} // namespace config
