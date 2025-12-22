#include "config/config_validation.hpp"
#include <filesystem>
#include <stdexcept>
#include <fstream>
#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>
#include <rapidjson/schema.h>

namespace config_schema {

static rapidjson::Document load_json_doc_from_file(const std::string &path) {
    std::ifstream in(path);
    if(!in.is_open()) throw std::runtime_error("Failed to open JSON: " + path);
    rapidjson::IStreamWrapper isw(in);
    rapidjson::Document d;
    d.ParseStream(isw);
    if(d.HasParseError()) throw std::runtime_error("Invalid JSON: parse error");
    return d;
}

void validate_json_file_against_schema(const std::string &jsonPath, const std::string &schemaPath) {
    rapidjson::Document doc = load_json_doc_from_file(jsonPath);
    rapidjson::Document schema = load_json_doc_from_file(schemaPath);
    rapidjson::SchemaDocument sd(schema);
    rapidjson::SchemaValidator validator(sd);
    if(!doc.Accept(validator)) {
        throw std::runtime_error("Schema validation failed");
    }
}

} // namespace config_schema

namespace service_config {

Config load_and_validate_from_paths(const std::string &config_path,
                                    const std::string &schema_path_optional) {
    if (config_path.empty()) {
        throw std::runtime_error("Service configuration path is required");
    }

    std::string schema_path = schema_path_optional;

    if (schema_path.empty()) {
        // Default schema path if available
        const std::string default_schema = "config/schema.json";
        if (std::filesystem::exists(default_schema)) {
            schema_path = default_schema;
        }
    }

    if (!schema_path.empty()) {
        config_schema::validate_json_file_against_schema(config_path, schema_path);
    }

    return load_config_from_json(config_path);
}

} // namespace service_config
