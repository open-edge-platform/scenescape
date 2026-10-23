# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Render a robot-vision scenario recording, or real tracker output, as a short video.

Usage (from tools/tracker/evaluation):
  python visualization/render_video.py <scenario dir> [--zoom ID] [--speed F] [--trail S]
                                       [--zoom-size M] [--gif] [--output DIR] [--fps FPS]

Writes <scenario dir>/videos/overview.mp4: all ground-truth objects (black, dashed)
and tracks (one colour each) as boxes with position, size and heading, and their
trails. Each --zoom ID (ground-truth object id or track id) adds zoom_<ID>.mp4, a
follow camera on that object that also shows the track's predicted position, the
χ² gate ellipse from the predicted measurement covariance S and the velocity arrow.
Objects without a size are drawn as points.
"""

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 pylint: disable=wrong-import-position
import numpy as np  # noqa: E402 pylint: disable=wrong-import-position
import pandas as pd  # noqa: E402 pylint: disable=wrong-import-position
from matplotlib import animation  # noqa: E402 pylint: disable=wrong-import-position
from matplotlib.patches import Ellipse, Polygon  # noqa: E402 pylint: disable=wrong-import-position

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=wrong-import-position
from visualization.plot_scenario import Pairs, label, pair_tracks, track_color  # noqa: E402
from visualization.scenario_data import (  # noqa: E402
  EstimatorTrace,
  Scenario,
  frame_rate,
  load_scenario,
)
# pylint: enable=wrong-import-position

MAX_VIDEO_FPS = 30.0
GATE_PROBABILITY = 0.99  # production association gate_probability
MIN_ZOOM_SIZE = 4.0  # [m]
ZOOM_SIZE_FACTOR = 4.0  # zoom window per largest object dimension
FIGURE_SIZE = (8, 8)  # inches; with DPI an even pixel size, as H.264 requires
DPI = 100
TRUTH_COLOR = "black"


class RenderError(ValueError):
  """Invalid input: unknown zoom id, non-positive speed, empty scenario or missing ffmpeg."""


@dataclass
class Series:  # pylint: disable=too-many-instance-attributes
  """Positions and boxes of one object or track, sorted by time."""

  t: np.ndarray
  x: np.ndarray
  y: np.ndarray
  yaw: np.ndarray
  length: np.ndarray
  width: np.ndarray
  vx: np.ndarray
  vy: np.ndarray

  @classmethod
  def from_table(cls, table: pd.DataFrame) -> "Series":
    """Series from rows of a ground-truth or track table."""
    table = table.sort_values("t", kind="stable")
    return cls(*(table[column].to_numpy(dtype=float) if column in table else
                 np.full(len(table), np.nan)
                 for column in ("t", "x", "y", "yaw", "length", "width", "vx", "vy")))

  def index_at(self, t: float, hold: float) -> Optional[int]:
    """Latest sample at or before t, if it is at most `hold` seconds old."""
    return sample_index(self.t, t, hold)


def sample_index(times: np.ndarray, t: float, hold: float) -> Optional[int]:
  """Index of the latest time at or before t, or None if there is none within `hold` seconds."""
  index = int(np.searchsorted(times, t + 1e-9, side="right")) - 1
  if index < 0 or t - times[index] > hold:
    return None
  return index


def video_timing(start: float, end: float, data_fps: float,
                 speed: float) -> Tuple[float, np.ndarray]:
  """Video frame rate and the scenario time of each video frame.

  Playback runs at `speed` times real time; the video shows data_fps * speed frames per
  second, at most MAX_VIDEO_FPS (data frames are then skipped).
  """
  video_fps = min(MAX_VIDEO_FPS, data_fps * speed)
  step = speed / video_fps
  count = int(math.floor((end - start) / step + 1e-6)) + 1
  return video_fps, start + step * np.arange(count)


def gate_ellipse(covariance: np.ndarray,
                 probability: float = GATE_PROBABILITY) -> Tuple[float, float, float]:
  """Width, height and angle [deg] of the χ² gate ellipse of a 2x2 covariance (2 DOF)."""
  threshold = -2.0 * math.log(1.0 - probability)
  eigenvalues, eigenvectors = np.linalg.eigh(covariance)
  eigenvalues = np.clip(eigenvalues, 0.0, None)
  angle = math.degrees(math.atan2(eigenvectors[1, 1], eigenvectors[0, 1]))
  return (2.0 * math.sqrt(threshold * eigenvalues[1]), 2.0 * math.sqrt(threshold * eigenvalues[0]),
          angle)


def box_corners(x: float, y: float, yaw: float, length: float, width: float) -> np.ndarray:
  """Corners of a box with its length along the yaw direction."""
  c, s = math.cos(yaw), math.sin(yaw)
  half = np.array([[1, 1], [-1, 1], [-1, -1], [1, -1]]) * [length / 2, width / 2]
  return np.column_stack((x + half[:, 0] * c - half[:, 1] * s, y + half[:, 0] * s + half[:, 1] * c))


class BoxArtist:  # pylint: disable=too-few-public-methods
  """Box with a heading line and a trail; a point marker when the size is unknown."""

  def __init__(self, ax, color: str, linestyle: str, name: str):
    self.box = Polygon(np.zeros((4, 2)), closed=True, fill=False, edgecolor=color,
                       linestyle=linestyle, linewidth=1.5, label=name)
    ax.add_patch(self.box)
    (self.heading,) = ax.plot([], [], color=color, linewidth=1.5)
    (self.point,) = ax.plot([], [], "o", color=color, markersize=4)
    (self.trail,) = ax.plot([], [], color=color, linestyle=linestyle, linewidth=1.0, alpha=0.6)

  def update(self, series: Series, t: float, hold: float, trail: float) -> Optional[int]:
    """Show the sample at t and the trail before it; hide everything without a sample."""
    index = series.index_at(t, hold)
    first = int(np.searchsorted(series.t, t - trail, side="left"))
    last = (index + 1) if index is not None else first
    self.trail.set_data(series.x[first:last], series.y[first:last])
    if index is None:
      for artist in (self.box, self.heading, self.point):
        artist.set_visible(False)
      return None
    x, y = series.x[index], series.y[index]
    yaw = series.yaw[index] if np.isfinite(series.yaw[index]) else 0.0
    length, width = series.length[index], series.width[index]
    has_box = np.isfinite(length) and np.isfinite(width) and length > 0 and width > 0
    if has_box:
      self.box.set_xy(box_corners(x, y, yaw, length, width))
      self.heading.set_data([x, x + 0.5 * length * math.cos(yaw)],
                            [y, y + 0.5 * length * math.sin(yaw)])
    else:
      self.point.set_data([x], [y])
    self.box.set_visible(has_box)
    self.heading.set_visible(has_box and np.isfinite(series.yaw[index]))
    self.point.set_visible(not has_box)
    return index


class ZoomArtist:  # pylint: disable=too-few-public-methods
  """Velocity arrow of a track, plus its predicted position and gate ellipse from the estimator."""

  def __init__(self, ax, color: str, trace: Optional[EstimatorTrace]):
    self.trace = trace
    if trace is not None:
      (self.prediction,) = ax.plot([], [], "+", color=color, markersize=12, markeredgewidth=2,
                                   label="predicted position")
      self.gate = Ellipse((0, 0), 0, 0, fill=False, edgecolor=color, linestyle=":",
                          linewidth=1.5, label=f"gate p={GATE_PROBABILITY}")
      ax.add_patch(self.gate)
    self.velocity = ax.quiver([0], [0], [0], [0], color=color, angles="xy", scale_units="xy",
                              scale=1.0, width=0.004, label="velocity (1 s)")

  def update(self, track: Series, t: float, hold: float) -> None:
    """Show the track's velocity and the estimator values of the step at t."""
    index = track.index_at(t, hold)
    self.velocity.set_visible(index is not None)
    if index is not None:
      self.velocity.set_offsets([[track.x[index], track.y[index]]])
      self.velocity.set_UVC([track.vx[index]], [track.vy[index]])
    trace = self.trace
    if trace is None:
      return
    step = sample_index(trace.t, t, hold)
    prediction = trace.predicted_measurement[step, :2] if step is not None else None
    visible = prediction is not None and bool(np.all(np.isfinite(prediction)))
    self.prediction.set_visible(visible)
    self.gate.set_visible(visible)
    if visible:
      self.prediction.set_data([prediction[0]], [prediction[1]])
      width, height, angle = gate_ellipse(trace.predicted_measurement_cov[step, :2, :2])
      self.gate.set_center(prediction)
      self.gate.set_width(width)
      self.gate.set_height(height)
      self.gate.set_angle(angle)


