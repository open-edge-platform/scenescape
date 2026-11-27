#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Numerical PTZ solver ported from the lab fit_ptz_curves.py; no runtime service."""

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

AXES = ("pan", "tilt")
# A stop that no rotation at all fits to within this many times the median stop
# (and at least MIN_REJECT_PX) has mis-matched tags, not a model error.
OUTLIER_ERROR_RATIO = 3.0
MIN_REJECT_PX = 15.0


def load_settings(data):
  entry = data.get("config")
  if entry is None:
    raise ValueError("No initial camera settings in the measurement")
  settings = {}
  for axis in AXES:
    curve = entry.get(f"{axis}_curve") or [0.0, entry.get(f"{axis}_scale") or 1.0]
    sign = -1.0 if entry.get(f"invert_{axis}") else 1.0
    settings[axis] = {
        # Fitted as the effective angle; invert is folded back in on output.
        "curve": [sign * c for c in curve],
        "sign": sign,
        "backlash": backlash_table(entry.get(f"{axis}_backlash_deg")),
    }
  axis = np.array(entry.get("pan_axis") or [0.0, 0.0, 1.0], dtype=float)
  settings["pan_axis"] = axis / np.linalg.norm(axis)
  return settings


def angle(curve, position):
  return sum(c * position ** i for i, c in enumerate(curve))


def slope(curve, position):
  return sum(i * c * position ** (i - 1) for i, c in enumerate(curve) if i)


def backlash_table(value):
  """Config ``*_backlash_deg`` (a number, or [[position, degrees], ...]) as a knot list."""
  if isinstance(value, list):
    return [(float(p), float(d)) for p, d in value]
  return [(0.0, float(value or 0.0))]


def backlash_at(table, position):
  """Backlash in degrees at a position; matches pose_math.backlash_degrees_at."""
  if len(table) == 1:
    return max(0.0, table[0][1])
  positions, values = zip(*table)
  return max(0.0, float(np.interp(position, positions, values)))


def backlash_config(table):
  if len(table) == 1:
    return float(table[0][1])
  return [[float(p), float(d)] for p, d in table]


def angle_deltas(curve, positions, start, backlash, start_fraction):
  """Track physical angle through the axis backlash deadband.

  ``backlash`` is a knot table (see ``backlash_table``), so the band can widen
  across the travel. ``start_fraction`` (-1..1) is where the physical angle sat
  in the band at the start, relative to the reported one.
  """
  start_angle = angle(curve, start) + start_fraction * backlash_at(backlash, start) / 2.0
  current, deltas = start_angle, []
  for position in positions:
    reported = angle(curve, position)
    half = backlash_at(backlash, position) / 2.0
    current = min(max(current, reported - half), reported + half)
    deltas.append(current - start_angle)
  return deltas


def project(rotation, stop):
  """Match pose_math.project_world_points_to_pixels, vectorised."""
  points = np.array(stop["points_3d"], dtype=float)
  cam = (points - np.array(stop["translation"])) @ rotation.as_matrix()
  xn, yn = cam[:, 0] / cam[:, 2], cam[:, 1] / cam[:, 2]
  d = stop.get("distortion") or {}
  k1, k2, k3 = d.get("k1") or 0.0, d.get("k2") or 0.0, d.get("k3") or 0.0
  p1, p2 = d.get("p1") or 0.0, d.get("p2") or 0.0
  r2 = xn * xn + yn * yn
  radial = 1 + k1 * r2 + k2 * r2 ** 2 + k3 * r2 ** 3
  xd = xn * radial + 2 * p1 * xn * yn + p2 * (r2 + 2 * xn * xn)
  yd = yn * radial + p1 * (r2 + 2 * yn * yn) + 2 * p2 * xn * yn
  k = stop["intrinsics"]
  return np.stack([k["fx"] * xd + k["cx"], k["fy"] * yd + k["cy"]], axis=1)


