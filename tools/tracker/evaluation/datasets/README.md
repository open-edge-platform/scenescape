<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Tracking Datasets

This directory contains dataset adapter implementations for the tracker evaluation pipeline.

## Overview

Each dataset adapter implements the `TrackingDataset` abstract base class (see [../base/tracking_dataset.py](../base/tracking_dataset.py)) to provide:

- Scene and camera configuration in SceneScape canonical format
- Input data (object detections) from configured cameras
- Ground-truth object locations for evaluation

Dataset adapters convert dataset-specific formats to SceneScape canonical formats as defined in the tracker schemas.

## Available Datasets

### MetricTestDataset

**Purpose**: Adapter for `tests/system/metric/test_data` dataset used in acceptance tests.

**Key Features**:
- Single scene: `Retail_Demo`
- Two cameras: `x1`, `x2` (Cam_x1_0, Cam_x2_0)
- Multiple FPS options: 1, 10, 30 (separate JSON files per FPS)
- Ground truth in MOTChallenge 3D CSV format

**Usage Example**:
```python
from datasets.metric_test_dataset import MetricTestDataset

dataset = MetricTestDataset("/path/to/tests/system/metric/test_data")

# Configure dataset
dataset.set_cameras(["x1", "x2"]).set_camera_fps(30)

# Get scene configuration
scene_config = dataset.get_scene_config()

# Get camera inputs
for camera_input in dataset.get_inputs("x1"):
    # Process detection data
    pass

# Get ground truth
gt_path = dataset.get_ground_truth()
```

**Documentation**: See [MetricTestDataset docstring](metric_test_dataset.py) for detailed API documentation.

**Tests**: See [tests/test_metric_test_dataset.py](tests/test_metric_test_dataset.py) for comprehensive test suite.

## Adding New Datasets

To add support for a new dataset:

1. **Create adapter class**: Implement all abstract methods from `TrackingDataset` base class
2. **Format conversion**: Convert dataset-specific formats to SceneScape canonical formats:
   - Scene config → [tracker/schema/scene.schema.json](../../../../tracker/schema/scene.schema.json)
   - Camera inputs → [tracker/schema/camera-data.schema.json](../../../../tracker/schema/camera-data.schema.json)
   - Ground truth → MOTChallenge 3D CSV format (8 columns: frame, id, x, y, z, conf, class, visibility)
3. **Create tests**: Add comprehensive tests validating format conversion and schema compliance
4. **Update documentation**: Add entry to this README with usage example and key features

### Dataset Adapter Template

```python
from typing import List, Dict, Any, Optional, Iterator
from pathlib import Path
from base.tracking_dataset import TrackingDataset

class MyDataset(TrackingDataset):
  """Adapter for MyDataset.

  Dataset description and key features.
  """

  def __init__(self, dataset_path: str):
    """Initialize dataset adapter."""
    self._dataset_path = Path(dataset_path)
    # Initialize state

  def set_scene(self, scene: Optional[str] = None) -> 'MyDataset':
    """Set scene identifier."""
    # Implementation
    return self

  def set_cameras(self, cameras: Optional[List[str]] = None) -> 'MyDataset':
    """Set camera identifiers."""
    # Implementation
    return self

  def set_time_range(self, start: Optional[str] = None,
                     end: Optional[str] = None) -> 'MyDataset':
    """Set time range for sequences."""
    # Implementation
    return self

  def set_camera_fps(self, camera_fps: float) -> 'MyDataset':
    """Set camera frame rate."""
    # Implementation
    return self

  def set_custom_config(self, config: Dict[str, Any]) -> 'MyDataset':
    """Set custom configuration."""
    # Implementation
    return self

  def get_scene_config(self) -> Dict[str, Any]:
    """Get scene config in canonical format."""
    # Convert to tracker/schema/scene.schema.json format
    pass

  def get_scene_config_raw(self) -> Dict[str, Any]:
    """Get raw scene config in dataset-specific format."""
    # Load and return raw config
    pass

  def get_inputs(self, camera: Optional[str] = None) -> Iterator[Dict[str, Any]]:
    """Get camera inputs in canonical format."""
    # Convert to tracker/schema/camera-data.schema.json format
    pass

  def get_ground_truth(self) -> str:
    """Get ground truth in MOTChallenge CSV format."""
    # Convert to MOTChallenge 3D CSV
    pass

  def reset(self) -> 'MyDataset':
    """Reset to initial state."""
    # Reset state
    return self
```

## Design Documentation

See [tracker-evaluation-pipeline.md](../../../../docs/design/tracker-evaluation-pipeline.md) for overall architecture and design decisions.
