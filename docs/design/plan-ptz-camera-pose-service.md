<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# PTZ Positioning Capability: Revised Implementation and Branching Plan

## Goal

Implement PTZ as a capability of one Positioning deployable: an ONVIF poller passes versioned protobuf samples in-process to the Resolver, which reads Manager-owned home calibration and publishes resolved PoseContext over MQTT. Controller and Tracker independently join poses to detections using the same dwell contract.
A PTZ camera is a tracking source only while parked; each reposition incurs a measured motion, settling, and dwell blackout.

Phases have focused acceptance criteria. Keep Controller and Tracker feature flags disabled until each profile independently passes its shadow-mode gates.

## Prerequisites Outside the Feature Branch

1. **Auto-Calibration hardening:** Submit a small prerequisite PR to `main`, unless equivalent protection has already merged. Lift the PoC's point-spread/degenerate-geometry rejection into Auto-Calibration. Test degenerate inputs and verify valid calibration behavior is unchanged.

2. **Golden-data measurement session:** Run the isolated PoC lab measurement on hardware and commit `tests/data/ptz/reprojection_golden.json` before closing Phase 1 math acceptance or starting Phase 6 acceptance. Store no images. Include measured calibration values and held-out residuals across both travel directions and supported range, plus instrument/version, camera model and firmware, `calibration_version`, date, operator, and measurement provenance. Development can use provisional fixtures before this dataset exists. Deployment spatial-error, latency, and post-motion availability budgets are also required for Phase 6.

## Integration Branch and Phase PRs

Create `feature/ptz-camera-pose-service` from a base containing the PTZ design. Verify `HEAD` and `git status` first; preserve unrelated worktree changes. If the design is not in `main`, either wait for it to merge or base the feature branch on the design branch and stack the final PR accordingly.

Every phase PR targets the integration branch, never `main`. Branch sequential work from the latest merged integration tip. Phase 3a is on the critical path for every later phase. Phase 3b starts after 3a merges and can run in parallel with Phases 4 and 5; those consumers use Phase 1 for implementation/conformance, Phase 3a for broker/status/ACL end-to-end wiring, and Phase 3b only for runs against resolved poses. Open the final PR to `main` after Phase 6 acceptance.

| Phase                                         | Branch                                    | PR target          |
| --------------------------------------------- | ----------------------------------------- | ------------------ |
| 1. Contracts and pose math                    | `feature/ptz-pose/01-contracts-math`      | Integration branch |
| 2. Manager calibration and import contract    | `feature/ptz-pose/02-manager-calibration` | Integration branch |
| 3a. Positioning service skeleton              | `feature/ptz-pose/03a-service-skeleton`   | Integration branch |
| 3b. PTZ poller and resolver                   | `feature/ptz-pose/03b-ptz-runtime`        | Integration branch |
| 4. Controller dwell consumer                  | `feature/ptz-pose/04-controller-consumer` | Integration branch |
| 5. Tracker dwell consumer                     | `feature/ptz-pose/05-tracker-consumer`    | Integration branch |
| 6. Shadow validation and feature-flag rollout | `feature/ptz-pose/06-acceptance`          | Integration branch |

## Implementation Phases

### 1. Contracts and Pose Math

Define the versioned `scenescape.ptz.v1` protobuf at `api/positioning/v1/`; generate Python message types for the in-process poller-to-Resolver boundary. Preserve the versioned `SubmitPTZSample` contract for a possible future external producer, but do not add an internal gRPC channel. Define PoseContext, MQTT topics, compatibility policy, shared conformance vectors, and `valid_until`. Add the PoseContext definition to `controller/src/schema/metadata.schema.json`; both Controller and Tracker validate incoming MQTT payloads against it and additionally reject non-finite matrix values or oversized arrays/payloads before use.

**Normative dwell admission (v1).** No pending-detection queue, per-detection wait, timestamp bracketing, interpolation, extrapolation, or shared C++ selector. Each consumer tracks `stationary_since` and `stationary_since_uncertainty_s` per source from contiguous valid stationary PoseContexts. The latter is the `timestamp_uncertainty_s` of the PoseContext that established `stationary_since`, retained in the source's dwell state. Reset dwell on invalid/non-stationary state, calibration change, Resolver session change, source/frame mismatch, sequence gap, or non-increasing sequence.

