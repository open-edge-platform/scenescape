# Nokia Enhancements to Intel SceneScape 2025.2

**Branch:** `nokia/enhancements-2025.2`
**Base:** Intel SceneScape `release-2025.2`
**Author:** Mohammed Sufiyan Saqib (`mohammed.sufiyan_saqib@nokia.com`)

This document summarizes Nokia's contributions on top of Intel SceneScape 2025.2.
Each section is marked as either **New** (written from scratch) or **Enhanced**
(modifications to existing Intel code).

---

## What Changed at a Glance

| Area | What Nokia Did | Type |
|------|----------------|------|
| Controller multiprocessing | Added worker processes, crash recovery, async publish | Enhanced Intel code |
| Time chunking | Rewrote buffer for scene-aware, hybrid dispatch | Enhanced Intel code |
| Cache manager | Added thread-safety, lock-free lookups | Enhanced Intel code |
| Object tracking | O(1) lookups, UUID stability across track states | Enhanced Intel code |
| Triton inference scripts | Three new Python modules for GPU inference via gRPC | New |
| YOLOv7 model repository | TensorRT FP16 engine + DALI preprocessing ensemble | New |
| NVIDIA GPU bootstrap | k3s installer, device plugin, containerd config | New |
| Triton Helm templates | Kubernetes deployment, services, configmaps | New |
| Pipeline generator | NVDEC decode path, Triton model type | Enhanced Intel code |
| DLStreamer adapter | Resolution rescaling for 640x640 inference | Enhanced Intel code |
| UI | SVG coordinate fix, scale controls, ID overlay | Enhanced Intel code |

---

## 1. Controller Architecture

### 1.1 Multiprocessing in SceneController [Enhanced]

**File:** `controller/src/controller/scene_controller.py` (+1198 / -111 lines)

Added `ProcessPoolExecutor`-based worker architecture to Intel's `SceneController`.
Each scene gets its own worker process, created on demand:

```python
executor = ProcessPoolExecutor(
    max_workers=1, mp_context=multiprocessing.get_context('spawn'),
    initializer=_init_worker_process, initargs=(self._worker_config,))
```

Additional mechanisms:
- **Overwrite buffer**: only the latest frame per camera is processed
- **Semaphore admission control** (default 20) to bound memory under burst load
- **Async MQTT publish** on a dedicated thread, decoupled from tracking
- **Crash recovery**: `BrokenProcessPool` triggers automatic `_recreate_scene_executor()`
- **Publish watchdog**: monitors the publish thread every 30s, restarts if needed

### 1.2 Scene-Aware Time Chunking [Enhanced]

**File:** `controller/src/controller/time_chunking.py` (+568 / -209 lines)

Intel's `TimeChunkBuffer` used a flat dictionary with no scene awareness, which
could dispatch mixed-scene batches. Replaced with `SceneAwareCategoryBuffer`:

```python
class SceneAwareCategoryBuffer:
  # {scene_id: {camera_id: (objects, timestamp, ...)}}
  def update(self, camera_id, scene_id, objects, when, already_tracked):
      # When all cameras for a scene report in, dispatch immediately
```

