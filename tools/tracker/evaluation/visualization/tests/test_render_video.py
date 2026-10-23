# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for rendering robot-vision scenario recordings as videos."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from matplotlib import animation
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# pylint: disable-next=wrong-import-position
from visualization.render_video import (  # noqa: E402
  RenderError,
  box_corners,
  gate_ellipse,
  main,
  render_video,
  sample_index,
  video_timing,
)

requires_ffmpeg = pytest.mark.skipif(not animation.writers.is_available("ffmpeg"),
                                     reason="ffmpeg is not available")


def gif_frames(path):
  """Number of frames in a GIF file."""
  with Image.open(path) as image:
    return image.n_frames


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
def test_gate_ellipse(angle):
  """Axes are 2 sqrt(χ² λ) with χ²(0.99, 2 DOF) = 9.21, rotated with the major eigenvector."""
  rotation = np.array([[math.cos(math.radians(angle)), -math.sin(math.radians(angle))],
                       [math.sin(math.radians(angle)), math.cos(math.radians(angle))]])
  covariance = rotation @ np.diag([4.0, 1.0]) @ rotation.T

  width, height, ellipse_angle = gate_ellipse(covariance)

  assert width == pytest.approx(2 * math.sqrt(9.2103404 * 4.0))
  assert height == pytest.approx(2 * math.sqrt(9.2103404 * 1.0))
  # An ellipse is symmetric under 180° rotation.
  assert (ellipse_angle - angle + 90.0) % 180.0 - 90.0 == pytest.approx(0.0, abs=1e-9)


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
  """Without estimator and ground-truth size, objects are points and the zoom has no gate."""
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
