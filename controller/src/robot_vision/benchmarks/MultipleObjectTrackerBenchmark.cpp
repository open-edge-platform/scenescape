//# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
//# SPDX-License-Identifier: Apache-2.0

#include <benchmark/benchmark.h>
#include <random>
#include <vector>
#include <chrono>
#include <memory>
#include <cmath>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "rv/tracking/MultipleObjectTracker.hpp"
#include "rv/tracking/TrackedObject.hpp"
#include "rv/tracking/ObjectMatching.hpp"

namespace rv {
namespace tracking {
namespace benchmark {

/**
 * @brief Simple test data generator for creating people tracking scenarios
 */
class PeopleTrackingBenchmarkFixture {
public:
    PeopleTrackingBenchmarkFixture() : gen(42), pos_dist(-25.0, 25.0), walking_speed_dist(0.5, 2.0) {
        baseTimestamp = std::chrono::system_clock::now();
    }
    
    /**
     * @brief Generate a realistic person TrackedObject with human-like properties
     */
    TrackedObject generateRandomPerson(Id personId = InvalidObjectId) {
        TrackedObject person;
        
        // Basic properties for a person
        person.id = personId;
        person.x = pos_dist(gen);  // Position in scene (-25m to +25m)
        person.y = pos_dist(gen);
        person.z = 0.0;  // Assume ground level
        
        // Human dimensions (realistic ranges)
        person.width = 0.4 + std::abs(pos_dist(gen)) / 150.0;   // 0.4-0.7 meters (shoulder width)
        person.height = 1.6 + std::abs(pos_dist(gen)) / 100.0;  // 1.6-1.9 meters (person height)
        person.length = 0.3 + std::abs(pos_dist(gen)) / 200.0;  // 0.3-0.5 meters (body depth)
        
        // Walking velocity (realistic human speeds: 0.5-2.0 m/s)
        double speed = walking_speed_dist(gen);
        double direction = std::uniform_real_distribution<double>(0, 2 * M_PI)(gen);
        person.vx = speed * std::cos(direction);
        person.vy = speed * std::sin(direction);
        
        // Person orientation (walking direction)
        person.yaw = direction;
        person.previousYaw = direction;
        
        // Classification biased toward "person" class
        person.classification = Eigen::VectorXd::Zero(5);
        person.classification[0] = 0.8 + 0.15 * std::uniform_real_distribution<double>(0, 1)(gen); // High confidence person
        person.classification[1] = 0.05 * std::uniform_real_distribution<double>(0, 1)(gen);      // Low confidence car
        person.classification[2] = 0.05 * std::uniform_real_distribution<double>(0, 1)(gen);      // Low confidence bike  
        person.classification[3] = 0.05 * std::uniform_real_distribution<double>(0, 1)(gen);      // Low confidence truck
        person.classification[4] = 0.05 * std::uniform_real_distribution<double>(0, 1)(gen);      // Low confidence unknown
        person.classification.normalize();
        
        // Kalman filter matrices for person tracking
        person.predictedMeasurementMean = cv::Mat::zeros(7, 1, CV_64F);
        person.predictedMeasurementMean.at<double>(0, 0) = person.x;
        person.predictedMeasurementMean.at<double>(1, 0) = person.y;
        person.predictedMeasurementMean.at<double>(2, 0) = person.width;
        person.predictedMeasurementMean.at<double>(3, 0) = person.height;
        person.predictedMeasurementMean.at<double>(4, 0) = person.vx;
        person.predictedMeasurementMean.at<double>(5, 0) = person.vy;
        person.predictedMeasurementMean.at<double>(6, 0) = person.yaw;
        
        // Higher uncertainty for people (more erratic movement than vehicles)
        person.predictedMeasurementCov = cv::Mat::eye(7, 7, CV_64F) * 0.2;
        cv::invert(person.predictedMeasurementCov, person.predictedMeasurementCovInv);
        person.errorCovariance = cv::Mat::eye(7, 7, CV_64F) * 0.1;
        
        return person;
    }
    
