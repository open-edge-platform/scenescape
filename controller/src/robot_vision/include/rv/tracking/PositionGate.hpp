// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "rv/Utils.hpp"
#include "rv/tracking/TrackedObject.hpp"

#include <algorithm>
#include <vector>

namespace rv {
namespace tracking {
namespace position_gate {

/// Association and birth gate Z only when both sides measured it (ground point vs box centre otherwise).
inline bool gatesZ(bool trackMeasured, bool detectionMeasured)
{
  return trackMeasured && detectionMeasured;
}

inline bool gatesZ(const TrackedObject &track, const TrackedObject &detection)
{
  return gatesZ(track.zMeasured, detection.zMeasured);
}

/// A track with sticky measured z draws / pairs at df=3 when the other side also measured z.
inline bool trackCanGateZ(const TrackedObject &track)
{
  return track.zMeasured;
}

inline int positionDof(bool includeZ)
{
  return includeZ ? 3 : 2;
}

inline double positionChi2(double gateProbability, bool includeZ)
{
  return rv::chi2Threshold(gateProbability, positionDof(includeZ));
}

/// match() uses one cost threshold chi2(p, 3); scale a df=2 d² so it passes at the same p.
inline double xyCostScaleForChi2Threshold3(double chi2Threshold3)
{
  const double gateProbability = std::clamp(rv::chi2Cdf3(chi2Threshold3), 1e-9, 1.0 - 1e-9);
  return chi2Threshold3 / rv::chi2Threshold(gateProbability, 2);
}

inline void appendPositionMeasurementRows(std::vector<int> &rows, bool includeZ)
{
  rows.push_back(MeasurementIndex::X);
  rows.push_back(MeasurementIndex::Y);
  if (includeZ)
  {
    rows.push_back(MeasurementIndex::Z);
  }
}

} // namespace position_gate
} // namespace tracking
} // namespace rv
