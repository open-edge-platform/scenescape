// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "ptz_time.hpp"

#include <cmath>
#include <limits>

namespace tracker::ptz {

namespace {

constexpr int64_t kNsPerUs = 1000;
constexpr int kMicrosecondDigits = 6;

class Cursor {
public:
    explicit Cursor(std::string_view text) : text_(text) {}

    /// Read exactly @p count decimal digits.
    std::optional<int> digits(size_t count) {
        if (pos_ + count > text_.size()) {
            return std::nullopt;
        }
        int value = 0;
        for (size_t i = 0; i < count; ++i) {
            const char c = text_[pos_ + i];
            if (c < '0' || c > '9') {
                return std::nullopt;
            }
            value = value * 10 + (c - '0');
        }
        pos_ += count;
        return value;
    }

    bool accept(char expected) {
        if (pos_ < text_.size() && text_[pos_] == expected) {
            ++pos_;
            return true;
        }
        return false;
    }

    [[nodiscard]] bool done() const { return pos_ == text_.size(); }
    [[nodiscard]] char peek() const { return pos_ < text_.size() ? text_[pos_] : '\0'; }
    void advance() { ++pos_; }

private:
    std::string_view text_;
    size_t pos_ = 0;
};

/// Fraction after '.', truncated to microseconds; at least one digit is required.
std::optional<int64_t> parseFractionUs(Cursor& cursor) {
    int64_t micros = 0;
    int count = 0;
    while (cursor.peek() >= '0' && cursor.peek() <= '9') {
        if (count < kMicrosecondDigits) {
            micros = micros * 10 + (cursor.peek() - '0');
        }
        ++count;
        cursor.advance();
    }
    if (count == 0) {
        return std::nullopt;
    }
    for (int i = count; i < kMicrosecondDigits; ++i) {
        micros *= 10;
    }
    return micros;
}

/// Timezone suffix as an offset in seconds east of UTC.
std::optional<int64_t> parseOffsetS(Cursor& cursor) {
    if (cursor.accept('Z') || cursor.accept('z')) {
        return 0;
    }
    int sign = 0;
    if (cursor.accept('+')) {
        sign = 1;
    } else if (cursor.accept('-')) {
        sign = -1;
    } else {
        return std::nullopt;
    }
    auto hours = cursor.digits(2);
    if (!hours || !cursor.accept(':')) {
        return std::nullopt;
    }
    auto minutes = cursor.digits(2);
    if (!minutes || *hours > 23 || *minutes > 59) {
        return std::nullopt;
    }
    return sign * (*hours * 3600 + *minutes * 60);
}

} // namespace

std::optional<int64_t> parseIsoTimestampNs(std::string_view text) {
    Cursor cursor(text);
    auto year = cursor.digits(4);
    if (!year || !cursor.accept('-')) {
        return std::nullopt;
    }
    auto month = cursor.digits(2);
    if (!month || !cursor.accept('-')) {
        return std::nullopt;
    }
    auto day = cursor.digits(2);
    if (!day || !(cursor.accept('T') || cursor.accept(' '))) {
        return std::nullopt;
    }
    auto hour = cursor.digits(2);
    if (!hour || !cursor.accept(':')) {
        return std::nullopt;
    }
    auto minute = cursor.digits(2);
    if (!minute || !cursor.accept(':')) {
        return std::nullopt;
    }
    auto second = cursor.digits(2);
    if (!second || *hour > 23 || *minute > 59 || *second > 59) {
        return std::nullopt;
    }

    int64_t micros = 0;
    if (cursor.accept('.')) {
        auto fraction = parseFractionUs(cursor);
        if (!fraction) {
            return std::nullopt;
        }
        micros = *fraction;
    }
    auto offset_s = parseOffsetS(cursor);
    if (!offset_s || !cursor.done()) {
        return std::nullopt;
    }

    const std::chrono::year_month_day date{std::chrono::year{*year},
                                           std::chrono::month{static_cast<unsigned>(*month)},
                                           std::chrono::day{static_cast<unsigned>(*day)}};
    if (!date.ok()) {
        return std::nullopt;
    }
    const int64_t days = std::chrono::sys_days{date}.time_since_epoch().count();
    const int64_t seconds = days * 86400 + *hour * 3600 + *minute * 60 + *second - *offset_s;
    // Reject instants outside the int64 nanosecond range (about 1677..2262) instead of overflowing.
    // Widen first: seconds alone may sit just past the limit while the microseconds bring it back.
    const __int128 ns = static_cast<__int128>(seconds) * kNsPerS + micros * kNsPerUs;
    if (ns > std::numeric_limits<int64_t>::max() || ns < std::numeric_limits<int64_t>::min()) {
        return std::nullopt;
    }
    return static_cast<int64_t>(ns);
}

int64_t secondsToNs(double seconds) {
    // nearbyint honours the default FE_TONEAREST mode: round half to even, as Python round().
    return static_cast<int64_t>(std::nearbyint(seconds * static_cast<double>(kNsPerS)));
}

} // namespace tracker::ptz