Let `latest_stationary` be the newest received valid stationary PoseContext in the current uninterrupted dwell. Reject the observation if `observation.timestamp > latest_stationary.timestamp`; the camera's pose is unknown after the latest stationary sample, so use `invalid_reason: no_pose_available` and `reason_detail: no_sample`. Also reject if `observation.timestamp - max_detection_timestamp_uncertainty_s < stationary_since`. Detection age is computed against the synchronized local clock and must not exceed `max_detection_pipeline_latency_s`.

The normative dwell condition implemented by both consumers is:

`dwell_elapsed_s = latest_stationary.timestamp - stationary_since`

`dwell_elapsed_s - latest_stationary.timestamp_uncertainty_s - stationary_since_uncertainty_s >= max_detection_pipeline_latency_s`

Admit only when the dwell condition, timestamp bounds, valid/fresh pose, matching source/frame/calibration version, and detection-age bound all pass. During motion, settling, incomplete dwell, or any failed gate, drop immediately without blocking the MQTT callback; existing tracks continue normal prediction/aging. Use the latest valid pose. A PTZ source contributes detections only while parked; each reposition incurs motion, settle, and dwell blackout.

Resolver session changes are detected by subscribing to `scenescape/positioning/status/{resolver_id}`. The deployment-owned manifest `deployment/positioning-assignments.json` contains only the single-owner mapping `source_id -> resolver_id`; Positioning, Controller, and Tracker receive the same read-only manifest and do not read another service's private config. Camera-to-scene membership remains authoritative in Manager (`Cam.scene`); consumers derive their assigned camera subscriptions from their Manager-loaded scene, and Manager derives the corresponding ACL scope from that same assignment. A changed status `timestamp` resets dwell for mapped sources even if sequence continues. Status does not establish pose validity.

Sequence semantics are normative: `PoseContext.sequence` equals the accepted `PTZSample.sequence` per source. Every accepted sample yields exactly one PoseContext, valid or invalid, including unchanged positions. A sample rejected by Resolver input validation yields no context and therefore appears as a sequence gap. Consumers reset dwell on every non-contiguous or non-increasing sequence.

Require `max_pose_age_s >= poll_interval_s + max_timestamp_uncertainty_s` at startup. Require a measured hard `max_detection_pipeline_latency_s`, bounded `max_detection_timestamp_uncertainty_s`, trustworthy detection acquisition timestamps, and synchronized clocks before enabling PTZ. `max_lag` is not a substitute. The design's midpoint timestamp and local freshness rules remain in force.

`frame_id` is provisional in v1. Compose child-scene transforms explicitly into the target scene frame and fail closed if unresolved; nested scenes are not blanket-disabled, but must pass the Phase 6 frame-mapping gate before enablement. The resolved topic is `scenescape/positioning/pose/{source_id}`; v1 `source_id` is the Manager camera UID. Keep it source-keyed and distinct from `scenescape/data/camera/+/+`.

Use per-axis scale/curves, backlash, and calibrated pan- and tilt-axis orientations with calibration-defined frames/order. Phase 1 defines a provisional, versioned tilt-axis parameterization in `ptz_calibration`; hardware measurement validates it before enablement. Parameterization changes must not change PoseContext or dwell contracts. Verify advertised ONVIF URI/ranges against calibration and reuse repository/SciPy transform conversions. Production calibration tooling is out of scope.

Use canonical `invalid_reason` values `no_pose_available`, `pose_expired`, and `invalid_pose`, with the closed PTZ `reason_detail` set: `no_sample`, `sample_stale`, `moving`, `settling`, `calibration_missing`, `calibration_changed`, `invalid_sample`, `backlash_unknown`. Fixtures define every rejection-to-reason mapping. Include `temporal_score`, `calibration_score`, `score`, and calibration-time `reprojection_rms_px`; the Resolver computes publication quality, consumers recompute local age, and scores never replace validity gates.

**Configuration contract** (all deployment-owned values must be present and validated before enabling the source):

