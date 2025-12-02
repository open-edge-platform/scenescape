# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import uuid
import time
import numpy as np
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
from scene_common import log
from abc import ABC, abstractmethod
from scipy.optimize import linear_sum_assignment

class ClusterState:
  """Finite State Machine states for cluster lifecycle tracking"""
  NEW = 'new'              # Just detected, awaiting confirmation
  ACTIVE = 'active'        # Confirmed and consistently detected
  STABLE = 'stable'        # Long-term stable presence
  FADING = 'fading'        # Recently missed detections
  LOST = 'lost'            # Not detected for extended period

@dataclass
class ClusterHistory:
  """Historical observations for temporal analysis"""
  positions: List[Tuple[float, float, float]] = field(default_factory=list)  # [(x, y, timestamp)]
  velocities: List[Tuple[float, float, float]] = field(default_factory=list)  # [(vx, vy, timestamp)]
  sizes: List[int] = field(default_factory=list)
  shapes: List[str] = field(default_factory=list)
  timestamps: List[float] = field(default_factory=list)

  MAX_HISTORY_SIZE = 100

  def addObservation(self, position: Tuple[float, float], velocity: Tuple[float, float],
                                      size: int, shape: str, timestamp: float) -> None:
    """Add new observation and maintain history size limit"""
    self.positions.append((*position, timestamp))
    self.velocities.append((*velocity, timestamp))
    self.sizes.append(size)
    self.shapes.append(shape)
    self.timestamps.append(timestamp)

    # Trim to maximum size
    if len(self.timestamps) > self.MAX_HISTORY_SIZE:
      self.positions = self.positions[-self.MAX_HISTORY_SIZE:]
      self.velocities = self.velocities[-self.MAX_HISTORY_SIZE:]
      self.sizes = self.sizes[-self.MAX_HISTORY_SIZE:]
      self.shapes = self.shapes[-self.MAX_HISTORY_SIZE:]
      self.timestamps = self.timestamps[-self.MAX_HISTORY_SIZE:]
    return

