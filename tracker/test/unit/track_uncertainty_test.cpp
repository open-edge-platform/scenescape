// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "track_uncertainty.hpp"

#include <cmath>
#include <limits>

#include <gtest/gtest.h>
#include <rv/tracking/TrackedObject.hpp>

namespace tracker {
namespace {

using rv::tracking::StateIndex;
using rv::tracking::TrackedObject;

// A symmetric P whose every entry differs, so a wrong index shows up as a wrong value.
TrackedObject trackWithCovariance(bool z_measured) {
    TrackedObject track;
    track.z_measured = z_measured;
    for (int i = 0; i < TrackedObject::StateSize; ++i) {
        for (int j = i; j < TrackedObject::StateSize; ++j) {
            const double value = 0.001 * (1 + 13 * i + j) + (i == j ? 1.0 : 0.0);
            track.errorCovariance(i, j) = value;
            track.errorCovariance(j, i) = value;
        }
    }
    return track;
}

double p(const TrackedObject& track, int row, int col) {
    return track.errorCovariance(row, col);
}

TEST(TrackUncertaintyTest, VelocityAndSizeAreRowMajorBlocksOfP) {
    const auto track = trackWithCovariance(true);

    const auto uncertainty = buildTrackUncertainty(track);

    ASSERT_TRUE(uncertainty.has_value());
    ASSERT_TRUE(uncertainty->velocity.has_value());
    ASSERT_TRUE(uncertainty->size.has_value());
    const int velocity_index[3] = {StateIndex::VX, StateIndex::VY, StateIndex::VZ};
    const int size_index[3] = {StateIndex::LENGTH, StateIndex::WIDTH, StateIndex::HEIGHT};
    for (int row = 0; row < 3; ++row) {
        for (int col = 0; col < 3; ++col) {
            EXPECT_DOUBLE_EQ((*uncertainty->velocity)[3 * row + col],
                             p(track, velocity_index[row], velocity_index[col]));
            EXPECT_DOUBLE_EQ((*uncertainty->size)[3 * row + col],
                             p(track, size_index[row], size_index[col]));
        }
    }
}

TEST(TrackUncertaintyTest, TranslationDescribesThePublishedFootprintBase) {
    // The filter tracks the centre of mass; the published z is z - height / 2, so
    // Var(z_pub) = Pzz - Pzh + Phh / 4 and Cov(x, z_pub) = Pxz - Pxh / 2.
    const auto track = trackWithCovariance(true);
    constexpr int X = StateIndex::X, Y = StateIndex::Y, Z = StateIndex::Z, H = StateIndex::HEIGHT;

    const auto uncertainty = buildTrackUncertainty(track);

    ASSERT_TRUE(uncertainty.has_value());
    ASSERT_TRUE(uncertainty->translation.has_value());
    const auto& t = *uncertainty->translation;
    EXPECT_DOUBLE_EQ(t[0], p(track, X, X));
    EXPECT_DOUBLE_EQ(t[1], p(track, X, Y));
    EXPECT_DOUBLE_EQ(t[3], p(track, Y, X));
    EXPECT_DOUBLE_EQ(t[4], p(track, Y, Y));
    const double var_z = p(track, Z, Z) - p(track, Z, H) + 0.25 * p(track, H, H);
    const double cov_xz = p(track, X, Z) - 0.5 * p(track, X, H);
    const double cov_yz = p(track, Y, Z) - 0.5 * p(track, Y, H);
    EXPECT_NEAR(t[8], var_z, 1e-12);
    EXPECT_NEAR(t[2], cov_xz, 1e-12);
    EXPECT_NEAR(t[6], cov_xz, 1e-12);
    EXPECT_NEAR(t[5], cov_yz, 1e-12);
    EXPECT_NEAR(t[7], cov_yz, 1e-12);
}

TEST(TrackUncertaintyTest, ZRelatedValuesAreZeroWithoutMeasuredZ) {
    const auto track = trackWithCovariance(false);

    const auto uncertainty = buildTrackUncertainty(track);

    ASSERT_TRUE(uncertainty.has_value());
    ASSERT_TRUE(uncertainty->translation.has_value());
    ASSERT_TRUE(uncertainty->velocity.has_value());
    const auto& t = *uncertainty->translation;
    const auto& v = *uncertainty->velocity;
    for (const int i : {2, 5, 6, 7, 8}) {
        EXPECT_EQ(t[i], 0.0) << "translation entry " << i;
        EXPECT_EQ(v[i], 0.0) << "velocity entry " << i;
    }
    EXPECT_DOUBLE_EQ(t[0], p(track, StateIndex::X, StateIndex::X));
    EXPECT_DOUBLE_EQ(t[1], p(track, StateIndex::X, StateIndex::Y));
    EXPECT_DOUBLE_EQ(t[4], p(track, StateIndex::Y, StateIndex::Y));
    EXPECT_DOUBLE_EQ(v[0], p(track, StateIndex::VX, StateIndex::VX));
    EXPECT_DOUBLE_EQ(v[1], p(track, StateIndex::VX, StateIndex::VY));
    EXPECT_DOUBLE_EQ(v[4], p(track, StateIndex::VY, StateIndex::VY));
}

TEST(TrackUncertaintyTest, SizeBlockKeepsItsHeightEntriesWithoutMeasuredZ) {
    const auto track = trackWithCovariance(false);

    const auto uncertainty = buildTrackUncertainty(track);

    ASSERT_TRUE(uncertainty.has_value());
    ASSERT_TRUE(uncertainty->size.has_value());
    EXPECT_DOUBLE_EQ((*uncertainty->size)[8], p(track, StateIndex::HEIGHT, StateIndex::HEIGHT));
}

TEST(TrackUncertaintyTest, BlocksAreSymmetrized) {
    auto track = trackWithCovariance(true);
    track.errorCovariance(StateIndex::VX, StateIndex::VY) = 0.5;
    track.errorCovariance(StateIndex::VY, StateIndex::VX) = 0.1;

    const auto uncertainty = buildTrackUncertainty(track);

    ASSERT_TRUE(uncertainty.has_value());
    ASSERT_TRUE(uncertainty->velocity.has_value());
    EXPECT_DOUBLE_EQ((*uncertainty->velocity)[1], 0.3);
    EXPECT_DOUBLE_EQ((*uncertainty->velocity)[3], 0.3);
}

TEST(TrackUncertaintyTest, NonFiniteBlockIsOmittedAndTheOthersStay) {
    auto track = trackWithCovariance(true);
    track.errorCovariance(StateIndex::WIDTH, StateIndex::WIDTH) =
        std::numeric_limits<double>::quiet_NaN();

    const auto uncertainty = buildTrackUncertainty(track);

    ASSERT_TRUE(uncertainty.has_value());
    EXPECT_FALSE(uncertainty->size.has_value());
    EXPECT_TRUE(uncertainty->translation.has_value());
    EXPECT_TRUE(uncertainty->velocity.has_value());
}

TEST(TrackUncertaintyTest, PlanarTranslationIgnoresANonFiniteZOrHeightVariance) {
    for (const int unused_state :
         {static_cast<int>(StateIndex::Z), static_cast<int>(StateIndex::HEIGHT)}) {
        auto track = trackWithCovariance(false);
        for (int i = 0; i < 13; ++i) {
            track.errorCovariance(unused_state, i) = std::numeric_limits<double>::quiet_NaN();
            track.errorCovariance(i, unused_state) = std::numeric_limits<double>::quiet_NaN();
        }

        const auto uncertainty = buildTrackUncertainty(track);

        ASSERT_TRUE(uncertainty.has_value());
        ASSERT_TRUE(uncertainty->translation.has_value());
        const auto& translation = *uncertainty->translation;
        EXPECT_DOUBLE_EQ(translation[0], track.errorCovariance(StateIndex::X, StateIndex::X));
        EXPECT_DOUBLE_EQ(translation[1], track.errorCovariance(StateIndex::X, StateIndex::Y));
        EXPECT_DOUBLE_EQ(translation[4], track.errorCovariance(StateIndex::Y, StateIndex::Y));
        for (const int index : {2, 5, 6, 7, 8}) {
            EXPECT_EQ(translation[index], 0.0);
        }
    }
}

TEST(TrackUncertaintyTest, MeasuredTranslationIsOmittedForANonFiniteZVariance) {
    auto track = trackWithCovariance(true);
    track.errorCovariance(StateIndex::Z, StateIndex::Z) = std::numeric_limits<double>::quiet_NaN();

    const auto uncertainty = buildTrackUncertainty(track);

    ASSERT_TRUE(uncertainty.has_value());
    EXPECT_FALSE(uncertainty->translation.has_value());
    EXPECT_TRUE(uncertainty->velocity.has_value());
}

TEST(TrackUncertaintyTest, NothingFiniteGivesNoUncertainty) {
    TrackedObject track;
    track.errorCovariance =
        TrackedObject::StateMatrix::all(std::numeric_limits<double>::quiet_NaN());

    EXPECT_FALSE(buildTrackUncertainty(track).has_value());
}

} // namespace
} // namespace tracker
