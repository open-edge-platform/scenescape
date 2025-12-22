#pragma once

#include <string>
#include "config.h"

namespace config_schema {
// Validate a JSON file against a JSON Schema file. Throws std::runtime_error on failure.
void validate_json_file_against_schema(const std::string &jsonPath, const std::string &schemaPath);
}

namespace service_config {
// Load Config from JSON path and validate against schema if provided.
// If schema_path is empty, this will look for a default schema at
// "config/schema.json" relative to the current working directory and validate if present.
// Throws std::runtime_error on any failure.
Config load_and_validate_from_paths(const std::string &config_path,
                                    const std::string &schema_path_optional);
}