class TrackedCluster:
  """
  Represents a cluster being tracked across video frames.

  Responsibilities:
  - Maintain cluster state (NEW -> ACTIVE -> STABLE -> FADING -> LOST)
  - Track confidence metrics and position/velocity
  - Maintain observation history
  - Predict future positions for matching
  """

  def __init__(self, scene_id: str, category: str, centroid: Dict[str, float],
           shape_analysis: Dict, velocity_analysis: Dict, object_ids: List[str],
           dbscan_params: Dict, detection_timestamp: float) -> None:
    """Initialize a new tracked cluster"""
    # Hardcoded cluster tracking parameters
    # State transitions
    self.FRAMES_TO_ACTIVATE = 3
    self.FRAMES_TO_STABLE = 20
    self.FRAMES_TO_FADE = 15
    self.FRAMES_TO_LOST = 10

    # Confidence
    self.INITIAL_CONFIDENCE = 0.5
    self.ACTIVATION_THRESHOLD = 0.6
    self.STABILITY_THRESHOLD = 0.7
    self.CONFIDENCE_MISS_PENALTY = 0.1
    self.CONFIDENCE_MAX_MISS_PENALTY = 0.5
    self.CONFIDENCE_LONGEVITY_BONUS_MAX = 0.2
    self.CONFIDENCE_LONGEVITY_FRAMES = 100

    # Identity
    self.uuid = str(uuid.uuid4())
    self.scene_id = scene_id
    self.category = category

    # Current state
    self.state = ClusterState.NEW
    self.centroid = centroid
    self.shape_analysis = shape_analysis
    self.velocity_analysis = velocity_analysis
    self.object_ids = object_ids
    self.object_count = len(object_ids)
    self.dbscan_params = dbscan_params

    # Temporal tracking
    self.first_seen = detection_timestamp
    self.last_seen = detection_timestamp
    self.last_updated = detection_timestamp
    self.frames_detected = 1
    self.frames_missed = 0
    self.total_frames = 1

    # Historical data
    self.history = ClusterHistory()
    self.history.addObservation(
            position=(centroid['x'], centroid['y']),
            velocity=tuple(velocity_analysis['average_velocity'][:2]),
            size=self.object_count,
            shape=shape_analysis['shape'],
            timestamp=detection_timestamp
    )

    # Computed metrics
    self.confidence = self.INITIAL_CONFIDENCE  # Use config-based initial confidence
    self.stability_score = 0.0
    self.predicted_position: Optional[Tuple[float, float]] = None
    self.predicted_velocity: Optional[Tuple[float, float]] = None

    self._updatePrediction()
    return

  def update(self, centroid: Dict[str, float], shape_analysis: Dict,
                      velocity_analysis: Dict, object_ids: List[str], detection_timestamp: float) -> None:
    """Update cluster with new detection"""
    old_state = self.state

    # Update current data
    self.centroid = centroid
    self.shape_analysis = shape_analysis
    self.velocity_analysis = velocity_analysis
    self.object_ids = object_ids
    self.object_count = len(object_ids)
    self.last_seen = detection_timestamp
    self.last_updated = detection_timestamp
    self.frames_detected += 1
    self.total_frames += 1
    self.frames_missed = 0

    # Update history
    self.history.addObservation(
            position=(centroid['x'], centroid['y']),
            velocity=tuple(velocity_analysis['average_velocity'][:2]),
            size=self.object_count,
            shape=shape_analysis['shape'],
            timestamp=detection_timestamp
    )

    # Recalculate metrics
    self._updateConfidence()
    self._updateStabilityScore()
    self._updateState()
    self._updatePrediction()

    if old_state != self.state:
      log.debug(f"Cluster {self.uuid} state transition: {old_state} -> {self.state}")
    return

  def markMissed(self, current_timestamp: float) -> None:
    """Mark cluster as not detected in current frame"""
    old_state = self.state

    self.frames_missed += 1
    self.total_frames += 1
    self.last_updated = current_timestamp

    self._updateConfidence()
    self._updateState()

    if old_state != self.state:
      log.debug(f"Cluster {self.uuid} state transition: {old_state} -> {self.state} (missed {self.frames_missed} frames)")
    return

  def _updateConfidence(self) -> None:
    """Calculate tracking confidence based on detection consistency"""
    detection_ratio = self.frames_detected / max(self.total_frames, 1)

    # Base confidence from detection ratio
    base_confidence = detection_ratio

    # Penalty for recent misses
    miss_penalty = min(self.frames_missed * self.CONFIDENCE_MISS_PENALTY, self.CONFIDENCE_MAX_MISS_PENALTY)

    # Bonus for long-term tracking
    longevity_bonus = min(
            self.frames_detected / self.CONFIDENCE_LONGEVITY_FRAMES,
            self.CONFIDENCE_LONGEVITY_BONUS_MAX
    )

    self.confidence = max(0.0, min(1.0, base_confidence - miss_penalty + longevity_bonus))
    return

  def _updateStabilityScore(self) -> None:
    """Calculate cluster stability based on historical variance"""
    if len(self.history.positions) < 3:
      self.stability_score = 0.0
      return

    # Analyze recent history (last 10 observations)
    recent_positions = self.history.positions[-10:]
    recent_sizes = self.history.sizes[-10:]
    recent_shapes = self.history.shapes[-10:]

    # Position stability (low variance = high stability)
    positions_array = np.array([(p[0], p[1]) for p in recent_positions])
    position_variance = np.mean(np.var(positions_array, axis=0))
    position_stability = 1.0 / (1.0 + position_variance)

    # Size stability
    size_variance = np.var(recent_sizes)
    size_stability = 1.0 / (1.0 + size_variance)

    # Shape consistency
    most_common_shape = max(set(recent_shapes), key=recent_shapes.count)
    shape_consistency = recent_shapes.count(most_common_shape) / len(recent_shapes)

    # Weighted combination
    self.stability_score = (
            0.4 * position_stability
            + 0.3 * size_stability
            + 0.3 * shape_consistency
    )
    return

  def _updateState(self) -> None:
    """Update cluster state based on tracking history (FSM)"""
    if self.state == ClusterState.NEW:
      if self.frames_detected >= self.FRAMES_TO_ACTIVATE and self.confidence > self.ACTIVATION_THRESHOLD:
        self.state = ClusterState.ACTIVE
    elif self.state == ClusterState.ACTIVE:
      if self.frames_detected >= self.FRAMES_TO_STABLE and self.stability_score > self.STABILITY_THRESHOLD:
        self.state = ClusterState.STABLE
      elif self.frames_missed >= self.FRAMES_TO_FADE:
        self.state = ClusterState.FADING
    elif self.state == ClusterState.STABLE:
      if self.frames_missed >= self.FRAMES_TO_FADE:
        self.state = ClusterState.FADING
    elif self.state == ClusterState.FADING:
      if self.frames_missed >= self.FRAMES_TO_LOST:
        self.state = ClusterState.LOST
      elif self.frames_missed == 0:  # Redetected
        self.state = ClusterState.ACTIVE
    return

  def _updatePrediction(self) -> None:
    """Predict next position using linear extrapolation"""
    if len(self.history.positions) < 2:
      self.predicted_position = (self.centroid['x'], self.centroid['y'])
      self.predicted_velocity = tuple(self.velocity_analysis['average_velocity'][:2])
      return

    # Use recent observations for prediction
    recent_velocities = self.history.velocities[-5:]
    avg_velocity = np.mean([v[:2] for v in recent_velocities], axis=0)

    current_pos = (self.centroid['x'], self.centroid['y'])

    # Predict next position (assuming time delta ~= 1 frame)
    self.predicted_position = (
            current_pos[0] + avg_velocity[0],
            current_pos[1] + avg_velocity[1]
    )
    self.predicted_velocity = tuple(avg_velocity)
    return

  def getAgeSeconds(self, current_time: Optional[float]) -> float:
    """Get cluster age in seconds"""
    if current_time is None:
      return float('inf')  # Return large value if no timestamp provided
    return current_time - self.first_seen

  def getTimeSinceLastSeen(self, current_time: Optional[float]) -> float:
    """Get time since last detection in seconds"""
    if current_time is None:
      return float('inf')  # Return large value if no timestamp provided
    return current_time - self.last_seen

  def shouldBeArchived(self, current_time: Optional[float], max_time_lost: float = 30.0) -> bool:
    """Determine if cluster should be archived"""
    return (self.state == ClusterState.LOST
                    and self.getTimeSinceLastSeen(current_time) > max_time_lost)

  def toDict(self) -> Dict:
    """Convert to dictionary for MQTT publishing"""
    return {
            'id': self.uuid,
            'category': self.category,
            'objects_count': self.object_count,
            'center_of_mass': self.centroid,
            'shape_analysis': self.shape_analysis,
            'velocity_analysis': self.velocity_analysis,
            'object_ids': self.object_ids,
            'dbscan_params': self.dbscan_params,
            'tracking': {
                    'tracking_id': self.uuid,
                    'state': self.state,
                    'confidence': round(self.confidence, 3),
                    'stability_score': round(self.stability_score, 3),
                    'frames_detected': self.frames_detected,
                    'frames_missed': self.frames_missed,
                    'age_seconds': round(self.last_updated - (self.first_seen or self.last_updated), 2),
                    'time_since_last_seen': round(time.time() - self.last_seen, 2),
                    'first_seen': self.first_seen,
                    'last_seen': self.last_seen,
                    'predicted_position': {
                            'x': self.predicted_position[0] if self.predicted_position else None,
                            'y': self.predicted_position[1] if self.predicted_position else None
                    }
            }
    }

