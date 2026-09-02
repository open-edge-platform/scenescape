#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fly a PX4 SIH vehicle through the demo ROI using MAVLink.

Default mode uploads a looping mission that ping-pongs across one ROI edge so
the vehicle centre crosses enter/exit every few seconds (spatial analytics).

The MAVLink *adapter* only publishes telemetry — run this script (``run_demo.sh
fly``) in a separate terminal to move the drone.

Connects to the SIH offboard port (default UDP 14540). Position updates reach
the SceneScape MAVLink adapter on UDP 14550 automatically in SIH.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from pymavlink import mavutil
from pymavlink.mavutil import mavlink


def load_config(path):
  with open(path, encoding="utf-8") as fh:
    return json.load(fh)


def offset_lla(lat, lon, north_m, east_m):
  """Approximate lat/lon offset in metres (flat earth, fine for demo scale)."""
  dlat = north_m / 111_320.0
  dlon = east_m / (111_320.0 * math.cos(math.radians(lat)))
  return lat + dlat, lon + dlon


def haversine_m(lat1, lon1, lat2, lon2):
  r = 6_371_000.0
  p1, p2 = math.radians(lat1), math.radians(lat2)
  dlat = math.radians(lat2 - lat1)
  dlon = math.radians(lon2 - lon1)
  a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
  return 2 * r * math.asin(math.sqrt(a))


def wait_heartbeat(mav, timeout_s=60):
  msg = mav.wait_heartbeat(timeout=timeout_s)
  if msg is None:
    raise TimeoutError("No MAVLink heartbeat from PX4 SIH")
  return msg


def set_mode(mav, *mode_names):
  mapping = mav.mode_mapping()
  for mode_name in mode_names:
    if mode_name not in mapping:
      continue
    mav.set_mode(mode_name)
    for _ in range(30):
      hb = mav.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
      if hb and mav.flightmode == mode_name:
        return mode_name
      time.sleep(0.2)
    return mode_name
  raise RuntimeError(
    f"No requested mode available (tried {mode_names!r}); have {sorted(mapping)}")


def takeoff_to_alt(mav, lat, lon, alt_m, position_tol_m):
  del position_tol_m
  set_mode(mav, "TAKEOFF", "POSCTL", "ALTCTL")
  arm_vehicle(mav)
  cmd_takeoff(mav, lat, lon, alt_m)
  print("Takeoff commanded …")
  deadline = time.time() + 90
  while time.time() < deadline:
    pos = read_global_position(mav, timeout_s=1)
    if pos and pos[2] >= alt_m - 5:
      return
    time.sleep(0.5)
  print("Warning: takeoff altitude not confirmed; continuing")


def arm_vehicle(mav, timeout_s=30):
  mav.mav.command_long_send(
    mav.target_system, mav.target_component,
    mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
  deadline = time.time() + timeout_s
  while time.time() < deadline:
    hb = mav.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
    if hb and hb.base_mode & mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
      return
    time.sleep(0.2)
  raise RuntimeError("Vehicle did not arm — check PX4 preflight / SIH logs")


def cmd_takeoff(mav, lat, lon, alt_m):
  mav.mav.command_long_send(
    mav.target_system, mav.target_component,
    mavlink.MAV_CMD_NAV_TAKEOFF, 0,
    0, 0, 0, 0, 0, 0,
    lat, lon, alt_m)


def read_global_position(mav, timeout_s=2):
  msg = mav.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=timeout_s)
  if msg is None:
    return None
  return msg.lat / 1e7, msg.lon / 1e7, msg.alt / 1000.0


def roi_ping_points(cfg, axis, outside_margin_m, inside_margin_m):
  """Return (outside, inside) lat/lon pairs straddling one ROI edge."""
  half = cfg["roi_half_size_m"]
  lat0 = cfg["px4_home_lat"]
  lon0 = cfg["px4_home_lon"]
  out_d = half + outside_margin_m
  in_d = max(half - inside_margin_m, 5.0)
  axis = axis.lower()
  if axis == "north":
    outside = offset_lla(lat0, lon0, out_d, 0)
    inside = offset_lla(lat0, lon0, in_d, 0)
  elif axis == "south":
    outside = offset_lla(lat0, lon0, -out_d, 0)
    inside = offset_lla(lat0, lon0, -in_d, 0)
  elif axis == "east":
    outside = offset_lla(lat0, lon0, 0, out_d)
    inside = offset_lla(lat0, lon0, 0, in_d)
  elif axis == "west":
    outside = offset_lla(lat0, lon0, 0, -out_d)
    inside = offset_lla(lat0, lon0, 0, -in_d)
  else:
    raise ValueError(f"Unknown axis: {axis}")
  return outside, inside


