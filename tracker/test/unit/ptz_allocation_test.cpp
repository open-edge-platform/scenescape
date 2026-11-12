// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Verifies that the per-detection PTZ hot path (isPtzCamera + admit) does not allocate.
// Replaces the global operator new/delete for this test binary with counting wrappers
// around malloc/free; counting is enabled only inside the measured region.

#include "ptz_registry.hpp"
#include "ptz_test_utils.hpp"

#include <gtest/gtest.h>

#include <cstdlib>
#include <new>

namespace {
thread_local bool g_counting = false;
thread_local size_t g_allocations = 0;

void* countedAlloc(std::size_t size) {
    if (g_counting) {
        ++g_allocations;
    }
    if (void* p = std::malloc(size == 0 ? 1 : size)) {
        return p;
    }
    throw std::bad_alloc();
}
} // namespace

void* operator new(std::size_t size) {
    return countedAlloc(size);
}
void* operator new[](std::size_t size) {
    return countedAlloc(size);
}
void operator delete(void* p) noexcept {
    std::free(p);
}
void operator delete[](void* p) noexcept {
    std::free(p);
}
void operator delete(void* p, std::size_t) noexcept {
    std::free(p);
}
void operator delete[](void* p, std::size_t) noexcept {
    std::free(p);
}

namespace tracker::ptz {
namespace {

using test::kBaseNs;
using test::ms;

TEST(PtzHotPathTest, AllocationCounterDetectsAllocations) {
    g_allocations = 0;
    g_counting = true;
    auto* probe = new std::string(64, 'x');
    g_counting = false;
    delete probe;
    EXPECT_GE(g_allocations, 1u);
}

TEST(PtzHotPathTest, AdmissionDoesNotAllocate) {
    const std::vector<Scene> scenes = {
        test::scene({test::camera(test::kSourceId, true), test::camera("static", false)})};
    PtzPoseRegistry registry(scenes, {{test::kSourceId, test::kResolverId}}, test::dwellConfig(),
                             PtzMessageParser(TRACKER_SCHEMA_DIR),
                             [] { return PtzClockReading{0, true}; });
    for (int i = 0; i < 4; ++i) {
        test::PoseJson json;
        json.sequence = i + 1;
        json.timestamp_ns = kBaseNs + ms(100 * i);
        ASSERT_EQ(registry.onPoseMessage(test::poseTopic(), json.json()), std::nullopt);
    }
    const std::string ptz_camera = test::kSourceId;
    const std::string static_camera = "static";
    const PtzClockReading clock{kBaseNs + ms(310), true};

    g_allocations = 0;
    g_counting = true;
    bool admitted = false;
    bool static_is_ptz = true;
    for (int i = 0; i < 1000; ++i) {
        static_is_ptz = registry.isPtzCamera(static_camera);
        if (registry.isPtzCamera(ptz_camera)) {
            admitted = registry.admitAt(ptz_camera, kBaseNs + ms(250), clock).admitted;
        }
        (void)registry.admitAt(ptz_camera, kBaseNs + ms(301), clock); // rejected path
    }
    g_counting = false;

    EXPECT_TRUE(admitted);
    EXPECT_FALSE(static_is_ptz);
    EXPECT_EQ(g_allocations, 0u);
}

} // namespace
} // namespace tracker::ptz