**Hybrid dispatch model** (replaces Intel's timer-only `Event.wait(timeout)`):
- **Event-driven**: immediate dispatch when all cameras for a scene report in
- **Timer fallback**: 200ms interval dispatches partial scenes
- Uses `time.monotonic()` for drift-resistant fixed-rate scheduling

Unit tests: `controller/src/controller/test_time_chunking.py` (371 lines).

Intel created the time chunking framework (`TimeChunkBuffer`, `TimeChunkProcessor`,
`TimeChunkedIntelLabsTracking`). Nokia rewrote the buffer internals and dispatch logic.

### 1.3 Thread-Safe CacheManager [Enhanced]

**File:** `controller/src/controller/cache_manager.py` (+325 / -78 lines)

Intel's `CacheManager` performed on-demand HTTP refresh inside accessor methods,
which blocked the MQTT callback thread. Added `threading.Lock` protection and
`_fast` lookup methods that never make HTTP calls:

```python
def sceneWithCameraID_fast(self, cameraID):
    """Dict-only lookup — safe to call from MQTT thread."""
    with self._lock:
      return self._cached_scenes_by_cameraID.get(cameraID, None)
```

HTTP refresh moved to a background thread (every 60s) with a lock-free pattern:
fetch data outside the lock, update the cache inside it.

### 1.4 Faster Object Association [Enhanced]

**File:** `controller/src/controller/ilabs_tracking.py` (+190 / -25 lines)

Intel's `from_tracked_object()` uses O(n) linear scan per object, creating O(n^2)
overhead in the batch path. Added `from_tracked_object_fast()` with O(1) hash-map lookups:

```python
def from_tracked_object_fast(self, tracked_obj, objects_by_uuid,
                              tracker_by_uuid, tracker_by_rv_id):
    # Constant-time association using pre-built dicts
```

Also fixed UUID stability: `pruneInactiveTracks()` previously only considered
reliable tracks, losing UUIDs during state transitions. Now includes all active states:

```python
all_active = (tracked_objects + self.tracker.get_unreliable_tracks()
              + self.tracker.get_suspended_tracks())
self.uuid_manager.pruneInactiveTracks(all_active)
```

### 1.5 Other Controller Enhancements

| What | Where | Details |
|------|-------|---------|
| **ReID extraction** | `moving_object.py` (+82/-25) | Changed ReID extraction path to read directly from detection `info` dict. Storage format `{'embedding_vector': array, 'model_name': ...}` retained from Intel's design. |
| **Detection schema fields** | `metadata.schema.json` (+58) | Added `reid`, `facemask`, `color`, `age`, `hat`, `gender`, `subtype` to Intel's existing `semantic_metadata` definitions. |
| **C++ tracker accessors** | `MultipleObjectTracker.hpp`, `tracking.cpp` | Exposed `getSuspendedTracks()` and `getUnreliableTracks()` with Python bindings — needed for the UUID stability fix above. |
| **Profiling support** | `controller-cmd` (+76/-33) | Added `--profile` flag for `cProfile` output. Simplified Intel's existing health check handler. |
| **Tracker tuning** | `tracker-config.json` | Retuned for 10 FPS: `baseline_frame_rate` 30->10, `non_measurement_frames_dynamic` 8->20, `time_chunking_interval_milliseconds` 50->200. |
| **Changelog** | `controller/docs/controller-upgrade-changelog.md` (1802 lines) | Detailed narrative of all architectural changes. |

---

## 2. Triton Inference Pipeline [New]

Intel SceneScape 2025.2 uses CPU/iGPU inference via OpenVINO. These modules
add GPU inference via NVIDIA Triton Inference Server.

### 2.1 Inference Scripts

Three new `gvapython` modules for Triton gRPC inference:

| File | Lines | What It Does |
|------|-------|--------------|
| `triton_inference_base.py` | 450 | Base classes shared by all models — gRPC client, frame processing, rolling latency stats |
| `yolov7_triton_inference.py` | 501 | YOLOv7-specific postprocessing — anchor decoding at strides 8/16/32, class-aware NMS, DALI ensemble support |
| `yolox_triton_inference.py` | 363 | YOLOX variant — simpler postprocessing, no color space conversion needed |

All files at: `dlstreamer-pipeline-server/user_scripts/gvapython/sscape/`

Configuration is passed as base64-encoded JSON through GStreamer's `arg=[...]`
parameter to avoid nested quote escaping in pipeline strings:

```python
config = {"triton_url": "tritonserver:8001", "model_name": "yolov7_tiny_e2e_v1", ...}
b64 = base64.b64encode(json.dumps(config).encode()).decode()
# Used in pipeline: gvapython class=process_frame arg=["<b64>"]
```

Built-in latency instrumentation (enable with `TRITON_ENABLE_TIMING=1`) reports
p50/p95/p99 for preprocess, gRPC, GPU inference, and postprocess every 10 seconds.

### 2.2 YOLOv7 Model Repository

Triton model repository with a three-stage ensemble pipeline:

```
Raw BGR frame (UINT8)
  -> DALI preprocess on GPU (normalize, BGR->RGB, HWC->CHW, cast to FP16)
    -> TensorRT YOLOv7-tiny (FP16, EfficientNMS baked in)
      -> Outputs: num_dets, det_boxes, det_scores, det_classes
```

Files at `model_repo/yolov7/`:

| File | Purpose |
|------|---------|
| `fp16/triton/yolov7_tiny_e2e_v1/1/model.plan` | TensorRT FP16 engine |
| `fp16/triton/yolov7_preprocess/1/model.dali` | DALI GPU preprocessing pipeline |
| `fp16/triton/yolov7_ensemble/config.pbtxt` | Ensemble orchestration (preprocess + inference) |
| `export/onnx/yolov7-tiny-e2e-fp16input.onnx` | Source ONNX model |

Configured for 3 GPU instances with dynamic batching (1-32), 100ms max queue delay.

### 2.3 Build Tooling

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/build_triton_repo.sh` | 527 | End-to-end: ONNX -> TensorRT engine + all config.pbtxt generation |
| `scripts/serialize_dali.py` | 81 | Generates the DALI preprocessing binary |
| `Dockerfile.triton` | 39 | Extends Intel's DLStreamer image with `tritonclient[grpc]` |
| `dlstreamer-pipeline-server/Makefile` | 60 | `make build-triton` target |

### 2.4 Model Configuration

Added a `yolov7_tiny_e2e` entry to Intel's `model_config.json`:

```json
"yolov7_tiny_e2e": {
  "type": "triton",
  "params": {
    "model": "yolov7_tiny_e2e_v1",
    "inference-script": "yolov7_triton_inference",
    "triton-url": "tritonserver:8001",
    "use-ensemble": true,
    "confidence-threshold": "0.45",
    "labels": ["person"]
  }
}
```

---

## 3. GStreamer Pipeline Generation [Enhanced]

### 3.1 NVDEC Decode Path

**File:** `manager/src/django/ppl_generator/pipeline_generator.py` (+82 / -12 lines)

Added NVDEC hardware decode for Triton pipelines. NVDEC runs on dedicated silicon,
separate from CUDA cores used for inference:

```python
if self._has_triton_model() or decode_device == "GPU_NVIDIA":
    self.decode = [
      "nvh264dec max-display-delay=0",                                    # NVDEC HW decode
      "queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 leaky=downstream",
      "videorate drop-only=true max-rate=10",                             # Cap at 10 FPS
      "video/x-raw,framerate=10/1"                                        # Pin framerate
    ]
```

The resulting end-to-end pipeline:

```
RTSP source -> H.264 parse -> NVDEC decode -> rate limit (10fps)
  -> tee -> [parallel buffer branch at 5fps for frame capture]
  -> CPU resize to 640x640 BGR -> Triton gRPC inference
  -> metadata conversion -> SceneScape adapter -> output
```

### 3.2 Triton Model Serialization

**File:** `manager/src/django/ppl_generator/inference_model.py` (+103 / -7 lines)

Added `triton` model type to Intel's `InferenceModel` with base64-encoded config:

```python
def _serialize_triton_model(self):
    config = {"triton_url": ..., "model_name": ..., "labels": ...}
    b64 = base64.b64encode(json.dumps(config).encode()).decode()
    return [f'gvapython module=...triton_inference.py class=process_frame arg=["{b64}"]']
```

### 3.3 Resolution Rescaling

**File:** `dlstreamer-pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py` (+130 / -7 lines)

Rescales bounding boxes from 640x640 inference resolution back to original camera resolution:

```python
sx = orig_w / framewidth   # e.g., 1920/640 = 3.0x
sy = orig_h / frameheight  # e.g., 1080/640 = 1.6875x
```

---

## 4. Kubernetes Deployment

### 4.1 Triton Server Templates [New]

Helm templates for Triton Inference Server:

| Template | What It Creates |
|----------|----------------|
| `tritonserver/deployment.yaml` (122 lines) | Pod with `runtimeClassName: nvidia`, model polling, health probes |
| `tritonserver/service.yaml` (35 lines) | ClusterIP — HTTP :8000, gRPC :8001, metrics :8002 |
| `tritonserver/nodeport-service.yaml` (73 lines) | Optional external access via NodePort or LoadBalancer |
| `tritonserver/configmap.yaml` (44 lines) | Model repository structure reference |

All gated by `tritonserver.enabled` in `values.yaml`.

### 4.2 NVIDIA GPU Bootstrap [New]

Installer for GPU support on k3s nodes:

| File | What It Does |
|------|--------------|
| `installer/install.sh` (501 lines) | Installs NVIDIA driver 580, Container Toolkit, k3s v1.32.9 |
| `installer/nvidia-device-plugin-k3s.yaml` | Device Plugin with GPU time-slicing (20 replicas) |
| `installer/containerd_nvidia_config.toml` | containerd runtime configuration |
| `installer/nvidiaruntime.yaml` | RuntimeClass definition for k3s |

### 4.3 Controller Deployment Updates [Enhanced]

Added to `scene-controller/deployment.yaml`:
- `CONTROLLER_MAX_WORKERS` and `OMP_NUM_THREADS` environment variables
- `/dev/shm` mount for shared-memory IPC between worker processes
- `reid-config` ConfigMap mount
- Configurable resource limits via `scene.resources`

### 4.4 GPU-Aware Pod Creation [Enhanced]

**File:** `manager/src/django/kubeclient.py` (+46 / -14 lines)

When a Triton model is selected, videoppl pods get `nvidia.com/gpu: 1`,
`runtimeClassName: nvidia`, and NVIDIA environment variables.

---

## 5. UI and Build System

**UI** (`sscape.js` +95, `style.css` +50): Fixed SVG coordinate mapping with
proper `viewBox` rendering, added scale controls (Fit / Native / 75% / 50% / 33%),
and a "Show IDs" toggle for debugging.

**Build system** (`Makefile` +95/-74, `kubernetes/Makefile` +26): Added
`make build-triton`, per-service rebuild (`make controller`), and
`make restart-service SERVICE=<name>`.

---

## 6. Compliance

| | |
|---|---|
| **DCO sign-off** | `Signed-off-by: Mohammed Sufiyan Saqib <mohammed.sufiyan_saqib@nokia.com>` |
| **New file headers** | `# SPDX-FileCopyrightText: (C) 2026 Nokia` |
| **Modified file headers** | `# Modifications: Nokia VPOD (Emerging Products, BLR), 2026` |
| **Python style** | 2-space indentation (Intel CI standard) |
| **Binary licensing** | `.reuse/dep5` covers `.onnx`, `.plan`, `.dali` files |
| **Git LFS** | `.gitattributes` tracks large model binaries |
