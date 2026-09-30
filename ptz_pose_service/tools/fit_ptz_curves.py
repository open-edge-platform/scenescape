#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fit ``pan_curve``, ``tilt_curve`` and ``pan_axis`` from a reprojection-accuracy measurement.

Refines both axes against what the service is judged on - detected AprilTags -
using the service's own model

    R = R_axis(pan_angle - start_pan_angle) * R_start * Rx(tilt_angle - start_tilt_angle)

with each angle tracked through its ``*_backlash_deg`` deadband along the
measured path, exactly as the service does. ``R_axis`` turns about the pan axis
in world coordinates, which is world vertical unless the mount leans. Backlash
is taken from the configuration that was measured (saved by
``measure_reprojection_accuracy.py``).

Fitted jointly with the curves, so the measurement doesn't have to start from a
freshly calibrated, known state:

- a small correction to the start pose ``R_start`` (the pose the service had
  stored there, which carries whatever tracking error it had), and
- where in the backlash band each axis started (it depends on how the camera
  last arrived, which the tool can't see).

Run inside the autocalibration container (it has numpy/scipy):

    docker cp scenescape-ptz-pose-1:/tmp/reprojection_accuracy.json /tmp/
    docker cp /tmp/reprojection_accuracy.json scenescape-autocalibration-1:/tmp/
    docker compose exec autocalibration python3 /tmp/tools/fit_ptz_curves.py

A curve is only trustworthy over the range it was fitted on; widen
``--pan-path``/``--tilt-path`` in the measurement to cover the travel the
camera is used over.
"""

import argparse
import json

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

AXES = ("pan", "tilt")
# A stop that no rotation at all fits to within this many times the median stop
# (and at least MIN_REJECT_PX) has mis-matched tags, not a model error.
OUTLIER_ERROR_RATIO = 3.0
MIN_REJECT_PX = 15.0


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--input", default="/tmp/reprojection_accuracy.json")
  parser.add_argument("--config",
                      help="cameras.json to read settings from, if the measurement "
                           "didn't record them")
  parser.add_argument("--pan-degree", type=int, default=2,
                      help="polynomial degree of the fitted pan curve (1 = constant scale)")
  parser.add_argument("--tilt-degree", type=int, default=2,
                      help="polynomial degree of the fitted tilt curve (1 = constant scale)")
  parser.add_argument("--pan-travel", type=float, nargs=2, default=[-1.0, 1.0],
                      help="ONVIF pan range the camera is used over; a curve whose slope "
                           "becomes implausible anywhere in it is flagged")
  parser.add_argument("--tilt-travel", type=float, nargs=2, default=[0.0, 1.0],
                      help="ONVIF tilt range the camera is used over (see --pan-travel)")
  parser.add_argument("--no-fit-pan-axis", dest="fit_pan_axis", action="store_false",
                      help="keep the configured pan_axis (default world vertical) fixed")
  parser.add_argument("--fit-backlash", action="store_true",
                      help="also fit pan/tilt backlash instead of using the configured values "
                           "(needs stops reached from both directions, as the default path has)")
  parser.add_argument("--backlash-knots", type=int, nargs=2, default=[1, 1],
                      metavar=("PAN", "TILT"),
                      help="with --fit-backlash: per axis, the number of positions across the "
                           "measured range where backlash is fitted, interpolated between them "
                           "and held constant beyond (1 = a single constant value)")
  parser.add_argument("--try-sign-flips", action="store_true",
                      help="also start the fit from the negated pan/tilt scale and keep the best; "
                           "for a new camera whose rotation directions aren't known yet")
  parser.add_argument("--result-json",
                      help="also write the fitted values and errors to this file")
  return parser


def load_settings(data, config_path):
  entry = data.get("config")
  if entry is None and config_path:
    with open(config_path, encoding="utf-8") as handle:
      entry = next(c for c in json.load(handle)["cameras"]
                   if c.get("scene_camera_uid") == data["camera_uid"])
  if entry is None:
    raise SystemExit("No camera settings in the measurement; pass --config")
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
    return round(float(table[0][1]), 2)
  return [[round(float(p), 4), round(float(d), 2)] for p, d in table]


def angle_deltas(curve, positions, start, backlash, start_fraction):
  """Mirror of the service's backlash tracking (see PTZPoseContext._rotationFor).

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


def stop_errors(stop, start_pose, delta_pan, delta_tilt, pan_axis):
  rotation = (Rotation.from_rotvec(pan_axis * np.radians(delta_pan)) * start_pose
              * Rotation.from_euler("x", delta_tilt, degrees=True))
  return np.hypot(*(project(rotation, stop) - np.array(stop["points_2d"])).T)


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
    residual = lambda r, s=stop: np.hypot(*(project(Rotation.from_rotvec(r) * start_pose, s)
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

  def unpack(self, x):
    correction, x = Rotation.from_rotvec(x[:3]), x[3:]
    fractions, backlash, curves = {}, {}, {}
    for axis in AXES:
      if self.fit_backlash:
        n = len(self.knots[axis])
        backlash[axis], x = list(zip(self.knots[axis], x[:n])), x[n:]
      else:
        backlash[axis] = self.settings[axis]["backlash"]
      fractions[axis], x = (x[0], x[1:]) if self._has_backlash(axis) else (0.0, x)
    pan_axis = self.settings["pan_axis"]
    if self.fit_pan_axis:
      pan_axis, x = axis_from_slopes(x[:2]), x[2:]
    for axis in AXES:
      n = self.degrees[axis]
      curves[axis], x = [0.0, *x[:n]], x[n:]
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
      if self._has_backlash(axis):
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

  def errors(self, x, only_axis=None):
    start_pose, offsets, backlash, pan_axis, curves = self.unpack(x)
    d = self.deltas(offsets, backlash, curves)
    return np.concatenate([stop_errors(self.stops[i], start_pose, d["pan"][i], d["tilt"][i],
                                       pan_axis)
                           for i in self.measured
                           if only_axis in (None, self.stops[i]["axis"])])

  def solve(self, fixed_curves=False):
    x0, (lower, upper) = self.initial()
    if not fixed_curves:
      return least_squares(self.errors, x0, bounds=(lower, upper)).x
    n = len(x0) - sum(self.degrees.values())
    head = least_squares(lambda h: self.errors(np.concatenate([h, x0[n:]])), x0[:n],
                         bounds=(lower[:n], upper[:n])).x
    return np.concatenate([head, x0[n:]])


def summary(errors):
  return f"mean {errors.mean():6.2f} px  max {errors.max():6.2f} px" if errors.size else "no data"


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


def main():
  args = build_argparser().parse_args()
  data = json.load(open(args.input, encoding="utf-8"))
  settings = load_settings(data, args.config)
  rejected = reject_bad_stops(
      data["stops"], Rotation.from_euler("XYZ", data["stops"][0]["rotation"], degrees=True))

  # Current settings with only the start state free: the baseline to beat.
  current = Fit(data, settings, {a: len(settings[a]["curve"]) - 1 for a in AXES},
                fit_pan_axis=False, rejected=rejected)
  current_x = current.solve(fixed_curves=True)
  linear, linear_x = solve_best(data, settings, {"pan": 1, "tilt": 1}, args.fit_pan_axis,
                                args.fit_backlash, args.try_sign_flips, rejected,
                                args.backlash_knots)
  fit, best_x = solve_best(data, settings, {"pan": args.pan_degree, "tilt": args.tilt_degree},
                           args.fit_pan_axis, args.fit_backlash, args.try_sign_flips, rejected,
                           args.backlash_knots)

  start_pose, offsets, backlash, pan_axis, curves = fit.unpack(best_x)
  deltas = fit.deltas(offsets, backlash, curves)
  _, current_offsets, current_backlash, _, current_curves = current.unpack(current_x)
  current_deltas = current.deltas(current_offsets, current_backlash, current_curves)

  correction = np.degrees(np.linalg.norm(best_x[:3]))
  print(f"Start pose correction: {correction:.2f} deg"
        + ("  (large: re-calibrate before measuring)" if correction > 1.0 else ""))
  print(f"Pan axis: configured {np.round(settings['pan_axis'], 4).tolist()} "
        f"({lean_degrees(settings['pan_axis']):.2f} deg from vertical)"
        + (f", fitted {np.round(pan_axis, 4).tolist()} "
           f"({lean_degrees(pan_axis):.2f} deg from vertical)" if args.fit_pan_axis else ""))
  result = {"start_pose_correction_deg": correction, "axes": {}, "warnings": [],
            "rejected_stops": sorted(i + 1 for i in rejected)}

  for axis in AXES:
    indices = [i for i in fit.measured if fit.stops[i]["axis"] == axis]
    if not indices:
      print(f"\n== {axis}: no measured stops")
      continue
    positions = [fit.stops[i][axis] for i in indices]
    half = backlash_at(backlash[axis], fit.start[axis]) / 2.0
    label = "fitted " if args.fit_backlash else ""
    band = (f", started {offsets[axis] * half:+.2f} deg within [{-half:+.2f}, {half:+.2f}]"
            if half else "")
    across = (f" ({backlash_at(backlash[axis], min(positions)):.2f} -> "
              f"{backlash_at(backlash[axis], max(positions)):.2f} deg across the range)"
              if len(backlash[axis]) > 1 else " deg")
    print(f"\n== {axis}  (range {min(positions):+.4f} .. {max(positions):+.4f}, "
          f"{label}backlash {backlash_config(backlash[axis])}{across}{band})")

    other = "tilt" if axis == "pan" else "pan"

    def stop_error(i, delta):
      pan, tilt = (delta, deltas[other][i]) if axis == "pan" else (deltas[other][i], delta)
      return stop_errors(fit.stops[i], start_pose, pan, tilt, pan_axis)

    floor = []
    print(f"{'position':>9} {'dir':>5} {'actual':>8} {'current':>8} {'fitted':>8} {'fitted px':>10}")
    for i in indices:
      stop = fit.stops[i]
      actual = least_squares(lambda a: stop_error(i, a[0]), [deltas[axis][i]]).x[0]
      floor.append(stop_error(i, actual))
      print(f"{stop[axis]:+9.4f} {stop['direction']:>5} {actual:+8.2f} "
            f"{current_deltas[axis][i]:+8.2f} {deltas[axis][i]:+8.2f} "
            f"{stop_error(i, deltas[axis][i]).mean():10.2f}")

    service = np.array([e for i in indices for e in fit.stops[i]["errors"] if e is not None])
    rounded = lambda c: [round(float(v), 2) for v in c]
    print(f"  service, as measured:           {summary(service)}")
    print(f"  current {rounded(current_curves[axis])}: "
          f"{summary(current.errors(current_x, only_axis=axis))}")
    print(f"  linear  {rounded(linear.unpack(linear_x)[4][axis])}: "
          f"{summary(linear.errors(linear_x, only_axis=axis))}")
    print(f"  curve   {rounded(curves[axis])}: {summary(fit.errors(best_x, only_axis=axis))}")
    print(f"  floor (best angle per stop):    {summary(np.concatenate(floor))}")
    warning = extrapolation_warning(curves[axis], positions, getattr(args, f"{axis}_travel"))
    if warning:
      print(f"  WARNING: fitted {axis} curve {warning}")
      result["warnings"].append(f"{axis}: {warning}")
    mean = lambda errors: float(np.mean(errors)) if len(errors) else None
    result["axes"][axis] = {
        "service_px": mean(service),
        "current_px": mean(current.errors(current_x, only_axis=axis)),
        "curve_px": mean(fit.errors(best_x, only_axis=axis)),
        "floor_px": mean(np.concatenate(floor)),
    }

  config = {f"{axis}_curve": [round(float(c) * settings[axis]["sign"], 2) for c in curves[axis]]
            for axis in AXES}
  if args.fit_pan_axis:
    config["pan_axis"] = [round(float(v), 4) for v in pan_axis]
  if args.fit_backlash:
    config.update({f"{axis}_backlash_deg": backlash_config(backlash[axis]) for axis in AXES})
  result["config"] = config
  if args.result_json:
    with open(args.result_json, "w", encoding="utf-8") as handle:
      json.dump(result, handle)

  print("\nFor config/cameras.json (curves replace *_scale):")
  for axis in AXES:
    curve = [round(float(c) * settings[axis]["sign"], 2) for c in curves[axis]]
    print(f'  "{axis}_curve": {json.dumps(curve)},')
  if args.fit_pan_axis:
    print(f'  "pan_axis": {json.dumps([round(float(v), 4) for v in pan_axis])},')
  if args.fit_backlash:
    for axis in AXES:
      print(f'  "{axis}_backlash_deg": {json.dumps(backlash_config(backlash[axis]))},')
  print("\n'actual' is the rotation the tags say the camera made; 'current'/'fitted' are what\n"
        "the service computes with the current/fitted curve, from the fitted start state.\n"
        "A floor well above the start-position error means the rest is not in the curve\n"
        "(e.g. a pan axis that isn't vertical).")
  return 0


if __name__ == "__main__":
  exit(main())