class ClusterMemory:
  """
  Repository for storing and managing tracked clusters.

  Responsibilities:
  - Store active clusters in memory
  - Archive old/lost clusters
  - Provide query operations (by scene, category, state)
  - Manage cleanup and lifecycle
  """

  MAX_ACTIVE_CLUSTERS = 10
  MAX_ARCHIVED_CLUSTERS = 50

  def __init__(self, config=None) -> None:
    # Hardcoded archival parameter
    self.ARCHIVE_TIME_THRESHOLD = 5.0

    # Primary storage
    self._active_clusters: Dict[str, TrackedCluster] = {}
    self._archived_clusters: Dict[str, TrackedCluster] = {}

    # Indexes for fast lookup
    self._clusters_by_scene: Dict[str, List[str]] = defaultdict(list)
    self._clusters_by_category: Dict[str, List[str]] = defaultdict(list)
    return

  def add(self, cluster: TrackedCluster) -> None:
    """Add new cluster to active tracking"""
    self._active_clusters[cluster.uuid] = cluster

    # Update indexes
    self._clusters_by_scene[cluster.scene_id].append(cluster.uuid)
    self._clusters_by_category[cluster.category].append(cluster.uuid)

    log.debug(f"Added cluster {cluster.uuid} to memory (scene: {cluster.scene_id}, category: {cluster.category})")
    return

  def get(self, cluster_uuid: str) -> Optional[TrackedCluster]:
    """Retrieve cluster by UUID"""
    return self._active_clusters.get(cluster_uuid)

  def getClustersByScene(self, scene_id: str) -> List[TrackedCluster]:
    """Get all active clusters for a scene"""
    cluster_uuids = self._clusters_by_scene.get(scene_id, [])
    return [self._active_clusters[uuid] for uuid in cluster_uuids
                    if uuid in self._active_clusters]

  def getClustersByCategory(self, category: str, scene_id: Optional[str] = None) -> List[TrackedCluster]:
    """Get clusters by category, optionally filtered by scene"""
    if scene_id:
      scene_clusters = self.getClustersByScene(scene_id)
      return [c for c in scene_clusters if c.category == category]
    else:
      cluster_uuids = self._clusters_by_category.get(category, [])
      return [self._active_clusters[uuid] for uuid in cluster_uuids
                      if uuid in self._active_clusters]

  def getClustersByState(self, state: str) -> List[TrackedCluster]:
    """Get all clusters in a specific state"""
    return [c for c in self._active_clusters.values() if c.state == state]

  def archive(self, cluster_uuid: str) -> None:
    """Move cluster from active to archive"""
    if cluster_uuid in self._active_clusters:
      cluster = self._active_clusters.pop(cluster_uuid)
      self._archived_clusters[cluster_uuid] = cluster

      # Remove from indexes
      if cluster.scene_id in self._clusters_by_scene:
        if cluster_uuid in self._clusters_by_scene[cluster.scene_id]:
          self._clusters_by_scene[cluster.scene_id].remove(cluster_uuid)
      if cluster.category in self._clusters_by_category:
        if cluster_uuid in self._clusters_by_category[cluster.category]:
          self._clusters_by_category[cluster.category].remove(cluster_uuid)

      log.debug(f"Archived cluster {cluster_uuid} (state: {cluster.state}, lifetime: {cluster.frames_detected} frames)")
    return

  def cleanupOldClusters(self, current_time: Optional[float]) -> None:
    """Archive lost clusters and limit archive size"""
    to_archive = []

    # Find clusters to archive
    for cluster_uuid, cluster in self._active_clusters.items():
      if cluster.shouldBeArchived(current_time, self.ARCHIVE_TIME_THRESHOLD):
        to_archive.append(cluster_uuid)

    # Archive them
    for cluster_uuid in to_archive:
      self.archive(cluster_uuid)

    # Limit archive size (remove oldest)
    if len(self._archived_clusters) > self.MAX_ARCHIVED_CLUSTERS:
      sorted_archived = sorted(
              self._archived_clusters.items(),
              key=lambda x: x[1].last_seen
      )
      to_remove = len(self._archived_clusters) - self.MAX_ARCHIVED_CLUSTERS
      for cluster_uuid, _ in sorted_archived[:to_remove]:
        del self._archived_clusters[cluster_uuid]
        log.debug(f"Removed old archived cluster {cluster_uuid}")
    return

  def forceClearClustersByCategory(self, scene_id: str, category: str) -> int:
    """Force-clear all clusters for a specific scene and category.

    This is useful when clustering parameters change significantly and
    existing clusters are no longer valid.

    @param scene_id: Scene identifier
    @param category: Object category to clear
    @return: Number of clusters cleared
    """
    cleared_count = 0
    clusters_to_archive = []

    # Find clusters matching scene and category
    for cluster_uuid, cluster in self._active_clusters.items():
      if cluster.scene_id == scene_id and cluster.category == category:
        clusters_to_archive.append(cluster_uuid)

    # Archive all matching clusters
    for cluster_uuid in clusters_to_archive:
      cluster = self._active_clusters.get(cluster_uuid)
      if cluster:
        # Force state to LOST to ensure immediate removal
        cluster.state = ClusterState.LOST
        self.archive(cluster_uuid)
        cleared_count += 1

    if cleared_count > 0:
      log.info(f"Cleared {cleared_count} clusters due to parameter change")
      log.debug(f"Scene: {scene_id}, Category: {category}")

    return cleared_count

  def getStatistics(self) -> Dict:
    """Get memory statistics for monitoring"""
    state_counts = {}
    for state in [ClusterState.NEW, ClusterState.ACTIVE, ClusterState.STABLE,
         ClusterState.FADING, ClusterState.LOST]:
      state_counts[state] = len(self.getClustersByState(state))

    return {
            'active_clusters': len(self._active_clusters),
            'archived_clusters': len(self._archived_clusters),
            'clusters_by_state': state_counts,
            'tracked_scenes': len([s for s in self._clusters_by_scene.values() if s]),
            'tracked_categories': len([c for c in self._clusters_by_category.values() if c])
    }