    /**
     * @brief Generate multiple people with realistic movement patterns
     */
    std::vector<TrackedObject> generateMovingPeopleScenario(size_t numPeople, double deltaTime = 0.0) {
        std::vector<TrackedObject> people;
        people.reserve(numPeople);
        
        for (size_t i = 0; i < numPeople; ++i) {
            auto person = generateRandomPerson(static_cast<Id>(i + 1));
            
            // Simulate movement over time
            if (deltaTime > 0.0) {
                person.x += person.vx * deltaTime;
                person.y += person.vy * deltaTime;
                
                // Add some randomness to walking pattern (people don't walk perfectly straight)
                double direction_change = std::normal_distribution<double>(0.0, 0.1)(gen);
                person.yaw += direction_change;
                person.vx = std::sqrt(person.vx * person.vx + person.vy * person.vy) * std::cos(person.yaw);
                person.vy = std::sqrt(person.vx * person.vx + person.vy * person.vy) * std::sin(person.yaw);
                
                // Update predicted measurement mean
                person.predictedMeasurementMean.at<double>(0, 0) = person.x;
                person.predictedMeasurementMean.at<double>(1, 0) = person.y;
                person.predictedMeasurementMean.at<double>(4, 0) = person.vx;
                person.predictedMeasurementMean.at<double>(5, 0) = person.vy;
                person.predictedMeasurementMean.at<double>(6, 0) = person.yaw;
            }
            
            people.push_back(std::move(person));
        }
        
        return people;
    }
    
    /**
     * @brief Create a tracker optimized for people tracking
     */
    std::unique_ptr<MultipleObjectTracker> createPeopleTracker() {
        return std::make_unique<MultipleObjectTracker>();
    }
    
    std::chrono::system_clock::time_point getTimestamp(int frameNumber = 0) {
        return baseTimestamp + std::chrono::milliseconds(frameNumber * 33); // ~30 FPS
    }

private:
    std::mt19937 gen;
    std::uniform_real_distribution<double> pos_dist;
    std::uniform_real_distribution<double> walking_speed_dist;
    std::chrono::system_clock::time_point baseTimestamp;
};

/**
 * @brief Benchmark for tracking 50 moving people in realistic scenarios
 */
static void BM_Tracking50MovingPeople(::benchmark::State& state) {
    PeopleTrackingBenchmarkFixture fixture;
    auto tracker = fixture.createPeopleTracker();
    
    // Pre-generate initial people positions
    const size_t numPeople = 50;
    auto initialPeople = fixture.generateMovingPeopleScenario(numPeople);
    auto timestamp = fixture.getTimestamp();
    
    // Track people movement over multiple frames
    const double frameTime = 0.033; // 33ms per frame (30 FPS)
    int frameCount = 0;
    
    for (auto _ : state) {
        // Generate people positions for current frame (simulating movement)
        auto currentPeople = fixture.generateMovingPeopleScenario(numPeople, frameCount * frameTime);
        
        // Track the moving people
        tracker->track(std::move(currentPeople), timestamp, 0.7); // Higher threshold for people
        
        // Advance to next frame
        frameCount++;
        timestamp = fixture.getTimestamp(frameCount);
        
        // Reset every 100 frames to avoid people walking too far away
        if (frameCount >= 100) {
            frameCount = 0;
            tracker = fixture.createPeopleTracker(); // Reset tracker state
        }
    }
    
    state.SetItemsProcessed(state.iterations() * numPeople);
    state.SetLabel("Moving people simulation with realistic walking patterns");
}
BENCHMARK(BM_Tracking50MovingPeople)->Unit(::benchmark::kMillisecond);

} // namespace benchmark
} // namespace tracking
} // namespace rv

// Benchmark main function
BENCHMARK_MAIN();