def stop_residuals(stop, start_pose, delta_pan, delta_tilt, pan_axis):
  rotation = (Rotation.from_rotvec(pan_axis * np.radians(delta_pan)) * start_pose
              * Rotation.from_euler("x", delta_tilt, degrees=True))
  return project(rotation, stop) - np.array(stop["points_2d"])


def stop_errors(stop, start_pose, delta_pan, delta_tilt, pan_axis):
  return np.linalg.norm(stop_residuals(stop, start_pose, delta_pan, delta_tilt, pan_axis), axis=1)


def axis_from_slopes(slopes):
  """Near-vertical unit axis from its x/z and y/z slopes (keeps it pointing up)."""
  axis = np.array([slopes[0], slopes[1], 1.0])
  return axis / np.linalg.norm(axis)


def lean_degrees(axis):
  return float(np.degrees(np.arccos(abs(axis[2]))))


def reject_bad_stops(stops, start_pose):
  """Stops whose detections no camera rotation explains, i.e. mis-matched tags.

  Checked with a free 3D rotation, so it doesn't depend on the model being
  fitted. One such stop can otherwise drag the whole fit.
  """
  errors = {}
  for i, stop in enumerate(stops):
    if not stop["points_2d"]:
      continue
    def residual(r, s=stop):
      return np.hypot(*(project(Rotation.from_rotvec(r) * start_pose, s)
                       - np.array(s["points_2d"])).T)
    errors[i] = float(np.mean(residual(least_squares(residual, np.zeros(3)).x)))
  if not errors:
    return set()
  threshold = max(OUTLIER_ERROR_RATIO * float(np.median(list(errors.values()))), MIN_REJECT_PX)
  rejected = {i for i, e in errors.items() if e > threshold}
  for i in sorted(rejected):
    stop = stops[i]
    print(f"Dropping stop {i + 1} ({stop['axis']} {stop[stop['axis']]:+.4f}): no rotation fits "
          f"its tags better than {errors[i]:.1f} px (limit {threshold:.1f}) - mis-matched tags")
  return rejected


