// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#ifndef TRACKER_TEST_UTILS_JSON_SCHEMA_VALIDATOR_HPP
#define TRACKER_TEST_UTILS_JSON_SCHEMA_VALIDATOR_HPP

#include <gtest/gtest.h>
#include <rapidjson/document.h>
#include <rapidjson/istreamwrapper.h>
#include <rapidjson/schema.h>

#include <filesystem>
#include <fstream>
#include <memory>
#include <string>

namespace tracker {
namespace test {

/**
 * @brief JSON Schema validator for testing log output.
 *
 * Uses RapidJSON to validate JSON strings against a JSON Schema file.
 */
class JsonSchemaValidator {
public:
    /**
     * @brief Construct validator by loading schema from file.
     * @param schema_path Path to the JSON schema file
     */
    explicit JsonSchemaValidator(const std::filesystem::path& schema_path) {
        std::ifstream ifs(schema_path);
        EXPECT_TRUE(ifs.is_open()) << "Failed to open schema file: " << schema_path;

        rapidjson::IStreamWrapper isw(ifs);
        rapidjson::Document schema_doc;
        schema_doc.ParseStream(isw);
        EXPECT_FALSE(schema_doc.HasParseError())
            << "Failed to parse JSON schema from: " << schema_path;

        schema_ = std::make_unique<rapidjson::SchemaDocument>(schema_doc);
        validator_ = std::make_unique<rapidjson::SchemaValidator>(*schema_);
    }

    /**
     * @brief Validate a JSON string against the schema.
     * @return true if valid, false otherwise (with error message in get_error())
     */
    bool validate(const std::string& json_str) {
        rapidjson::Document doc;
        doc.Parse(json_str.c_str());

        if (doc.HasParseError()) {
            last_error_ = "JSON parse error at offset " +
                          std::to_string(doc.GetErrorOffset()) + ": invalid JSON";
            return false;
        }

        validator_->Reset();
        if (!doc.Accept(*validator_)) {
            rapidjson::StringBuffer sb;
            validator_->GetInvalidSchemaPointer().StringifyUriFragment(sb);
            last_error_ = "Schema validation failed at: " + std::string(sb.GetString()) +
                          ", keyword: " + validator_->GetInvalidSchemaKeyword();
            return false;
        }

        return true;
    }

    [[nodiscard]] const std::string& get_error() const { return last_error_; }

private:
    std::unique_ptr<rapidjson::SchemaDocument> schema_;
    std::unique_ptr<rapidjson::SchemaValidator> validator_;
    std::string last_error_;
};

/**
 * @brief Get path to the log output JSON schema file.
 *
 * Uses TEST_SCHEMA_DIR defined by CMake when available, otherwise falls back
 * to a relative path for IDE/local development.
 */
inline std::filesystem::path get_log_schema_path() {
#ifdef TEST_SCHEMA_DIR
    return std::filesystem::path(TEST_SCHEMA_DIR) / "log.schema.json";
#else
    // Fallback for IDE/local development - navigate from utils to tracker/schema
    return std::filesystem::path(__FILE__).parent_path().parent_path().parent_path() / "schema" /
           "log.schema.json";
#endif
}

} // namespace test
} // namespace tracker

#endif // TRACKER_TEST_UTILS_JSON_SCHEMA_VALIDATOR_HPP
