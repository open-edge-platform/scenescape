// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
#include <cmath>
#include <optional>
#include <utility>

#include <rv/tracking/TrackedObject.hpp>

namespace tracker {

/// Row-major 3×3 covariance block.
using Covariance3 = std::array<double, 9>;

/**
 * @brief Covariance of the published track state (MQTT uncertainty), from the filter's P.
 *
 * Each block is taken from the posterior covariance P (IMM-combined); cross-block terms are not
 * published. A block with a non-finite value is absent.
 *
 *  - translation [m²]: x, y and the published z. The filter tracks the centre of mass and the
 *    published z is the footprint base z − height / 2, so the z entries come from J P Jᵀ with
 *    J(z_pub) = [1 on z, −1/2 on height]. For a track without measured z the z row and column are
 * 0.
 *  - velocity [m²/s²]: vx, vy, vz. For a track without measured z the vz row and column are 0.
 *  - size [m²]: length, width, height.
 *  - yaw [rad²]: only when the published rotation is the filter yaw.
 */
struct TrackUncertainty {
    std::optional<Covariance3> translation;
    std::optional<Covariance3> velocity;
    std::optional<Covariance3> size;
    std::optional<double> yaw;
};

namespace detail {

/// One published quantity as a linear combination of at most two state elements.
struct StateCombination {
    int first;
    double first_weight;
    int second;
    double second_weight;
};

/// Covariance block of three published quantities, each a combination of state elements of P.
inline std::optional<Covariance3> covarianceBlock(const rv::tracking::TrackedObject& track,
                                                  const std::array<StateCombination, 3>& rows,
                                                  bool zero_z_related) {
    Covariance3 block{};
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            if (zero_z_related && (i == 2 || j == 2)) {
                continue;
            }
            const auto& a = rows[i];
            const auto& b = rows[j];
            double sum = 0.0;
            for (const auto& [ia, wa] :
                 {std::pair{a.first, a.first_weight}, std::pair{a.second, a.second_weight}}) {
                for (const auto& [ib, wb] :
                     {std::pair{b.first, b.first_weight}, std::pair{b.second, b.second_weight}}) {
                    // Symmetrized: the filter's P is symmetric only up to rounding.
                    sum += wa * wb * 0.5 *
                           (track.errorCovariance(ia, ib) + track.errorCovariance(ib, ia));
                }
            }
            if (!std::isfinite(sum)) {
                return std::nullopt;
            }
            block[3 * i + j] = sum;
        }
    }
    return block;
}

} // namespace detail

/**
 * @brief Build the uncertainty of a centre-of-mass track's published state.
 *
 * @param track Track of the filter, with the centre-of-mass z.
 * @param filter_yaw_published True when the published rotation is the filter yaw.
 * @return The uncertainty, or no value when every block is absent.
 */
inline std::optional<TrackUncertainty>
buildTrackUncertainty(const rv::tracking::TrackedObject& track, bool filter_yaw_published) {
    using detail::StateCombination;
    using rv::tracking::StateIndex;
    const bool zero_z = !track.z_measured;

    TrackUncertainty uncertainty;
    uncertainty.translation =
        detail::covarianceBlock(track,
                                {StateCombination{StateIndex::X, 1.0, StateIndex::X, 0.0},
                                 StateCombination{StateIndex::Y, 1.0, StateIndex::Y, 0.0},
                                 StateCombination{StateIndex::Z, 1.0, StateIndex::HEIGHT, -0.5}},
                                zero_z);
    uncertainty.velocity =
        detail::covarianceBlock(track,
                                {StateCombination{StateIndex::VX, 1.0, StateIndex::VX, 0.0},
                                 StateCombination{StateIndex::VY, 1.0, StateIndex::VY, 0.0},
                                 StateCombination{StateIndex::VZ, 1.0, StateIndex::VZ, 0.0}},
                                zero_z);
    uncertainty.size = detail::covarianceBlock(
        track,
        {StateCombination{StateIndex::LENGTH, 1.0, StateIndex::LENGTH, 0.0},
         StateCombination{StateIndex::WIDTH, 1.0, StateIndex::WIDTH, 0.0},
         StateCombination{StateIndex::HEIGHT, 1.0, StateIndex::HEIGHT, 0.0}},
        false);
    if (filter_yaw_published) {
        const double yaw_variance = track.errorCovariance(StateIndex::YAW, StateIndex::YAW);
        if (std::isfinite(yaw_variance)) {
            uncertainty.yaw = yaw_variance;
        }
    }

    if (!uncertainty.translation && !uncertainty.velocity && !uncertainty.size &&
        !uncertainty.yaw) {
        return std::nullopt;
    }
    return uncertainty;
}

} // namespace tracker
