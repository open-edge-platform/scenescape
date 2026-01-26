# ControllerConfig Refactoring - Implementation Summary

## Overview

Successfully refactored the controller codebase to replace scattered `analytics_only` boolean flags with a centralized `ControllerConfig` object. This improves code organization while keeping mode checks explicit and readable.

## Files Created

### `controller/src/controller/controller_mode.py` (NEW)
- Defines `ControllerMode` enum: `FULL` and `ANALYTICS_ONLY`
- Defines `ControllerConfig` dataclass (immutable)
- Provides simple properties: `is_analytics_only`, `is_full_mode`
- Includes `from_analytics_only_flag()` for backward compatibility

## Files Modified

### 1. `controller/src/controller-cmd`
**Before:**
```python
from controller.scene_controller import SceneController

def main():
  args = build_argparser().parse_args()
  controller = SceneController(..., args.analytics_only)
```

**After:**
```python
from controller.scene_controller import SceneController
from controller.controller_mode import ControllerConfig

def main():
  args = build_argparser().parse_args()
  config = ControllerConfig.from_analytics_only_flag(args.analytics_only)
  controller = SceneController(..., config)
```

**Changes:**
- ✅ Import `ControllerConfig`
- ✅ Create config object from CLI flag
- ✅ Pass config instead of boolean

---

### 2. `controller/src/controller/scene_controller.py`
**Before:**
```python
class SceneController:
  def __init__(self, ..., analytics_only=False):
    self.analytics_only = analytics_only
    self.cache_manager = CacheManager(..., analytics_only=analytics_only)
    
  def publishDetections(self, ...):
    if not self.analytics_only:
      self.publishSceneDetections(...)
```

**After:**
```python
from controller.controller_mode import ControllerConfig

class SceneController:
  def __init__(self, ..., config: ControllerConfig):
    self.config = config
    self.cache_manager = CacheManager(..., config=config)
    
  def publishDetections(self, ...):
    # In analytics-only mode, scene detections are published by separate Tracker service
    if not self.config.is_analytics_only:
      self.publishSceneDetections(...)
```

**Changes:**
- ✅ Import `ControllerConfig`
- ✅ Accept `config` parameter instead of `analytics_only`
- ✅ Store `self.config` instead of `self.analytics_only`
- ✅ Pass config to `CacheManager`
- ✅ Replace `if self.analytics_only:` with `if self.config.is_analytics_only:`
- ✅ Add explicit comments explaining mode-specific behavior

**Mode Checks Updated:**
- Line 47: Initialization log
- Line 141: Publishing scene detections
- Line 192: Rate extraction for analytics-only
- Line 482: Analytics processing in handleSceneDataMessage
- Line 656: Camera/sensor subscription logic
- Line 674-678: Child scene subscription logic

---

### 3. `controller/src/controller/cache_manager.py`
**Before:**
```python
class CacheManager:
  def __init__(self, ..., analytics_only=False):
    self.analytics_only = analytics_only
    
  def refreshScenes(self):
    scene = Scene.deserialize(scene_data, self.analytics_only)
```

**After:**
```python
from controller.controller_mode import ControllerConfig

class CacheManager:
  def __init__(self, ..., config: ControllerConfig = None):
    self.config = config if config else ControllerConfig.from_analytics_only_flag(False)
    
  def refreshScenes(self):
    scene = Scene.deserialize(scene_data, self.config)
```

**Changes:**
- ✅ Import `ControllerConfig`
- ✅ Accept `config` parameter instead of `analytics_only`
- ✅ Store `self.config` with default fallback
- ✅ Pass config to `Scene.deserialize()`

---

### 4. `controller/src/controller/scene.py`
**Before:**
```python
class Scene:
  def __init__(self, ..., analytics_only=False):
    self.analytics_only = analytics_only
    if not analytics_only:
      self._setTracker(...)
      
  def processCameraData(self, ...):
    if self.analytics_only:
      return True
      
  @classmethod
  def deserialize(cls, data, analytics_only=False):
    scene = cls(..., analytics_only=analytics_only)
```

**After:**
```python
from controller.controller_mode import ControllerConfig

class Scene:
  def __init__(self, ..., config: ControllerConfig = None):
    self.config = config if config else ControllerConfig.from_analytics_only_flag(False)
    # In analytics-only mode, tracking is performed by separate Tracker service
    if not self.config.is_analytics_only:
      self._setTracker(...)
      
  def processCameraData(self, ...):
    # Analytics-only mode doesn't process raw camera data
    if self.config.is_analytics_only:
      return True
      
  @classmethod
  def deserialize(cls, data, config: ControllerConfig):
    scene = cls(..., config=config)
```

**Changes:**
- ✅ Import `ControllerConfig`
- ✅ Accept `config` parameter instead of `analytics_only`
- ✅ Store `self.config` with default fallback
- ✅ Replace all `self.analytics_only` checks with `self.config.is_analytics_only`
- ✅ Add explicit comments for each mode check
- ✅ Update `deserialize()` to accept config

