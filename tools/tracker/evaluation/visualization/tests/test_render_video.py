# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for rendering robot-vision scenario recordings as videos."""

import math
from pathlib import Path

import numpy as np
import pytest
from matplotlib import animation
from PIL import Image
import matplotlib.pyplot as plt

from visualization import render_video as render_video_module
from visualization.scenario_data import load_scenario
from visualization.render_video import (
  RenderError,
  Series,
  ZoomArtist,
  association_gate,
  box_corners,
  confidence_ellipse,
  detection_gate,
  gate_label,
  main,
  render_video,
  sample_index,
  side_box_corners,
  side_extent,
  video_timing,
)

requires_ffmpeg = pytest.mark.skipif(not animation.writers.is_available("ffmpeg"),
                                     reason="ffmpeg is not available")


def gif_frames(path):
  """Number of frames in a GIF file."""
  with Image.open(path) as image:
    return image.n_frames


def gif_size(path):
  """Width and height of a GIF file."""
  with Image.open(path) as image:
    return image.size


@pytest.mark.parametrize("data_fps, speed, video_fps, frames", [
  (10.0, 1.0, 10.0, 11),   # real time: one video frame per data frame
  (10.0, 0.5, 5.0, 11),    # slow motion: same frames, shown longer
  (25.0, 2.0, 30.0, 16),   # capped at 30 fps: data frames are skipped
])
def test_video_timing(data_fps, speed, video_fps, frames):
  """Playback speed sets the video frame rate, capped at 30 fps."""
  fps, times = video_timing(0.0, 1.0, data_fps, speed)

  assert fps == video_fps
  assert len(times) == frames
  assert times[0] == 0.0
  np.testing.assert_allclose(np.diff(times), speed / video_fps)


def test_sample_index_holds_latest_sample():
  """The latest sample is held for `hold` seconds, then dropped."""
  times = np.array([0.0, 0.1, 0.2])

  assert sample_index(times, -0.01, 0.15) is None
  assert sample_index(times, 0.1, 0.15) == 1
  assert sample_index(times, 0.15, 0.15) == 1
  assert sample_index(times, 0.36, 0.15) is None


@pytest.mark.parametrize("angle", [0.0, 30.0, -60.0])
def test_confidence_ellipse(angle):
  """Axes are 2 sqrt(χ² λ) with χ²(0.99, 2 DOF) = 9.21, rotated with the major eigenvector."""
  rotation = np.array([[math.cos(math.radians(angle)), -math.sin(math.radians(angle))],
                       [math.sin(math.radians(angle)), math.cos(math.radians(angle))]])
  covariance = rotation @ np.diag([4.0, 1.0]) @ rotation.T

  width, height, ellipse_angle = confidence_ellipse(covariance)

  assert width == pytest.approx(2 * math.sqrt(9.2103404 * 4.0))
  assert height == pytest.approx(2 * math.sqrt(9.2103404 * 1.0))
  # An ellipse is symmetric under 180° rotation.
  assert (ellipse_angle - angle + 90.0) % 180.0 - 90.0 == pytest.approx(0.0, abs=1e-9)


def test_association_gate_follows_method():
  """Mahalanobis: χ² ellipse with the gate probability; Euclidean: circle; no config: 99% ellipse."""
  covariance = np.diag([4.0, 1.0])
  mahalanobis = {"method": "position_mahalanobis", "gate_probability": 0.95, "max_radius_m": 10.0}
  euclidean = {"method": "euclidean", "max_radius_m": 2.0}

  assert association_gate(mahalanobis, covariance) == pytest.approx(
    confidence_ellipse(covariance, 0.95))
  assert association_gate(euclidean, covariance) == (4.0, 4.0, 0.0)
  assert association_gate(None, covariance) == pytest.approx(confidence_ellipse(covariance))
  assert gate_label(mahalanobis) == "association gate (χ² 0.95)"
  assert gate_label(euclidean) == "association gate (2 m)"
  assert gate_label(None) == "99% position ellipse"


def test_association_gate_clamps_probability_as_robot_vision():
  """gate_probability 1.0 is valid in both services; rv::chi2Threshold clamps it to 1 - 1e-9."""
  covariance = np.diag([4.0, 1.0])
  threshold = -2.0 * math.log(1e-9)

  width, height, _ = association_gate(
    {"method": "position_mahalanobis", "gate_probability": 1.0}, covariance)

  assert width == pytest.approx(2 * math.sqrt(threshold * 4.0))
  assert height == pytest.approx(2 * math.sqrt(threshold * 1.0))


def test_box_corners_follow_yaw():
  """The box length lies along the yaw direction."""
  corners = box_corners(1.0, 2.0, math.pi / 2, 4.0, 2.0)

  np.testing.assert_allclose(corners.min(axis=0), [0.0, 0.0], atol=1e-12)
  np.testing.assert_allclose(corners.max(axis=0), [2.0, 4.0], atol=1e-12)