| Parameter                               | Unit         | Default / requirement        | Owner                                    | Startup validation                                                                                      |
| --------------------------------------- | ------------ | ---------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `poll_interval_s`                       | s            | 0.2 (5 Hz)                   | Positioning default; deployment override | Positive; contributes to pose-age bound                                                                 |
| `max_pose_age_s`                        | s            | Required                     | Deployment                               | `>= poll_interval_s + max_timestamp_uncertainty_s`                                                      |
| `max_timestamp_uncertainty_s`           | s            | Required                     | Deployment                               | Finite, nonnegative, and compatible with max pose age                                                   |
| `max_clock_offset_s`                    | s            | Required                     | Deployment                               | Positive; source disabled while measured NTP offset exceeds it                                          |
| `max_detection_pipeline_latency_s`      | s            | Required measured hard bound | Deployment                               | Positive; detection age and dwell limit                                                                 |
| `max_detection_timestamp_uncertainty_s` | s            | Required                     | Deployment                               | Finite, nonnegative; detection source must provide trustworthy timestamps                               |
| `settle_angular_threshold_deg`          | deg per axis | Required                     | PTZ calibration/profile                  | Finite, positive, within calibrated travel                                                              |
| `settle_interval_s`                     | s            | Required                     | PTZ calibration/profile                  | Positive; ring buffer must cover the interval                                                           |
| `backlash_home_tolerance_deg`           | deg per axis | Required                     | PTZ calibration                          | Finite, positive, within calibrated travel                                                              |
| `backlash_history_s`                    | s per axis   | Required from calibration    | PTZ calibration                          | Positive; included when validating ring capacity                                                        |
| `sample_ring_buffer_size`               | samples      | 64 default                   | Positioning code/config                  | At startup require `>= ceil(max(settle_interval_s, backlash_history_s) / poll_interval_s) + 2`; bounded |
| `target_reprojection_rms_px`            | px           | Required                     | Deployment/calibration policy            | Finite and positive; missing/exceeded calibration invalidates pose                                      |
| `calibration_residual_threshold_px`     | px           | Required                     | Deployment import policy                 | Finite and positive; import rejects larger measured residual                                            |

**Shared conformance fixture:** commit JSON at `tests/data/ptz/dwell_conformance.json`. Each vector contains ordered PoseContext inputs, observation timestamp and uncertainty, consumer configuration, expected accept/reject decision, `invalid_reason`, and `reason_detail`. Both the Python Controller and C++ Tracker suites load this exact file unmodified.

Vectors cover: observation newer than latest stationary context; observation exactly at and at `stationary_since - ε`; dwell that passes without uncertainty subtraction but fails with it; sequence gap and non-monotonic sequence; Resolver status/LWT session change despite contiguous source sequence; motion/settling/reset/recovery; source/frame/calibration mismatch; freshness/`valid_until` boundaries; and invalid pose reasons. Golden math acceptance uses the committed hardware dataset; implementation may proceed with provisional fixtures before it exists.

**Documentation:** Publish protobuf compatibility, schema location, MQTT topics/QoS, sequence and dwell rules, configuration table, shared fixture path/format, failure mapping, and the golden-data reference.

Phase 1 math acceptance closes only after the golden measurement dataset is committed; implementation can proceed against provisional fixtures before then.

### 2. Manager Calibration and Import Contract

Add nullable `ptz_calibration` JSONField (`default=None`, `null=True`, `blank=True`) to `Cam`, add it to `CAM_SERIALIZER_FIELDS`, and expose it as a read/write field through `CamSerializer` on the camera-specific API: `GET`, `POST`, and `PUT /api/v1/camera/{uid}`; collection reads are `GET /api/v1/cameras`. Keep home pose/calibration readable by the Positioning service's least-privilege token client. Validate in a reusable `CamSerializer` validation helper at the REST boundary for stable field errors. Generate a Django migration with semantic name `add_ptz_calibration_to_cam` (Django assigns the numeric prefix).

Require home pan/tilt and per-axis approach directions; `calibration_version`; advertised position-space URI/ranges; per-axis scale/curve; backlash parameters; `settle_angular_threshold_deg`, `settle_interval_s`, per-axis `backlash_home_tolerance_deg`, per-axis `backlash_history_s`; calibrated pan/tilt axes, coordinate frames and inversion; and quality/provenance including `reprojection_rms_px`. These four motion/backlash parameters are stored in and validated as part of `ptz_calibration`, not as Positioning-only overrides. For point-correspondence cameras derive home transform from the computed pose matrix, not stored Euler fields. Incomplete/incompatible blocks are `calibration_missing`; never infer home from live pose. The validated import rejects residuals above the deployment threshold. On camera save, publish `scenescape/cmd/camera/config/{camera_id}` with the new version after commit; rollback publishes nothing.

