#include "health_server.h"
#include <httplib.h>

HealthServer::HealthServer(int port) : port_(port) {}

HealthServer::~HealthServer() { stop(); }

void HealthServer::start(std::atomic<bool>& liveFlag, std::atomic<bool>& readyFlag) {
    live_ = &liveFlag;
    ready_ = &readyFlag;
    server_ = std::make_unique<httplib::Server>();

    server_->Get("/healthz", [this](const httplib::Request&, httplib::Response& res) {
        if (live_ && live_->load()) {
            res.status = 200;
            res.set_content("ok", "text/plain");
        } else {
            res.status = 500;
            res.set_content("not live", "text/plain");
        }
    });

    server_->Get("/readyz", [this](const httplib::Request&, httplib::Response& res) {
        if (ready_ && ready_->load()) {
            res.status = 200;
            res.set_content("ready", "text/plain");
        } else {
            res.status = 503;
            res.set_content("not ready", "text/plain");
        }
    });

    server_thread_ = std::thread([this]() {
        server_->listen("0.0.0.0", port_);
    });
}

void HealthServer::stop() {
    if (server_) {
        server_->stop();
    }
    if (server_thread_.joinable()) {
        server_thread_.join();
    }
}
