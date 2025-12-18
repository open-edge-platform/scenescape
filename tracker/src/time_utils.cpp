#include "time_utils.h"

#include <absl/time/time.h>
#include <stdexcept>

std::chrono::system_clock::time_point parse_timestamp(const std::string& s) {
    absl::Time t;
    // Accept ISO-8601 with fractional seconds and Z/offset during parsing
    if (!absl::ParseTime("%Y-%m-%dT%H:%M:%E*S%Ez", s, &t, nullptr)) {
        throw std::runtime_error("failed to parse RFC3339 timestamp");
    }
    // Enforce strict form: exactly 3 fractional digits and trailing 'Z'
    const std::string strict = absl::FormatTime("%Y-%m-%dT%H:%M:%E3SZ", t, absl::UTCTimeZone());
    if (strict != s) {
        throw std::runtime_error("timestamp not in exact RFC3339 millisecond format");
    }
    return absl::ToChronoTime(t);
}
