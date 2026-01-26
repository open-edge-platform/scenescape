# Refactoring Proposal: Analytics-Only Mode Configuration

## Problem Statement

The current implementation in PR 884 spreads the `analytics_only` boolean flag across multiple classes:
- SceneController
- CacheManager  
- Scene
- ChildSceneController

This creates several issues:
1. **Tight coupling** - Every class needs to know about this operational mode
2. **Maintenance burden** - Adding new modes or behaviors requires changes in multiple places
3. **Testing complexity** - Each class needs tests for both modes
4. **Code clarity** - Boolean flags scattered through conditional logic are hard to reason about

## Proposed Solution: Centralized Configuration Class

### Key Principle: Explicit Over Abstract

**Important**: This approach keeps mode checks **explicit** in the code rather than hiding them behind vague property names. 

Consider these two approaches:

```python
# ❌ BAD: Abstract property hides context
if self.config.should_publish_scene_detections:
    self.publishSceneDetections(...)
# Reader thinks: "Why should or shouldn't this happen?"

# ✅ GOOD: Explicit mode check provides context  
if not self.config.is_analytics_only:
    # In analytics-only mode, tracking is done by separate Tracker service
    self.publishSceneDetections(...)
# Reader thinks: "Ah, this doesn't happen in analytics-only mode because..."
```

The config object centralizes **where** the mode is stored, not **what** the mode means. The meaning stays visible in the code where decisions are made.

### Architecture

```
┌─────────────────────────────────────────┐
│  ControllerConfig (Immutable)           │
│  - mode: ControllerMode enum            │
│  - is_analytics_only: bool              │
│  - is_full_mode: bool                   │
│  (Explicit mode checks, not "should_*") │
└─────────────────────────────────────────┘
                    ▲
                    │ passed to constructors
                    │
    ┌───────────────┼───────────────┐
    │               │               │
┌───▼──────┐  ┌────▼─────┐  ┌─────▼────┐
│  Scene   │  │  Cache   │  │   Child  │
│Controller│  │ Manager  │  │  Scene   │
│          │  │          │  │Controller│
└──────────┘  └──────────┘  └──────────┘
```

### Benefits

1. **Single Source of Truth**: Mode state centralized in one place, no flag spreading
2. **Immutability**: `@dataclass(frozen=True)` prevents accidental modification
3. **Explicit Context**: Code clearly states "if analytics_only" or "if full_mode" - reader knows WHY
4. **Extensibility**: Easy to add new modes (e.g., `REPLAY`, `SIMULATION`)
5. **Testability**: Mock/configure once, affects all classes consistently

### Implementation Changes

#### Before (Current):
```python
class SceneController:
  def __init__(self, ..., analytics_only=False):
    self.analytics_only = analytics_only
    # Pass to cache manager
    self.cache_manager = CacheManager(..., analytics_only=analytics_only)
    
  def publishDetections(self, ...):
    if not self.analytics_only:  # Scattered checks
      self.publishSceneDetections(...)
```

#### After (Proposed):
```python
from controller.controller_mode import ControllerConfig

class SceneController:
  def __init__(self, ..., config: ControllerConfig):
    self.config = config
    # Pass single config object
    self.cache_manager = CacheManager(..., config=config)
    
  def publishDetections(self, ...):
    # In analytics-only mode, we don't publish scene detections
    # because tracking is done by separate Tracker service
    if not self.config.is_analytics_only:
      self.publishSceneDetections(...)
```

### Migration Steps

**Phase 1: Add Configuration Class** (Non-breaking)
1. Create `controller_mode.py` with `ControllerConfig` class
2. Add compatibility constructor: `ControllerConfig.from_analytics_only_flag()`

**Phase 2: Update Entry Point**
```python
# controller-cmd
def main():
  args = build_argparser().parse_args()
  config = ControllerConfig.from_analytics_only_flag(args.analytics_only)
  controller = SceneController(..., config=config)
```

**Phase 3: Refactor Classes** (One at a time)
1. Update `SceneController.__init__` to accept `config` parameter
2. Replace `self.analytics_only` with `self.config`
3. Update conditional checks to use config properties
4. Repeat for CacheManager, Scene, ChildSceneController

**Phase 4: Update Tests**
```python
# Before
scene = Scene("test", None, analytics_only=True)

# After
config = ControllerConfig(mode=ControllerMode.ANALYTICS_ONLY)
scene = Scene("test", None, config=config)
```

