#include "time_chunk_scheduler.h"
#include "logger.h"
#include "time_chunk_processor.h"
#include <quill/LogMacros.h>
#include <algorithm>

TimeChunkScheduler& TimeChunkScheduler::getInstance() {
    static TimeChunkScheduler instance;
    return instance;
}

void TimeChunkScheduler::configure(std::chrono::milliseconds interval) {
    interval_ = interval;
}

void TimeChunkScheduler::start() {
    if (running_.exchange(true)) {
        return;
    }
    thread_ = std::thread(&TimeChunkScheduler::loop, this);
    LOG_INFO(logger::get_logger(), "Started TimeChunkScheduler with interval {}ms", interval_.count());
}

void TimeChunkScheduler::stop() {
    if (!running_.exchange(false)) {
        return;
    }
    if (thread_.joinable()) {
        thread_.join();
    }
    LOG_INFO(logger::get_logger(), "Stopped TimeChunkScheduler");
}

void TimeChunkScheduler::registerProcessor(TimeChunkProcessor* processor) {
    std::lock_guard<std::mutex> lk(mtx_);
    processors_.push_back(processor);
}

void TimeChunkScheduler::unregisterProcessor(TimeChunkProcessor* processor) {
    std::lock_guard<std::mutex> lk(mtx_);
    processors_.erase(std::remove(processors_.begin(), processors_.end(), processor), processors_.end());
}

void TimeChunkScheduler::loop() {
    using clock = std::chrono::steady_clock;
    while (running_.load(std::memory_order_acquire)) {
        auto start = clock::now();

        // Snapshot processors to minimize lock hold time
        std::vector<TimeChunkProcessor*> procs;
        {
            std::lock_guard<std::mutex> lk(mtx_);
            procs = processors_;
        }

        for (auto* p : procs) {
            if (p) {
                p->try_enqueue_tick();
            }
        }

        auto end = clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
        auto sleep_ms = interval_ - elapsed;
        if (sleep_ms.count() > 0) {
            std::this_thread::sleep_for(sleep_ms);
        } else {
            // Drift compensation: skip sleep to catch up
            continue;
        }
    }
}
