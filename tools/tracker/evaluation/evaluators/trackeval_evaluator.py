# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""TrackEval evaluator implementation for tracking quality metrics.

Integrates with TrackEval library to compute industry-standard tracking metrics
including HOTA, MOTA, IDF1, and CLEAR MOT metrics for 3D point tracking.
"""

from typing import Iterator, List, Dict, Any
from pathlib import Path
import sys
import tempfile
import numpy as np
import shutil

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from base.tracker_evaluator import TrackerEvaluator

# TrackEval imports
from trackeval.datasets.mot_challenge_2d_box import MotChallenge2DBox
from trackeval.eval import Evaluator
from trackeval.metrics import HOTA, CLEAR, Identity, Count


class MotChallenge3DPoint(MotChallenge2DBox):
  """MOTChallenge dataset class for 3D point tracking evaluation.

  Extends MotChallenge2DBox to support 3D point tracking instead of 2D bounding boxes.
  Uses Euclidean distance for similarity calculation instead of IoU.

  Key differences from MotChallenge2DBox:
  - Detections are 3D points (x, y, z) instead of 2D bounding boxes (x, y, w, h)
  - Similarity is Euclidean distance-based instead of IoU-based
  - Empty detection arrays are (0, 3) instead of (0, 4)
  """

  def _load_raw_file(self, tracker, seq, is_gt):
    """Load a file (gt or tracker) in the MOT Challenge 3D point format.

    Overrides parent to extract 3D positions (x, y, z) instead of 2D boxes (x, y, w, h).

    CSV format: frame,id,x,y,z,conf,class,visibility
    - Columns 2:5 contain x, y, z positions

    If is_gt, this returns a dict which contains the fields:
    [gt_ids, gt_classes] : list (for each timestep) of 1D NDArrays (for each det).
    [gt_dets, gt_crowd_ignore_regions]: list (for each timestep) of lists of detections.
    [gt_extras] : list (for each timestep) of dicts (for each extra) of 1D NDArrays (for each det).

    if not is_gt, this returns a dict which contains the fields:
    [tracker_ids, tracker_classes, tracker_confidences] : list (for each timestep) of 1D NDArrays (for each det).
    [tracker_dets]: list (for each timestep) of lists of detections.
    """
    import os

    # File location
    if self.data_is_zipped:
      if is_gt:
        zip_file = os.path.join(self.gt_fol, 'data.zip')
      else:
        zip_file = os.path.join(self.tracker_fol, tracker, self.tracker_sub_fol + '.zip')
      file = seq + '.txt'
    else:
      zip_file = None
      if is_gt:
        file = self.config["GT_LOC_FORMAT"].format(gt_folder=self.gt_fol, seq=seq)
      else:
        file = os.path.join(self.tracker_fol, tracker, self.tracker_sub_fol, seq + '.txt')

    # Load raw data from text file
    read_data, ignore_data = self._load_simple_text_file(
      str(file), is_zipped=self.data_is_zipped, zip_file=str(zip_file) if zip_file else None
    )

    # Convert data to required format
    num_timesteps = self.seq_lengths[seq]
    data_keys = ['ids', 'classes', 'dets']
    if is_gt:
      data_keys += ['gt_crowd_ignore_regions', 'gt_extras']
    else:
      data_keys += ['tracker_confidences']
    raw_data = {key: [None] * num_timesteps for key in data_keys}

    # Check for any extra time keys
    current_time_keys = [str(t + 1) for t in range(num_timesteps)]
    extra_time_keys = [x for x in read_data.keys() if x not in current_time_keys]
    if len(extra_time_keys) > 0:
      text = 'Ground-truth' if is_gt else 'Tracking'
      from trackeval.utils import TrackEvalException
      raise TrackEvalException(
        text + ' data contains the following invalid timesteps in seq %s: ' % seq + ', '.join(
          [str(x) + ', ' for x in extra_time_keys]
        )
      )

    for t in range(num_timesteps):
      time_key = str(t + 1)
      if time_key in read_data.keys():
        try:
          time_data = np.asarray(read_data[time_key], dtype=float)
        except ValueError:
          from trackeval.utils import TrackEvalException
          if is_gt:
            raise TrackEvalException(
              'Cannot convert gt data for sequence %s to float. Is data corrupted?' % seq
            )
          else:
            raise TrackEvalException(
              'Cannot convert tracking data from tracker %s, sequence %s to float. Is data corrupted?' % (tracker, seq)
            )
        try:
          # KEY DIFFERENCE: Extract 3D positions (columns 2:5) instead of 2D bounding boxes
          raw_data['dets'][t] = np.atleast_2d(time_data[:, 2:5])  # x, y, z
          raw_data['ids'][t] = np.atleast_1d(time_data[:, 1]).astype(int)
        except IndexError:
          from trackeval.utils import TrackEvalException
          if is_gt:
            err = 'Cannot load gt data from sequence %s, because there is not enough columns in the data.' % seq
            raise TrackEvalException(err)
          else:
            err = 'Cannot load tracker data from tracker %s, sequence %s, because there is not enough columns in the data.' % (tracker, seq)
            raise TrackEvalException(err)

        if time_data.shape[1] >= 8:
          raw_data['classes'][t] = np.atleast_1d(time_data[:, 7]).astype(int)
        else:
          if not is_gt:
            raw_data['classes'][t] = np.ones_like(raw_data['ids'][t])
          else:
            from trackeval.utils import TrackEvalException
            raise TrackEvalException(
              'GT data is not in a valid format, there is not enough rows in seq %s, timestep %i.' % (seq, t)
            )

        if is_gt:
          gt_extras_dict = {'zero_marked': np.atleast_1d(time_data[:, 6].astype(int))}
          raw_data['gt_extras'][t] = gt_extras_dict
        else:
          raw_data['tracker_confidences'][t] = np.atleast_1d(time_data[:, 6])
      else:
        # KEY DIFFERENCE: Empty detections are (0, 3) instead of (0, 4)
        raw_data['dets'][t] = np.empty((0, 3))
        raw_data['ids'][t] = np.empty(0).astype(int)
        raw_data['classes'][t] = np.empty(0).astype(int)
        if is_gt:
          gt_extras_dict = {'zero_marked': np.empty(0)}
          raw_data['gt_extras'][t] = gt_extras_dict
        else:
          raw_data['tracker_confidences'][t] = np.empty(0)

      if is_gt:
        # Note: crowd_ignore_regions still uses 2D format for compatibility
        # (not used in 3D point tracking evaluation)
        raw_data['gt_crowd_ignore_regions'][t] = np.empty((0, 4))

    if is_gt:
      key_map = {'ids': 'gt_ids', 'classes': 'gt_classes', 'dets': 'gt_dets'}
    else:
      key_map = {'ids': 'tracker_ids', 'classes': 'tracker_classes', 'dets': 'tracker_dets'}
    for k, v in key_map.items():
      raw_data[v] = raw_data.pop(k)
    raw_data['num_timesteps'] = num_timesteps
    raw_data['seq'] = seq
    return raw_data

  def _calculate_similarities(self, gt_dets_t, tracker_dets_t):
    """Calculate similarity scores between GT and tracker detections.

    Overrides parent to use Euclidean distance instead of IoU.

    Args:
      gt_dets_t: Ground truth detections at timestep t (Nx3 array of 3D points)
      tracker_dets_t: Tracker detections at timestep t (Mx3 array of 3D points)

    Returns:
      NxM array of similarity scores (0-1, where 1 is perfect match)
    """
    # Use Euclidean distance-based similarity with default zero_distance=2.0
    # (0.5 similarity threshold corresponds to 1m distance threshold)
    similarity_scores = self._calculate_euclidean_similarity(
      gt_dets_t, tracker_dets_t, zero_distance=2.0
    )
    return similarity_scores


class TrackEvalEvaluator(TrackerEvaluator):
  """Evaluator for tracking quality metrics using TrackEval library.

  This evaluator computes industry-standard tracking metrics such as:
  - HOTA (Higher Order Tracking Accuracy)
  - MOTA (Multiple Object Tracking Accuracy)
  - IDF1 (ID F1 Score)
  - CLEAR MOT metrics (precision, recall, etc.)

  Supported Metrics:
  - HOTA: Higher Order Tracking Accuracy and sub-metrics
  - CLEAR MOT: MOTA, MOTP, precision, recall, ID switches, etc.
  - Identity: IDF1, IDP, IDR
  - Count: number of objects, tracks, detections, etc.
  """

  # Supported metric names
  SUPPORTED_METRICS = [
    'HOTA', 'DetA', 'AssA', 'DetRe', 'DetPr', 'AssRe', 'AssPr', 'LocA',
    'MOTA', 'MOTP', 'MODA', 'CLR_Re', 'CLR_Pr', 'MTR', 'PTR', 'MLR',
    'sMOTA', 'CLR_TP', 'CLR_FN', 'CLR_FP', 'IDSW', 'MT', 'PT', 'ML',
    'Frag', 'IDF1', 'IDR', 'IDP', 'IDTP', 'IDFN', 'IDFP'
  ]

  def __init__(self):
    """Initialize TrackEvalEvaluator."""
    self._metrics: List[str] = []
    self._output_folder: Path = None
    self._processed: bool = False

    # Temporary storage for tracker outputs and ground truth
    self._temp_dir: tempfile.TemporaryDirectory = None
    self._tracker_csv_path: Path = None
    self._ground_truth_csv_path: Path = None
    self._seq_name: str = "evaluation_seq"
    self._class_name: str = "pedestrian"  # Class name used in MOTChallenge format
    self._num_frames: int = 0
    self._camera_fps: float = 30.0
    self._uuid_to_id_map: Dict[str, int] = {}

  def configure_metrics(self, metrics: List[str]) -> 'TrackEvalEvaluator':
    """Configure which metrics to evaluate.

    Args:
      metrics: List of metric names to compute (e.g., ['HOTA', 'MOTA', 'IDF1']).

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If any metric name is not supported.
    """
    # Validate metrics
    for metric in metrics:
      if metric not in self.SUPPORTED_METRICS:
        raise ValueError(
          f"Metric '{metric}' not supported. "
          f"Supported metrics: {self.SUPPORTED_METRICS}"
        )

    self._metrics = metrics
    return self

  def set_output_folder(self, path: Path) -> 'TrackEvalEvaluator':
    """Set folder where evaluation outputs should be stored.

    Args:
      path: Path to results folder. Will be created if it doesn't exist.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If path is invalid.
    """
    if not isinstance(path, Path):
      path = Path(path)

    # Create folder if it doesn't exist
    path.mkdir(parents=True, exist_ok=True)

    self._output_folder = path
    return self

  def process_tracker_outputs(
    self,
    tracker_outputs: Iterator[Dict[str, Any]],
    ground_truth: Iterator[Dict[str, Any]]
  ) -> 'TrackEvalEvaluator':
    """Process tracker outputs and ground-truth for evaluation.

    Converts tracker outputs from canonical format to MOTChallenge CSV format
    and prepares data for TrackEval evaluation.

    Args:
      tracker_outputs: Iterator of tracker output dictionaries in canonical Tracker Output Format.
      ground_truth: Iterator of ground-truth tracks in evaluator-specific format.
                   NOTE: In practice, this should be a file path (string) returned by
                   dataset.get_ground_truth(), but the base class signature requires Iterator.

    Returns:
      Self for method chaining.

    Raises:
      RuntimeError: If processing fails.
    """
    try:
      # Import conversion utilities
      sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))
      from format_converters import (
        convert_canonical_to_motchallenge_csv,
        create_motchallenge_seqinfo
      )

      # Create temporary directory for TrackEval input/output
      self._temp_dir = tempfile.TemporaryDirectory()
      temp_path = Path(self._temp_dir.name)

      # Convert tracker outputs to list for processing
      tracker_output_list = list(tracker_outputs)
      if not tracker_output_list:
        raise RuntimeError("No tracker outputs provided")

      # drop duplicated timestamps when production tracker runs metrics dataset without time-chunking
      seen_timestamps = set()
      filtered_outputs = []
      for data in tracker_output_list:
        timestamp = data.get("timestamp")
        if timestamp in seen_timestamps:
          continue
        seen_timestamps.add(timestamp)
        filtered_outputs.append(data)
      tracker_output_list = filtered_outputs

      # Calculate number of frames and FPS from timestamps
      from datetime import datetime
      timestamps = [
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        for data in tracker_output_list
      ]
      self._num_frames = len(timestamps)
      if self._num_frames > 1:
        # Calculate average FPS from timestamps
        time_span = (timestamps[-1] - timestamps[0]).total_seconds()
        self._camera_fps = (self._num_frames - 1) / time_span if time_span > 0 else 30.0
      else:
        self._camera_fps = 30.0  # Default

      # Setup directory structure for TrackEval
      # GT structure: GT_FOLDER/seq/gt/gt.txt + seqinfo.ini
      # Tracker structure: TRACKERS_FOLDER/tracker_name/data/seq.txt
      gt_seq_folder = temp_path / "gt" / self._seq_name
      gt_seq_folder.mkdir(parents=True, exist_ok=True)
      gt_folder = gt_seq_folder / "gt"
      gt_folder.mkdir(exist_ok=True)

      tracker_folder = temp_path / "trackers" / "tracker_eval"
      tracker_data_folder = tracker_folder / "data"
      tracker_data_folder.mkdir(parents=True, exist_ok=True)

      # Convert tracker outputs to MOTChallenge CSV format
      self._tracker_csv_path = tracker_data_folder / f"{self._seq_name}.txt"
      self._uuid_to_id_map = convert_canonical_to_motchallenge_csv(
        tracker_output_list,
        str(self._tracker_csv_path),
        self._camera_fps
      )

      if self._output_folder:
        mirrored_tracker_csv = self._output_folder / self._tracker_csv_path.name
        shutil.copy(self._tracker_csv_path, mirrored_tracker_csv)

      # Handle ground truth - it should be a file path string
      # but comes as iterator due to base class signature
      if isinstance(ground_truth, str):
        gt_file_path = ground_truth
      else:
        # If it's an iterator, try to get the first element (file path)
        gt_data = list(ground_truth)
        if gt_data and isinstance(gt_data[0], str):
          gt_file_path = gt_data[0]
        else:
          raise RuntimeError(
            "Ground truth must be a file path string. "
            "Ensure dataset.get_ground_truth() returns a CSV file path."
          )

      # Copy ground truth to expected location
      self._ground_truth_csv_path = gt_folder / "gt.txt"
      shutil.copy(gt_file_path, self._ground_truth_csv_path)

      # Determine actual number of frames from both tracker and ground truth
      # Read max frame from ground truth CSV
      import pandas as pd
      gt_df = pd.read_csv(self._ground_truth_csv_path, header=None, names=['frame', 'id', 'x', 'y', 'z', 'conf', 'class', 'vis'])
      max_gt_frame = int(gt_df['frame'].max()) if not gt_df.empty else self._num_frames

      # Use maximum of tracker frames and ground truth frames
      self._num_frames = max(self._num_frames, max_gt_frame)

      # Create seqinfo.ini
      create_motchallenge_seqinfo(
        self._seq_name,
        self._num_frames,
        self._camera_fps,
        gt_seq_folder
      )

      self._processed = True
      return self

    except Exception as e:
      raise RuntimeError(f"Failed to process tracker outputs: {str(e)}") from e

  def evaluate_metrics(self) -> Dict[str, float]:
    """Evaluate configured metrics.

    Runs TrackEval library to compute tracking metrics.

    Returns:
      Dictionary mapping metric names to computed values.

    Raises:
      RuntimeError: If evaluation fails or no data has been processed.
    """
    if not self._processed:
      raise RuntimeError(
        "No data has been processed. Call process_tracker_outputs() first."
      )

    if not self._metrics:
      raise RuntimeError(
        "No metrics configured. Call configure_metrics() first."
      )

    try:
      temp_path = Path(self._temp_dir.name)

      # Configure MotChallenge3DPoint dataset
      dataset_config = {
        'GT_FOLDER': str(temp_path / "gt"),
        'TRACKERS_FOLDER': str(temp_path / "trackers"),
        'OUTPUT_FOLDER': str(self._output_folder) if self._output_folder else str(temp_path / "results"),
        'TRACKERS_TO_EVAL': ['tracker_eval'],
        'CLASSES_TO_EVAL': ['pedestrian'],
        'BENCHMARK': 'MOT17',  # Use MOT17 format (generic)
        'SPLIT_TO_EVAL': 'train',
        'SEQ_INFO': {self._seq_name: self._num_frames},  # Direct sequence specification
        'DO_PREPROC': False,  # Data already preprocessed by our pipeline
        'TRACKER_SUB_FOLDER': 'data',
        'OUTPUT_SUB_FOLDER': '',
        'SKIP_SPLIT_FOL': True,  # Don't expect benchmark-split folder structure
        'PRINT_CONFIG': False
      }

      # Create dataset instance
      dataset = MotChallenge3DPoint(dataset_config)

      # Determine which metric classes to instantiate
      metrics_list = []
      metric_class_map = {
        'HOTA': HOTA,
        'CLEAR': CLEAR,
        'Identity': Identity,
        'Count': Count
      }

      # Map requested metrics to metric classes
      metrics_to_instantiate = set()
      for metric_name in self._metrics:
        if metric_name in ['HOTA', 'DetA', 'AssA', 'DetRe', 'DetPr', 'AssRe', 'AssPr', 'LocA']:
          metrics_to_instantiate.add('HOTA')
        elif metric_name in ['MOTA', 'MOTP', 'MODA', 'CLR_Re', 'CLR_Pr', 'MTR', 'PTR', 'MLR',
                             'sMOTA', 'CLR_TP', 'CLR_FN', 'CLR_FP', 'IDSW', 'MT', 'PT', 'ML', 'Frag']:
          metrics_to_instantiate.add('CLEAR')
        elif metric_name in ['IDF1', 'IDR', 'IDP', 'IDTP', 'IDFN', 'IDFP']:
          metrics_to_instantiate.add('Identity')
        else:
          metrics_to_instantiate.add('Count')

      # Instantiate metric classes
      for metric_class_name in metrics_to_instantiate:
        if metric_class_name in metric_class_map:
          metrics_list.append(metric_class_map[metric_class_name]())

      # Configure evaluator
      eval_config = {
        'USE_PARALLEL': False,
        'NUM_PARALLEL_CORES': 1,
        'BREAK_ON_ERROR': True,
        'RETURN_ON_ERROR': False,
        'LOG_ON_ERROR': str(temp_path / 'error.log'),
        'PRINT_RESULTS': False,
        'PRINT_ONLY_COMBINED': True,
        'PRINT_CONFIG': False,
        'TIME_PROGRESS': False,
        'DISPLAY_LESS_PROGRESS': True,
        'OUTPUT_SUMMARY': True,
        'OUTPUT_EMPTY_CLASSES': True,
        'OUTPUT_DETAILED': True,
        'PLOT_CURVES': False
      }

      # Run evaluation
      evaluator = Evaluator(eval_config)
      output_res, output_msg = evaluator.evaluate(
        [dataset],
        metrics_list
      )

      # Extract requested metrics from results
      results = {}
      # TrackEval output structure: output_res[dataset_name][tracker_name][seq_name][metric_name]
      dataset_name = dataset.get_name()
      tracker_name = 'tracker_eval'

      if (dataset_name in output_res and
          tracker_name in output_res[dataset_name] and
          self._seq_name in output_res[dataset_name][tracker_name]):

        seq_results = output_res[dataset_name][tracker_name][self._seq_name]

        # Results are nested under class name, then metric class
        if self._class_name in seq_results:
          class_results = seq_results[self._class_name]

          for metric_name in self._metrics:
            # Search for metric in all metric class results
            found = False
            for metric_class_name, metric_class_results in class_results.items():
              if isinstance(metric_class_results, dict) and metric_name in metric_class_results:
                value = metric_class_results[metric_name]
                # Handle array results (e.g., HOTA at different thresholds)
                if isinstance(value, np.ndarray):
                  # Use mean value across thresholds
                  results[metric_name] = float(np.mean(value))
                else:
                  results[metric_name] = float(value)
                found = True
                break

            if not found:
              # Metric not found in results
              results[metric_name] = 0.0

      return results

    except Exception as e:
      raise RuntimeError(f"Failed to evaluate metrics: {str(e)}") from e

  def reset(self) -> 'TrackEvalEvaluator':
    """Reset evaluator state to initial configuration.

    Returns:
      Self for method chaining.
    """
    self._metrics = []
    self._output_folder = None
    self._processed = False

    # Clean up temporary directory
    if self._temp_dir is not None:
      self._temp_dir.cleanup()
      self._temp_dir = None

    self._tracker_csv_path = None
    self._ground_truth_csv_path = None
    self._seq_name = "evaluation_seq"
    self._num_frames = 0
    self._camera_fps = 30.0
    self._uuid_to_id_map = {}

    return self
