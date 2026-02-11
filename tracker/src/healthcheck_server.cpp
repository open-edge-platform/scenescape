// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "healthcheck_server.hpp"

#include <chrono>
#include <ctime>
#include <httplib.h>
#include <iomanip>
#include <iostream>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <sstream>

namespace tracker {

namespace {

// Generate ISO8601/RFC3339 UTC timestamp for JSON logs
std::string get_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto time_t_now = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;

    std::tm tm_utc{};
    gmtime_r(&time_t_now, &tm_utc);

    std::ostringstream oss;
    oss << std::put_time(&tm_utc, "%Y-%m-%dT%H:%M:%S") << '.' << std::setfill('0') << std::setw(3)
        << ms.count() << 'Z';
    return oss.str();
}

} // namespace

std::pair<int, std::string> HealthcheckServer::handle_healthz(bool is_healthy) {
    rapidjson::StringBuffer json_buffer;
    rapidjson::Writer<rapidjson::StringBuffer> writer(json_buffer);
    writer.StartObject();
    writer.Key("status");
    writer.String(is_healthy ? "healthy" : "unhealthy");
    writer.EndObject();

    int status_code = is_healthy ? 200 : 503;
    return {status_code, json_buffer.GetString()};
}

std::pair<int, std::string> HealthcheckServer::handle_readyz(bool is_ready) {
    rapidjson::StringBuffer json_buffer;
    rapidjson::Writer<rapidjson::StringBuffer> writer(json_buffer);
    writer.StartObject();
    writer.Key("status");
    writer.String(is_ready ? "ready" : "notready");
    writer.EndObject();

    int status_code = is_ready ? 200 : 503;
    return {status_code, json_buffer.GetString()};
}

HealthcheckServer::HealthcheckServer(int port, std::atomic<bool>& liveness,
                                     std::atomic<bool>& readiness)
    : port_(port), liveness_(liveness), readiness_(readiness) {}

void HealthcheckServer::start() {
    if (thread_.joinable()) {
        std::cerr << "HealthcheckServer already running" << std::endl;
        return;
    }
    shutdown_requested_ = false;
    thread_ = std::thread(&HealthcheckServer::server_thread, this);
}

void HealthcheckServer::stop() {
    shutdown_requested_ = true;
    if (server_) {
        server_->stop();
    }
    if (thread_.joinable()) {
        thread_.join();
    }
}

HealthcheckServer::~HealthcheckServer() {
    stop();
}

void HealthcheckServer::server_thread() {
    httplib::Server server;

    // Store server pointer for stop() to access
    server_ = &server;

    // Handler for /healthz (liveness probe)
    server.Get("/healthz", [this](const httplib::Request&, httplib::Response& res) {
        auto [status_code, json_response] = handle_healthz(liveness_.load());
        res.set_content(json_response, "application/json");
        res.status = status_code;
    });

    // Handler for /readyz (readiness probe)
    server.Get("/readyz", [this](const httplib::Request&, httplib::Response& res) {
        auto [status_code, json_response] = handle_readyz(readiness_.load());
        res.set_content(json_response, "application/json");
        res.status = status_code;
    });

    std::cerr
        << R"({"timestamp":")" << get_timestamp()
        << R"(","level":"INFO","msg":"Healthcheck server listening","component":"healthcheck","port":)"
        << port_ << "}" << std::endl;

    // Start server and listen (blocks until stopped)
    if (!server.listen("0.0.0.0", port_)) {
        std::cerr
            << R"({"timestamp":")" << get_timestamp()
            << R"(","level":"ERROR","msg":"Failed to start healthcheck server","component":"healthcheck","port":)"
            << port_ << "}" << std::endl;
    }

    server_ = nullptr;
    std::cerr << R"({"timestamp":")" << get_timestamp()
              << R"(","level":"INFO","msg":"Healthcheck server stopped","component":"healthcheck"})"
              << std::endl;
}

} // namespace tracker
