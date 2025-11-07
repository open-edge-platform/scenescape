#pragma once

#include <quill/Logger.h>
#include <string>

namespace logger {

// Initialize the logger with the given log level string
// Valid levels (case-insensitive): trace, debug, info, warning, error
// Throws std::invalid_argument if level is invalid
void initialize(const std::string& log_level);

// Get the logger instance
quill::Logger* get_logger();

// Get current log level as string
std::string get_level();

} // namespace logger