class ClusterMatcher(ABC):
  """Abstract base class for cluster matching strategies"""

  @abstractmethod
  def match(self, existing_clusters: List[TrackedCluster],
       new_detections: List[Dict]) -> List[Tuple[str, int, float]]:
    """
    Match new detections to existing clusters.

    @param existing_clusters: List of TrackedCluster objects
    @param new_detections: List of detection dictionaries
    @return: List of (cluster_uuid, detection_index, similarity_score) tuples
    """
    pass

class HungarianMatcher(ClusterMatcher):
  """
  Hungarian algorithm matcher for optimal cluster assignment.
  Uses multi-feature cost matrix (position, velocity, size, shape).
  """

  # Configuration constants
  MAX_MATCHING_DISTANCE = 5.0  # Maximum distance for valid match
  POSITION_WEIGHT = 0.4
  VELOCITY_WEIGHT = 0.3
  SIZE_WEIGHT = 0.2
  SHAPE_WEIGHT = 0.1

  def __init__(self, max_distance: Optional[float] = None) -> None:
    """Initialize matcher with optional custom max distance"""
    self.max_distance = max_distance or self.MAX_MATCHING_DISTANCE
    return

  def match(self, existing_clusters: List[TrackedCluster],
       new_detections: List[Dict]) -> List[Tuple[str, int, float]]:
    """Match using Hungarian algorithm with multi-feature cost matrix"""
    if not existing_clusters or not new_detections:
      return []

    # Build cost matrix
    cost_matrix = self._buildCostMatrix(existing_clusters, new_detections)

    # Solve assignment problem
    row_indices, col_indices = linear_sum_assignment(cost_matrix)

    # Filter matches by threshold and return valid matches
    matches = []
    for row_idx, col_idx in zip(row_indices, col_indices):
      cost = cost_matrix[row_idx, col_idx]
      if cost < self.max_distance:
        similarity = 1.0 - (cost / self.max_distance)
        matches.append((
                existing_clusters[row_idx].uuid,
                col_idx,
                similarity
        ))

    return matches

  def _buildCostMatrix(self, existing_clusters: List[TrackedCluster],
                                          new_detections: List[Dict]) -> np.ndarray:
    """Build cost matrix for Hungarian algorithm"""
    cost_matrix = np.zeros((len(existing_clusters), len(new_detections)))

    for i, tracked in enumerate(existing_clusters):
      for j, detection in enumerate(new_detections):
        cost = self._calculateMatchingCost(tracked, detection)
        cost_matrix[i, j] = cost

    return cost_matrix

  def _calculateMatchingCost(self, tracked: TrackedCluster, detection: Dict) -> float:
    """Calculate matching cost between tracked cluster and new detection"""
    # Hard constraint: must be same category
    if tracked.category != detection.get('category'):
      return float('inf')

    # Position cost (use prediction if available)
    predicted_pos = tracked.predicted_position or (
            tracked.centroid['x'], tracked.centroid['y']
    )
    detection_pos = (
            detection['center_of_mass']['x'],
            detection['center_of_mass']['y']
    )
    position_distance = np.linalg.norm(
            np.array(predicted_pos) - np.array(detection_pos)
    )
    position_cost = position_distance * self.POSITION_WEIGHT

    # Velocity cost
    tracked_vel = np.array(tracked.velocity_analysis['average_velocity'][:2])
    detection_vel = np.array(detection['velocity_analysis']['average_velocity'][:2])
    velocity_distance = np.linalg.norm(tracked_vel - detection_vel)
    velocity_cost = velocity_distance * self.VELOCITY_WEIGHT

    # Size cost
    size_diff = abs(tracked.object_count - detection['objects_count'])
    size_cost = size_diff * self.SIZE_WEIGHT

    # Shape cost (binary: match or no match)
    shape_match = (tracked.shape_analysis['shape']
                                == detection['shape_analysis']['shape'])
    shape_cost = (1.0 if shape_match else 2.0) * self.SHAPE_WEIGHT

    total_cost = position_cost + velocity_cost + size_cost + shape_cost
    return total_cost