def test_renders_overview_and_zoom_gif(recording):
  """GIF output needs no ffmpeg; real-time playback shows every data frame."""
  written = render_video(recording, zoom=["1"], gif=True)

  assert written == [recording / "videos" / "overview.gif", recording / "videos" / "zoom_1.gif"]
  assert [gif_frames(path) for path in written] == [11, 11]


@requires_ffmpeg
def test_renders_mp4(recording, tmp_path):
  """MP4 output is an H.264 file in the chosen directory."""
  written = render_video(recording, output=tmp_path / "out", speed=0.5)

  assert written == [tmp_path / "out" / "overview.mp4"]
  assert written[0].read_bytes()[4:8] == b"ftyp"


def test_renders_tracker_output(tracker_output):
  """Without estimator and ground-truth size, objects are points and the zoom has no ellipse."""
  written = render_video(tracker_output, zoom=["0"], gif=True, trail=0.5)

  assert [path.name for path in written] == ["overview.gif", "zoom_0.gif"]
  assert gif_frames(written[1]) == 20


def test_rejects_invalid_input(recording):
  """Unknown zoom ids and non-positive speed are errors."""
  with pytest.raises(RenderError, match="Unknown object or track id"):
    render_video(recording, zoom=["nope"], gif=True)
  with pytest.raises(RenderError, match="speed"):
    render_video(recording, speed=0.0, gif=True)
  with pytest.raises(SystemExit):
    main([str(recording), "--gif", "--zoom", "nope"])


def test_command_line(recording, capsys):
  """The CLI writes the videos and lists them."""
  assert main([str(recording), "--gif", "--zoom", "1", "--zoom-size", "6"]) == 0

  assert capsys.readouterr().out.splitlines() == [
    str(recording / "videos" / "overview.gif"),
    str(recording / "videos" / "zoom_1.gif"),
  ]


def test_side_extent_follows_yaw():
  """A box seen along x or y covers its footprint projected on that axis."""
  assert side_extent("x", 0.0, 4.0, 2.0) == pytest.approx(4.0)
  assert side_extent("y", 0.0, 4.0, 2.0) == pytest.approx(2.0)
  assert side_extent("x", math.pi / 2, 4.0, 2.0) == pytest.approx(2.0)
  assert side_extent("y", math.pi / 2, 4.0, 2.0) == pytest.approx(4.0)
  assert side_extent("x", math.pi / 4, 4.0, 2.0) == pytest.approx(side_extent("y", math.pi / 4, 4.0, 2.0))


def test_side_box_is_centred_on_z():
  """The side view of a box spans its extent horizontally and its height around z."""
  corners = side_box_corners(10.0, 2.0, 4.0, 1.5)

  np.testing.assert_allclose(corners.min(axis=0), [8.0, 1.25])
  np.testing.assert_allclose(corners.max(axis=0), [12.0, 2.75])


def test_side_views_follow_vertical_motion(recording, climbing_recording, tmp_path):
  """Auto adds the x-z and y-z views for vertical motion only; zoom videos stay top-down."""
  planar = render_video(recording, output=tmp_path / "planar", gif=True)[0]
  climbing = render_video(climbing_recording, output=tmp_path / "climbing", gif=True, zoom=["1"])

  assert gif_size(planar) == (800, 800)
  assert gif_size(climbing[0]) == (1000, 1000)
  assert gif_size(climbing[1]) == (800, 800)
  assert gif_frames(climbing[0]) == gif_frames(climbing[1])


def test_side_views_can_be_forced_or_disabled(recording, climbing_recording, tmp_path):
  """`always` also draws them for planar data (at z = 0), `never` omits them."""
  forced = render_video(recording, output=tmp_path / "forced", gif=True, side_views="always")[0]
  disabled = render_video(climbing_recording, output=tmp_path / "disabled", gif=True,
                          side_views="never")[0]

  assert gif_size(forced) == (1000, 1000)
  assert gif_size(disabled) == (800, 800)


def test_rejects_unknown_side_views_mode(recording, capsys):
  """The mode is checked in the API and by the command line."""
  with pytest.raises(RenderError, match="side_views"):
    render_video(recording, gif=True, side_views="sideways")
  with pytest.raises(SystemExit):
    main([str(recording), "--gif", "--side-views", "sideways"])
  assert "invalid choice" in capsys.readouterr().err


def test_zoom_side_writes_x_z_and_y_z_follow_views(climbing_recording, tmp_path):
  """--zoom-side adds one true-to-scale side view per axis next to the top-down zoom."""
  written = render_video(climbing_recording, output=tmp_path / "out", gif=True, zoom=["1"],
                         zoom_side=True)

  assert [path.name for path in written] == ["overview.gif", "zoom_1.gif", "zoom_1_xz.gif",
                                             "zoom_1_yz.gif"]
  assert gif_size(written[2]) == gif_size(written[3]) == (800, 800)
  assert gif_frames(written[2]) == gif_frames(written[3]) == gif_frames(written[0])