Register all three topics together in `scene_common.mqtt.PubSub`, `PubSubACL.TOPIC_CHOICES`, one Django ACL migration, `manager/config/user_access_config.json`, the `api.yaml` topic enum, and `constants.js`: `scenescape/cmd/camera/config/{camera_id}` (Manager publishes invalidation), `scenescape/positioning/pose/{source_id}` (Positioning publishes; Controller/Tracker subscribe only to cameras assigned to their scenes in Manager), and `scenescape/positioning/status/{resolver_id}` (Positioning publishes; assigned consumers subscribe). ACL rules for consumer pose reads are generated/enforced from Manager's authoritative `Cam.scene` membership, not from the deployment manifest; write access remains limited to the named topic publisher.

**Tests and acceptance:** both camera transform types; valid, partial, malformed, incompatible, and out-of-threshold data; stable API errors; read-only API round-trip; transaction rollback does not invalidate; read-only client can retrieve complete home/calibration. A per-camera onboarding procedure uses the isolated PoC/Auto-Calibration workflow, tilt sweeps both directions, and held-out residual validation. Production calibration tooling remains out of scope.

**Documentation:** Document calibration schema, API validation/import, invalidation, and per-camera onboarding.
### 3a. Positioning Service Skeleton

**Infrastructure only:** Phase 3a contains no ONVIF client, no camera polling, no PTZ sample handling, no calibration interpretation, and no pose math. It establishes build, test, broker identity, and deployment wiring before runtime behavior is introduced.

Create the service tree following `cluster_analytics/`: `positioning/Dockerfile`, `positioning/Makefile`, `requirements-build.txt`, `requirements-runtime.txt`, `src/positioning/` with a minimal service entrypoint, `config/positioning.json`, `tests/__init__.py`, `tests/service/`, `tests/README.md`, `README.md`, `docs/README.md`, and required `Agents.md`. Add SPDX headers to all new files.

Update all root `Makefile` component registrations: `CORE_IMAGE_FOLDERS`, `IMAGE_FOLDERS`, the explicit `build-common` dependency list, `TEST_IMAGE_FOLDERS`, and `TEST_IMAGES` so `scenescape-positioning-test` is built by `make setup-tests` and its suite runs under root test targets. Update root help text and clean/rebuild targets as well.

Update `tools/certificates/Makefile`: add `positioning-cert` with `HOST=positioning` and `KEY_USAGE=clientAuth`, generating `$(SECRETSDIR)/certs/scenescape-positioning.key` and `.crt`; add `positioning-csr` following `reid-csr`; register both in `.PHONY`, `deploy-certificates`, and `deploy-csr`. `make init-secrets` must produce the key/certificate. Mount the CA, client certificate, and key read-only.

Create the `positioning.auth` broker identity and bind it to Phase 2 ACL entries. In 3a, write access is limited to `scenescape/positioning/status/{resolver_id}` and read access to `scenescape/cmd/camera/config/{camera_id}`. Test that this identity cannot publish outside its write scope. The minimal service connects to Mosquitto over mTLS using its own certificate and auth file, publishes retained status plus LWT, and remains healthy without PTZ configuration.

Add `tests/compose/compose.positioning.yml` and include it in `tests/utils/profiles.py` compositions used by Controller/scene and Tracker service runs. Add a `sample_data/compose/` override only if a demo scenario requires one. Provision the dedicated auth secret, client cert/CA, broker dependency, and health/readiness check in the test stack.

Add `kubernetes/scenescape-chart/templates/positioning/` deployment, service, and configmap templates. Add Positioning image/config values to `values.yaml`; wire auth and client certificate secret mounts through `_secrets.tpl` and the shared certificate-volume helper; reference the existing `ntp` chart component. Verify Helm renders and deploys the service.

Create root `deployment/` and `deployment/positioning-assignments.json` in 3a. The manifest contains only the single-owner `source_id -> resolver_id` mapping, never camera-to-scene membership. Also define the replay artifact sink before consumers start shadow work: services emit sampled JSONL records to stdout, and the acceptance harness combines Controller/Tracker records by `run_id` into immutable `tests/artifacts/ptz/shadow/<run_id>.jsonl`, published as the CI/acceptance artifact. Services do not write local files or require production volumes; field runs export the equivalent named bundle from structured logs.

**3a acceptance (infrastructure only):**