class ClusterTracker:
  """
  Main coordinator for cluster tracking operations.

  Responsibilities:
  - Orchestrate cluster lifecycle (create, update, archive)
  - Match new detections to existing clusters
  - Manage cluster memory and cleanup
  - Provide query interface for active clusters
  """

  def __init__(self, matcher: Optional[ClusterMatcher] = None, config=None) -> None:
    """Initialize tracker with memory and matching strategy"""
    self.config = config
    self.memory = ClusterMemory(config=config)
    self.matcher = matcher or HungarianMatcher()
    return

  def processNewDetections(self, scene_id: str, new_cluster_detections: List[Dict],
                                                  timestamp: float) -> None:
    """
    Process new cluster detections and update tracking state.

    @param scene_id: Scene identifier
    @param new_cluster_detections: List of cluster detection dictionaries
    @param timestamp: Detection timestamp
    """
    # Group detections by category
    detections_by_category = self._groupByCategory(new_cluster_detections)

    # Process each category separately
    for category, category_detections in detections_by_category.items():
      self._processCategoryDetections(
              scene_id, category, category_detections, timestamp
      )

    self._validateAllClustersInScene(scene_id, timestamp)

    # Cleanup old clusters
    self.memory.cleanupOldClusters(timestamp)
    return

  def _groupByCategory(self, detections: List[Dict]) -> Dict[str, List[Dict]]:
    """Group detections by category"""
    grouped = defaultdict(list)
    for detection in detections:
      category = detection.get('category', 'unknown')
      grouped[category].append(detection)
    return dict(grouped)

  def _validateAllClustersInScene(self, scene_id: str, timestamp: float) -> None:
    """
    Validate all clusters in a scene and mark as missed if not recently updated.

    This is the SIMPLEST and most robust approach - check every cluster
    regardless of whether detections were found.

    @param scene_id: Scene identifier
    @param timestamp: Current processing timestamp
    """
    all_scene_clusters = self.memory.getClustersByScene(scene_id)
    missed_count = 0

    for cluster in all_scene_clusters:
      # Skip already LOST clusters
      if cluster.state == ClusterState.LOST:
        continue

      # If cluster wasn't updated this frame (last_updated < current timestamp)
      # then mark it as missed
      if cluster.last_updated < timestamp:
        cluster.markMissed(timestamp)
        missed_count += 1
        log.debug(f"Cluster {cluster.uuid} marked as missed (not updated this frame)")

    if missed_count > 0:
      log.debug(f"Marked {missed_count} clusters as missed in scene {scene_id}")
    return

  def _processCategoryDetections(self, scene_id: str, category: str,
                             detections: List[Dict], timestamp: float) -> None:
    """Process detections for a specific category"""
    # Get existing trackable clusters for this scene and category
    existing_clusters = self.memory.getClustersByCategory(category, scene_id)
    trackable_clusters = [
            c for c in existing_clusters
            if c.state in [ClusterState.NEW, ClusterState.ACTIVE,
                                        ClusterState.STABLE, ClusterState.FADING]
    ]

    # Match detections to existing clusters
    matches = self.matcher.match(trackable_clusters, detections)

    # Track which clusters and detections were matched
    matched_cluster_uuids: Set[str] = set()
    matched_detection_indices: Set[int] = set()

    # Update matched clusters
    for cluster_uuid, detection_idx, similarity in matches:
      cluster = self.memory.get(cluster_uuid)
      if cluster:
        detection = detections[detection_idx]
        cluster.update(
                centroid=detection['center_of_mass'],
                shape_analysis=detection['shape_analysis'],
                velocity_analysis=detection['velocity_analysis'],
                object_ids=detection['object_ids'],
                detection_timestamp=timestamp
        )
        matched_cluster_uuids.add(cluster_uuid)
        matched_detection_indices.add(detection_idx)
        log.debug(f"Updated cluster {cluster_uuid} (similarity: {similarity:.3f})")

    # Create new clusters for unmatched detections
    for idx, detection in enumerate(detections):
      if idx not in matched_detection_indices:
        new_cluster = self._createTrackedCluster(
                scene_id, detection, timestamp
        )
        self.memory.add(new_cluster)
        log.debug(f"Created new cluster {new_cluster.uuid} "
                        f"(scene: {scene_id}, category: {category})")

    # Mark unmatched existing clusters as missed
    for cluster in trackable_clusters:
      if cluster.uuid not in matched_cluster_uuids:
        cluster.markMissed(timestamp)
    return

  def _createTrackedCluster(self, scene_id: str, detection: Dict,
                       timestamp: float) -> TrackedCluster:
    """Create new TrackedCluster from detection data"""
    return TrackedCluster(
            scene_id=scene_id,
            category=detection['category'],
            centroid=detection['center_of_mass'],
            shape_analysis=detection['shape_analysis'],
            velocity_analysis=detection['velocity_analysis'],
            object_ids=detection['object_ids'],
            dbscan_params=detection['dbscan_params'],
            detection_timestamp=timestamp
    )

  def getActiveClusters(self, scene_id: Optional[str] = None,
                   publishable_only: bool = True) -> List[TrackedCluster]:
    """
    Get active clusters for publishing.

    @param scene_id: Optional scene filter
    @param publishable_only: If True, return only ACTIVE, STABLE, and FADING clusters
    @return: List of TrackedCluster objects
    """
    if scene_id:
      clusters = self.memory.getClustersByScene(scene_id)
    else:
      clusters = list(self.memory._active_clusters.values())

    # Filter by state and minimum cluster size
    filtered_clusters = []
    for c in clusters:
      # Never include LOST clusters in visualization
      if c.state == ClusterState.LOST:
        log.debug(f"Excluding LOST cluster {c.uuid} from visualization")
        continue

      # Check state filter for publishable clusters
      if publishable_only and c.state not in [ClusterState.ACTIVE, ClusterState.STABLE, ClusterState.FADING]:
        log.debug(f"Excluding {c.state} cluster {c.uuid} from publication (publishable_only=True)")
        continue

      filtered_clusters.append(c)

    return filtered_clusters

  def forceClearClustersByCategory(self, scene_id: str, category: str) -> int:
    """Force-clear all clusters for a specific scene and category."""
    return self.memory.forceClearClustersByCategory(scene_id, category)

  def getStatistics(self) -> Dict:
    """Get tracking statistics for monitoring"""
    return self.memory.getStatistics()
