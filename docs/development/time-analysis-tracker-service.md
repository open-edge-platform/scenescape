<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Time handling in the tracker service (`tracker/`)

Scope: how the **detection timestamp** carried in each input message and the
**system/wall-clock time** are consumed by the standalone C++ tracker service.
Like the legacy controller, the tracker service uses the Robot Vision
(`rv::tracking`) library — a multi-model Kalman filter plus Hungarian matching.
The Kalman filter advances its state by the *time delta* (`dt`) between
successive `track()` calls, so **whatever timestamp is handed to `track()` is
what drives the motion prediction**. This document traces that timestamp through
the service.

Unlike the controller, the tracker service is C++ and **always** runs the
time-chunked pipeline: a buffer keyed by `(scene, category) → camera` feeds a
fixed-rate scheduler that dispatches chunks to per-scope worker threads.

Pipeline:

```
MQTT msg ─▶ MessageHandler ─▶ TimeChunkBuffer ─▶ TimeChunkScheduler ─▶ TrackingWorker ─▶ rv::track()
```

---

## 1. Clock injection (system clock vs NTP)

Time "now" is provided through an injectable `ClockFn`
([tracker/inc/time_utils.hpp#L22](../../tracker/inc/time_utils.hpp#L22)):

- [main.cpp#L131](../../tracker/src/main.cpp#L131) — default `clock_fn = makeSystemClock()` (`system_clock::now()`, [time_utils.cpp#L24](../../tracker/src/time_utils.cpp#L24)).
- [main.cpp#L132-L137](../../tracker/src/main.cpp#L132) — if `infrastructure.ntp` is configured, an in-process `NtpClock` is started and `clock_fn = ntp_clock.asClockFn()`.
- [time_utils.hpp#L86-L89](../../tracker/inc/time_utils.hpp#L86) — `NtpClock::now()` returns `system_clock::now() + offset_ns`, where the offset is computed by a background RFC‑5905 NTP exchange ([time_utils.cpp#L52](../../tracker/src/time_utils.cpp#L52), offset formula at [time_utils.cpp#L186](../../tracker/src/time_utils.cpp#L186)).

The same `clock_fn` is injected into the `MessageHandler`, the
`TimeChunkScheduler`, and every `TrackingWorker`, so all wall-clock reads share
one (optionally NTP-corrected) source.

> The tracker service has its **own** NTP implementation (raw UDP, RFC 5905),
> whereas the controller uses the `ntplib` Python package. Both yield an additive
> offset on top of the system clock.

## 2. Where the detection timestamp enters the system

`MessageHandler::handleCameraMessage`
([tracker/src/message_handler.cpp#L184](../../tracker/src/message_handler.cpp#L184))
receives each MQTT camera message.

- [message_handler.cpp#L379-L391](../../tracker/src/message_handler.cpp#L379) — `parseCameraMessage` extracts the `/timestamp` string field (ISO‑8601).
- [message_handler.cpp#L252-L260](../../tracker/src/message_handler.cpp#L252) — `parseTimestamp(message->timestamp)` converts it to a `sys_time<milliseconds>`; messages with an unparseable timestamp are **dropped** ([time_utils.cpp#L256](../../tracker/src/time_utils.cpp#L256)).

### Lag gate (system clock vs detection timestamp)

- [message_handler.cpp#L262-L270](../../tracker/src/message_handler.cpp#L262) — `isMessageLagged(*msg_time)` decides whether to drop.
- [message_handler.cpp#L475-L484](../../tracker/src/message_handler.cpp#L475) — implementation: `now = clock_fn_()`, `lag = now - msg_time`, drop if `lag > max_lag_s` (default 1.0 s, [tracker/config/tracker.json#L44](../../tracker/config/tracker.json#L44)).

> **Difference vs controller:** the gate uses a *signed* difference
> (`now - msg_time`), **not** `abs(...)`. A message whose detection timestamp is
> in the *future* (negative lag) is therefore **never** dropped by the lag gate,
> whereas the controller drops both past and future outliers.
>
> **Also note:** the tracker service has **no** `rewrite_all_time` /
> `rewrite_bad_time` equivalent. A lagged message is dropped outright; it is
> never re-stamped with system time. The detection timestamp is otherwise always
> preserved (the only system-time substitution is the empty-chunk fallback, §4).

## 3. Buffering: detection timestamp stored per batch

For each active `(scene, category)` scope, a `DetectionBatch` is created and
stored:

- [message_handler.cpp#L279](../../tracker/src/message_handler.cpp#L279) — `receive_time = std::chrono::steady_clock::now()` — a **monotonic wall-clock arrival time** (used only for ordering, not for tracking math).
- [message_handler.cpp#L308-L314](../../tracker/src/message_handler.cpp#L308) — the batch records both `timestamp_iso` (original string) and `timestamp = *msg_time` (the parsed **detection timestamp**).
- [message_handler.cpp#L320](../../tracker/src/message_handler.cpp#L320) — `buffer_.add(scope, camera_id, std::move(batch))`.
- [time_chunk_buffer.cpp#L10-L13](../../tracker/src/time_chunk_buffer.cpp#L10) — the buffer keeps only the **latest batch per camera** within a scope (last-write-wins), mirroring the controller's "latest frame only" optimization.

Empty batches are intentionally created for scopes not present in the current
message ([message_handler.cpp#L274-L277](../../tracker/src/message_handler.cpp#L274)) so the Kalman filter can keep advancing time and age out stale tracks.

## 4. Scheduling and the canonical track timestamp

`TimeChunkScheduler` flushes the buffer at a fixed rate:

- [time_chunk_scheduler.cpp#L24-L25](../../tracker/src/time_chunk_scheduler.cpp#L24) — interval = `1000 / time_chunking_rate_fps` ms (default 15 fps, [tracker/config/tracker.json#L45](../../tracker/config/tracker.json#L45)).
- [time_chunk_scheduler.cpp#L89-L101](../../tracker/src/time_chunk_scheduler.cpp#L89) — `run()` waits one interval on a condition variable (system-clock-driven cadence) then `buffer_.pop_all()` and `dispatch()`.
- [time_chunk_scheduler.cpp#L184-L188](../../tracker/src/time_chunk_scheduler.cpp#L184) — `build_chunk` sorts the camera batches by `receive_time` (monotonic arrival order), **not** by detection timestamp.

The worker then derives the timestamp fed to the Kalman filter:

- [tracking_worker.cpp#L161-L167](../../tracker/src/tracking_worker.cpp#L161) —
  ```cpp
  auto now = clock_fn_();
  auto track_timestamp = chunk.camera_batches.empty()
                             ? now                                   // fallback: system clock
                             : chunk.camera_batches.back().timestamp; // detection timestamp
  ```
  Because batches are sorted by `receive_time`, `back()` is the **most recently
  received** camera batch, and its **detection timestamp** becomes the chunk's
  `track_timestamp`.
- [tracking_worker.cpp#L174](../../tracker/src/tracking_worker.cpp#L174) — `match_and_convert(..., track_timestamp)`.
- [tracking_worker.cpp#L271](../../tracker/src/tracking_worker.cpp#L271) — `tracker_.track(objects_per_camera, timestamp, ...)` — the detection timestamp drives the Kalman prediction `dt`. With no detections, `track()` still runs to advance time and increment non-measurement counters ([tracking_worker.cpp#L266-L272](../../tracker/src/tracking_worker.cpp#L266)).

> **Key behavioral difference vs the controller's chunked path:** the controller
> anchors the chunk on `max()` of all cameras' detection timestamps
> ([time_chunking.py#L119](../../controller/src/controller/time_chunking.py#L119)),
> while the tracker service anchors on the detection timestamp of the
> *last-received* batch (`back()` after sorting by `receive_time`). These can
> diverge when message arrival order does not match detection-timestamp order
> (e.g. clock skew between cameras, or network reordering).

## 5. Uses of the system clock (independent of detection timestamps)

- **Lag gate** — `now = clock_fn_()` ([message_handler.cpp#L476](../../tracker/src/message_handler.cpp#L476)).
- **Empty-chunk fallback** — `track_timestamp = now` only when a chunk has no batches ([tracking_worker.cpp#L162-L164](../../tracker/src/tracking_worker.cpp#L162)); the published `timestamp_iso` is then `formatTimestamp(now)` ([tracking_worker.cpp#L165-L167](../../tracker/src/tracking_worker.cpp#L165)).
- **Dispatch cadence** — the scheduler interval timer ([time_chunk_scheduler.cpp#L24](../../tracker/src/time_chunk_scheduler.cpp#L24), [time_chunk_scheduler.cpp#L106-L108](../../tracker/src/time_chunk_scheduler.cpp#L106)).
- **Arrival ordering** — `steady_clock` `receive_time` used to sort batches ([message_handler.cpp#L279](../../tracker/src/message_handler.cpp#L279), [time_chunk_scheduler.cpp#L186](../../tracker/src/time_chunk_scheduler.cpp#L186)) and `chunk_time` ([time_chunk_scheduler.cpp#L178](../../tracker/src/time_chunk_scheduler.cpp#L178)). These never reach the Kalman filter.

There is **no** wall-clock-based track retirement equivalent to the controller's
`mergeAlreadyTrackedObjects` — the tracker service only subscribes to camera
topics ([message_handler.cpp#L107-L135](../../tracker/src/message_handler.cpp#L107)) and has no child-scene `already_tracked` merge path. All track aging is handled inside `rv::track()` using the detection-timestamp `dt`.

## 6. Frame-rate parameter (config-time, not per-message)

- [tracking_worker.cpp#L33-L50](../../tracker/src/tracking_worker.cpp#L33) — `build_tracker_config` maps `max_unreliable_time_s`, `non_measurement_time_dynamic_s`, `non_measurement_time_static_s` (config defaults 1.0 / 0.8 / 1.6 s, [tracker/config/tracker.json#L46-L48](../../tracker/config/tracker.json#L46)).
- [tracking_worker.cpp#L66](../../tracker/src/tracking_worker.cpp#L66) — `tracker_.updateTrackerParams(time_chunking_rate_fps)` translates the time-based parameters into frame counts using the **fixed chunk rate** (the controller uses a per-camera `ref_camera_frame_rate` that can change at runtime).

## 7. Output timestamp

- [tracking_worker.cpp#L165-L183](../../tracker/src/tracking_worker.cpp#L165) — the published timestamp is the **detection timestamp string** of the last-received batch (`back().timestamp_iso`), or `formatTimestamp(now)` for an empty chunk. The service does not echo a separately-rewritten input timestamp; it forwards the chosen detection timestamp.

## 8. Summary

| Aspect | Behavior | Reference |
| --- | --- | --- |
| Kalman `dt` source | Detection timestamp of the **last-received** batch in the chunk | [tracking_worker.cpp#L163](../../tracker/src/tracking_worker.cpp#L163) |
| Chunk anchor selection | `back()` after sorting by `receive_time` (arrival order) | [time_chunk_scheduler.cpp#L186](../../tracker/src/time_chunk_scheduler.cpp#L186) |
| System time correction | Optional in-process RFC‑5905 `NtpClock`, additive offset | [time_utils.hpp#L86](../../tracker/inc/time_utils.hpp#L86) |
| Lag gate | `now - msg_time > max_lag_s` → drop (**past only**, not `abs`) | [message_handler.cpp#L477](../../tracker/src/message_handler.cpp#L477) |
| Detection-time override | None — lagged messages are dropped, never re-stamped | [message_handler.cpp#L262](../../tracker/src/message_handler.cpp#L262) |
| Dispatch cadence | System-clock timer at `time_chunking_rate_fps` | [time_chunk_scheduler.cpp#L24](../../tracker/src/time_chunk_scheduler.cpp#L24) |
| System clock in tracking math | Empty-chunk fallback only | [tracking_worker.cpp#L162](../../tracker/src/tracking_worker.cpp#L162) |
| Output timestamp | Last-received batch's detection timestamp (or `now` if empty) | [tracking_worker.cpp#L165](../../tracker/src/tracking_worker.cpp#L165) |

## 9. Controller vs tracker service — time differences at a glance

| Dimension | Controller (`controller/`) | Tracker service (`tracker/`) |
| --- | --- | --- |
| Language | Python | C++ |
| Chunked anchor timestamp | `max()` of cameras' detection timestamps | Detection timestamp of last-*received* batch |
| Lag gate | `abs(now - msg_when) > max_lag` (past **and** future) | `now - msg_time > max_lag_s` (past only) |
| Re-stamp on lag/always | `rewrite_bad_time` / `rewrite_all_time` substitute system time | Not supported (drop only) |
| NTP | `ntplib`, refreshed every 300 s, offset added to `now` | In-process RFC‑5905 `NtpClock`, injectable `ClockFn` |
| Frame-rate param | Per-camera `ref_camera_frame_rate`, runtime-updatable | Fixed `time_chunking_rate_fps` |
| Wall-clock in tracking math | Child-scene already-tracked retirement | None (empty-chunk fallback only) |
| Non-chunked mode | Available (`IntelLabsTracking`) | Not available (always chunked) |
