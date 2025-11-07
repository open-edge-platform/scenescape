#include "config/config_source.h"
#include "config/file_config_source.h"
#include "config/api_config_source.h"
#include "config.h"
#include "logger.h"
#include <quill/LogMacros.h>
#include <memory>
#include <stdexcept>

namespace config {

/**
 * @brief Create a config source based on service configuration
 * 
 * Factory function that instantiates the appropriate IConfigSource implementation
 * based on the scenes configuration source type.
 * 
 * @param service_config The main service configuration
 * @return std::unique_ptr<IConfigSource> The created config source
 * @throws std::runtime_error if source type is invalid or required fields are missing
 */
std::unique_ptr<IConfigSource> createConfigSource(const Config& service_config) {
    const auto& scenes_config = service_config.scenes;

    if (scenes_config.source == "file") {
        // File-based config source
        if (scenes_config.file_path.empty()) {
            throw std::runtime_error("scene_config.file_path is required when source='file'");
        }

        LOG_INFO(logger::get_logger(), 
                "Creating file-based config source: {}", 
                scenes_config.file_path);

        return std::make_unique<FileConfigSource>(scenes_config.file_path);

    } else if (scenes_config.source == "api") {
        // API-based config source
        if (scenes_config.api_endpoint.url.empty()) {
            throw std::runtime_error("scene_config.api_endpoint.url is required when source='api'");
        }
        if (scenes_config.api_endpoint.output_file.empty()) {
            throw std::runtime_error("scene_config.api_endpoint.output_file is required when source='api'");
        }
        if (scenes_config.api_endpoint.reload_topic.empty()) {
            LOG_WARNING(logger::get_logger(), 
                       "scene_config.api_endpoint.reload_topic is empty - API config will not update at runtime");
        }

        ApiConfigSource::ApiConfig api_config{
            .manager_url = scenes_config.api_endpoint.url,
            .username = scenes_config.api_endpoint.username,
            .password = scenes_config.api_endpoint.password,
            .output_file = scenes_config.api_endpoint.output_file,
            .fallback_file = scenes_config.file_path, // Use file_path as fallback
            .skip_ssl_verification = scenes_config.api_endpoint.skip_ssl_verification,
            .reload_topic = scenes_config.api_endpoint.reload_topic
        };

        LOG_INFO(logger::get_logger(), 
                "Creating API-based config source: {} (reload topic: {})", 
                scenes_config.api_endpoint.url,
                api_config.reload_topic.empty() ? "none" : api_config.reload_topic);

        return std::make_unique<ApiConfigSource>(std::move(api_config));

    } else {
        throw std::runtime_error("Invalid scene_config.source: '" + scenes_config.source + 
                               "' (must be 'file' or 'api')");
    }
}

} // namespace config