def test_zoom_side_is_off_by_default(climbing_recording, tmp_path):
  """Without the flag only the top-down zoom is written."""
  written = render_video(climbing_recording, output=tmp_path / "out", gif=True, zoom=["1"])

  assert [path.name for path in written] == ["overview.gif", "zoom_1.gif"]


def test_zoom_side_command_line(climbing_recording, capsys):
  """The CLI lists the side zoom videos."""
  assert main([str(climbing_recording), "--gif", "--zoom", "1", "--zoom-side"]) == 0

  assert [Path(line).name for line in capsys.readouterr().out.splitlines()] == [
    "overview.gif", "zoom_1.gif", "zoom_1_xz.gif", "zoom_1_yz.gif"]


def test_pairing_space_flags(recording, capsys):
  """--xy-only and --z-only reach the pairing; the space is checked and the flags exclude each other."""
  assert main([str(recording), "--gif", "--xy-only"]) == 0
  assert main([str(recording), "--gif", "--z-only"]) == 0
  assert capsys.readouterr().out.count("overview.gif") == 2
  with pytest.raises(ValueError, match="space"):
    render_video(recording, gif=True, space="xz")
  with pytest.raises(SystemExit):
    main([str(recording), "--gif", "--xy-only", "--z-only"])


def test_side_views_without_size_or_z(tracker_output, tmp_path):
  """Objects without a size are points; tracker output with z = 0 still renders."""
  written = render_video(tracker_output, output=tmp_path / "out", gif=True, side_views="always")

  assert gif_size(written[0]) == (1000, 1000)
  assert gif_frames(written[0]) == 20


def test_detection_gate_adds_the_detection_noise_to_hpht():
  """A detection with its own R is gated on HPHt + R (x, y); a Euclidean circle ignores R."""
  hpht = np.diag([1.0, 0.5, 0.3, 0.2, 0.2, 0.2, 0.2])
  noise = np.full((7, 7), 0.01) + np.diag([2.0, 0.1, 0.2, 0.2, 0.2, 0.2, 0.2])
  mahalanobis = {"method": "position_mahalanobis", "gate_probability": 0.95, "max_radius_m": 10.0}

  assert detection_gate(mahalanobis, hpht, noise) == pytest.approx(
    association_gate(mahalanobis, hpht[:2, :2] + noise[:2, :2]))
  assert detection_gate(None, hpht, noise) == pytest.approx(
    confidence_ellipse(hpht[:2, :2] + noise[:2, :2]))
  assert detection_gate({"method": "euclidean", "max_radius_m": 2.0}, hpht, noise) is None


def test_zoom_artist_draws_the_gate_of_each_detection_with_r(noisy_recording):
  """At a step with HPHt, each detection with R of the followed object gets its gate."""
  scenario = load_scenario(noisy_recording)
  trace = scenario.estimator["1"]
  detections = scenario.detections[scenario.detections["object_id"] == "1"]
  track = Series.from_table(scenario.tracks[scenario.tracks["track_id"] == "1"])
  fig, ax = plt.subplots()
  artist = ZoomArtist(ax, "C0", trace, detections)

  artist.update(track, trace.t[5], 0.05)

  ellipse = artist.detection_ellipses["camera"]
  assert ellipse.get_visible()
  np.testing.assert_allclose(ellipse.get_center(), trace.predicted_measurement[5, :2])
  noise = detections.iloc[5]["measurement_noise_cov"]
  width, height, angle = detection_gate(None, trace.predicted_state_measurement_cov[5], noise)
  assert (ellipse.get_width(), ellipse.get_height(), ellipse.get_angle()) == pytest.approx(
    (width, height, angle))
  assert ellipse.get_label() == "detection gate (HPHt + R)"

  # The init step has no prediction and no HPHt.
  artist.update(track, trace.t[0], 0.05)
  assert not ellipse.get_visible()
  plt.close(fig)


def test_zoom_artist_without_detections_draws_no_detection_gate(recording):
  scenario = load_scenario(recording)
  fig, ax = plt.subplots()
  artist = ZoomArtist(ax, "C0", scenario.estimator["1"])
  assert not artist.detection_ellipses
  plt.close(fig)


@pytest.mark.parametrize("flag, expect_detections", [(False, False), (True, True)])
def test_detection_gates_are_off_by_default(noisy_recording, monkeypatch, flag, expect_detections):
  """Only --detection-gates hands the zoomed object's detections to the zoom view."""
  received = []
  real = render_video_module.ZoomArtist

  def spy(ax, color, trace, detections=None):
    received.append(detections)
    return real(ax, color, trace, detections)

  monkeypatch.setattr(render_video_module, "ZoomArtist", spy)
  args = [str(noisy_recording), "--gif", "--zoom", "1"] + (["--detection-gates"] if flag else [])
  assert main(args) == 0

  assert len(received) == 1
  assert (received[0] is not None and len(received[0]) == 11) == expect_detections
