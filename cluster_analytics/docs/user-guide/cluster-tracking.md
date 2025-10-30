# Cluster Tracking System - Intel® SceneScape

## Overview

The Cluster Tracking System provides temporal continuity for clusters detected across video frames. By maintaining persistent cluster identities, the system enables long-term behavioral analysis, trend detection, and lifecycle management.

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Cluster Tracker                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           ClusterMemory (Repository)                 │   │
│  │  • Active Clusters (UUID → TrackedCluster)           │   │
│  │  • Archived Clusters (UUID → TrackedCluster)         │   │
│  │  • Indexes (Scene, Category lookups)                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │        HungarianMatcher (Strategy)                   │   │
│  │  • Build Cost Matrix (Position, Velocity, Size)      │   │
│  │  • Optimal Assignment Algorithm                      │   │
│  │  • Similarity Scoring                                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          TrackedCluster (Entity)                     │   │
│  │  • State Machine (NEW/ACTIVE/STABLE/FADING/LOST)     │   │
│  │  • Confidence & Stability Metrics                    │   │
│  │  • History Management (100 observations)             │   │
│  │  • Prediction System                                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Frame N Detection
       ↓
1. Group by Category
       ↓
2. Retrieve Existing Clusters (by scene + category)
       ↓
3. Hungarian Matching (cost matrix optimization)
       ↓
4. Process Matches:
   ├─→ Update Matched Clusters
   │   ├─→ Update position, shape, velocity
   │   ├─→ Recalculate confidence
   │   ├─→ Update state machine
   │   └─→ Add to history
   │
   ├─→ Create New Clusters (unmatched detections)
   │   └─→ Initialize with NEW state
   │
   └─→ Mark Missed Clusters
       ├─→ Increment frames_missed
       ├─→ Reduce confidence
       └─→ Update state (possibly → FADING → LOST)
       ↓
5. Cleanup & Archive
   └─→ Archive LOST clusters after threshold
```

## State Machine

### States and Transitions

```{mermaid}
stateDiagram-v2
    [*] --> NEW: First Detection

    NEW --> ACTIVE: Conditions:<br/>• frames_detected ≥ 3<br/>• confidence > 0.6

    ACTIVE --> STABLE: Conditions:<br/>• frames_detected ≥ 20<br/>• stability_score > 0.7

    ACTIVE --> FADING: Condition:<br/>• frames_missed ≥ 5

    STABLE --> FADING: Condition:<br/>• frames_missed ≥ 5

    FADING --> ACTIVE: Condition:<br/>• Re-detected (frames_missed = 0)

    FADING --> LOST: Condition:<br/>• frames_missed ≥ 10

    LOST --> [*]: Archive after:<br/>• time_since_last_seen > 5.0s
```

### State Characteristics

| State  | Description                       | Publishable | Typical Duration |
| ------ | --------------------------------- | ----------- | ---------------- |
| NEW    | Just detected, unconfirmed        | No          | 1-3 frames       |
| ACTIVE | Confirmed, consistently detected  | Yes         | Variable         |
| STABLE | Long-term stable presence         | Yes         | Extended         |
| FADING | Temporarily lost, may reappear    | Yes         | 1-10 frames      |
| LOST   | Extended absence, pending archive | No          | Until archived   |

### Configuration Parameters

```json
{
  "cluster_tracking": {
    "state_transitions": {
      "frames_to_activate": 3,
      "frames_to_stable": 20,
      "frames_to_fade": 5,
      "frames_to_lost": 10
    }
  }
}
```

## Confidence Scoring

### Calculation Components

**1. Detection Ratio (Base Confidence)**

```python
detection_ratio = frames_detected / total_frames
```

- Measures overall detection consistency
- Range: 0.0 to 1.0
- Higher values indicate reliable tracking

**2. Miss Penalty**

```python
miss_penalty = min(frames_missed × 0.1, 0.5)
```

- Reduces confidence for recent detection failures
- Capped at 0.5 to allow recovery
- Linearly increases with consecutive misses

**3. Longevity Bonus**

```python
longevity_bonus = min(frames_detected / 100, 0.2)
```

- Rewards long-term stable tracking
- Maximum bonus: 0.2
- Reaches maximum at 100 detected frames

**4. Final Confidence**

```python
confidence = clamp(
    detection_ratio - miss_penalty + longevity_bonus,
    0.0,
    1.0
)
```

### Configuration

```json
{
  "cluster_tracking": {
    "confidence": {
      "initial_confidence": 0.5,
      "activation_threshold": 0.6,
      "stability_threshold": 0.7,
      "miss_penalty": 0.1,
      "max_miss_penalty": 0.5,
      "longevity_bonus_max": 0.2,
      "longevity_frames": 100
    }
  }
}
```

### Example Confidence Evolution

```
Frame    Detected    frames_detected    frames_missed    Confidence
-----    --------    ---------------    -------------    ----------
  1         ✓              1                  0            0.50
  2         ✓              2                  0            0.52
  3         ✓              3                  0            0.56
  4         ✗              3                  1            0.46
  5         ✗              3                  2            0.36
  6         ✓              4                  0            0.51
 10         ✓              8                  0            0.68
 20         ✓             18                  0            0.88
