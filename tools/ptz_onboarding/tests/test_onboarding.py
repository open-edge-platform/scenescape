# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Offline synthetic geometry and mocked-device tests; no hardware is accessed."""

import base64
import contextlib
import copy
from datetime import datetime, timezone
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from scipy.spatial.transform import Rotation

import config
import devices
import discovery
import fitting
import model
import ptz


ROOT = Path(__file__).resolve().parents[1]


def settings():
  value = config.read_json(ROOT / "camera.example.json")
  value["camera_uid"] = "my-camera"
  value["motion"].update(
    pan_range=[-1, 1], tilt_range=[-1, 1], home=[0.2, 0.3],
    approach_offset=[0.08, 0.08], lens_pan=[0.14, 0.2, 0.26],
    lens_tilt=[0.24, 0.3, 0.36],
    pan_path=[0, -0.05, -0.1, -0.05, 0, 0.05, 0.1, 0.05, 0],
    tilt_path=[0, -0.05, -0.1, -0.05, 0, 0.05, 0.1, 0.05, 0])
  return value


def synthetic():
  """Known nonlinear imaging, signed axis scales and nonzero backlash."""
  value = settings()
  home = value["motion"]["home"]
  lens = {"camera_uid": value["camera_uid"], "zoom": 0.0, "dataset_sha256": "synthetic",
          "scene": "my-scene",
          "config": {"resolution": [1280, 960],
                     "intrinsics": {"fx": 800.0, "fy": 800.0, "cx": 640.0, "cy": 480.0},
                     "distortion": {"k1": -0.02, "k2": 0.0, "k3": 0.0, "p1": 0.0, "p2": 0.0}}}
  space = {"uri": "http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace",
           "pan_min": -1.0, "pan_max": 1.0, "tilt_min": -1.0, "tilt_max": 1.0}
  camera = {**copy.deepcopy(lens["config"]), "scene": "my-scene", "name": "User camera",
            "scale": [1.0, 1.0, 1.0]}
  data = {"kind": "ptz", "camera_uid": "my-camera", "camera": camera,
          "zoom": 0.0, "home": home, "approach": value["motion"]["approach"],
          "approach_offset": value["motion"]["approach_offset"],
          "position_space": space, "stops": []}
  positions = [("pan", *home)]
  positions += [("pan", home[0] + d, home[1]) for d in value["motion"]["pan_path"]]
  positions += [("tilt", home[0], home[1] + d) for d in value["motion"]["tilt_path"]]
  specs = {
    "pan": {"curve": [0.0, 80.0], "backlash": 0.5, "axis": [0.0, 0.0, 1.0],
            "frame": "world_home", "approach_direction": "decreasing", "home_position": home[0]},
    "tilt": {"curve": [0.0, -60.0], "backlash": 0.8, "axis": [1.0, 0.0, 0.0],
             "frame": "camera_local", "approach_direction": "increasing", "home_position": home[1]},
  }
  for spec in specs.values():
    spec.update(backlash_home_tolerance_deg=0.2, backlash_history_s=10.0)
  deltas = {
    axis: fitting.angle_deltas(specs[axis]["curve"], [p[i + 1] for p in positions],
                              home[i], [(0, specs[axis]["backlash"])], 1)
    for i, axis in enumerate(fitting.AXES)}
  rng = np.random.default_rng(42)
  points = rng.uniform([-2.8, -2.0, 5.0], [2.8, 2.0, 8.0], size=(70, 3)).tolist()
  previous = home
  for i, (axis, pan, tilt) in enumerate(positions):
    rotation = (Rotation.from_euler("z", deltas["pan"][i], degrees=True) *
                Rotation.from_euler("x", deltas["tilt"][i], degrees=True))
    stop = {**lens["config"], "points_3d": points, "translation": [0, 0, 0]}
    pixels = fitting.project(rotation, stop).tolist()
    index = 0 if axis == "pan" else 1
    change = [pan, tilt][index] - previous[index]
    data["stops"].append({"axis": axis, "pan": pan, "tilt": tilt, "resolution": [1280, 960],
                          "direction": "-" if abs(change) < 1e-8 else
                          ("up" if change > 0 else "down"), "points_2d": pixels,
                          "points_3d": points})
    previous = [pan, tilt]
  bundle = {"camera_uid": data["camera_uid"], "home": home, "approach": data["approach"],
            "zoom": 0.0, "lens": lens, "rotation": [0.0, 0.0, 0.0],
            "translation": [0.0, 0.0, 0.0], "camera_before": camera,
            "ptz_calibration": {
              "parameterization_version": "v1", "calibration_version": "synthetic",
              "position_space": space, "settle_angular_threshold_deg": 0.1,
              "settle_interval_s": 0.6, "composition_order": ["pan", "home", "tilt"],
              "axes": specs, "quality": {"reprojection_rms_px": 0.0}}}
  return data, lens, bundle