### Alternative Considered: Strategy Pattern

Could use Strategy pattern with polymorphism:
```python
class AnalyticsStrategy(ABC):
    @abstractmethod
    def get_tracked_objects(self, scene) -> List[Object]: ...

class FullModeStrategy(AnalyticsStrategy):
    def get_tracked_objects(self, scene):
        return scene.tracker.currentObjects()

class AnalyticsOnlyStrategy(AnalyticsStrategy):
    def get_tracked_objects(self, scene):
        return scene.cached_objects
```

**Rejected because**: 
- More complex for simple boolean-like decisions
- Doesn't reduce the number of classes aware of the mode
- Configuration class provides better clarity for this use case

### Code Example: Scene Class

#### Current (7 analytics_only checks):
```python
class Scene:
  def __init__(self, ..., analytics_only=False):
    self.analytics_only = analytics_only
    if not analytics_only:
      self._setTracker(...)
    
  def processCameraData(self, ...):
    if self.analytics_only:
      return True  # Check #1
    # ... process
    
  def getTrackedObjects(self, detection_type):
    if self.analytics_only:  # Check #2
      return self._deserializeTrackedObjects(...)
    if self.tracker:  # Check #3
      return self.tracker.currentObjects(...)
```

#### Proposed (cleaner and explicit):
```python
class Scene:
  def __init__(self, ..., config: ControllerConfig):
    self.config = config
    # In analytics-only mode, no tracker needed (separate Tracker service)
    if not config.is_analytics_only:
      self._setTracker(...)
    
  def processCameraData(self, ...):
    # Analytics-only mode doesn't process raw camera data
    if self.config.is_analytics_only:
      return True
    # ... process
    
  def getTrackedObjects(self, detection_type):
    # Analytics-only mode: get tracked objects from MQTT (published by Tracker service)
    # Full mode: get tracked objects directly from local tracker
    if self.config.is_analytics_only:
      return self._deserializeTrackedObjects(...)
    elif self.tracker:
      return self.tracker.currentObjects(...)
```

### Backward Compatibility

Maintain backward compatibility during migration:
```python
class Scene:
  def __init__(self, ..., config: ControllerConfig = None, analytics_only: bool = None):
    # Support both old and new API temporarily
    if config is None and analytics_only is not None:
      config = ControllerConfig.from_analytics_only_flag(analytics_only)
    elif config is None:
      config = ControllerConfig.from_analytics_only_flag(False)
    self.config = config
```

### Testing Impact

**Before**: Test each class in both modes
```python
def test_scene_analytics_only():
    scene = Scene("test", None, analytics_only=True)
    assert scene.use_tracker == False

def test_scene_full_mode():
    scene = Scene("test", None, analytics_only=False)
    assert scene.use_tracker == True
```

**After**: Test configuration once, use everywhere
```python
@pytest.fixture
def analytics_only_config():
    return ControllerConfig(mode=ControllerMode.ANALYTICS_ONLY)

@pytest.fixture  
def full_mode_config():
    return ControllerConfig(mode=ControllerMode.FULL)

def test_scene_with_analytics_config(analytics_only_config):
    scene = Scene("test", None, config=analytics_only_config)
    assert not scene.config.should_initialize_tracker
```

### Future Extensions

Easy to add new modes without touching existing code:

```python
class ControllerMode(Enum):
  FULL = "full"
  ANALYTICS_ONLY = "analytics_only"
  REPLAY = "replay"  # NEW: replay from recorded data
  SIMULATION = "simulation"  # NEW: simulation testing

@dataclass(frozen=True)
class ControllerConfig:
  mode: ControllerMode
  replay_file: Optional[str] = None  # Mode-specific config
  
  @property
  def is_analytics_only(self) -> bool:
    return self.mode == ControllerMode.ANALYTICS_ONLY
  
  @property
  def is_simulation(self) -> bool:
    return self.mode == ControllerMode.SIMULATION

# Usage in code:
if config.is_analytics_only:
  # Analytics-only specific behavior with clear context
  ...
```

## Recommendation

**Strongly recommend** refactoring to use the `ControllerConfig` approach before merging PR 884. The current implementation will create technical debt that becomes harder to fix as more features depend on the analytics-only mode.

**Effort estimate**: 2-3 hours to implement + 1-2 hours for testing
**Risk**: Low - can be done incrementally with backward compatibility
**Benefit**: Much cleaner architecture that's easier to extend and maintain
