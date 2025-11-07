#pragma once

#include "config/config_source.h"
#include <atomic>
#include <string>
#include <thread>

namespace config {

/**
 * @brief File-based configuration source with SIGHUP reload support
 * 
 * Loads scene configuration from a JSON file and watches for SIGHUP signals
 * to trigger reloads. Uses a background polling thread to check the signal
 * flag without blocking the main thread.
 * 
 * Thread-safety:
 * - Signal handler sets atomic flag (async-signal-safe)
 * - Background thread polls flag and invokes callback
 * - Callback invocation is serialized (one reload at a time)
 */
class FileConfigSource : public IConfigSource {
public:
    /**
     * @brief Construct a file-based config source
     * 
     * @param file_path Absolute path to scenes.json file
     */
    explicit FileConfigSource(std::string file_path);

    /**
     * @brief Destructor - stops watching thread if running
     */
    ~FileConfigSource() override;

    // Disable copy/move (has thread member)
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

} // namespace config
