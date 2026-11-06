// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "rv/Utils.hpp"
#include "rv/tracking/TrackedObject.hpp"

#include <cmath>
#include <optional>
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

// Portable π — avoid M_PI (non-standard; may be undefined without platform macros).
constexpr double kPi = 3.14159265358979323846;

/**
 * @brief Pick ``yaw`` or ``yaw + π`` closest to ``reference`` (front/back box ambiguity).
 */
inline double chooseYawTowardReference(double yaw, double reference)
{
  const double flipped = yaw + kPi;
  if (std::fabs(rv::angleDifference(flipped, reference))
      < std::fabs(rv::angleDifference(yaw, reference)))
  {
    return flipped;
  }
  return yaw;
}

/**
 * @brief Whether a state is fast enough for the yaw speed gate (MIN_SPEED_FOR_YAW_GATE or faster).
 */
inline bool movingForYawGate(const TrackedObject &state)
{
  return std::hypot(state.vx, state.vy) >= MIN_SPEED_FOR_YAW_GATE;
}

/**
 * @brief Detection ``yaw`` or ``yaw + π``, whichever is closer to the direction of travel of a moving ``state``, or
 * nullopt when it stays more than MAX_YAW_VELOCITY_RESIDUAL off it.
 */
inline std::optional<double> yawAlongTravel(const TrackedObject &state, double yaw)
{
  const double velocityHeading = std::atan2(state.vy, state.vx);
  const double chosen = chooseYawTowardReference(yaw, velocityHeading);
  if (std::fabs(rv::angleDifference(chosen, velocityHeading)) > MAX_YAW_VELOCITY_RESIDUAL)
  {
    return std::nullopt;
  }
  return chosen;
}

/**
 * @brief Whether prepareYawMeasurement keeps the yaw of an orienting detection: always while ``state`` is slower than
 * MIN_SPEED_FOR_YAW_GATE, otherwise when it is consistent with the direction of travel.
 */
inline bool yawPassesSpeedGate(const TrackedObject &state, double yaw)
{
  return !movingForYawGate(state) || yawAlongTravel(state, yaw).has_value();
}

/**
 * @brief Prepare measurement yaw for Kalman correct.
 *
 * Non-orienting sensors: yaw is not observed; the estimator leaves it out of the
 * update, so yaw only predicts. Orienting sensors while moving: π-disambiguate
 * toward velocity heading; if still inconsistent with motion, drop the yaw
 * observation for this frame (position/size still correct). While slow/stopped:
 * unwrap vs previousYaw with box-symmetric ``deltaTheta`` as before. A dropped
 * yaw clears ``has_orientation`` on the measurement and keeps the predicted yaw.
 */
inline void prepareYawMeasurement(const TrackedObject &state, TrackedObject &measurement)
{
  if (!hasOrientation(measurement))
  {
    measurement.yaw = state.yaw;
    return;
  }

  if (movingForYawGate(state))
  {
    const auto chosen = yawAlongTravel(state, measurement.yaw);
    if (!chosen)
    {
      measurement.yaw = state.yaw;
      setHasOrientation(measurement, false);
      return;
    }
    // Continuous unwrap without re-applying box π-fold against a stale yaw.
    measurement.yaw = state.previousYaw - rv::angleDifference(*chosen, state.previousYaw);
    return;
  }

  measurement.yaw = state.previousYaw - rv::deltaTheta(measurement.yaw, state.previousYaw);
}

} // namespace orientation
} // namespace tracking
} // namespace rv