class ConfigurationTests(unittest.TestCase):
  def load(self, value):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "camera.json"
      config.write_json(path, value)
      return config.load_config(path)

  def test_generic_config_and_relative_paths(self):
    result = self.load(settings())
    self.assertTrue(Path(result["manager_auth"]).is_absolute())

  def test_template_cannot_move_a_camera(self):
    with self.assertRaises(ValueError):
      self.load(config.read_json(ROOT / "camera.example.json"))

  def test_unsafe_targets_nonfinite_and_wildcards_rejected(self):
    for field, replacement in (("home", [2, 0]), ("approach_offset", [0, 0.1]),
                               ("pan_path", [0, 10, 0]), ("pan_path", [0, 0.1, 0]),
                               ("settle_s", float("inf"))):
      value = settings()
      value["motion"][field] = replacement
      with self.subTest(field=field), self.assertRaises(ValueError):
        if replacement == float("inf"):
          config.numbers([replacement])
        else:
          self.load(value)
    value = settings()
    value["camera_uid"] = "camera/#"
    with self.assertRaises(ValueError):
      self.load(value)

  def test_output_is_private_and_never_overwritten(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "result.json"
      config.write_json(path, {"value": 1})
      self.assertEqual(path.stat().st_mode & 0o777, 0o600)
      with self.assertRaises(FileExistsError):
        config.write_json(path, {"value": 2})

  def test_clock_skew_must_be_finite_nonnegative_even_without_motion(self):
    for skew in (-0.1, True, "0.1", float("inf"), float("nan")):
      with self.subTest(skew=skew), tempfile.TemporaryDirectory() as directory:
        value = settings()
        value["mqtt"]["max_clock_skew_s"] = skew
        path = Path(directory) / "camera.json"
        # Non-finite JSON is already forbidden by write_json.
        with patch("config.read_json", return_value=value), self.assertRaises(ValueError):
          config.load_config(path, motion_mode="probe")
    for skew in (0, 0.1):
      value = settings()
      value["mqtt"]["max_clock_skew_s"] = skew
      self.assertEqual(self.load(value)["mqtt"]["max_clock_skew_s"], skew)


class GeometryTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.data, cls.lens, cls.truth = synthetic()
    with contextlib.redirect_stdout(io.StringIO()):
      cls.fitted = model.solve_model(cls.data, cls.lens)

  def test_recovers_signed_scales_axis_and_backlash(self):
    axes = self.fitted["ptz_calibration"]["axes"]
    self.assertAlmostEqual(axes["pan"]["curve"][1], 80, delta=0.01)
    self.assertAlmostEqual(axes["tilt"]["curve"][1], -60, delta=0.01)
    self.assertAlmostEqual(axes["pan"]["backlash"], 0.5, delta=0.01)
    self.assertAlmostEqual(axes["tilt"]["backlash"], 0.8, delta=0.01)
    self.assertAlmostEqual(np.linalg.norm(axes["pan"]["axis"]), 1.0)
    result = model.verify_model(self.fitted, self.data, 0.01)
    self.assertLess(result["rms_px"], 0.01)

  def test_exact_threshold_and_all_points_not_mean_error(self):
    shifted = copy.deepcopy(self.data)
    for stop in shifted["stops"]:
      stop["points_2d"] = [[x + 3, y + 4] for x, y in stop["points_2d"]]
    result = model.verify_model(self.truth, shifted, 6)
    self.assertAlmostEqual(result["rms_px"], 5)
    self.assertEqual(result["points"], sum(len(s["points_2d"]) for s in shifted["stops"]))
    model.verify_model(self.truth, shifted, result["rms_px"])
    with self.assertRaisesRegex(ValueError, "exceeds"):
      model.verify_model(self.truth, shifted, result["rms_px"] - 0.000001)

  def test_bad_points_and_mismatched_zoom_scene_or_home_rejected(self):
    for mutate in (
      lambda d: d["stops"][2].update(points_2d=[]),
      lambda d: d.update(zoom=0.5),
      lambda d: d["camera"].update(scene="another-scene"),
      lambda d: d.update(home=[0, 0]),
      lambda d: d["stops"][0]["points_2d"][0].__setitem__(0, float("nan")),
    ):
      value = copy.deepcopy(self.data)
      mutate(value)
      with self.assertRaises(ValueError):
        model.verify_model(self.truth, value, 12)

  def test_lens_fit_recovers_intrinsics_and_distortion(self):
    data = copy.deepcopy(self.data)
    data["kind"] = "lens"
    data["camera"]["intrinsics"].update(fx=780, fy=780)
    with contextlib.redirect_stdout(io.StringIO()):
      result = model.solve_lens(data)
    self.assertFalse(result["poorly_constrained"])
    self.assertAlmostEqual(result["config"]["intrinsics"]["fx"], 800, delta=0.1)
    self.assertAlmostEqual(result["config"]["distortion"]["k1"], -0.02, delta=0.001)

  def test_insufficient_axis_coverage_rejected(self):
    value = copy.deepcopy(self.data)
    value["stops"] = value["stops"][:3]
    with self.assertRaises(ValueError):
      model.solve_model(value, self.lens)

  def test_another_scene_origin_orientation_and_native_degree_units(self):
    value = copy.deepcopy(self.data)
    scene_rotation = Rotation.from_euler("XYZ", [10, -8, 20], degrees=True)
    translation = np.array([2, -4, 1])
    for stop in value["stops"]:
      stop["points_3d"] = (scene_rotation.apply(stop["points_3d"]) + translation).tolist()
      stop["pan"] *= 100
      stop["tilt"] *= 100
    value["home"] = [p * 100 for p in value["home"]]
    value["approach_offset"] = [p * 100 for p in value["approach_offset"]]
    value["position_space"] = {"uri": "urn:my-camera:native-degrees",
                               "pan_min": -100, "pan_max": 100,
                               "tilt_min": -100, "tilt_max": 100}
    fitted = model.solve_model(value, self.lens)
    axes = fitted["ptz_calibration"]["axes"]
    self.assertAlmostEqual(axes["pan"]["curve"][1], 0.8, delta=0.001)
    self.assertAlmostEqual(axes["tilt"]["curve"][1], -0.6, delta=0.001)
    np.testing.assert_allclose(fitted["translation"], translation, atol=1e-5)
    np.testing.assert_allclose(axes["pan"]["axis"], scene_rotation.apply([0, 0, 1]), atol=1e-5)
    self.assertLess(model.verify_model(fitted, value, 0.01)["rms_px"], 0.01)


class DiscoveryTests(unittest.TestCase):
  def test_probe_and_planning_allow_empty_measurement_paths_but_not_unsafe_limits(self):
    value = settings()
    for key in ("lens_pan", "lens_tilt", "pan_path", "tilt_path"):
      value["motion"][key] = []
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "config.json"
      config.write_json(path, value)
      config.load_config(path, motion_mode="planning")
      with self.assertRaises(ValueError):
        config.load_config(path)
      value["motion"]["pan_range"] = []
      other = Path(directory) / "probe.json"
      config.write_json(other, value)
      config.load_config(other, motion_mode="probe")
      with self.assertRaises(ValueError):
        config.load_config(other, motion_mode="planning")

  def test_discovery_grid_stays_inside_limits_and_includes_exact_approach(self):
    motion = settings()["motion"]
    pans, tilts = discovery.grid(motion, 3)
    for i, values in enumerate((pans, tilts)):
      low, high = motion[f"{('pan', 'tilt')[i]}_range"]
      self.assertTrue(all(low <= value <= high for value in values))
      self.assertIn(motion["home"][i], values)
      before = motion["home"][i] + (1 if motion["approach"][i] == "decreasing" else -1) * motion["approach_offset"][i]
      self.assertIn(before, values)

  def test_rectangle_does_not_bridge_tag_visibility_holes(self):
    motion = settings()["motion"]
    pans, tilts = discovery.grid(motion, 3)
    observations = [{"requested_pan": p, "requested_tilt": t, "usable": True}
                    for p in pans for t in tilts]
    observations[0]["usable"] = False
    xs, ys = discovery.select_rectangle(pans, tilts, observations, motion)
    self.assertFalse(pans[0] in xs and tilts[0] in ys)
    self.assertIn(motion["home"][0], xs)
    self.assertIn(motion["home"][1], ys)
    for observation in observations:
      observation["usable"] = False
    with self.assertRaisesRegex(ValueError, "No sampled"):
      discovery.select_rectangle(pans, tilts, observations, motion)

  def test_discovery_records_coverage_and_proposes_valid_config(self):
    value = settings()
    stop = {"points_2d": [[1, 2]] * 6, "resolution": [1280, 960]}
    with tempfile.TemporaryDirectory() as directory, \
         patch("discovery.Camera") as camera, patch("discovery.Manager"), \
         patch("discovery.Tags") as tags, contextlib.redirect_stdout(io.StringIO()):
      camera.return_value.move.side_effect = lambda p, t: [p, t]
      tags.return_value.collect.return_value = stop
      output = Path(directory) / "coverage"
      discovery.discover(value, output, 3)
      self.assertEqual(camera.return_value.home.call_count, 2)
      proposed = config.load_config(output / "camera.discovered.json")
      self.assertEqual(proposed["motion"]["pan_range"], value["motion"]["pan_range"])
      self.assertGreaterEqual(len(proposed["motion"]["lens_pan"]), 3)
      self.assertEqual(proposed["motion"]["pan_path"][-1], 0)

  def test_discovered_offsets_round_inward_without_relaxing_move_bounds(self):
    value = settings()
    value["motion"].update(home=[-0.2, 0.2], pan_range=[-0.4, 0.1], tilt_range=[-0.1, 0.4])
    stop = {"points_2d": [[1, 2]] * 6, "resolution": [1280, 960]}
    with tempfile.TemporaryDirectory() as directory, \
         patch("discovery.Camera") as camera, patch("discovery.Manager"), \
         patch("discovery.Tags") as tags, contextlib.redirect_stdout(io.StringIO()):
      camera.return_value.move.side_effect = lambda p, t: [p, t]
      tags.return_value.collect.return_value = stop
      output = Path(directory) / "coverage"
      discovery.discover(value, output, 3)
      proposed = config.load_config(output / "camera.discovered.json")
    mover = devices.Camera.__new__(devices.Camera)
    mover.motion = proposed["motion"]
    mover.token, mover.zoom = "profile", None
    mover.space, mover.ptz = {"uri": "native"}, Mock()

    def feedback(*args):
      position = mover.ptz.AbsoluteMove.call_args.args[0]["Position"]["PanTilt"]
      return SimpleNamespace(Position=SimpleNamespace(
        PanTilt=SimpleNamespace(x=position["x"], y=position["y"]), Zoom=None), MoveStatus=None)

    mover.ptz.GetStatus.side_effect = feedback
    for i, axis in enumerate(("pan", "tilt")):
      original = value["motion"]
      low, high = original[f"{axis}_range"]
      home = original["home"][i]
      endpoint = high if i == 0 else low
      raw_offset = endpoint - home
      self.assertFalse(low <= home + raw_offset <= high)
      self.assertEqual(proposed["motion"][f"{axis}_range"], [low, high])
      offsets = proposed["motion"][f"{axis}_path"]
      self.assertIn(np.nextafter(raw_offset, 0.0), offsets)
      for offset in offsets:
        target = original["home"].copy()
        target[i] += offset
        with patch("devices.time.sleep"):
          self.assertEqual(mover.move(*target), target)
      unsafe = original["home"].copy()
      unsafe[i] = home + raw_offset
      with self.assertRaisesRegex(ValueError, "outside configured safe limits"):
        mover.move(*unsafe)

  def test_transport_failure_aborts_discovery_but_returns_home_and_saves_report(self):
    with tempfile.TemporaryDirectory() as directory, \
         patch("discovery.Camera") as camera, patch("discovery.Manager"), \
         patch("discovery.Tags") as tags:
      tags.return_value.collect.side_effect = TimeoutError("broker unavailable")
      output = Path(directory) / "coverage"
      with self.assertRaises(TimeoutError):
        discovery.discover(settings(), output, 3)
      self.assertEqual(camera.return_value.home.call_count, 2)
      self.assertTrue((output / "coverage.json").exists())
      self.assertFalse((output / "camera.discovered.json").exists())

  def test_backend_failure_during_grid_aborts_without_visiting_later_points(self):
    stop = {"points_2d": [[1, 2]] * 6, "resolution": [1280, 960]}
    with tempfile.TemporaryDirectory() as directory, \
         patch("discovery.Camera") as camera, patch("discovery.Manager"), \
         patch("discovery.Tags") as tags, contextlib.redirect_stdout(io.StringIO()):
      camera.return_value.move.return_value = [0, 0]
      tags.return_value.collect.side_effect = [
        stop, RuntimeError("AprilTag calibration failed: Missing internal state")]
      output = Path(directory) / "coverage"
      with self.assertRaisesRegex(RuntimeError, "Missing internal state"):
        discovery.discover(settings(), output, 3)
      camera.return_value.move.assert_called_once()
      self.assertEqual(camera.return_value.home.call_count, 2)
      self.assertEqual(config.read_json(output / "coverage.json")["observations"], [])
      self.assertFalse((output / "camera.discovered.json").exists())

  def test_fresh_frame_timeout_aborts_discovery_instead_of_becoming_a_visibility_gap(self):
    stop = {"points_2d": [[1, 2]] * 6, "resolution": [1280, 960]}
    with tempfile.TemporaryDirectory() as directory, \
         patch("discovery.Camera") as camera, patch("discovery.Manager"), \
         patch("discovery.Tags") as tags:
      tags.return_value.collect.side_effect = [stop, TimeoutError("No fresh calibration image")]
      output = Path(directory) / "coverage"
      with self.assertRaisesRegex(TimeoutError, "No fresh calibration image"):
        discovery.discover(settings(), output, 3)
      camera.return_value.move.assert_called_once()
      self.assertEqual(camera.return_value.home.call_count, 2)
      self.assertEqual(config.read_json(output / "coverage.json")["observations"], [])
      self.assertFalse((output / "camera.discovered.json").exists())

  def test_no_coverage_can_be_recorded_but_not_network_failure(self):
    stop = {"points_2d": [[1, 2]] * 6, "resolution": [1280, 960]}
    with tempfile.TemporaryDirectory() as directory, \
         patch("discovery.Camera") as camera, patch("discovery.Manager"), \
         patch("discovery.Tags") as tags, contextlib.redirect_stdout(io.StringIO()):
      value = settings()
      pans, tilts = discovery.grid(value["motion"], 3)
      camera.return_value.move.side_effect = lambda p, t: [p, t]
      tags.return_value.collect.side_effect = [
        stop, *[devices.TagCoverageError("no tags") for _ in range(len(pans) * len(tilts))]]
      output = Path(directory) / "coverage"
      with self.assertRaisesRegex(ValueError, "No sampled"):
        discovery.discover(value, output, 3)
      self.assertTrue(all(not s["usable"] for s in config.read_json(
        output / "coverage.json")["observations"]))


class DeviceWorkflowTests(unittest.TestCase):
  def test_onboard_saves_raw_capture_before_fit_failure_without_manager_writes(self):
    data, _, _ = synthetic()
    data["kind"] = "lens"
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "camera.json"
      config.write_json(path, settings())
      output = Path(directory) / "run"
      with patch("ptz.capture", return_value=data), \
           patch("model.solve_lens", side_effect=ValueError("Lens fit is poorly constrained")), \
           patch("devices.Manager") as manager:
        with self.assertRaisesRegex(ValueError, "poorly constrained"):
          ptz.main(["--config", str(path), "onboard", "--output-dir", str(output), "--yes"])
        manager.assert_not_called()
      self.assertEqual(config.read_json(output / "lens-capture.json"), data)
      self.assertEqual({p.name for p in output.iterdir()}, {"lens-capture.json"})

  def test_onboard_persists_all_steps_without_manager_writes(self):
    data, _, _ = synthetic()
    views = copy.deepcopy(data)
    views["kind"] = "lens"
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "camera.json"
      config.write_json(path, settings())
      output = Path(directory) / "run"
      with patch("ptz.capture", side_effect=[views, data, copy.deepcopy(data)]), \
           patch("devices.Manager") as manager, contextlib.redirect_stdout(io.StringIO()):
        self.assertEqual(ptz.main(["--config", str(path), "onboard",
                                   "--output-dir", str(output), "--yes"]), 0)
        manager.assert_not_called()
      self.assertEqual({p.name for p in output.iterdir()},
                       {"lens-capture.json", "lens.json", "ptz-capture.json", "model.json",
                        "verify-capture.json", "verification.json"})
      self.assertLess(config.read_json(output / "verification.json")["rms_px"], 0.1)

  def test_onvif_profile_selection_and_advertised_native_space(self):
    profile = SimpleNamespace(token="my-profile", PTZConfiguration=SimpleNamespace(
      token="cfg", DefaultAbsolutePantTiltPositionSpace="urn:native"))
    space = SimpleNamespace(URI="urn:native", XRange=SimpleNamespace(Min=-1, Max=1),
                            YRange=SimpleNamespace(Min=-1, Max=1))
    with patch("onvif.ONVIFCamera") as factory, patch("devices.read_json") as account:
      account.return_value = {"username": "unused", "password": "unused"}
      service = factory.return_value.create_ptz_service.return_value
      media = factory.return_value.create_media_service.return_value
      media.GetProfiles.return_value = [profile]
      service.GetStatus.return_value.Position = SimpleNamespace(
        PanTilt=SimpleNamespace(space="urn:native"), Zoom=None)
      service.GetConfigurationOptions.return_value.Spaces.AbsolutePanTiltPositionSpace = [space]
      camera = devices.Camera(settings())
      self.assertEqual(camera.token, "my-profile")
      self.assertEqual(camera.space["uri"], "urn:native")
      service.GetStatus.return_value.Position.PanTilt.space = None
      self.assertEqual(devices.Camera(settings()).space["uri"], "urn:native")
      media.GetProfiles.return_value = [profile, profile]
      with self.assertRaisesRegex(ValueError, "exactly one"):
        devices.Camera(settings())
      media.GetProfiles.return_value = [profile]
      space.XRange.Max = 0.1
      with self.assertRaisesRegex(ValueError, "exceeds"):
        devices.Camera(settings())

  def test_manager_uses_existing_auth_contract_and_tls(self):
    with patch("devices.requests.Session") as session, patch("devices.read_json") as account:
      account.return_value = {"user": "unused", "password": "unused"}
      session.return_value.request.return_value.json.return_value = {"token": "test-token"}
      devices.Manager(settings())
      self.assertEqual(session.return_value.verify, settings()["ca_cert"])
      self.assertEqual(session.return_value.request.call_args.kwargs["data"],
                       {"username": "unused", "password": "unused"})

  def test_mqtt_waits_for_suback_and_ignores_retained_frames(self):
    import paho.mqtt.client as mqtt
    with patch("paho.mqtt.client.Client") as factory, patch("devices.read_json") as account, \
         patch("devices.time.time", side_effect=[1000, 1001]):
      account.return_value = {"user": "unused", "password": "unused"}
      client = factory.return_value
      client.publish.return_value.rc = mqtt.MQTT_ERR_SUCCESS

      def network_loop(**kwargs):
        if not client.publish.called:
          client.on_connect(client, None, None, SimpleNamespace(is_failure=False), None)
          client.on_subscribe(client, None, 1, [SimpleNamespace(is_failure=False)], None)
          client.on_message(client, None, SimpleNamespace(
            retain=False, payload=b'{"image":"pre-request"}'))
        else:
          client.on_message(client, None, SimpleNamespace(retain=True, payload=b'{"image":"old"}'))
          client.on_message(client, None, SimpleNamespace(
            retain=False, payload=b'{"image":"fresh","timestamp":"1970-01-01T00:16:40.500Z"}'))
        return mqtt.MQTT_ERR_SUCCESS

      client.loop.side_effect = network_loop
      tags = devices.Tags(settings())
      self.assertEqual(tags.image(), {"image": "fresh", "timestamp": "1970-01-01T00:16:40.500Z"})
      client.tls_set.assert_called_once_with(ca_certs=settings()["ca_cert"])
      client.publish.assert_called_once_with(
        "scenescape/cmd/camera/my-camera", "getcalibrationimage", qos=1)
      client.disconnect.assert_called_once()

  def test_mqtt_rejects_unverifiable_and_future_frames_before_calibration(self):
    import json
    import paho.mqtt.client as mqtt

    def timestamp(seconds):
      return datetime.fromtimestamp(seconds, timezone.utc).isoformat()

    cases = [
      ({}, "requires"),
      ({"timestamp": None}, "requires"),
      ({"timestamp": 1000.5}, "requires"),
      ({"timestamp": "invalid"}, "Invalid"),
      ({"timestamp": "NaN"}, "Invalid"),
      ({"timestamp": "1970-01-01T00:16:40.500"}, "timezone"),
      ({"timestamp": timestamp(1001.250001)}, "future"),
    ]
    for payload, reason in cases:
      with self.subTest(payload=payload), \
           patch("paho.mqtt.client.Client") as factory, patch("devices.read_json") as account, \
           patch("devices.time.time", side_effect=[1000, 1001]):
        account.return_value = {"user": "unused", "password": "unused"}
        client = factory.return_value
        client.publish.return_value.rc = mqtt.MQTT_ERR_SUCCESS

        def network_loop(**kwargs):
          if not client.publish.called:
            client.on_subscribe(client, None, 1, [SimpleNamespace(is_failure=False)], None)
          else:
            client.on_message(client, None, SimpleNamespace(
              retain=False, payload=json.dumps({"image": "unused", **payload}).encode()))
          return mqtt.MQTT_ERR_SUCCESS

        client.loop.side_effect = network_loop
        value = settings()
        value["mqtt"]["max_clock_skew_s"] = 0.25
        tags = devices.Tags(value)
        tags.session = Mock()
        with self.assertRaisesRegex(ValueError, reason) as raised:
          tags.collect()
        self.assertNotIsInstance(raised.exception, devices.TagCoverageError)
        tags.session.post.assert_not_called()
        client.disconnect.assert_called_once()

  def test_mqtt_discards_stale_frames_without_advancing_the_freshness_boundary(self):
    import json
    import paho.mqtt.client as mqtt
    stale = {"image": "stale", "timestamp": "1970-01-01T00:16:39.999Z"}
    fresh = {"image": "fresh", "timestamp": "1970-01-01T00:16:40.500Z"}
    for frames, succeeds in (([stale, fresh], True), ([stale, stale], False)):
      with self.subTest(succeeds=succeeds), \
           patch("paho.mqtt.client.Client") as factory, patch("devices.read_json") as account, \
           patch("devices.time.time", side_effect=[1000, 1001, 1001.1]), \
           patch("devices.time.monotonic", side_effect=[0, 0, 0, 0, 21]), \
           contextlib.redirect_stdout(io.StringIO()):
        account.return_value = {"user": "unused", "password": "unused"}
        client = factory.return_value
        client.publish.return_value.rc = mqtt.MQTT_ERR_SUCCESS
        pending = iter(frames)

        def network_loop(**kwargs):
          if not client.publish.called:
            client.on_subscribe(client, None, 1, [SimpleNamespace(is_failure=False)], None)
          else:
            client.on_message(client, None, SimpleNamespace(
              retain=False, payload=json.dumps(next(pending)).encode()))
          return mqtt.MQTT_ERR_SUCCESS

        client.loop.side_effect = network_loop
        tags = devices.Tags(settings())
        tags.session = Mock()
        if succeeds:
          self.assertEqual(tags.image(), fresh)
          self.assertEqual(client.publish.call_count, 2)
        else:
          with self.assertRaisesRegex(TimeoutError, "No fresh calibration image"):
            tags.collect()
          tags.session.post.assert_not_called()
        client.disconnect.assert_called_once()

  def test_timestamp_policy_rejects_even_slightly_stale_frames(self):
    for timestamp in ("1970-01-01T00:16:39.999Z", "1970-01-01T00:16:40.249999Z"):
      with self.subTest(timestamp=timestamp), self.assertRaises(devices.StaleFrameError):
        devices._validate_frame_timestamp({"timestamp": timestamp}, 1000, 1001, 0.25)

  def test_timestamp_policy_accepts_exact_boundaries_and_explicit_timezones(self):
    for timestamp in ("1970-01-01T00:16:40.250Z", "1970-01-01T00:16:41.250+00:00",
                      "1970-01-01T01:16:40.500+01:00"):
      with self.subTest(timestamp=timestamp):
        devices._validate_frame_timestamp({"timestamp": timestamp}, 1000, 1001, 0.25)
    devices._validate_frame_timestamp({"timestamp": "1970-01-01T00:16:40Z"}, 1000, 1001, 0)

  def test_calibration_polls_and_errors_are_not_success_shaped(self):
    import cv2
    _, image = cv2.imencode(".jpg", np.zeros((48, 64, 3), dtype=np.uint8))
    frame = {"image": base64.b64encode(image).decode(), "timestamp": "2026-10-30T12:00:00Z"}
    with patch("devices.Tags.image", return_value=frame), \
         patch("devices.time.sleep"):
      tags = devices.Tags(settings())
      tags.session = Mock()
      busy, done = Mock(), Mock()
      busy.json.return_value = {"status": "calibrating"}
      done.json.return_value = {"status": "success",
                                "calibration_points_2d": [[1, 2]] * 6,
                                "calibration_points_3d": [[1, 2, 3]] * 6}
      tags.session.get.side_effect = [busy, done]
      stop = tags.collect()
      self.assertEqual(stop["resolution"], [64, 48])
      self.assertEqual(stop["frame_timestamp"], frame["timestamp"])
      done.json.return_value = {"status": "error", "message": "no tags"}
      tags.session.get.side_effect = [done]
      with self.assertRaisesRegex(RuntimeError, "no tags"):
        tags.collect()

  def test_backend_errors_never_become_coverage_gaps(self):
    import cv2
    _, image = cv2.imencode(".jpg", np.zeros((48, 64, 3), dtype=np.uint8))
    frame = {"image": base64.b64encode(image).decode(), "timestamp": "2026-10-30T12:00:00Z"}
    with patch("devices.Tags.image", return_value=frame):
      tags = devices.Tags(settings())
      tags.session = Mock()
      for message in ("Missing calibration state", "Unexpected error: solver failed",
                      "Fewer than 4 tags found", "Unknown backend failure"):
        with self.subTest(message=message):
          tags.session.get.return_value.json.return_value = {
            "status": "error", "message": message}
          with self.assertRaisesRegex(RuntimeError, "AprilTag calibration failed") as raised:
            tags.collect()
          self.assertNotIsInstance(raised.exception, devices.TagCoverageError)
      tags.session.get.return_value.json.return_value = {"status": "pending", "message": "no tags"}
      with self.assertRaises(devices.TagCoverageError):
        tags.collect()
      tags.session.get.return_value.json.return_value = {
        "status": "success", "calibration_points_2d": [], "calibration_points_3d": []}
      with self.assertRaises(devices.TagCoverageError):
        tags.collect()

  def test_motion_requires_confirmation_before_device_access(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "config.json"
      config.write_json(path, settings())
      with patch("devices.Camera") as camera, contextlib.redirect_stderr(io.StringIO()):
        with self.assertRaises(SystemExit):
          ptz.main(["--config", str(path), "capture-ptz",
                    "--output", str(Path(directory) / "out.json")])
        camera.assert_not_called()

  def test_failed_collection_attempts_return_home_without_manager_write(self):
    with patch("devices.Manager") as manager, patch("devices.Camera") as camera, \
         patch("devices.Tags") as tags, contextlib.redirect_stdout(io.StringIO()):
      data, _, _ = synthetic()
      manager.return_value.camera.return_value = data["camera"]
      camera.return_value.space = data["position_space"]
      camera.return_value.zoom.x = 0.0
      camera.return_value.move.return_value = [0.2, 0.3]
      tags.return_value.collect.side_effect = TimeoutError("no image")
      with self.assertRaises(TimeoutError):
        ptz.capture(settings(), "ptz")
      self.assertEqual(camera.return_value.home.call_count, 2)
      manager.return_value.request.assert_not_called()

  def test_move_timeout_and_safe_bounds(self):
    camera = devices.Camera.__new__(devices.Camera)
    camera.motion = settings()["motion"]
    camera.motion["timeout_s"] = 0.01
    camera.token, camera.zoom = "profile", None
    camera.space, camera.ptz = {"uri": "native"}, Mock()
    status = SimpleNamespace(Position=SimpleNamespace(
      PanTilt=SimpleNamespace(x=0.0, y=0.0), Zoom=None), MoveStatus=None)
    camera.ptz.GetStatus.return_value = status
    with self.assertRaises(ValueError):
      camera.move(5, 0)
    camera.ptz.AbsoluteMove.assert_not_called()
    with patch("devices.time.sleep"), self.assertRaises(TimeoutError):
      camera.move(0.2, 0.3)

  def test_changed_verification_model_refused_before_network_access(self):
    data, _, bundle = synthetic()
    checked = model.verify_model(bundle, data, 12)
    bundle["rotation"][0] += 1
    with patch("devices.Camera") as camera, self.assertRaises(ValueError):
      ptz.apply_model(settings(), bundle, checked, "unused.json")
    camera.assert_not_called()

  def test_apply_single_write_backup_and_readback(self):
    data, _, bundle = synthetic()
    checked = model.verify_model(bundle, data, 12)
    after = {**data["camera"], "ptz_calibration": bundle["ptz_calibration"],
             "rotation": bundle["rotation"], "translation": bundle["translation"]}
    after["ptz_calibration"]["quality"]["reprojection_rms_px"] = checked["rms_px"]
    with tempfile.TemporaryDirectory() as directory, \
         patch("devices.Camera") as camera, patch("devices.Manager") as manager, \
         contextlib.redirect_stdout(io.StringIO()):
      camera.return_value.space = data["position_space"]
      camera.return_value.status.return_value.Position = SimpleNamespace(
        PanTilt=SimpleNamespace(x=0.2, y=0.3), Zoom=SimpleNamespace(x=0.0))
      manager.return_value.camera.side_effect = [data["camera"], after]
      backup = Path(directory) / "backup.json"
      ptz.apply_model(settings(), bundle, checked, backup)
      self.assertEqual(config.read_json(backup)["name"], "User camera")
      manager.return_value.request.assert_called_once()
      self.assertEqual(manager.return_value.request.call_args.args[0], "PUT")


if __name__ == "__main__":
  unittest.main()
