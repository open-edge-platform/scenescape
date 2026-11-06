// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <rv/tracking/TrackedObject.hpp>

#include <span>
#include <vector>

namespace tracker {

/**
 * @brief Vertical reference of the z fed to RobotVision.
 *
 * FootprintBase (legacy): inputs and published tracks use z as projected.
 * CentreOfMass (with the remote projection service): inputs are converted to the object's centre of
 * mass and published tracks report the footprint base.
 */
enum class ZReference {
    FootprintBase,
    CentreOfMass
};

/// Raise z of every input without measured z (footprint base) by half its height.
inline void toCentreOfMass(std::span<std::vector<rv::tracking::TrackedObject>> objects_per_camera) {
    for (auto& objects : objects_per_camera) {
        for (auto& object : objects) {
            if (!object.zMeasured) {
                object.z += object.height / 2.0;
            }
        }
    }
}

/// Footprint-base z of a centre-of-mass track.
inline double footprintBaseZ(const rv::tracking::TrackedObject& track) {
    return track.z - track.height / 2.0;
}

} // namespace tracker