class Fit:
  """Parameters: start-pose correction (3); per axis either the backlash and where
  in its band the axis started (if fitted) or just the start offset; pan axis
  slopes (2, if fitted); curves."""

  def __init__(self, data, settings, degrees, fit_pan_axis, fit_backlash=False, rejected=(),
               backlash_knots=(1, 1)):
    self.stops = data["stops"]
    self.start = {"pan": data["start_pan"], "tilt": data["start_tilt"]}
    self.stored_start = Rotation.from_euler("XYZ", self.stops[0]["rotation"], degrees=True)
    self.settings = settings
    self.degrees = degrees
    self.fit_pan_axis = fit_pan_axis
    self.fit_backlash = fit_backlash
    # Rejected stops still count for backlash tracking: the head did move there.
    self.measured = [i for i, s in enumerate(self.stops) if s["points_2d"] and i not in rejected]
    # Knots spread over the positions that have tag data; held constant beyond.
    self.knots = {}
    for axis, count in zip(AXES, backlash_knots):
      seen = [self.stops[i][axis] for i in self.measured if self.stops[i]["axis"] == axis]
      seen = seen or [self.start[axis]]
      self.knots[axis] = (list(np.linspace(min(seen), max(seen), count))
                          if count > 1 else [0.0])

  def _has_backlash(self, axis):
    return self.fit_backlash or any(d for _, d in self.settings[axis]["backlash"])

  def _fit_start_fraction(self, axis):
    return self._has_backlash(axis) and axis not in self.settings.get("home_approaches", {})

  def unpack(self, x):
    correction, x = Rotation.from_rotvec(x[:3]), x[3:]
    fractions, backlash, curves = {}, {}, {}
    for axis in AXES:
      if self.fit_backlash:
        n = len(self.knots[axis])
        backlash[axis], x = list(zip(self.knots[axis], x[:n])), x[n:]
      else:
        backlash[axis] = self.settings[axis]["backlash"]
      fractions[axis], x = (x[0], x[1:]) if self._fit_start_fraction(axis) else (0.0, x)
    pan_axis = self.settings["pan_axis"]
    if self.fit_pan_axis:
      pan_axis, x = axis_from_slopes(x[:2]), x[2:]
    for axis in AXES:
      n = self.degrees[axis]
      curves[axis], x = [0.0, *x[:n]], x[n:]
    # A controlled approach fixes the initial side of each backlash band.
    for axis, approach in self.settings.get("home_approaches", {}).items():
      sign = np.sign(slope(curves[axis], self.start[axis]))
      fractions[axis] = -sign * (1 if approach == "increasing" else -1)
    return correction * self.stored_start, fractions, backlash, pan_axis, curves

  def initial(self):
    x, lower, upper = [0.0] * 3, [-0.2] * 3, [0.2] * 3
    for axis in AXES:
      if self.fit_backlash:
        start_value = max(backlash_at(self.settings[axis]["backlash"], self.start[axis]), 0.5)
        n = len(self.knots[axis])
        x += [start_value] * n
        lower += [0.0] * n
        upper += [6.0] * n
      if self._fit_start_fraction(axis):
        x.append(0.0)
        lower.append(-1.0)
        upper.append(1.0)
    if self.fit_pan_axis:
      configured = self.settings["pan_axis"]
      x += [configured[0] / configured[2], configured[1] / configured[2]]
      # Up to ~30 deg of lean; beyond that it isn't a pan axis.
      lower += [-0.6, -0.6]
      upper += [0.6, 0.6]
    for axis in AXES:
      n = self.degrees[axis]
      x += (list(self.settings[axis]["curve"][1:]) + [0.0] * n)[:n]
      lower += [-np.inf] * n
      upper += [np.inf] * n
    return np.array(x), (lower, upper)

  def deltas(self, offsets, backlash, curves):
    return {axis: angle_deltas(curves[axis], [s[axis] for s in self.stops], self.start[axis],
                               backlash[axis], offsets[axis])
            for axis in AXES}

  def residuals(self, x):
    start_pose, offsets, backlash, pan_axis, curves = self.unpack(x)
    d = self.deltas(offsets, backlash, curves)
    return np.concatenate([stop_residuals(self.stops[i], start_pose, d["pan"][i], d["tilt"][i],
                                          pan_axis).ravel() for i in self.measured])

  def errors(self, x):
    return np.linalg.norm(self.residuals(x).reshape(-1, 2), axis=1)

  def solve(self):
    x0, (lower, upper) = self.initial()
    return least_squares(self.residuals, x0, bounds=(lower, upper)).x


def extrapolation_warning(curve, positions, travel):
  """Flag a curve that only fits because it bends outside the measured range."""
  reference = slope(curve, (min(positions) + max(positions)) / 2.0)
  for edge in travel:
    ratio = slope(curve, edge) / reference if reference else 0.0
    if not 0.5 <= ratio <= 2.0:
      return (f"slope at position {edge:+.2f} is {slope(curve, edge):+.1f} deg/unit vs "
              f"{reference:+.1f} mid-range, so it is only valid over the measured range. "
              "Widen the path in the measurement, or use a lower degree.")
  return None


def solve_best(data, settings, degrees, fit_pan_axis, fit_backlash, try_sign_flips, rejected,
               backlash_knots=(1, 1)):
  """Fit, optionally from each sign of the starting curves, keeping the lowest error."""
  signs = [(1, 1), (-1, 1), (1, -1), (-1, -1)] if try_sign_flips else [(1, 1)]
  best = None
  for pan_sign, tilt_sign in signs:
    variant = dict(settings)
    for axis, sign in (("pan", pan_sign), ("tilt", tilt_sign)):
      variant[axis] = dict(settings[axis], curve=[sign * c for c in settings[axis]["curve"]])
    fit = Fit(data, variant, degrees, fit_pan_axis, fit_backlash, rejected, backlash_knots)
    x = fit.solve()
    error = float(np.mean(fit.errors(x)))
    if best is None or error < best[2]:
      best = (fit, x, error)
  return best[0], best[1]
