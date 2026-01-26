// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "healthcheck_server.hpp"

#include <httplib.h>
#include <iostream>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

namespace tracker {

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

    std::cerr << "Healthcheck server listening on port " << port_ << std::endl;

    // Start server and listen (blocks until stopped)
    if (!server.listen("0.0.0.0", port_)) {
        std::cerr << "Failed to start healthcheck server on port " << port_ << std::endl;
    }

    server_ = nullptr;
    std::cerr << "Healthcheck server stopped" << std::endl;
}

} // namespace tracker