def render_video(directory, *, output=None,  # pylint: disable=too-many-arguments,too-many-locals
                 zoom: Optional[Sequence[str]] = None, speed: float = 1.0, trail: float = 2.0,
                 zoom_size: Optional[float] = None, gif: bool = False,
                 fps: Optional[float] = None) -> List[Path]:
  """Render the overview video and one zoom video per id in `zoom`.

  Args:
    directory: Scenario directory.
    output: Output directory, by default <directory>/videos.
    zoom: Ground-truth object ids or track ids to follow.
    speed: Playback speed relative to real time.
    trail: Trail length [s].
    zoom_size: Zoom window width [m], by default from the object size.
    gif: Write GIF instead of MP4.
    fps: Frame rate for pairing tracks with ground truth, by default the ground-truth rate.

  Returns:
    Written files.

  Raises:
    RenderError: for an unknown zoom id, a non-positive speed, an empty scenario, or MP4
      output without ffmpeg.
    FileNotFoundError: if the directory has no scenario files.
  """
  if speed <= 0:
    raise RenderError("speed must be positive")
  scenario = load_scenario(directory)
  if scenario.ground_truth.empty and scenario.tracks.empty:
    raise RenderError(f"No ground truth or tracks in {directory}")
  pairs = pair_tracks(scenario, fps)
  targets = [_zoom_target(scenario, pairs, item_id) for item_id in (zoom or [])]
  if not gif and not animation.writers.is_available("ffmpeg"):
    raise RenderError("ffmpeg is not available; install it or use --gif")

  output = Path(output) if output else scenario.directory / "videos"
  output.mkdir(parents=True, exist_ok=True)
  suffix = ".gif" if gif else ".mp4"
  renderer = _Renderer(scenario, pairs, speed, trail)
  written = [renderer.render(output / f"overview{suffix}", gif)]
  for item_id, object_id, track_id in targets:
    name = re.sub(r"[^A-Za-z0-9_-]", "_", item_id)
    written.append(renderer.render(output / f"zoom_{name}{suffix}", gif, object_id, track_id,
                                   zoom_size))
  return written