100         ✓             98                  0            1.00 (max)
```

## Stability Scoring

### Components

**1. Position Stability**

```python
position_variance = variance(recent_positions)  # Last 10 observations
position_stability = 1.0 / (1.0 + position_variance)
```

- Low variance = high stability
- Indicates stationary or smooth movement

**2. Size Stability**

```python
size_variance = variance(recent_sizes)
size_stability = 1.0 / (1.0 + size_variance)
```

- Consistent object count over time
- Indicates stable cluster membership

**3. Shape Consistency**

```python
most_common_shape = mode(recent_shapes)
shape_consistency = count(most_common_shape) / total_observations
```

- Frequency of dominant shape
- Range: 0.0 to 1.0

**4. Combined Score**

```python
stability_score = (
    0.4 × position_stability +
    0.3 × size_stability +
    0.3 × shape_consistency
)
```

### Interpretation

| Stability Score | Interpretation    | Typical Scenario     |
| --------------- | ----------------- | -------------------- |
| 0.9 - 1.0       | Extremely stable  | Stationary queue     |
| 0.7 - 0.9       | Highly stable     | Slow-moving group    |
| 0.5 - 0.7       | Moderately stable | Normal walking group |
| 0.3 - 0.5       | Low stability     | Dynamic clustering   |
| 0.0 - 0.3       | Very unstable     | Chaotic movement     |

## Hungarian Matching Algorithm

### Cost Matrix Construction

For each (tracked_cluster, new_detection) pair:

**1. Hard Constraint - Category Match**

```python
if tracked.category != detection.category:
    cost = INFINITE
```

**2. Position Cost (Weight: 0.4)**

```python
predicted_pos = tracked.predicted_position or tracked.centroid
detection_pos = detection.cluster_center
position_distance = euclidean_distance(predicted_pos, detection_pos)
position_cost = position_distance × 0.4
```

**3. Velocity Cost (Weight: 0.3)**

```python
velocity_distance = euclidean_distance(
    tracked.average_velocity,
    detection.average_velocity
)
velocity_cost = velocity_distance × 0.3
```

**4. Size Cost (Weight: 0.2)**

```python
size_difference = abs(
    tracked.object_count - detection.objects_in_cluster
)
size_cost = size_difference × 0.2
```

**5. Shape Cost (Weight: 0.1)**

```python
shape_match = (tracked.shape == detection.shape)
shape_cost = (1.0 if shape_match else 2.0) × 0.1
```

**6. Total Cost**

```python
total_cost = position_cost + velocity_cost + size_cost + shape_cost
```

### Assignment Process

```python
# 1. Build cost matrix
cost_matrix[i, j] = calculate_cost(clusters[i], detections[j])

# 2. Apply Hungarian algorithm (scipy.optimize.linear_sum_assignment)
row_indices, col_indices = linear_sum_assignment(cost_matrix)