def stop_mission(mav):
  """Exit auto mission and hold position (does not disarm or stop PX4 SIH)."""
  print("Stopping mission — switching to POSCTL hold …")
  try:
    mav.mav.mission_clear_all_send(mav.target_system, mav.target_component)
    time.sleep(0.3)
  except Exception:
    pass
  set_mode(mav, "POSCTL", "ALTCTL", "LOITER")
  print("Mission stopped.")


def cancel_rtl(mav):
  """Leave RTL/LAND/LOITER so a new mission can run."""
  if mav.flightmode in ("RTL", "LAND", "DESCEND", "LOITER"):
    print(f"  Leaving {mav.flightmode} …")
    set_mode(mav, "POSCTL", "MISSION")


def start_ping_mission(mav, waypoints):
  """Upload, arm, and start the ping-pong mission."""
  cancel_rtl(mav)
  upload_mission(mav, waypoints)
  set_mode(mav, "MISSION", "AUTO.MISSION")
  arm_and_start_mission(mav)


def position_spread_m(positions):
  if len(positions) < 2:
    return 0.0
  lats = [p[0] for p in positions]
  lons = [p[1] for p in positions]
  mid_lat = sum(lats) / len(lats)
  scale_lon = 111_320.0 * math.cos(math.radians(mid_lat))
  ns = (max(lats) - min(lats)) * 111_320.0
  ew = (max(lons) - min(lons)) * scale_lon
  return max(ns, ew)


def fly_roi_ping(mav, cfg, axis, leg_period_s, outside_margin_m, inside_margin_m,
                 position_tol_m, stuck_timeout_s, cruise_speed_mps, accept_radius_m):
  """Upload a looping mission that crosses one ROI edge repeatedly."""
  del position_tol_m
  half = cfg["roi_half_size_m"]
  outside, inside = roi_ping_points(cfg, axis, outside_margin_m, inside_margin_m)

  print(f"ROI half-size {half} m; ping-pong on {axis} edge "
        f"(outside +{outside_margin_m} m, inside -{inside_margin_m} m from edge)")
  print(f"  outside ≈ {outside[0]:.6f}, {outside[1]:.6f}")
  print(f"  inside  ≈ {inside[0]:.6f}, {inside[1]:.6f}")
  cross_m = outside_margin_m + inside_margin_m
  est_leg_s = cross_m / max(cruise_speed_mps, 1.0)
  print(f"  crossing distance ≈ {cross_m:.0f} m (~{est_leg_s:.1f} s per leg at "
        f"{cruise_speed_mps:.0f} m/s)")
  print("  Auto-restarts on RTL/LAND/LOITER or if stuck (Ctrl+C to stop)")

  waypoints = build_ping_mission(
    cfg, axis, outside_margin_m, inside_margin_m, cruise_speed_mps, accept_radius_m)
  print(f"Uploading {len(waypoints)}-item looping mission …")
  start_ping_mission(mav, waypoints)
  print("Mission started — drone should cross ROI enter/exit repeatedly.")
  print("Watch events: ./tools/px4_sih_demo/run_demo.sh watch-roi")

  positions = []
  last_restart = time.monotonic()
  stuck_move_m = max(3.0, cross_m * 0.15)
  try:
    while True:
      pos = read_global_position(mav, timeout_s=5)
      now = time.monotonic()
      if pos:
        positions.append(pos[:2])
        if len(positions) > 30:
          positions.pop(0)
        dist_out = haversine_m(pos[0], pos[1], outside[0], outside[1])
        dist_in = haversine_m(pos[0], pos[1], inside[0], inside[1])
        side = "outside" if dist_out < dist_in else "inside"
        mc = mav.recv_match(type="MISSION_CURRENT", blocking=False)
        seq = getattr(mc, "seq", None)
        print(f"  lat={pos[0]:.6f} lon={pos[1]:.6f} alt={pos[2]:.1f}m "
              f"mode={mav.flightmode} seq={seq} ({side})")

        restart_reason = None
        if mav.flightmode in ("RTL", "LAND", "DESCEND", "LOITER"):
          restart_reason = f"mode={mav.flightmode}"
        elif (now - last_restart > stuck_timeout_s
              and len(positions) >= 6
              and position_spread_m(positions) < stuck_move_m):
          restart_reason = (
            f"stuck (moved <{stuck_move_m:.0f} m in {stuck_timeout_s:.0f} s)")

        if restart_reason and now - last_restart > 5:
          print(f"  ↻ Restarting ping mission: {restart_reason}")
          start_ping_mission(mav, waypoints)
          positions.clear()
          last_restart = now
      time.sleep(leg_period_s)
  except KeyboardInterrupt:
    print("\nStopped monitor (PX4 mission may still be running)")