class _Renderer:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
  """Draws the scene for every video frame."""

  def __init__(self, scenario: Scenario, pairs: Pairs, speed: float, trail: float):
    self.scenario = scenario
    self.pairs = pairs
    self.trail = trail
    self.truth = {object_id: Series.from_table(table)
                  for object_id, table in scenario.ground_truth.groupby("object_id")}
    self.tracks = {track_id: Series.from_table(table)
                   for track_id, table in scenario.tracks.groupby("track_id")}
    times = np.concatenate([series.t for series in [*self.truth.values(), *self.tracks.values()]])
    data_fps = frame_rate(scenario.ground_truth) or frame_rate(scenario.tracks) or 10.0
    self.hold = 1.5 / data_fps
    self.video_fps, self.times = video_timing(times.min(), times.max(), data_fps, speed)

  def render(self, path: Path, gif: bool,  # pylint: disable=too-many-locals
             object_id: Optional[str] = None, track_id: Optional[str] = None,
             zoom_size: Optional[float] = None) -> Path:
    """Write one video; with an object or track id it follows that object."""
    zoomed = object_id is not None or track_id is not None
    fig, ax = self._figure(label(object_id or track_id) if zoomed else None)
    truth_artists = {key: BoxArtist(ax, TRUTH_COLOR, "--", f"truth {label(key)}")
                     for key in self.truth}
    track_artists = {key: BoxArtist(ax, track_color(self.pairs, key), "-", f"track {label(key)}")
                     for key in self.tracks}
    zoom_artist = (ZoomArtist(ax, track_color(self.pairs, track_id),
                              self.scenario.estimator.get(track_id)) if track_id else None)
    clock = ax.text(0.02, 0.97, "", transform=ax.transAxes, va="top", family="monospace")
    handles, _ = ax.get_legend_handles_labels()
    if len(handles) <= 12:
      ax.legend(loc="upper right", fontsize="small")
    target = self.truth.get(object_id) if object_id else None
    track = self.tracks.get(track_id) if track_id else None
    window = (zoom_size or self._zoom_size(target, track)) if zoomed else None

    writer = animation.PillowWriter(fps=self.video_fps) if gif else animation.FFMpegWriter(
      fps=self.video_fps, codec="libx264", extra_args=["-pix_fmt", "yuv420p"])
    with writer.saving(fig, str(path), DPI):
      for t in self.times:
        for key, artist in truth_artists.items():
          artist.update(self.truth[key], t, self.hold, self.trail)
        for key, artist in track_artists.items():
          artist.update(self.tracks[key], t, self.hold, self.trail)
        if zoom_artist is not None:
          zoom_artist.update(track, t, self.hold)
        if zoomed:
          self._follow(ax, target, track, t, window)
        clock.set_text(f"t = {t:6.2f} s")
        writer.grab_frame()
    plt.close(fig)
    return path

  def _figure(self, zoom_label: Optional[str]):
    """Figure and axes; the overview gets fixed limits, a zoom view moves with its target."""
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    title = f"{self.scenario.directory.parent.name}/{self.scenario.directory.name}"
    if zoom_label is None:
      ax.set_xlim(*self._bounds(0))
      ax.set_ylim(*self._bounds(1))
      ax.set_title(title)
    else:
      ax.set_title(f"{title}: {zoom_label}")
    return fig, ax

  def _bounds(self, axis: int) -> Tuple[float, float]:
    """Limits covering all positions plus the largest box and a margin."""
    columns = ("x", "y")[axis]
    values = np.concatenate([getattr(series, columns) for series in
                             [*self.truth.values(), *self.tracks.values()]])
    sizes = np.concatenate([np.concatenate((series.length, series.width)) for series in
                            [*self.truth.values(), *self.tracks.values()]])
    margin = 1.0 + (np.nanmax(sizes) if np.isfinite(sizes).any() else 0.0)
    return float(np.nanmin(values) - margin), float(np.nanmax(values) + margin)

  @staticmethod
  def _zoom_size(target: Optional[Series], track: Optional[Series]) -> float:
    """Zoom window from the largest dimension of the ground truth, else of the track."""
    for series in (target, track):
      if series is None:
        continue
      dimensions = np.concatenate((series.length, series.width))
      dimensions = dimensions[np.isfinite(dimensions)]
      if dimensions.size:
        return max(MIN_ZOOM_SIZE, ZOOM_SIZE_FACTOR * float(dimensions.max()))
    return MIN_ZOOM_SIZE

  def _follow(self, ax, target: Optional[Series], track: Optional[Series], t: float,
              window: float) -> None:
    """Centre the view on the target's latest position, or the track's without ground truth."""
    for series in (target, track):
      if series is None:
        continue
      index = sample_index(series.t, t, math.inf)
      if index is not None:
        x, y = series.x[index], series.y[index]
        ax.set_xlim(x - window / 2, x + window / 2)
        ax.set_ylim(y - window / 2, y + window / 2)
        return