# 3. Filter by maximum distance threshold
valid_matches = [
    (cluster_uuid, detection_idx, similarity)
    for (i, j) in zip(row_indices, col_indices)
    if cost_matrix[i, j] < MAX_DISTANCE  # Default: 5.0 meters
]
```

### Matching Configuration

```python
# HungarianMatcher constants
MAX_MATCHING_DISTANCE = 5.0      # Maximum valid match distance
POSITION_WEIGHT = 0.4            # Position importance
VELOCITY_WEIGHT = 0.3            # Velocity importance
SIZE_WEIGHT = 0.2                # Size importance
SHAPE_WEIGHT = 0.1               # Shape importance
```

## History Management

### Data Structure

```python
@dataclass
class ClusterHistory:
    positions: List[Tuple[float, float, float]]      # (x, y, timestamp)
    velocities: List[Tuple[float, float, float]]     # (vx, vy, timestamp)
    sizes: List[int]                                 # object counts
    shapes: List[str]                                # detected shapes
    timestamps: List[float]                          # frame timestamps

    MAX_HISTORY_SIZE = 100
```

### Operations

**Add Observation:**

```python
def addObservation(position, velocity, size, shape, timestamp):
    # Append new data
    history.positions.append((position.x, position.y, timestamp))
    history.velocities.append((velocity.x, velocity.y, timestamp))
    history.sizes.append(size)
    history.shapes.append(shape)
    history.timestamps.append(timestamp)

    # Trim to maximum size (keep most recent)
    if len(history.timestamps) > MAX_HISTORY_SIZE:
        all_arrays = trim_to_last_n(MAX_HISTORY_SIZE)
```

### Usage

**Position Stability Analysis:**

```python
recent_positions = cluster.history.positions[-10:]
position_variance = calculate_variance(recent_positions)
```

**Velocity Prediction:**

```python
recent_velocities = cluster.history.velocities[-5:]
avg_velocity = calculate_mean(recent_velocities)
predicted_position = current_position + avg_velocity
```

**Shape Consistency:**

```python
recent_shapes = cluster.history.shapes[-10:]
most_common_shape = mode(recent_shapes)
shape_consistency = count(most_common_shape) / len(recent_shapes)
```

## Prediction System

### Linear Extrapolation

**Algorithm:**

```python
# 1. Extract recent velocity observations
recent_velocities = cluster.history.velocities[-5:]  # Last 5 frames

# 2. Calculate average velocity
avg_velocity = np.mean([v[:2] for v in recent_velocities], axis=0)

# 3. Current position
current_pos = (cluster.centroid['x'], cluster.centroid['y'])

# 4. Predict next position (assuming ~1 frame time delta)
predicted_position = (
    current_pos[0] + avg_velocity[0],
    current_pos[1] + avg_velocity[1]
)
```

### Benefits

1. **Improved Matching Accuracy**
   - Accounts for cluster motion
   - Reduces false negatives for moving objects
   - Better handles fast-moving clusters

2. **Occlusion Handling**
   - Maintains predicted position during brief occlusions
   - Enables recovery when cluster reappears

3. **Smooth Tracking**
   - Reduces jitter in cluster assignments
   - More stable tracking across frames

### Fallback Behavior

```python
if len(history.positions) < 2:
    # Insufficient data for prediction
    predicted_position = current_position
    predicted_velocity = current_velocity
```

## Archival System

### Archival Criteria

```python
def should_be_archived(cluster, current_time):
    return (
        cluster.state == ClusterState.LOST and
        (current_time - cluster.last_seen) > ARCHIVE_TIME_THRESHOLD
    )
```

Default threshold: **5.0 seconds**

### Archive Management

**Configuration:**

```json
{
  "cluster_tracking": {
    "archival": {
      "archive_time_threshold": 5.0
    }
  }
}
```

**Limits:**

- Maximum archived clusters: 50 (global)
- Oldest clusters removed when limit exceeded

### Cleanup Process

```python
def cleanup_old_clusters(current_time):
    # 1. Find clusters to archive
    to_archive = [
        cluster for cluster in active_clusters
        if cluster.should_be_archived(current_time)
    ]

    # 2. Move to archive
    for cluster in to_archive:
        archived_clusters[cluster.uuid] = cluster
        remove_from_active(cluster.uuid)

    # 3. Limit archive size
    if len(archived_clusters) > MAX_ARCHIVED_CLUSTERS:
        remove_oldest_archived_clusters()
