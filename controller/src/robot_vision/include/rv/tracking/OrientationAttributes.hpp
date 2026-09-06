// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "rv/tracking/TrackedObject.hpp"

#include <string>
#include <unordered_map>

namespace rv {
namespace tracking {
namespace orientation {

constexpr const char *HAS_ORIENTATION = "has_orientation";
constexpr const char *ORIENTATION_OBSERVED = "orientation_observed";
constexpr const char *TRUE_VALUE = "true";

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

} // namespace orientation
} // namespace tracking
} // namespace rv
