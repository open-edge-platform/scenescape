// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "association_window.hpp"

#include <cmath>
#include <numbers>

#include <gtest/gtest.h>
#include <rv/Utils.hpp>

namespace tracker {
namespace {

rv::tracking::TrackedObject trackWithPositionCovariance(double s00, double s01, double s11,
                                                        bool z_measured = false) {
    rv::tracking::TrackedObject track;
    track.z_measured = z_measured;
    track.predictedMeasurementCov = rv::tracking::TrackedObject::MeasurementMatrix::eye();
    track.predictedMeasurementCov(0, 0) = s00;
    track.predictedMeasurementCov(0, 1) = s01;
    track.predictedMeasurementCov(1, 0) = s01;
    track.predictedMeasurementCov(1, 1) = s11;
    return track;
}

AssociationConfig mahalanobisConfig(double gate_probability) {
    AssociationConfig config;
    config.method = AssociationMethod::PositionMahalanobis;
    config.gate_probability = gate_probability;
    return config;
}

// An ellipse is symmetric under a half turn, so its angle is defined modulo pi.
double angleDifferenceModuloPi(double a, double b) {
    return std::remainder(a - b, std::numbers::pi);
}

TEST(AssociationWindowTest, EuclideanIsCircleOfMaxRadius) {
    AssociationConfig config;
    config.method = AssociationMethod::Euclidean;
    config.max_radius_m = 2.5;

    const auto window = buildAssociationWindow(config, trackWithPositionCovariance(4.0, 0.0, 1.0));

    EXPECT_EQ(window.method, "euclidean");
    EXPECT_EQ(window.shape, "circle");
    EXPECT_DOUBLE_EQ(window.radius_m.value(), 2.5);
    EXPECT_FALSE(window.semi_major_m.has_value());
}

TEST(AssociationWindowTest, MahalanobisEllipseFollowsRotatedCovariance) {
    // S_xy = R(angle) diag(4, 1) R(angle)^T: semi-axes sqrt(chi2(p, 2) * 4) and sqrt(chi2(p, 2) *
    // 1), major axis at angle.
    const double chi2 = rv::chi2Threshold(0.95, 2);
    for (const double degrees : {0.0, 30.0, 90.0, -60.0, 135.0}) {
        SCOPED_TRACE(degrees);
        const double angle = degrees * std::numbers::pi / 180.0;
        const double c = std::cos(angle);
        const double s = std::sin(angle);
        const auto track =
            trackWithPositionCovariance(4.0 * c * c + s * s, 3.0 * c * s, 4.0 * s * s + c * c);

        const auto window = buildAssociationWindow(mahalanobisConfig(0.95), track);

        EXPECT_EQ(window.method, "position_mahalanobis");
        EXPECT_EQ(window.shape, "ellipse");
        EXPECT_NEAR(window.semi_major_m.value(), std::sqrt(chi2 * 4.0), 1e-9);
        EXPECT_NEAR(window.semi_minor_m.value(), std::sqrt(chi2 * 1.0), 1e-9);
        EXPECT_NEAR(angleDifferenceModuloPi(window.angle_rad.value(), angle), 0.0, 1e-9);
    }
}

TEST(AssociationWindowTest, MahalanobisMajorAxisFollowsLargerVariance) {
    // The larger variance is on y: the major axis points along y whatever the matrix order.
    const auto window =
        buildAssociationWindow(mahalanobisConfig(0.99), trackWithPositionCovariance(1.0, 0.0, 9.0));

    const double chi2 = rv::chi2Threshold(0.99, 2);
    EXPECT_NEAR(window.semi_major_m.value(), std::sqrt(chi2 * 9.0), 1e-9);
    EXPECT_NEAR(window.semi_minor_m.value(), std::sqrt(chi2 * 1.0), 1e-9);
    EXPECT_NEAR(angleDifferenceModuloPi(window.angle_rad.value(), std::numbers::pi / 2.0), 0.0,
                1e-9);
}

TEST(AssociationWindowTest, MahalanobisClampsNegativeEigenvaluesToZero) {
    // Eigenvalues 3 and -1, major axis at 45 degrees: the minor semi-axis is 0, not NaN.
    const auto window =
        buildAssociationWindow(mahalanobisConfig(0.99), trackWithPositionCovariance(1.0, 2.0, 1.0));

    EXPECT_NEAR(window.semi_major_m.value(), std::sqrt(rv::chi2Threshold(0.99, 2) * 3.0), 1e-9);
    EXPECT_DOUBLE_EQ(window.semi_minor_m.value(), 0.0);
    EXPECT_NEAR(angleDifferenceModuloPi(window.angle_rad.value(), std::numbers::pi / 4.0), 0.0,
                1e-9);
}

TEST(AssociationWindowTest, MahalanobisWindowUsesTheTrackDegreesOfFreedom) {
    // The XY shadow of the gate: chi2(p, 2) for a track without measured z, whose pairs are gated
    // on x and y only; chi2(p, 3) once the track has measured z (pairs with a measured-z detection
    // gate x, y and z).
    const auto planar = buildAssociationWindow(mahalanobisConfig(0.99),
                                               trackWithPositionCovariance(1.0, 0.0, 0.25));
    EXPECT_NEAR(planar.semi_major_m.value(), std::sqrt(rv::chi2Threshold(0.99, 2) * 1.0), 1e-9);
    EXPECT_NEAR(planar.semi_minor_m.value(), std::sqrt(rv::chi2Threshold(0.99, 2) * 0.25), 1e-9);

    const auto measured = buildAssociationWindow(mahalanobisConfig(0.99),
                                                 trackWithPositionCovariance(1.0, 0.0, 0.25, true));
    EXPECT_NEAR(measured.semi_major_m.value(), std::sqrt(rv::chi2Threshold(0.99, 3) * 1.0), 1e-9);
    EXPECT_NEAR(measured.semi_minor_m.value(), std::sqrt(rv::chi2Threshold(0.99, 3) * 0.25), 1e-9);
}

TEST(AssociationWindowTest, MahalanobisClipsSemiAxesToMaxRadius) {
    // Unclipped χ²(0.99) radius for S=100·I is ~30 m; the hard gate is 10 m.
    AssociationConfig config = mahalanobisConfig(0.99);
    config.max_radius_m = 10.0;

    const auto window =
        buildAssociationWindow(config, trackWithPositionCovariance(100.0, 0.0, 100.0));

    EXPECT_EQ(window.shape, "ellipse");
    EXPECT_DOUBLE_EQ(window.semi_major_m.value(), 10.0);
    EXPECT_DOUBLE_EQ(window.semi_minor_m.value(), 10.0);
}

} // namespace
} // namespace tracker
