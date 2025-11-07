#pragma once

#include "config/config_source.h"
#include <memory>

// Forward declaration
struct Config;

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
std::unique_ptr<IConfigSource> createConfigSource(const Config& service_config);

} // namespace config