- Root `make positioning` builds the image; `make init-secrets` emits the client key and certificate.
- The container starts without PTZ configuration, passes health checks, connects to the broker over mTLS, and publishes retained status plus LWT.
- The broker identity is denied publish outside its status topic ACL and can read only camera-configuration invalidation.
- `scenescape-positioning-test` builds and the minimal suite runs under root test targets.
- The Compose fragment is included in Controller/scene and Tracker test compositions.
- The Helm chart renders and deploys with the new template, config, secret, certificate, and NTP references.
- `positioning/Agents.md`, `README.md`, `docs/README.md`, and the assignments manifest exist.

**Documentation:** Document component layout, build/test targets, certificate and broker identity provisioning, Compose/Helm deployment, assignment manifest, artifact sink, and rollback in `positioning/docs/README.md`; link it from `positioning/Agents.md` and `positioning/README.md`.


### 3b. PTZ Poller and Resolver

Depends on Phases 1, 2, and 3a. Runtime development can use contract fixtures before either consumer phase; Phases 4 and 5 may proceed after 3a merges and need 3b only for runs against real resolved poses.

Implement the PTZ-specific poller and Resolver modules inside the 3a Positioning shell. The shell owns sample ingest/validation, Manager calibration load/cache/invalidation, motion/settle state, publication, status/LWT, freshness, and health; the replaceable PTZ model owns axis scale/curves, backlash, calibrated axis transforms, and pose composition. Adding a second source type must not require changes to the generic shell.

Select and pin the ONVIF client in this phase. Record the package/version decision and evaluate active maintenance, license, supported Python/runtime versions, API coverage for GetStatus and position-space metadata, and dependency pinning. Do not clone/vendor source during image build. Poll every 0.2 s by default, including while stationary. Emit generated `PTZSample` messages in-process with midpoint timestamp, at least half-round-trip uncertainty, raw position/ranges/URI, per-camera sequence, and a new `adapter_instance_id` after poller restart. No internal gRPC, retry queue, stale replay, calibration math in poller, or raw PTZ MQTT. Keep credentials in mounted deployment secrets and redact logs.

Load calibration through authenticated read-only Manager API access. Validate finite values, timestamps, sequence/order, reported position space/ranges, and calibration version. A camera-scoped invalidation drops cache and requires reload before another valid pose; failed reload invalidates the source, with periodic read as recovery. Each Positioning instance's `resolver_id` comes from `positioning/config/positioning.json`; its assigned sources are derived solely from entries targeting that resolver in the shared `deployment/positioning-assignments.json`. Validate every configured source maps to exactly one deployed resolver and every mapping target names a configured instance. Controller and Tracker read only the source-to-resolver mapping there; their scene camera lists and MQTT subscription/ACL scopes come from Manager's authoritative scene assignment. Replica count alone is not a scaling mechanism; use a lease only if dynamic ownership is later required.
Record the PoC snapshot and fitting script as described under PoC Boundary.

At startup verify NTP synchronization against configured `max_clock_offset_s` and emit clock offset. If a source's clock exceeds the bound or NTP is unavailable, keep the service running but mark affected PTZ sources invalid/disabled until synchronization recovers. Maintain a bounded sample ring buffer sized for settle and backlash history. Derive motion state from measured event timestamps with an injectable clock. Backlash becomes unknown after Resolver/poller restart or calibration change unless the sample is within calibrated home tolerance and approach direction is known; unknown contributing axes never yield valid pose.

Publish exactly one valid/invalid PoseContext per accepted sample on retained QoS 0 `scenescape/positioning/pose/{source_id}`. Invalid raw samples yield no PoseContext. Extend the 3a-owned single status/LWT publisher with runtime health; do not create a second publisher for `scenescape/positioning/status/{resolver_id}`. Consumers enforce freshness independently.

Use metric prefix `positioning_`; minimum names and types: `positioning_pose_age_seconds` (histogram), `positioning_pose_sequence_gaps_total` (counter), `positioning_dwell_state_seconds` (histogram with bounded state label), `positioning_dwell_rejected_detections_total` (counter with bounded `reason_detail`), `positioning_motion_state_seconds` (histogram with bounded `motion_state`), `positioning_calibration_version_info` (info gauge), `positioning_projection_drift_pixels` and `positioning_projection_drift_meters` (histograms), and `positioning_clock_offset_seconds` (gauge). Use camera id only where per-camera series are required; never label by detection/object id. No pending-queue or bracket-wait metrics.

