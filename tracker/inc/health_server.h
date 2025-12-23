#pragma once

#include <atomic>
#include <memory>
#include <thread>

namespace httplib { class Server; }

class HealthServer {
public:
    explicit HealthServer(int port = 8080);
    ~HealthServer();

    // Non-copyable
    HealthServer(const HealthServer&) = delete;
    HealthServer& operator=(const HealthServer&) = delete;

    // Start HTTP health server in background
    void start(std::atomic<bool>& liveFlag, std::atomic<bool>& readyFlag);

    // Stop server and join thread
    void stop();

private:
    int port_;
    std::unique_ptr<httplib::Server> server_;
    std::thread server_thread_;
    std::atomic<bool>* live_{};
    std::atomic<bool>* ready_{};
};
