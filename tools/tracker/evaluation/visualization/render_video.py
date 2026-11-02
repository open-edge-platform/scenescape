# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Render a robot-vision scenario recording, or real tracker output, as a short video.

Usage (from tools/tracker/evaluation):
  python visualization/render_video.py <scenario dir> [--zoom ID] [--speed F] [--trail S]
                                       [--zoom-size M] [--side-views MODE] [--zoom-side] [--gif]
                                       [--output DIR] [--fps FPS] [--xy-only | --z-only]

Writes <scenario dir>/videos/overview.mp4: all ground-truth objects (black, dashed)
and tracks (one colour each) as boxes with position, size and heading, and their
trails. When the recording has vertical motion (--side-views auto, the default), two
side views are added under the top-down view: x-z and y-z. They show each body as the
extent of its box along that axis by its height, centred on z, with the z trail. Their
horizontal axis has the scale of the top-down view, the vertical one is scaled to the
heights, so they are not to scale. Each --zoom ID (ground-truth object id or track id)
adds zoom_<ID>.mp4, a
follow camera on that object that also shows the track's predicted position, an
ellipse around it and the velocity arrow. For tracker-level recordings the ellipse is
the association gate from the track's estimator config: the χ² ellipse of the XY block
of the predicted measurement covariance S (most probable model) for
position_mahalanobis, without the max_radius_m ceiling, or a circle of max_radius_m for
euclidean. Without an association config it is the 99% confidence ellipse of S.
Objects without a size are drawn as points. With --zoom-side each --zoom ID also adds
zoom_<ID>_xz.mp4 and zoom_<ID>_yz.mp4: the x-z and y-z side views, true to scale, following
the object. Tracks are paired with ground-truth objects by x, y and z distance (--xy-only: the
ground plane, --z-only: the height).
"""

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
from utils.tracks import add_space_arguments  # noqa: E402
from visualization.scenario_data import (  # noqa: E402
  EstimatorTrace,
  Scenario,
  frame_rate,
  load_scenario,
)
# pylint: enable=wrong-import-position

MAX_VIDEO_FPS = 30.0
CONFIDENCE_PROBABILITY = 0.99  # share of the predicted position distribution inside the ellipse
MIN_ZOOM_SIZE = 4.0  # [m]
ZOOM_SIZE_FACTOR = 4.0  # zoom window per largest object dimension
FIGURE_SIZE = (8, 8)  # inches; with DPI an even pixel size, as H.264 requires
SIDE_VIEWS_FIGURE_SIZE = (10, 10)  # top-down view above the two side views
SIDE_VIEW_MODES = ("auto", "always", "never")
Z_MARGIN = 0.5  # [m] around the z range of the side views, besides half the largest height
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
  z: np.ndarray
  height: np.ndarray

  @classmethod
  def from_table(cls, table: pd.DataFrame) -> "Series":
    """Series from rows of a ground-truth or track table."""
    table = table.sort_values("t", kind="stable")
    return cls(*(table[column].to_numpy(dtype=float) if column in table else
                 np.full(len(table), np.nan)
                 for column in ("t", "x", "y", "yaw", "length", "width", "vx", "vy", "z",
                                "height")))

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


def confidence_ellipse(covariance: np.ndarray,
                       probability: float = CONFIDENCE_PROBABILITY) -> Tuple[float, float, float]:
  """Width, height and angle [deg] of the χ² confidence ellipse of a 2x2 covariance (2 DOF)."""
  threshold = -2.0 * math.log(1.0 - probability)
  eigenvalues, eigenvectors = np.linalg.eigh(covariance)
  eigenvalues = np.clip(eigenvalues, 0.0, None)
  angle = math.degrees(math.atan2(eigenvectors[1, 1], eigenvectors[0, 1]))
  return (2.0 * math.sqrt(threshold * eigenvalues[1]), 2.0 * math.sqrt(threshold * eigenvalues[0]),
          angle)


def association_gate(association: Optional[Dict[str, Any]],
                     covariance: np.ndarray) -> Tuple[float, float, float]:
  """Width, height and angle [deg] of the association gate around the predicted position.

  position_mahalanobis: χ² ellipse with the gate probability, without the max_radius_m
  ceiling. euclidean: circle of max_radius_m. No association config: the
  CONFIDENCE_PROBABILITY ellipse.
  """
  if association and association.get("method") == "euclidean":
    diameter = 2.0 * float(association["max_radius_m"])
    return diameter, diameter, 0.0
  probability = CONFIDENCE_PROBABILITY
  if association and "gate_probability" in association:
    probability = float(association["gate_probability"])
  return confidence_ellipse(covariance, probability)


def gate_label(association: Optional[Dict[str, Any]]) -> str:
  """Legend entry for association_gate()."""
  if association and association.get("method") == "euclidean":
    return f"association gate ({float(association['max_radius_m']):g} m)"
  if association and "gate_probability" in association:
    return f"association gate (χ² {float(association['gate_probability']):g})"
  return f"{CONFIDENCE_PROBABILITY:.0%} position ellipse"


def box_corners(x: float, y: float, yaw: float, length: float, width: float) -> np.ndarray:
  """Corners of a box with its length along the yaw direction."""
  c, s = math.cos(yaw), math.sin(yaw)
  half = np.array([[1, 1], [-1, 1], [-1, -1], [1, -1]]) * [length / 2, width / 2]
  return np.column_stack((x + half[:, 0] * c - half[:, 1] * s, y + half[:, 0] * s + half[:, 1] * c))


def side_extent(axis: str, yaw: float, length: float, width: float) -> float:
  """Extent along x (axis "x") or y (axis "y") of a box with its length along the yaw direction."""
  along, across = abs(math.cos(yaw)), abs(math.sin(yaw))
  return length * along + width * across if axis == "x" else length * across + width * along


def side_box_corners(position: float, z: float, extent: float, height: float) -> np.ndarray:
  """Corners of the side view of a box centred on (position, z)."""
  half = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * [extent / 2, height / 2]
  return half + [position, z]


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


class SideBoxArtist:  # pylint: disable=too-few-public-methods
  """Box seen from the side, with a trail: its extent along x or y by its height, centred on z."""

  def __init__(self, ax, axis: str, color: str, linestyle: str):
    self.axis = axis
    self.box = Polygon(np.zeros((4, 2)), closed=True, fill=False, edgecolor=color,
                       linestyle=linestyle, linewidth=1.5)
    ax.add_patch(self.box)
    (self.point,) = ax.plot([], [], "o", color=color, markersize=4)
    (self.trail,) = ax.plot([], [], color=color, linestyle=linestyle, linewidth=1.0, alpha=0.6)

  def update(self, series: Series, t: float, hold: float, trail: float) -> None:
    """Show the sample at t and the trail before it; hide everything without a sample or a z."""
    position = getattr(series, self.axis)
    index = series.index_at(t, hold)
    first = int(np.searchsorted(series.t, t - trail, side="left"))
    last = (index + 1) if index is not None else first
    self.trail.set_data(position[first:last], series.z[first:last])
    if index is None or not np.isfinite(series.z[index]):
      self.box.set_visible(False)
      self.point.set_visible(False)
      return
    yaw = series.yaw[index] if np.isfinite(series.yaw[index]) else 0.0
    length, width, height = series.length[index], series.width[index], series.height[index]
    has_box = all(np.isfinite(size) and size > 0 for size in (length, width, height))
    if has_box:
      self.box.set_xy(side_box_corners(position[index], series.z[index],
                                       side_extent(self.axis, yaw, length, width), height))
    else:
      self.point.set_data([position[index]], [series.z[index]])
    self.box.set_visible(has_box)
    self.point.set_visible(not has_box)


class ZoomArtist:  # pylint: disable=too-few-public-methods
  """Velocity arrow of a track, plus its predicted position and gate ellipse (estimator)."""

  def __init__(self, ax, color: str, trace: Optional[EstimatorTrace]):
    self.trace = trace
    self.association = trace.config.get("association") if trace is not None else None
    if trace is not None:
      (self.prediction,) = ax.plot([], [], "+", color=color, markersize=12, markeredgewidth=2,
                                   label="predicted position")
      self.ellipse = Ellipse((0, 0), 0, 0, fill=False, edgecolor=color, linestyle=":",
                             linewidth=1.5, label=gate_label(self.association))
      ax.add_patch(self.ellipse)
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
    self.ellipse.set_visible(visible)
    if visible:
      self.prediction.set_data([prediction[0]], [prediction[1]])
      width, height, angle = association_gate(self.association,
                                              trace.predicted_measurement_cov[step, :2, :2])
      self.ellipse.set_center(prediction)
      self.ellipse.set_width(width)
      self.ellipse.set_height(height)
      self.ellipse.set_angle(angle)


def render_video(directory, *, output=None,  # pylint: disable=too-many-arguments,too-many-locals
                 zoom: Optional[Sequence[str]] = None, speed: float = 1.0, trail: float = 2.0,
                 zoom_size: Optional[float] = None, gif: bool = False,
                 fps: Optional[float] = None, side_views: str = "auto",
                 zoom_side: bool = False, space: str = "xyz") -> List[Path]:
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
    side_views: "always", "never" or "auto" (only for recordings with vertical motion) for the
      x-z and y-z views under the top-down view of the overview video.
    zoom_side: Also write zoom_<ID>_xz and zoom_<ID>_yz, the x-z and y-z side views following
      each zoom target.
    space: Axes of the pairing of tracks with ground truth: "xyz" (default), "xy" or "z".

  Returns:
    Written files.

  Raises:
    RenderError: for an unknown zoom id, a non-positive speed, an unknown side_views mode, an
      empty scenario, or MP4 output without ffmpeg.
    FileNotFoundError: if the directory has no scenario files.
  """
  if speed <= 0:
    raise RenderError("speed must be positive")
  if side_views not in SIDE_VIEW_MODES:
    raise RenderError(f"side_views must be one of {', '.join(SIDE_VIEW_MODES)}")
  scenario = load_scenario(directory)
  if scenario.ground_truth.empty and scenario.tracks.empty:
    raise RenderError(f"No ground truth or tracks in {directory}")
  pairs = pair_tracks(scenario, fps, space)
  targets = [_zoom_target(scenario, pairs, item_id) for item_id in (zoom or [])]
  if not gif and not animation.writers.is_available("ffmpeg"):
    raise RenderError("ffmpeg is not available; install it or use --gif")

  output = Path(output) if output else scenario.directory / "videos"
  output.mkdir(parents=True, exist_ok=True)
  suffix = ".gif" if gif else ".mp4"
  show_side_views = side_views == "always" or (side_views == "auto"
                                               and scenario.has_vertical_motion)
  renderer = _Renderer(scenario, pairs, speed, trail, show_side_views)
  written = [renderer.render(output / f"overview{suffix}", gif)]
  for item_id, object_id, track_id in targets:
    name = re.sub(r"[^A-Za-z0-9_-]", "_", item_id)
    written.append(renderer.render(output / f"zoom_{name}{suffix}", gif, object_id, track_id,
                                   zoom_size))
    for axis in ("x", "y") if zoom_side else ():
      written.append(renderer.render(output / f"zoom_{name}_{axis}z{suffix}", gif, object_id,
                                     track_id, zoom_size, axis))
  return written