**3b tests and acceptance:** fake ONVIF device; timestamp/uncertainty and raw validation; sequence/restart; secret redaction; motion/backlash; calibration reload; deterministic replay; one context per accepted sample; valid/invalid retained pose; NTP fail-closed; and runtime metrics. The 3a identity/ACL/health/Helm and test-image checks remain owned by Phase 3a. No certificate-to-camera authorization test is needed for the in-process path. Adding a second source type must not require changes to the generic shell.

**Documentation:** Document ONVIF dependency choice, polling/sample contract, calibration reload, motion/backlash, NTP behavior, runtime metrics, and runtime rollback.

### 4. Controller Dwell Consumer

This phase depends on Phase 1 contracts and shared vectors. Phase 3a provides broker identity, topic registration, and status/LWT for subscription and ACL end-to-end wiring; Phase 3b is required only for runs against real resolved poses. Subscribe to PoseContext/status only for cameras in the Controller's Manager-loaded scene; enforce ACL from Manager's scene assignment and test unauthorized-camera subscription denial. Implement dwell natively at the Controller projection ingress, with no shared C++ selector or detection queue. Pass immutable per-frame pose context through `Scene.processCameraData()` and `MovingObject`, preserving static home pose and intrinsics.

Track `stationary_since` and its uncertainty from the first valid stationary context; require contiguous, strictly increasing sequences. Reset on invalid/non-stationary state, sequence gap/non-increase, calibration change, configured Resolver session change (per Phase 1 status mapping), or source/frame mismatch. Apply the single normative Phase 1 dwell and observation-time inequality without restating or weakening it. Drop detections immediately on any failed gate; existing tracks continue normal aging/prediction and rejected detections neither initiate nor update MOT.

For visibility, evaluate every scene camera using its latest valid pose within the age bound. A camera with no valid PTZ pose does not see the object; never fall back to its home view region. Reject PTZ scenes using `rewrite_all_time` or `rewrite_bad_time`.

Configure independent default-off flags `CONTROLLER_PTZ_ENABLED` and `CONTROLLER_PTZ_SHADOW_MODE` in the Controller deployment environment/Compose service. Shadow mode computes but never feeds candidate detections to MOT or changes track state. Emit sampled structured JSONL records to Controller logs and the replay artifact sink with source, sequence, calibration version, pose age, timestamp uncertainty, dwell elapsed, decision/reason detail, candidate projection, and residual versus static baseline.

**Tests and acceptance:** load the exact Phase 1 JSON vectors unchanged; test scene camera assignment/ACLs, schema and finite matrix validation, session/sequence resets, age and `valid_until`, child-scene composition/fail-closed behavior, shadow isolation, visibility, and regulated output. Compare home pose fed as a synthetic PoseContext with static projection using `ε_synthetic = 1e-6 px` as a double-precision round-off tolerance; confirm the transform path meets it, and do not treat it as a hardware budget. Invalid, moving, settling, incomplete-dwell, and over-age detections never reach MOT; forbidden rewrite policies fail visibly.

**Documentation:** Document Controller flags/configuration, scene-scoped subscriptions, dwell rule reference, rewrite rejection, frame mapping, shadow record/sink, and rollback.

### 5. Tracker Dwell Consumer

This phase depends on Phase 1 contracts/vectors and can be implemented in parallel with Phase 4 after Phase 3a merges. Phase 3a provides broker identity, topic registration, and status/LWT for subscription and ACL end-to-end wiring; Phase 3b is required only for runs against real resolved poses. Subscribe to pose/status topics only for cameras in the Tracker's Manager-loaded scene, enforced by least-privilege ACLs derived from Manager's scene assignment and tested. Apply the same dwell/session/sequence resets and normative Phase 1 admission inequalities. Select per `DetectionBatch.timestamp`, pass the transform as an argument to `transformDetections()` rather than transformer state, preserve static intrinsics, and gate invalid batches before MOT while normal track aging continues.

Preserve multiple same-camera batches with distinct timestamps in one time chunk: each batch can have a different pose validity and dwell decision, so a one-batch-per-camera overwrite can apply one decision to another batch's detections. Reject timestamp rewrites that replace acquisition time.

Configure independent default-off flags `TRACKER_PTZ_ENABLED` and `TRACKER_PTZ_SHADOW_MODE` in `tracker/config/tracker.json` with `TRACKER_` environment overrides. Shadow mode never modifies detections or track state. Emit the same sampled structured JSONL shadow record to Tracker logs and the replay artifact sink: source, sequence, calibration version, pose age, timestamp uncertainty, dwell elapsed, decision/reason detail, candidate projection, and static-baseline residual.

