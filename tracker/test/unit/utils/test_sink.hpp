// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#ifndef TRACKER_TEST_UTILS_TEST_SINK_HPP
#define TRACKER_TEST_UTILS_TEST_SINK_HPP

#include <quill/sinks/Sink.h>

#include <mutex>
#include <string>
#include <string_view>
#include <vector>

namespace tracker {
namespace test {

/**
 * @brief Custom Quill sink that captures log statements for testing.
 *
 * This sink stores all log statements written to it, allowing tests to
 * validate the JSON structure of log output.
 */
class TestSink final : public quill::Sink {
public:
    TestSink() = default;

    void write_log(quill::MacroMetadata const* /* log_metadata */, uint64_t /* log_timestamp */,
                   std::string_view /* thread_id */, std::string_view /* thread_name */,
                   std::string const& /* process_id */, std::string_view /* logger_name */,
                   quill::LogLevel /* log_level */, std::string_view /* log_level_description */,
                   std::string_view /* log_level_short_code */,
                   std::vector<std::pair<std::string, std::string>> const* /* named_args */,
                   std::string_view /* log_message */, std::string_view log_statement) override {
        std::lock_guard<std::mutex> lock(mutex_);
        // Remove trailing newline if present
        if (!log_statement.empty() && log_statement.back() == '\n') {
            log_statements_.emplace_back(log_statement.data(), log_statement.size() - 1);
        } else {
            log_statements_.emplace_back(log_statement);
        }
    }

    void flush_sink() noexcept override {
        // Nothing to flush for in-memory storage
    }

    /**
     * @brief Get all captured log statements.
     */
    [[nodiscard]] std::vector<std::string> get_statements() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return log_statements_;
    }

    /**
     * @brief Clear all captured statements.
     */
    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        log_statements_.clear();
    }

private:
    mutable std::mutex mutex_;
    std::vector<std::string> log_statements_;
};

} // namespace test
} // namespace tracker

#endif // TRACKER_TEST_UTILS_TEST_SINK_HPP
