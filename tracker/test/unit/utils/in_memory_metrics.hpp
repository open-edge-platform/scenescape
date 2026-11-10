// SPDX-FileCopyrightText: 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <utility>

#include <opentelemetry/exporters/memory/in_memory_metric_data.h>
#include <opentelemetry/exporters/memory/in_memory_metric_exporter_factory.h>
#include <opentelemetry/sdk/metrics/export/metric_producer.h>
#include <opentelemetry/sdk/metrics/instruments.h>
#include <opentelemetry/sdk/metrics/push_metric_exporter.h>

namespace tracker::test {

/**
 * @brief In-memory metric store that answers from the latest export.
 *
 * The SDK's SimpleAggregateInMemoryMetricData keeps the first exported point per series, so an
 * export before the one a test waits for (the periodic reader exports as soon as its thread starts,
 * at a scheduling-dependent moment, and then every interval) freezes a partial value. Together with
 * cumulative temporality, the latest export holds every recording, whatever the number and timing
 * of the exports before it.
 */
class LatestInMemoryMetricData final : public opentelemetry::exporter::memory::InMemoryMetricData {
public:
    using AttributeToPoint =
        opentelemetry::exporter::memory::SimpleAggregateInMemoryMetricData::AttributeToPoint;

    void
    Add(std::unique_ptr<opentelemetry::sdk::metrics::ResourceMetrics> resource_metrics) override {
        auto export_data =
            std::make_unique<opentelemetry::exporter::memory::SimpleAggregateInMemoryMetricData>();
        export_data->Add(std::move(resource_metrics));
        std::lock_guard<std::mutex> lock(mutex_);
        exports_.push_back(std::move(export_data));
    }

    /// Time series of a metric in the latest export; empty before the first export. The reference
    /// stays valid for the lifetime of this object.
    const AttributeToPoint& Get(const std::string& scope, const std::string& metric) {
        std::lock_guard<std::mutex> lock(mutex_);
        return exports_.empty() ? empty_ : exports_.back()->Get(scope, metric);
    }

private:
    std::mutex mutex_;
    // Kept, not replaced, so references returned by Get() outlive later exports.
    std::deque<std::unique_ptr<opentelemetry::exporter::memory::SimpleAggregateInMemoryMetricData>>
        exports_;
    const AttributeToPoint empty_;
};

/**
 * @brief Create an in-memory metric exporter with cumulative temporality and its backing store.
 */
inline std::pair<std::unique_ptr<opentelemetry::sdk::metrics::PushMetricExporter>,
                 std::shared_ptr<LatestInMemoryMetricData>>
make_in_memory_exporter() {
    auto data = std::make_shared<LatestInMemoryMetricData>();
    auto exporter = opentelemetry::exporter::memory::InMemoryMetricExporterFactory::Create(
        data, [](opentelemetry::sdk::metrics::InstrumentType) {
            return opentelemetry::sdk::metrics::AggregationTemporality::kCumulative;
        });
    return {std::move(exporter), data};
}

} // namespace tracker::test