def mission_item_int(seq, command, lat, lon, alt_m, param1=0, param2=2, param3=0, param4=0,
                     frame=None):
  """Build one MAV_MISSION_ITEM_INT dict."""
  if frame is None:
    frame = mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
  return {
    "seq": seq,
    "frame": frame,
    "command": command,
    "current": 0,
    "autocontinue": 1,
    "param1": param1,
    "param2": param2,
    "param3": param3,
    "param4": param4,
    "x": int(lat * 1e7),
    "y": int(lon * 1e7),
    "z": alt_m,
  }


def build_ping_mission(cfg, axis, outside_margin_m, inside_margin_m, cruise_speed_mps,
                       accept_radius_m):
  """Repeating mission: takeoff → outside ROI → inside → loop."""
  alt_m = cfg["px4_takeoff_alt_m"]
  lat0, lon0 = cfg["px4_home_lat"], cfg["px4_home_lon"]
  outside, inside = roi_ping_points(cfg, axis, outside_margin_m, inside_margin_m)

  # NAV_WAYPOINT: param1 hold (s), param2 acceptance radius (m). Keep hold at 0 and
  # use a generous radius so PX4 does not sit in LOITER waiting for a tight fix.
  mission_frame = mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
  items = [
    mission_item_int(0, mavlink.MAV_CMD_NAV_TAKEOFF, lat0, lon0, alt_m),
    mission_item_int(
      1, mavlink.MAV_CMD_DO_CHANGE_SPEED, 0, 0, 0,
      param1=1,  # groundspeed
      param2=cruise_speed_mps,
      frame=mavlink.MAV_FRAME_MISSION,
    ),
    mission_item_int(2, mavlink.MAV_CMD_NAV_WAYPOINT, outside[0], outside[1], alt_m,
                     param1=0, param2=accept_radius_m),
    mission_item_int(3, mavlink.MAV_CMD_NAV_WAYPOINT, inside[0], inside[1], alt_m,
                     param1=0, param2=accept_radius_m),
    {
      "seq": 4,
      "frame": mavlink.MAV_FRAME_MISSION,
      "command": mavlink.MAV_CMD_DO_JUMP,
      "current": 0,
      "autocontinue": 1,
      "param1": 2,  # jump back to "outside" waypoint (seq 2)
      "param2": 0,  # repeat indefinitely (PX4)
      "param3": 0, "param4": 0,
      "x": 0, "y": 0, "z": 0,
    },
  ]
  for item in items:
    if "frame" not in item or item["frame"] is None:
      item["frame"] = mission_frame
  return items


def build_square_mission(cfg):
  """Legacy one-shot square mission through map centre."""
  home_lat = cfg["px4_home_lat"]
  home_lon = cfg["px4_home_lon"]
  alt_m = cfg["px4_takeoff_alt_m"]
  leg_m = cfg.get("flight_leg_m", cfg.get("roi_half_size_m", 45.0) * 1.2)

  center = (home_lat, home_lon)
  north = offset_lla(center[0], center[1], leg_m, 0)
  south = offset_lla(center[0], center[1], -leg_m, 0)
  east = offset_lla(center[0], center[1], 0, leg_m)
  west = offset_lla(center[0], center[1], 0, -leg_m)

  path = [center, north, east, south, west, center]
  wps = []
  for seq, (lat, lon) in enumerate(path):
    wps.append({
      "seq": seq,
      "frame": mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
      "command": mavlink.MAV_CMD_NAV_WAYPOINT,
      "current": 0,
      "autocontinue": 1,
      "param1": 0, "param2": 0, "param3": 0, "param4": 0,
      "x": int(lat * 1e7),
      "y": int(lon * 1e7),
      "z": alt_m,
    })
  return wps


def upload_mission(mav, waypoints):
  mav.waypoint_clear_all_send()
  time.sleep(0.5)
  mav.mav.mission_count_send(mav.target_system, mav.target_component, len(waypoints))
  sent = set()
  deadline = time.time() + 30
  while len(sent) < len(waypoints) and time.time() < deadline:
    req = mav.recv_match(type=["MISSION_REQUEST", "MISSION_REQUEST_INT"], blocking=True, timeout=2)
    if req is None:
      continue
    seq = req.seq
    if seq in sent or seq >= len(waypoints):
      continue
    wp = waypoints[seq]
    mav.mav.mission_item_int_send(
      mav.target_system, mav.target_component,
      wp["seq"], wp["frame"], wp["command"], wp["current"], wp["autocontinue"],
      wp["param1"], wp["param2"], wp["param3"], wp["param4"],
      wp["x"], wp["y"], wp["z"])
    sent.add(seq)
  if len(sent) != len(waypoints):
    raise RuntimeError(f"Mission upload incomplete: {len(sent)}/{len(waypoints)}")