**Mode Checks Updated:**
- Line 66: Tracker initialization
- Line 72: `use_tracker` flag
- Line 155: processCameraData early exit
- Line 235: processSceneData early exit
- Line 272: _finishProcessing tracker call
- Line 347: getTrackedObjects source selection
- Line 433: _updateEvents object retrieval
- Line 573: deserialize use_tracker

---

### 5. `controller/src/controller/child_scene_controller.py`
**Before:**
```python
class ChildSceneController:
  def __init__(self, ..., parent_controller):
    self.analytics_only = parent_controller.analytics_only
    
    if self.analytics_only:
      self.child_scene_topic = PubSub.formatTopic(PubSub.DATA_SCENE, ...)
```

**After:**
```python
class ChildSceneController:
  def __init__(self, ..., parent_controller):
    self.config = parent_controller.config
    
    # Analytics-only mode: subscribe to tracked objects from DATA_SCENE
    # Full mode: subscribe to raw detections from DATA_EXTERNAL
    if self.config.is_analytics_only:
      self.child_scene_topic = PubSub.formatTopic(PubSub.DATA_SCENE, ...)
```

**Changes:**
- ✅ Store `self.config` instead of `self.analytics_only`
- ✅ Replace `self.analytics_only` with `self.config.is_analytics_only`
- ✅ Add explicit comment explaining mode difference

---

## Benefits Achieved

### ✅ Single Source of Truth
- Mode state now centralized in `ControllerConfig`
- No more passing boolean flags through 4+ classes
- Config created once at entry point, shared everywhere

### ✅ Explicit and Readable
- Mode checks like `if config.is_analytics_only:` are clear
- Comments added explaining WHY behavior differs per mode
- Reader understands context, not just "should do X"

### ✅ Type Safety
- `ControllerConfig` is a proper type, not just `bool`
- IDEs provide better autocomplete and type checking
- Immutable dataclass prevents accidental modification

### ✅ Extensibility
- Easy to add new modes (REPLAY, SIMULATION, etc.)
- Just add to `ControllerMode` enum
- No need to add new boolean flags everywhere

### ✅ Testability
- Mock config object in tests
- Single fixture for analytics-only tests
- Single fixture for full-mode tests

---

## Migration Path (If Needed)

The implementation includes backward compatibility through `from_analytics_only_flag()`:

```python
# Old code still works (with deprecation path):
config = ControllerConfig.from_analytics_only_flag(True)

# New code is explicit:
config = ControllerConfig(mode=ControllerMode.ANALYTICS_ONLY)
```

---

## Testing Recommendations

### Unit Tests
```python
@pytest.fixture
def analytics_config():
    return ControllerConfig(mode=ControllerMode.ANALYTICS_ONLY)

@pytest.fixture
def full_config():
    return ControllerConfig(mode=ControllerMode.FULL)

def test_scene_skips_tracker_in_analytics_mode(analytics_config):
    scene = Scene("test", None, config=analytics_config)
    assert scene.tracker is None
    assert not scene.use_tracker

def test_scene_initializes_tracker_in_full_mode(full_config):
    scene = Scene("test", None, config=full_config)
    assert scene.tracker is not None
    assert scene.use_tracker
```

### Integration Tests
- Test controller startup with `CONTROLLER_ENABLE_ANALYTICS_ONLY=true`
- Verify correct MQTT topic subscriptions per mode
- Verify analytics processing works in both modes

---

## Code Statistics

**Lines Changed:**
- controller-cmd: 5 lines
- scene_controller.py: 15 locations updated
- cache_manager.py: 4 locations updated
- scene.py: 10 locations updated
- child_scene_controller.py: 3 locations updated

**Total:** ~40 specific location updates + 1 new file

**Reduction:**
- Eliminated 4 instance variables (`self.analytics_only`)
- Reduced parameter passing in constructors
- Centralized mode logic in one file

---

## Next Steps

1. **Run existing tests** to ensure no regressions
2. **Update test fixtures** to use ControllerConfig
3. **Update documentation** to reference new config approach
4. **Consider adding mode validation** (e.g., analytics-only requires tracker service)
5. **Add integration tests** specifically for mode switching

---

## Example: Adding a New Mode

To add a new `SIMULATION` mode in the future:

```python
# 1. Add to enum
class ControllerMode(Enum):
  FULL = "full"
  ANALYTICS_ONLY = "analytics_only"
  SIMULATION = "simulation"  # NEW

# 2. Add property
@property
def is_simulation(self) -> bool:
  return self.mode == ControllerMode.SIMULATION

# 3. Use in code
if config.is_simulation:
  # Simulation-specific behavior
  ...
```

No need to modify every class - just use the config object that's already being passed!
