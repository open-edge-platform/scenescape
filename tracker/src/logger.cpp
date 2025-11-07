#include "logger.h"
#include <algorithm>
#include <quill/Backend.h>
#include <quill/core/LogLevel.h>
#include <quill/Frontend.h>
#include <quill/Logger.h>
#include <quill/LogMacros.h>
#include <quill/sinks/ConsoleSink.h>
#include <quill/sinks/JsonSink.h>
#include <string>
#include <unordered_map>

namespace logger {

// Helper function to convert string log level to quill::LogLevel
static quill::LogLevel parse_to_quill_level(const std::string& level) {
    static const std::unordered_map<std::string, quill::LogLevel> level_map = {
        {"trace", quill::LogLevel::TraceL1}, {"debug", quill::LogLevel::Debug},
        {"info", quill::LogLevel::Info},     {"warning", quill::LogLevel::Warning},
        {"warn", quill::LogLevel::Warning},  {"error", quill::LogLevel::Error}};

    std::string lower_level = level;
    std::transform(lower_level.begin(), lower_level.end(), lower_level.begin(), ::tolower);

    auto it = level_map.find(lower_level);
    if (it == level_map.end()) {
        throw std::invalid_argument("Invalid log level: " + level +
                                    ". Valid levels are: trace, debug, info, warning, error");
    }
    return it->second;
}

static std::string current_log_level = "info";
static quill::Logger* logger_instance = nullptr;

void initialize(const std::string& log_level) {
    // Parse and validate log level (throws on invalid input)
    quill::LogLevel quill_log_level = parse_to_quill_level(log_level);

    // Store normalized lowercase version
    current_log_level = log_level;
    std::transform(current_log_level.begin(), current_log_level.end(), current_log_level.begin(),
                   ::tolower);

    // Start quill backend (safe to call multiple times)
    quill::Backend::start();

    // Always use ConsoleSink for text format with custom pattern (no logger name)
    auto console_sink = quill::Frontend::create_or_get_sink<quill::ConsoleSink>("tracker_console");

    // Create logger with custom pattern
    quill::PatternFormatterOptions pattern_options;
    pattern_options.format_pattern =
        "%(time) [%(thread_id)] %(file_name):%(line_number:<6) %(log_level:<13) %(message)";

    logger_instance =
        quill::Frontend::create_or_get_logger("tracker", std::move(console_sink), pattern_options);

    // Set log level filter on the logger itself (required in quill 10.x)
    logger_instance->set_log_level(quill_log_level);
}

quill::Logger* get_logger() {
    return logger_instance;
}

std::string get_level() {
    return current_log_level;
}

} // namespace logger