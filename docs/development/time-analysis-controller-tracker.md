<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Time handling in the legacy controller tracker (`controller/`)

Scope: how the **detection timestamp** carried in each input message and the
**system/wall-clock time** are consumed by the legacy controller tracker. Both
the controller and the standalone tracker service use the same Robot Vision
(`robot_vision` / `rv`) library — a multi-model Kalman filter plus Hungarian
matching. The Kalman filter advances its state by the *time delta* (`dt`)
between successive `track()` calls, so **whatever timestamp is handed to
`track()` is what drives the motion prediction**. This document traces where
that timestamp comes from in the controller.

The controller is implemented in Python. Two tracker variants exist:

- `IntelLabsTracking` — one `track()` call per incoming camera message
  ([controller/src/controller/ilabs_tracking.py](../../controller/src/controller/ilabs_tracking.py)).
- `TimeChunkedIntelLabsTracking` — buffers messages and dispatches the latest
  frame per camera at a fixed rate
  ([controller/src/controller/time_chunking.py](../../controller/src/controller/time_chunking.py)).

---

## 1. Where the detection timestamp enters the system

Camera detection messages arrive over MQTT and are handled by
`handleMovingObjectMessage`
([controller/src/controller/scene_controller.py](../../controller/src/controller/scene_controller.py#L477)).

The handler establishes a notion of "now" from the **system clock**, optionally
corrected by an NTP offset:

- [scene_controller.py#L491](../../controller/src/controller/scene_controller.py#L491) — `now = get_epoch_time()` (system clock, see `time.time()` in [scene_common/src/scene_common/timestamp.py#L21](../../scene_common/src/scene_common/timestamp.py#L21)).
- [scene_controller.py#L492-L494](../../controller/src/controller/scene_controller.py#L492) — `adjust_time(...)` refreshes the NTP offset (only re-queries every 300 s; see [timestamp.py#L33](../../scene_common/src/scene_common/timestamp.py#L33)).
- [scene_controller.py#L495](../../controller/src/controller/scene_controller.py#L495) — `now += self.time_offset` applies the NTP correction to the system clock.

The timestamp actually used for tracking (`msg_when`) is then selected:

- [scene_controller.py#L502-L504](../../controller/src/controller/scene_controller.py#L502) — if `rewrite_all_time` is set, the detection timestamp is **ignored** and replaced with system time: `msg_when = now` and `jdata['timestamp']` is overwritten.
- [scene_controller.py#L505-L506](../../controller/src/controller/scene_controller.py#L506) — otherwise `msg_when = get_epoch_time(jdata['timestamp'])`, i.e. the **detection timestamp from the message** (ISO‑8601 string parsed to epoch float, [timestamp.py#L21](../../scene_common/src/scene_common/timestamp.py#L21)).

### Lag gate (system clock vs detection timestamp)

- [scene_controller.py#L508](../../controller/src/controller/scene_controller.py#L508) — `lag = abs(now - msg_when)`.
- [scene_controller.py#L509-L514](../../controller/src/controller/scene_controller.py#L509) — if `lag > self.max_lag` (default 1 s, `--maxlag`) the message is **dropped** ("FELL BEHIND") unless `rewrite_bad_time` is set.
- [scene_controller.py#L515](../../controller/src/controller/scene_controller.py#L515) — when `rewrite_bad_time` is set, the detection timestamp is discarded and `msg_when = now` (system clock) is used instead.

> **Note:** the gate uses `abs(...)`, so messages whose detection timestamp is
> *too far in the future* are dropped as well as those too far in the past.

`msg_when` is forwarded into the scene pipeline:

- [scene_controller.py#L538](../../controller/src/controller/scene_controller.py#L538) — `scene.processCameraData(jdata, when=msg_when)`.

## 2. Timestamp propagation through the scene pipeline

- [scene.py#L204-L215](../../controller/src/controller/scene.py#L204) — `processCameraData` keeps the passed `when`; only if it is missing does it fall back to the system clock (`get_epoch_time()`) or to `get_epoch_time(jdata['timestamp'])`.
- [scene.py#L237](../../controller/src/controller/scene.py#L237) — `when` is attached to each created `MovingObject` (stored as `first_seen` / `Chronoloc.when`, see [moving_object.py#L188](../../controller/src/controller/moving_object.py#L188) and [moving_object.py#L376](../../controller/src/controller/moving_object.py#L376)).
- [scene.py#L325-L334](../../controller/src/controller/scene.py#L325) — `_finishProcessing` calls `tracker.trackObjects(objects, already_tracked_objects, when, ...)`.

## 3. How the timestamp reaches the Kalman filter

### Non-chunked path (`IntelLabsTracking`)

- [tracking.py#L57-L89](../../controller/src/controller/tracking.py#L57) — `trackObjects` enqueues `(new_objects, when, already_tracked_objects, STREAMING_MODE)` onto a per-category worker queue. `when` is the per-message detection timestamp.
- [tracking.py#L171-L195](../../controller/src/controller/tracking.py#L171) — the worker thread (`run`) pops the queue and calls `trackCategory(objects, when, ...)`.
- [ilabs_tracking.py#L171-L173](../../controller/src/controller/ilabs_tracking.py#L171) — `trackCategory` converts `when = datetime.fromtimestamp(when)`.
- [ilabs_tracking.py#L99](../../controller/src/controller/ilabs_tracking.py#L99) — `update_tracks` calls `self.tracker.track(rv_objects, timestamp, ...)`, handing the **detection timestamp** to the Robot Vision Kalman filter. This is the value that determines the prediction `dt`.

So in the non-chunked path, **each camera message is tracked individually using
its own detection timestamp** (or the rewritten system time, per §1).

> **Timezone note:** `datetime.fromtimestamp(when)`
> ([ilabs_tracking.py#L173](../../controller/src/controller/ilabs_tracking.py#L173))
> produces a *local-time naive* `datetime`. Because the Kalman filter only uses
> the *difference* between consecutive timestamps, the constant offset is
> harmless as long as it is applied consistently.

### Chunked path (`TimeChunkedIntelLabsTracking`)

- [time_chunking.py#L141-L174](../../controller/src/controller/time_chunking.py#L141) — `trackObjects` does **not** track immediately; it buffers `(objects, when, already_tracked)` per `camera_id`+`category` via `add_message`. Only the latest frame per camera+category is retained ([time_chunking.py#L52-L61](../../controller/src/controller/time_chunking.py#L52)).
- [time_chunking.py#L78-L123](../../controller/src/controller/time_chunking.py#L78) — `TimeChunkProcessor.run` is a timer thread that wakes every `1/rate_fps` seconds (a **system-clock-driven** interval, [time_chunking.py#L74](../../controller/src/controller/time_chunking.py#L74)) and flushes the buffer.
- [time_chunking.py#L116](../../controller/src/controller/time_chunking.py#L116) — cameras are sorted by their detection `when`.
- [time_chunking.py#L111-L119](../../controller/src/controller/time_chunking.py#L111) — the chunk's timestamp is `latest_when = max(when across all cameras)`, i.e. the **newest detection timestamp** in the chunk.
- [time_chunking.py#L123](../../controller/src/controller/time_chunking.py#L123) — enqueues `(objects_per_camera, latest_when, all_already_tracked, BATCHED_MODE)`.
- [ilabs_tracking.py#L185-L200](../../controller/src/controller/ilabs_tracking.py#L185) — `trackCategoryBatched` again does `when = datetime.fromtimestamp(when)` and feeds it to `self.tracker.track(...)` ([ilabs_tracking.py#L222](../../controller/src/controller/ilabs_tracking.py#L222), `update_tracks_batched`).

So in the chunked path the Kalman filter is advanced once per dispatch interval,
using the **maximum detection timestamp** of all buffered cameras as `dt` anchor.
The dispatch *cadence* is governed by the system clock, but the *value* handed to
`track()` is still a detection timestamp.

## 4. Uses of the system clock (independent of detection timestamps)

These code paths use the wall clock directly, not the detection timestamp:

- **NTP offset refresh & lag gate** — §1 above ([scene_controller.py#L491-L515](../../controller/src/controller/scene_controller.py#L491)).
- **`rewrite_all_time` / `rewrite_bad_time`** — substitute system time for the detection timestamp ([scene_controller.py#L502](../../controller/src/controller/scene_controller.py#L502), [scene_controller.py#L515](../../controller/src/controller/scene_controller.py#L515)).
- **Child-scene already-tracked retirement** — `mergeAlreadyTrackedObjects` stamps `last_seen = now` and retires entries using `now = get_epoch_time()` (system clock) compared against `MAX_UNRELIABLE_TIME`:
  - [ilabs_tracking.py#L136](../../controller/src/controller/ilabs_tracking.py#L136) — `now = get_epoch_time()`.
  - [ilabs_tracking.py#L164-L166](../../controller/src/controller/ilabs_tracking.py#L164) — `if now - obj.last_seen < MAX_UNRELIABLE_TIME`. This path applies to objects coming from child scenes (`retrack=False`), **not** to the Robot Vision Kalman tracks, and it mixes wall-clock with the detection-driven tracker.
- **Chunk dispatch cadence** — the timer interval ([time_chunking.py#L74](../../controller/src/controller/time_chunking.py#L74), [time_chunking.py#L90](../../controller/src/controller/time_chunking.py#L90)).
- **Output publish rate-limiting** — regulated/external publish decisions use `get_epoch_time()` ([scene_controller.py#L233](../../controller/src/controller/scene_controller.py#L233), [scene_controller.py#L273](../../controller/src/controller/scene_controller.py#L273)). These affect output rate, not tracking math.

## 5. Frame-rate parameter (config-time, not per-message)

The Robot Vision time-based parameters (`max_unreliable_time`,
`non_measurement_time_dynamic/static`) are translated into frame counts using a
reference frame rate:

- [ilabs_tracking.py#L27](../../controller/src/controller/ilabs_tracking.py#L27) — `ref_camera_frame_rate = effective_object_update_rate`.
- [ilabs_tracking.py#L50](../../controller/src/controller/ilabs_tracking.py#L50) — `self.tracker.update_tracker_params(self.ref_camera_frame_rate)`.
- [tracking.py#L91-L96](../../controller/src/controller/tracking.py#L91) — `_updateRefCameraFrameRate` re-applies the rate per category when it changes.

Default time constants (used when the tracker-config file omits them):

- [tracking.py#L22-L24](../../controller/src/controller/tracking.py#L22) — `MAX_UNRELIABLE_TIME = 0.3333`, `NON_MEASUREMENT_TIME_DYNAMIC = 0.2666`, `NON_MEASUREMENT_TIME_STATIC = 0.5333`.

## 6. Output timestamp

The controller republishes the (possibly rewritten) **input** timestamp rather
than synthesizing a new one:

- [scene_controller.py#L294](../../controller/src/controller/scene_controller.py#L294) — `'timestamp': jdata['timestamp']` in the regulated output.

## 7. Summary

| Aspect | Behavior | Reference |
| --- | --- | --- |
| Kalman `dt` source (non-chunked) | Per-message detection timestamp | [ilabs_tracking.py#L99](../../controller/src/controller/ilabs_tracking.py#L99) |
| Kalman `dt` source (chunked) | `max()` detection timestamp across cameras in the chunk | [time_chunking.py#L119](../../controller/src/controller/time_chunking.py#L119) |
| System time correction | `ntplib` offset, refreshed every 300 s, added to `now` | [scene_controller.py#L492](../../controller/src/controller/scene_controller.py#L492) |
| Lag gate | `abs(now - msg_when) > max_lag` → drop (both past & future) | [scene_controller.py#L508](../../controller/src/controller/scene_controller.py#L508) |
| Detection-time override | `rewrite_all_time` (always) / `rewrite_bad_time` (on lag) → use system time | [scene_controller.py#L502](../../controller/src/controller/scene_controller.py#L502) |
| Dispatch cadence (chunked) | System-clock timer at `time_chunking_rate_fps` | [time_chunking.py#L74](../../controller/src/controller/time_chunking.py#L74) |
| System clock in tracking math | Child-scene already-tracked retirement only | [ilabs_tracking.py#L136](../../controller/src/controller/ilabs_tracking.py#L136) |
| Output timestamp | Echoes input (possibly rewritten) timestamp | [scene_controller.py#L294](../../controller/src/controller/scene_controller.py#L294) |
