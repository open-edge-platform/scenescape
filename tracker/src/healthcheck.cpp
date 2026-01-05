// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "healthcheck.hpp"

#include <httplib.h>
#include <iostream>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

namespace tracker {

HealthServer::HealthServer(int port, std::atomic<bool>& liveness, std::atomic<bool>& readiness)
    : port_(port), liveness_(liveness), readiness_(readiness) {}

void HealthServer::start() {
    if (thread_.joinable()) {
        std::cerr << "HealthServer already running" << std::endl;
        return;
    }
    shutdown_requested_ = false;
    thread_ = std::thread(&HealthServer::server_thread, this);
}

void HealthServer::stop() {
    shutdown_requested_ = true;
    if (server_) {
        server_->stop();
    }
    if (thread_.joinable()) {
        thread_.join();
    }
}

HealthServer::~HealthServer() {
    stop();
}

void HealthServer::server_thread() {
    httplib::Server server;

    // Store server pointer for stop() to access
    server_ = &server;

    // Handler for /healthz (liveness probe)
    server.Get("/healthz", [this](const httplib::Request&, httplib::Response& res) {
        bool is_healthy = liveness_.load();

        // Build JSON response
        rapidjson::StringBuffer json_buffer;
        rapidjson::Writer<rapidjson::StringBuffer> writer(json_buffer);
        writer.StartObject();
        writer.Key("status");
        writer.String(is_healthy ? "healthy" : "unhealthy");
        writer.EndObject();

        res.set_content(json_buffer.GetString(), "application/json");
        res.status = is_healthy ? 200 : 503;
    });

    // Handler for /readyz (readiness probe)
    server.Get("/readyz", [this](const httplib::Request&, httplib::Response& res) {
        bool is_ready = readiness_.load();

        // Build JSON response
        rapidjson::StringBuffer json_buffer;
        rapidjson::Writer<rapidjson::StringBuffer> writer(json_buffer);
        writer.StartObject();
        writer.Key("status");
        writer.String(is_ready ? "ready" : "notready");
        writer.EndObject();

        res.set_content(json_buffer.GetString(), "application/json");
        res.status = is_ready ? 200 : 503;
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