class _Renderer:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
  """Draws the scene for every video frame."""

  def __init__(self, scenario: Scenario, pairs: Pairs, speed: float, trail: float,
               side_views: bool = False):
    self.scenario = scenario
    self.pairs = pairs
    self.trail = trail
    self.side_views = side_views
    self.truth = {object_id: Series.from_table(table)
                  for object_id, table in scenario.ground_truth.groupby("object_id")}
    self.tracks = {track_id: Series.from_table(table)
                   for track_id, table in scenario.tracks.groupby("track_id")}
    times = np.concatenate([series.t for series in [*self.truth.values(), *self.tracks.values()]])
    data_fps = frame_rate(scenario.ground_truth) or frame_rate(scenario.tracks) or 10.0
    self.hold = 1.5 / data_fps
    self.video_fps, self.times = video_timing(times.min(), times.max(), data_fps, speed)

  def render(self, path: Path, gif: bool,  # pylint: disable=too-many-locals,too-many-arguments
             object_id: Optional[str] = None, track_id: Optional[str] = None,
             zoom_size: Optional[float] = None, side_axis: Optional[str] = None) -> Path:
    """Write one video; with an object or track id it follows that object.

    With side_axis "x" or "y" the followed view is the x-z or y-z side view instead of top-down.
    """
    zoomed = object_id is not None or track_id is not None
    if side_axis:
      fig, ax, side_axes = self._side_zoom_figure(label(object_id or track_id), side_axis)
      truth_artists, track_artists, zoom_artist = {}, {}, None
    else:
      fig, ax, side_axes = self._figure(label(object_id or track_id) if zoomed else None,
                                        self.side_views and not zoomed)
      truth_artists = {key: BoxArtist(ax, TRUTH_COLOR, "--", f"truth {label(key)}")
                       for key in self.truth}
      track_artists = {key: BoxArtist(ax, track_color(self.pairs, key), "-", f"track {label(key)}")
                       for key in self.tracks}
      zoom_artist = (ZoomArtist(ax, track_color(self.pairs, track_id),
                                self.scenario.estimator.get(track_id)) if track_id else None)
      handles, _ = ax.get_legend_handles_labels()
      if len(handles) <= 12:
        ax.legend(loc="upper right", fontsize="small")
    side_artists = self._side_artists(side_axes)
    clock = ax.text(0.02, 0.97, "", transform=ax.transAxes, va="top", family="monospace")
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
        for series, artist in side_artists:
          artist.update(series, t, self.hold, self.trail)
        if zoom_artist is not None:
          zoom_artist.update(track, t, self.hold)
        if zoomed:
          self._follow(ax, target, track, t, window, side_axis)
        clock.set_text(f"t = {t:6.2f} s")
        writer.grab_frame()
    plt.close(fig)
    return path

  def _figure(self, zoom_label: Optional[str], side_views: bool = False):
    """Figure, top-down axes and the side-view axes by horizontal axis name ("x", "y").

    The overview gets fixed limits, a zoom view moves with its target. With side views the
    top-down view is on top of the x-z and y-z views.
    """
    side_axes = {}
    if side_views:
      fig = plt.figure(figsize=SIDE_VIEWS_FIGURE_SIZE)
      grid = fig.add_gridspec(2, 2, height_ratios=[3, 2], left=0.08, right=0.97, top=0.95,
                              bottom=0.07, hspace=0.3, wspace=0.28)
      ax = fig.add_subplot(grid[0, :])
      side_axes = {"x": fig.add_subplot(grid[1, 0]), "y": fig.add_subplot(grid[1, 1])}
    else:
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
    for axis, side_ax in side_axes.items():
      side_ax.grid(True, alpha=0.3)
      side_ax.axhline(0.0, color="gray", linewidth=0.8)
      side_ax.set_xlabel(f"{axis} [m]")
      side_ax.set_ylabel("z [m]")
      side_ax.set_title(f"{axis}-z view (not to scale)")
      side_ax.set_xlim(*self._bounds("xy".index(axis)))
      side_ax.set_ylim(*self._z_bounds())
    return fig, ax, side_axes

  def _side_zoom_figure(self, zoom_label: str, axis: str):
    """Figure with one true-to-scale side view that follows its target; same return as _figure."""
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.axhline(0.0, color="gray", linewidth=0.8)
    ax.set_xlabel(f"{axis} [m]")
    ax.set_ylabel("z [m]")
    ax.set_title(f"{self.scenario.directory.parent.name}/{self.scenario.directory.name}: "
                 f"{zoom_label} ({axis}-z view)")
    return fig, ax, {axis: ax}

  def _side_artists(self, side_axes) -> List[Tuple[Series, SideBoxArtist]]:
    """One side-view artist per object and track in each side-view axes."""
    artists = []
    for axis, side_ax in side_axes.items():
      for series in self.truth.values():
        artists.append((series, SideBoxArtist(side_ax, axis, TRUTH_COLOR, "--")))
      for key, series in self.tracks.items():
        artists.append((series, SideBoxArtist(side_ax, axis, track_color(self.pairs, key), "-")))
    return artists

  def _z_bounds(self) -> Tuple[float, float]:
    """Limits of the side views: the z range plus half the largest height and a margin."""
    series_list = [*self.truth.values(), *self.tracks.values()]
    heights = np.concatenate([series.height for series in series_list])
    values = np.concatenate([series.z for series in series_list])
    values = values[np.isfinite(values)]
    if not values.size:
      return -1.0, 1.0
    half = 0.5 * float(np.nanmax(heights)) if np.isfinite(heights).any() else 0.0
    margin = half + Z_MARGIN
    return float(values.min() - margin), float(values.max() + margin)

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
              window: float, side_axis: Optional[str] = None) -> None:
    """Centre the view on the target's latest position, or the track's without ground truth.

    A side view is centred on (x or y, z); a series without a z is skipped.
    """
    for series in (target, track):
      if series is None:
        continue
      index = sample_index(series.t, t, math.inf)
      if index is None:
        continue
      horizontal = getattr(series, side_axis or "x")[index]
      vertical = series.z[index] if side_axis else series.y[index]
      if np.isfinite(vertical):
        ax.set_xlim(horizontal - window / 2, horizontal + window / 2)
        ax.set_ylim(vertical - window / 2, vertical + window / 2)
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
  parser.add_argument("--side-views", choices=SIDE_VIEW_MODES, default="auto",
                      help="x-z and y-z views under the overview: only for recordings with "
                      "vertical motion (auto, default), always or never")
  parser.add_argument("--zoom-side", action="store_true",
                      help="with --zoom, also write zoom_<ID>_xz and zoom_<ID>_yz: the x-z and "
                      "y-z side views following the object")
  parser.add_argument("--output", type=Path, help="output directory (default: <directory>/videos)")
  add_space_arguments(parser)
  parser.add_argument("--fps", type=float,
                      help="frame rate for pairing tracks with ground truth "
                      "(default: from ground truth)")
  args = parser.parse_args(argv)
  try:
    written = render_video(args.directory, output=args.output, zoom=args.zoom, speed=args.speed,
                           trail=args.trail, zoom_size=args.zoom_size, gif=args.gif,
                           fps=args.fps, side_views=args.side_views, zoom_side=args.zoom_side,
                           space=args.space)
  except (FileNotFoundError, RenderError) as error:
    parser.error(str(error))
  for path in written:
    print(path)
  return 0


if __name__ == "__main__":
  sys.exit(main())