def arm_and_start_mission(mav):
  mav.mav.command_long_send(
    mav.target_system, mav.target_component,
    mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
  for _ in range(30):
    hb = mav.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
    if hb and hb.base_mode & mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
      break
    time.sleep(0.3)
  else:
    raise RuntimeError("Vehicle did not arm — check PX4 preflight / SIH logs")

  mav.mav.command_long_send(
    mav.target_system, mav.target_component,
    mavlink.MAV_CMD_MISSION_START, 0, 0, 0, 0, 0, 0, 0, 0)


def parse_args(argv=None):
  default_cfg = Path(__file__).resolve().parent / "px4_sih_config.json"
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--config", default=str(default_cfg))
  parser.add_argument(
    "--connection", default="udp:127.0.0.1:14540",
    help="MAVLink connection (PX4 offboard port for single-instance SIH)")
  parser.add_argument(
    "--pattern", choices=("ping", "square"), default="ping",
    help="ping: ROI edge enter/exit loop (default); square: one-shot box mission")
  parser.add_argument(
    "--axis", choices=("north", "south", "east", "west"), default="north",
    help="ROI edge to cross for ping pattern (default: north)")
  parser.add_argument(
    "--leg-period", type=float,
    default=float(os.environ.get("PX4_ROI_LEG_PERIOD_S", "2")),
    help="Status print interval in seconds (default: 2)")
  parser.add_argument(
    "--cruise-speed", type=float,
    default=float(os.environ.get("PX4_ROI_CRUISE_SPEED_MPS", "10")),
    help="Mission groundspeed in m/s (default: 10)")
  parser.add_argument(
    "--accept-radius", type=float,
    default=float(os.environ.get("PX4_ROI_ACCEPT_RADIUS_M", "8")),
    help="Waypoint acceptance radius in m — larger = less loiter at corners (default: 8)")
  parser.add_argument(
    "--outside-margin", type=float,
    default=float(os.environ.get("PX4_ROI_OUTSIDE_MARGIN_M", "8")),
    help="Metres beyond ROI edge for outside waypoint (default: 8)")
  parser.add_argument(
    "--inside-margin", type=float,
    default=float(os.environ.get("PX4_ROI_INSIDE_MARGIN_M", "8")),
    help="Metres inside ROI edge for inside waypoint (default: 8)")
  parser.add_argument(
    "--stuck-timeout", type=float,
    default=float(os.environ.get("PX4_ROI_STUCK_TIMEOUT_S", "8")),
    help="Restart mission if barely moving this many seconds (default: 8)")
  parser.add_argument(
    "--position-tol", type=float, default=4.0,
    help="Arrival tolerance in metres (default: 4)")
  parser.add_argument("--takeoff-only", action="store_true",
                      help="Arm and takeoff vertically; hover at home (no ROI crossing)")
  parser.add_argument(
    "--stop", action="store_true",
    help="Exit auto mission and hold position (does not stop PX4 SIH container)")
  return parser.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  cfg = load_config(args.config)
  print(f"Connecting to PX4 SIH at {args.connection} …")
  mav = mavutil.mavlink_connection(args.connection)
  wait_heartbeat(mav)
  print(f"Heartbeat from system {mav.target_system}")

  if args.stop:
    stop_mission(mav)
    return 0

  if args.takeoff_only:
    takeoff_to_alt(mav, cfg["px4_home_lat"], cfg["px4_home_lon"], cfg["px4_takeoff_alt_m"],
                   args.position_tol)
    print("Hover over home (inside ROI — no enter/exit events).")
    return 0

  if args.pattern == "ping":
    fly_roi_ping(
      mav, cfg, args.axis, args.leg_period,
      args.outside_margin, args.inside_margin, args.position_tol,
      args.stuck_timeout, args.cruise_speed, args.accept_radius)
    return 0

  waypoints = build_square_mission(cfg)
  print(f"Uploading {len(waypoints)}-waypoint square mission …")
  upload_mission(mav, waypoints)
  set_mode(mav, "MISSION", "AUTO.MISSION")
  arm_and_start_mission(mav)
  print("Mission started — one lap through the ROI.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
