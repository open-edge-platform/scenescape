// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "time_utils.hpp"

#include <chrono>
#include <cstdio>
#include <format>

namespace tracker {

std::optional<std::chrono::sys_time<std::chrono::milliseconds>>
parseTimestamp(const std::string& timestamp_iso) {
    using namespace std::chrono;

    int y, mo, d, h, mi, s, n = 0;
    if (std::sscanf(timestamp_iso.c_str(), "%d-%d-%dT%d:%d:%d%n", &y, &mo, &d, &h, &mi, &s, &n) !=
            6 ||
        n == 0) {
        return std::nullopt;
    }

    // Validate time ranges
    if (h < 0 || h > 23 || mi < 0 || mi > 59 || s < 0 || s > 59) {
        return std::nullopt;
    }

    // Parse optional fractional seconds, then require trailing 'Z'
    const char* rest = timestamp_iso.c_str() + n;
    int millis = 0;
    if (*rest == '.') {
        ++rest;
        int digits = 0;
        int frac = 0;
        while (*rest >= '0' && *rest <= '9') {
            if (digits < 3) {
                frac = frac * 10 + (*rest - '0');
            }
            ++digits;
            ++rest;
        }
        if (digits == 0)
            return std::nullopt;
        // Scale to milliseconds based on digits parsed (up to 3)
        for (int i = digits; i < 3; ++i)
            frac *= 10;
        millis = frac;
    }

    if (*rest != 'Z' || *(rest + 1) != '\0') {
        return std::nullopt;
    }

    // Validate date via C++20 calendar types
    auto ymd = year{y} / month{static_cast<unsigned>(mo)} / day{static_cast<unsigned>(d)};
    if (!ymd.ok()) {
        return std::nullopt;
    }

    return sys_days{ymd} + hours{h} + minutes{mi} + seconds{s} + milliseconds{millis};
}

std::string formatTimestamp(std::chrono::system_clock::time_point tp) {
    using namespace std::chrono;
    auto ms = floor<milliseconds>(tp);
    auto sec = floor<seconds>(ms);
    return std::format("{:%Y-%m-%dT%H:%M:%S}.{:03d}Z", sec, (ms - sec).count());
}

} // namespace tracker
