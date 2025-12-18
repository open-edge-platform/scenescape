#pragma once

#include <chrono>
#include <string>

// Parse strict RFC3339 with exactly milliseconds and trailing 'Z'.
// Example: 2025-12-18T13:13:24.835Z
std::chrono::system_clock::time_point parse_timestamp(const std::string& s);
