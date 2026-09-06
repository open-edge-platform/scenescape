// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "rv/Utils.hpp"
#include "rv/tracking/TrackedObject.hpp"

#include <cmath>
#include <string>
#include <unordered_map>

namespace rv {
namespace tracking {
namespace orientation {

constexpr const char *HAS_ORIENTATION = "has_orientation";
constexpr const char *ORIENTATION_OBSERVED = "orientation_observed";
constexpr const char *TRUE_VALUE = "true";

// Match Scene Controller publish hysteresis (moving_object.SPEED_THRESHOLD_ON).
constexpr double MIN_SPEED_FOR_YAW_GATE = 1.0;
// Reject detector yaw that remains this far from velocity heading after a
// front/back (π) disambiguation. Applies to any orienting modality.
constexpr double MAX_YAW_VELOCITY_RESIDUAL = 0.6;

inline bool attributeIsTrue(const std::unordered_map<std::string, std::string> &attributes,
                            const char *key)
{
  const auto it = attributes.find(key);
  return it != attributes.end() && it->second == TRUE_VALUE;
}

inline bool hasOrientation(const TrackedObject &object)
{
  return attributeIsTrue(object.attributes, HAS_ORIENTATION);
}

inline bool orientationObserved(const TrackedObject &object)
{
  return attributeIsTrue(object.attributes, ORIENTATION_OBSERVED)
    || hasOrientation(object);
}

inline void setHasOrientation(TrackedObject &object, bool value)
{
  if (value)
  {
    object.attributes[HAS_ORIENTATION] = TRUE_VALUE;
  }
  else
  {
    object.attributes.erase(HAS_ORIENTATION);
  }
}

inline void markOrientationObserved(TrackedObject &object)
{
  object.attributes[ORIENTATION_OBSERVED] = TRUE_VALUE;
}

/**
 * @brief After replacing track attributes with a measurement, preserve sticky
 * orientation_observed and mirror has_orientation from the measurement.
 */
inline void mergeOrientationAttributes(const TrackedObject &priorState,
                                       const TrackedObject &measurement,
                                       TrackedObject &outState)
{
  const bool observed = orientationObserved(priorState) || hasOrientation(measurement);
  if (hasOrientation(measurement))
  {
    outState.attributes[HAS_ORIENTATION] = TRUE_VALUE;
  }
  else
  {
    outState.attributes.erase(HAS_ORIENTATION);
  }
  if (observed)
  {
    outState.attributes[ORIENTATION_OBSERVED] = TRUE_VALUE;
  }
}

/**
 * @brief Pick ``yaw`` or ``yaw + π`` closest to ``reference`` (front/back box ambiguity).
 */
inline double chooseYawTowardReference(double yaw, double reference)
{
  const double flipped = yaw + M_PI;
  if (std::fabs(rv::angleDifference(flipped, reference))
      < std::fabs(rv::angleDifference(yaw, reference)))
  {
    return flipped;
  }
  return yaw;
}

/**
 * @brief Prepare measurement yaw for Kalman correct.
 *
 * Non-orienting sensors: zero yaw innovation (keep predicted yaw).
 * Orienting sensors while moving: π-disambiguate toward velocity heading;
 * if still inconsistent with motion, drop the yaw observation for this frame
 * (position/size still correct). While slow/stopped: unwrap vs previousYaw
 * with box-symmetric ``deltaTheta`` as before.
 */
inline void prepareYawMeasurement(const TrackedObject &state, TrackedObject &measurement)
{
  if (!hasOrientation(measurement))
  {
    measurement.yaw = state.yaw;
    return;
  }

  const double speed = std::hypot(state.vx, state.vy);
  if (speed >= MIN_SPEED_FOR_YAW_GATE)
  {
    const double velocityHeading = std::atan2(state.vy, state.vx);
    const double chosen = chooseYawTowardReference(measurement.yaw, velocityHeading);
    if (std::fabs(rv::angleDifference(chosen, velocityHeading)) > MAX_YAW_VELOCITY_RESIDUAL)
    {
      measurement.yaw = state.yaw;
      setHasOrientation(measurement, false);
      return;
    }
    // Continuous unwrap without re-applying box π-fold against a stale yaw.
    measurement.yaw = state.previousYaw - rv::angleDifference(chosen, state.previousYaw);
    return;
  }

  measurement.yaw = state.previousYaw - rv::deltaTheta(measurement.yaw, state.previousYaw);
}

} // namespace orientation
} // namespace tracking
} // namespace rv
