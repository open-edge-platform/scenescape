#pragma once

#include <atomic>
#include <chrono>
#include <mutex>
#include <thread>
#include <vector>

class TimeChunkProcessor;

class TimeChunkScheduler {
public:
    static TimeChunkScheduler& getInstance();

    void configure(std::chrono::milliseconds interval);
    void start();
    void stop();

    void registerProcessor(TimeChunkProcessor* processor);
    void unregisterProcessor(TimeChunkProcessor* processor);

private:
    TimeChunkScheduler() = default;
    ~TimeChunkScheduler() = default;
    TimeChunkScheduler(const TimeChunkScheduler&) = delete;
    TimeChunkScheduler& operator=(const TimeChunkScheduler&) = delete;

    void loop();

    std::thread thread_;
    std::atomic<bool> running_{false};
    std::mutex mtx_;
    std::vector<TimeChunkProcessor*> processors_;
    std::chrono::milliseconds interval_{66};
};