**Tests and acceptance:** load the exact same Phase 1 JSON vectors unchanged; schema/finite-matrix and payload-bound validation; per-batch timestamps; transform argument/intrinsics; dwell and session resets; source assignment/ACL denial; invalid-batch exclusion; frame mapping; timestamp rewrite; shadow isolation. Controller and Tracker decisions match for every shared vector; excluded detections neither initiate nor update tracks; replay is deterministic.

**Documentation:** Document Tracker flags/configuration, scene-scoped subscriptions, multi-batch rationale, dwell reference, shadow record/sink, and rollback.

### 6. Shadow Validation and Feature-Flag Rollout

This phase depends on Phases 1, 2, 3a, 3b, 4, and 5, the calibrated per-camera measurement/import, and the golden dataset. Entry also requires deployment-provided ground-plane/reprojection error, camera-to-tracker latency, and post-motion availability budgets. Before enabling a nested-scene camera, resolve the Shared Scene Graph frame-name adapter and demonstrate child-to-target-scene transform composition; otherwise keep that source disabled.

Prove the real projection path at physical home and at off-home target positions; this is separate from Phase 4's synthetic check. Replay the named/versioned golden dataset and hardware sequences across both directions, motion/settling/dwell recovery, sequence gaps and non-increasing sequence, restarts/session changes, stale retained pose, calibration reload failure, timestamp uncertainty, and clock offset. Record calibration versions, dataset, baseline, and each profile's shadow records.

**Per-profile shadow exit criteria:** Controller and Tracker produce identical dwell/validity decisions on every shared vector. Each independently meets configured reprojection RMS, 95th-percentile ground-plane position error, latency, and post-motion eligibility/recovery budgets. At-home pose is equivalent to static calibration within the deployment tolerance; off-home projections meet measured spatial-error budget. Neither profile feeds detections during motion, settling, incomplete dwell, invalid/stale pose, or over-age observations. Replay has one PoseContext per accepted sample and no increase in false initiations or duplicate tracks against the named static baseline. Dwell rejection/recovery and eligibility telemetry meet availability budgets.

Keep `CONTROLLER_PTZ_ENABLED` and `TRACKER_PTZ_ENABLED` disabled until each profile independently passes its own shadow gate; shadow flags remain separate. Do not run two active MOT publishers for one scene/lease to compare them. Rollback immediately disables the relevant profile flag and returns to static projection.

**Documentation:** Record numeric budgets, dataset/baseline/calibration provenance, shadow evidence, per-profile rollout decision, and rollback procedure.

## PoC Boundary

Reuse the PoC's measured data and algorithms as an offline lab/onboarding reference, not as a production dependency. Reuse per-axis curves, backlash deadband/interpolation, measured pan-axis evidence, golden reprojection data, and offline coefficient fitting from a pinned PoC snapshot. The snapshot/commit and exact fitting-script path/revision are recorded in calibration provenance; treat the starting backlash band as a nuisance parameter during fitting. Onboarding stops depending on the PoC branch when supported-camera calibration can be reproduced from versioned procedure/data and imported calibration independently passes held-out validation. A differential Resolver-versus-PoC fit test is recommended for mid-travel backlash interpolation if the referenced fitting script is reproducible; it is not a production runtime dependency.

Scale derivation from FOV and advertised position space belongs only to isolated lab/offline calibration work, not the Positioning runtime or a new production calibration tool. Production composes rotations about the calibrated pan and tilt axes according to versioned calibration frames/order. Do not reproduce live-pose REST writes, adopting live position as home, automatic rebaseline, settle-gated pose publication, hand-rolled conversions where repository/SciPy support exists, or build-time source cloning.

PTZ v1 is the first capability of the ADR 13 Positioning Service. The consumer-side pose join is a transitional adapter toward ADR 13's inline Positioning → Spatial Transform flow. Deferred work includes non-PTZ observation/measurement ingest, inline observation enrichment, `getPose(id, when)`, pose-to-Persistence integration, and canonical Scene Graph frame names; migration from the v1 join is not move-only.

## Scope

Exclude zoom-dependent intrinsics, non-ONVIF adapters, RTP timed metadata, UI live-pose display, and live-pose persistence. Keep the above ADR 13 capabilities out of this PTZ v1 implementation.