```

## Performance Characteristics

### Memory Usage

**Per Cluster:**

- Base TrackedCluster object: ~1-2 KB
- History (100 observations): ~8-10 KB
- Total per cluster: ~10-12 KB

**System Limits:**

- Active clusters: Unlimited (depends on scene)
- Archived clusters: 50 maximum
- History per cluster: 100 observations

**Typical Deployment:**

- 10-20 active clusters: ~200 KB
- 50 archived clusters: ~600 KB
- Total tracking overhead: ~1 MB

### Computational Complexity

**Per Frame Processing:**

- Hungarian matching: O(n³) where n = max(clusters, detections)
- Typical n < 20: ~0.1-1ms
- Position updates: O(n) linear
- History management: O(1) amortized

**Optimization:**

- Early category filtering reduces cost matrix size
- Spatial indexing could further optimize (future enhancement)

## Best Practices

### Configuration Tuning

**Short-lived Scenarios (e.g., pedestrian crossings):**

```json
{
  "frames_to_activate": 2,
  "frames_to_lost": 5,
  "archive_time_threshold": 2.0
}
```

**Long-lived Scenarios (e.g., parking lots):**

```json
{
  "frames_to_activate": 5,
  "frames_to_stable": 30,
  "frames_to_lost": 15,
  "archive_time_threshold": 10.0
}
```

### Monitoring

**Key Metrics to Track:**

- Average confidence score (target: >0.7)
- State distribution (most clusters should be ACTIVE/STABLE)
- Archived cluster rate (indicates cluster churn)
- Match success rate (>90% ideal)

**Logging:**

```python
# Enable INFO logging for lifecycle events
INFO: Created new cluster a1b2c3d4 (scene: 123, category: person)
INFO: Cluster a1b2c3d4 state transition: new -> active
INFO: Archived cluster a1b2c3d4 (state: lost, lifetime: 45 frames)
```

### Troubleshooting

**Problem: High cluster churn (many NEW → LOST)**

- Solution: Reduce `frames_to_activate` threshold
- Check DBSCAN parameters (eps might be too strict)

**Problem: False cluster merges**

- Solution: Reduce `MAX_MATCHING_DISTANCE`
- Increase POSITION_WEIGHT in cost matrix

**Problem: Clusters not transitioning to STABLE**

- Solution: Reduce `frames_to_stable` threshold
- Check scene stability (high motion prevents STABLE state)

**Problem: Excessive memory usage**

- Solution: Reduce `MAX_HISTORY_SIZE`
- Lower `MAX_ARCHIVED_CLUSTERS` limit
- Decrease `archive_time_threshold`

## API Reference

### ClusterTracker

```python
tracker = ClusterTracker(matcher=HungarianMatcher(), config=config)

# Process new detections for a scene
tracker.processNewDetections(
    scene_id="scene-uuid",
    new_cluster_detections=[...],
    timestamp=1729501601.734
)

# Get active clusters (publishable)
active_clusters = tracker.getActiveClusters(
    scene_id="scene-uuid",
    publishable_only=True  # Only ACTIVE, STABLE, FADING
)

# Get tracking statistics
stats = tracker.getStatistics()
# Returns: {
#   'active_clusters': 10,
#   'archived_clusters': 25,
#   'clusters_by_state': {...},
#   'tracked_scenes': 2,
#   'tracked_categories': 3
# }
```

### TrackedCluster

```python
# Convert to dictionary for MQTT publishing
cluster_dict = cluster.toDict()

# Check if cluster should be archived
should_archive = cluster.shouldBeArchived(current_time, max_time_lost=30.0)

# Get cluster metrics
age_seconds = cluster.getAgeSeconds(current_time)
time_since_seen = cluster.getTimeSinceLastSeen(current_time)
```

## License

Apache 2.0 License - See LICENSE file for details

---

_Intel® SceneScape Cluster Analytics - Advanced Temporal Tracking System_