def _zoom_target(scenario: Scenario, pairs: Pairs,
                 item_id: str) -> Tuple[str, Optional[str], Optional[str]]:
  """(id, object_id, track_id) for a ground-truth object id or a track id."""
  if item_id in scenario.object_ids:
    track_id = next((track for track, obj in pairs.items() if obj == item_id), None)
    return item_id, item_id, track_id
  if item_id in pairs:
    return item_id, pairs[item_id], item_id
  raise RenderError(f"Unknown object or track id {item_id!r}; "
                    f"objects: {scenario.object_ids}, tracks: {list(pairs)}")


def main(argv: Optional[List[str]] = None) -> int:
  """Command-line entry point."""
  parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
  parser.add_argument("directory", type=Path, help="scenario directory")
  parser.add_argument("--zoom", action="append", metavar="ID",
                      help="ground-truth object id or track id to follow (repeatable)")
  parser.add_argument("--speed", type=float, default=1.0, help="playback speed (default: 1)")
  parser.add_argument("--trail", type=float, default=2.0, help="trail length [s] (default: 2)")
  parser.add_argument("--zoom-size", type=float,
                      help=f"zoom window width [m] (default: {ZOOM_SIZE_FACTOR:g}x the object "
                      f"size, at least {MIN_ZOOM_SIZE:g})")
  parser.add_argument("--gif", action="store_true", help="write GIF instead of MP4")
  parser.add_argument("--output", type=Path, help="output directory (default: <directory>/videos)")
  parser.add_argument("--fps", type=float,
                      help="frame rate for pairing tracks with ground truth "
                      "(default: from ground truth)")
  args = parser.parse_args(argv)
  try:
    written = render_video(args.directory, output=args.output, zoom=args.zoom, speed=args.speed,
                           trail=args.trail, zoom_size=args.zoom_size, gif=args.gif,
                           fps=args.fps)
  except (FileNotFoundError, RenderError) as error:
    parser.error(str(error))
  for path in written:
    print(path)
  return 0


if __name__ == "__main__":
  sys.exit(main())
