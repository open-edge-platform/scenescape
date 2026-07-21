<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Test Data Specification — Point-Cloud AutoCalibration

## Purpose

This document specifies the point-cloud and mesh **test data** required to validate the
point-cloud registration (sensor localization) foundation added to the AutoCalibration
service (see `docs/design/point-cloud-autocalibration-plan.md`).

The capability is **sensor-agnostic**: the point cloud may originate from any perceptual
sensor (e.g. LiDAR, depth camera, stereo rig, or a photogrammetry pipeline). The test
data therefore describes generic point clouds and is not tied to a specific sensor type.

It is an **input specification for a separate data-generation task**. Producing the data
is **out of scope** for the implementation task; this document defines *what* must be
produced, in *which formats*, and with *which properties and metadata* so the generated
data can drive unit tests, API-level tests, and the KPI performance test.

## Scope of the Data

The foundation implementation covers only the **basic case of complete overlap** between
the sensor point cloud and the scene point cloud. Accordingly, the required data set is
limited to:

- Scene 3D meshes (GLB and PLY) that convert cleanly to point clouds.
- Sensor point clouds (PLY and PCD) that fully overlap the corresponding scene.
- Paired scene/sensor data with a **known ground-truth transform** for accuracy checks.
- A large point-cloud pair for the KPI performance test.
- Malformed / degenerate inputs for negative tests.

Explicitly **not** required (out of scope): partial-overlap data, high-density sensor
captures, multi-return / intensity-rich real sensor logs, and dynamic-scene sequences.

## Global Conventions

These conventions apply to every generated artifact unless a dataset overrides them.

- **Coordinate system**: right-handed, Z-up, consistent with the Scenescape scene
  coordinate frame used by the AutoCalibration service. Point clouds are expressed in the
  **local scene frame** (near-origin), never in global geodetic / ECEF coordinates.
- **Units**: meters.
- **Numeric precision**: point coordinates are stored as **float32**. In meters and in the
  local scene frame this preserves ≤1 mm quantization to ~8 km and ≤1 cm to ~84 km from
  the origin, which satisfies cm precision for scenes spanning up to a few kilometers.
- **Canonical format**: **PCD (`binary_compressed`)** is the canonical serialization for
  scene / cached clouds (`scene_cloud`). Sensor inputs (`sensor_cloud`) are provided in
  **both PLY and PCD** to exercise the API's accepted input formats.
- **Geometry types**: triangle meshes for scene models; unstructured point clouds for
  sensor inputs.
- **Point attributes**: XYZ required. Normals and color are optional; when present they
  must be valid (unit-length normals, 8-bit RGB). Intensity is not required.
- **File encoding**: binary encoding preferred for PLY/PCD to keep files compact; an
  ASCII variant of at least one small fixture should be included to exercise both paths.
- **Determinism**: generation must be reproducible. Record the random seed used for any
  sampling or noise in the dataset metadata.
- **No secrets / no PII**: synthetic geometry only.

## Storage Layout and Naming

- Small fixtures used by unit tests live under `tests/ui/test_media/point_cloud/`
  (co-located with existing mesh fixtures such as `box.glb`).
- Large performance fixtures live under `test_data/point_cloud/` (kept out of unit-test
  media to avoid bloating that directory) and may be produced on demand by the generation
  task.
- Naming pattern: `<dataset-id>_<role>.<ext>`, where `role` is one of `scene_mesh`,
  `scene_cloud`, `sensor_cloud`, `expected_transform`.
  - `scene_cloud` (derived / cached scene clouds) is serialized as **PCD**
    (`binary_compressed`, float32 meters, normals persisted).
  - `sensor_cloud` is provided in **both PLY and PCD**.
  - Example: `box_complete_scene_mesh.glb`, `box_complete_scene_cloud.pcd`,
    `box_complete_sensor_cloud.ply`, `box_complete_sensor_cloud.pcd`,
    `box_complete_expected_transform.json`.

## Ground-Truth Transform Format

Each paired dataset must include a ground-truth transform describing the rigid pose that
maps the **sensor cloud into the scene frame** (the value the registration algorithm is
expected to recover, within tolerance).

- File: `<dataset-id>_expected_transform.json`.
- Content: a 4x4 row-major homogeneous transform matrix plus provenance metadata.

Fields:

- `matrix`: array of 4 arrays of 4 floats (row-major, meters for translation).
- `rotation_convention`: fixed string `"scene_from_sensor"`.
- `seed`: integer random seed used during generation.
- `notes`: optional human-readable description.

## Dataset Catalog

### 1. Mesh conversion fixtures (unit tests)

Purpose: validate scene-mesh-to-point-cloud conversion for both supported mesh formats.

Required artifacts per fixture:

- One **GLB** scene mesh and one **PLY** scene mesh of the same simple watertight solid
  (e.g. a box or a small room shell).
- Approximate size: a few thousand to tens of thousands of triangles — large enough to
  produce a meaningful sampled cloud, small enough for fast tests.
- Expectations to document: bounding-box extents and a nominal target sample count so the
  test can assert the resulting cloud is non-empty and within the expected bounds.

### 2. Complete-overlap registration pairs (unit + API accuracy tests)

Purpose: validate that the algorithm recovers a known transform under complete overlap.

For each pair provide:

- `scene_mesh` (GLB and/or PLY) — the reference scene model.
- `sensor_cloud` (PLY **and** PCD variants of the same cloud) — derived from the scene
  geometry, then transformed by a known rigid transform.
- `expected_transform.json` — the applied transform (see format above).

Recommended variety (at least three pairs):

- **Identity-ish**: small rotation (a few degrees) and small translation (< 0.5 m).
- **Moderate**: rotation up to ~30 degrees about an arbitrary axis, translation ~1-2 m.
- **Noisy**: moderate transform plus low-amplitude Gaussian sensor noise on points
  (document the noise standard deviation, e.g. 1-2 cm) to test robustness of refinement.

Point counts: on the order of 10k-100k points per cloud (fast enough for CI, dense enough
to converge). Complete overlap: every sensor point corresponds to scene geometry.

### 3. KPI performance pair (performance test)

Purpose: validate the KPI — registration of two point clouds where **both exceed
1,000,000 points** completes in **under 30 seconds** on CPU.

- `scene_cloud` and `sensor_cloud`: each **> 1,000,000 points**, complete overlap,
  related by a known moderate transform with `expected_transform.json`.
- Provide as binary PLY (and optionally PCD) to keep file size manageable.
- This fixture may be generated on demand rather than committed, if size is prohibitive;
  document the exact generation parameters (seed, point count, transform) so the test is
  reproducible.

### 4. Negative / edge-case inputs (negative tests)

Purpose: validate input validation and graceful failure.

- **Empty cloud**: a valid PLY/PCD header with zero points.
- **Malformed file**: a file whose extension is `.ply`/`.pcd` but whose contents are not
  a valid point cloud (truncated header / wrong magic bytes).
- **Degenerate cloud**: all points identical or collinear (insufficient geometry to
  register).
- **Oversized payload** (optional): a file that, once base64-encoded, exceeds the API
  request size limit — used to confirm size-limit rejection.
- **Invalid mesh**: a `.glb` that fails to load (analogous to the existing
  `box_invalid.glb`), to exercise scene-side error handling.

## Metadata Manifest

The generation task must emit a machine-readable manifest (`manifest.json`) alongside the
data describing every artifact, so tests can be parameterized without hard-coding values.

Per-artifact fields:

- `dataset_id`, `role`, `path`, `format` (`glb` | `ply` | `pcd` | `json`).
- `point_count` (for clouds) or `triangle_count` (for meshes).
- `encoding` (`binary` | `ascii`).
- `bounding_box`: `{ min: [x,y,z], max: [x,y,z] }`.
- `has_normals`, `has_color` (booleans).
- `seed`, and for sensor clouds `noise_stddev_m` and the `expected_transform` reference.
- `overlap`: fixed `"complete"` for in-scope pairs.

## Acceptance Criteria for the Generated Data

- All in-scope pairs load with the project's mesh/point-cloud utilities
  (`scene_common.mesh_util`, Open3D) without error.
- Every registration pair includes a valid `expected_transform.json`.
- The KPI pair provides two clouds each exceeding 1,000,000 points with complete overlap.
- Negative fixtures reliably trigger the corresponding validation or load failure.
- `manifest.json` is present, complete, and consistent with the files on disk.
- Generation is reproducible from the recorded seeds and parameters.

## Data-Generation Tool Requirements

This section specifies the Python tool that produces the data described above. It is a
requirements specification only; implementation is a separate task.

### Purpose and Scope

The tool generates and validates the point-cloud / mesh fixtures defined in this document
so they can drive unit tests, API-level tests, and the KPI performance test. Beyond bulk
generation, it is a **development and verification aid** for the point-cloud registration
algorithm: it can synthesize paired clouds with a known ground-truth transform, apply
controlled perturbations, and report registration error against that ground truth.

**In scope (the tool's value-add):**

- Orchestrated, reproducible generation of every dataset in the *Dataset Catalog*
  (mesh-conversion fixtures, complete-overlap registration pairs, the KPI pair, and
  negative / edge-case fixtures).
- Applying a **known rigid transform** to derive a `sensor_cloud` from scene geometry and
  emitting the matching `expected_transform.json` (see *Ground-Truth Transform Format*).
- Injecting controlled, seeded Gaussian point noise at documented standard deviations.
- Producing degenerate / malformed / empty / oversized fixtures deterministically.
- Emitting the `manifest.json` manifest and validating it against files on disk.
- A **verification mode** that loads a registration pair, runs the project's registration
  entry point (or a supplied 4x4 transform), and reports fitness, inlier RMSE, and the
  rotation/translation error versus the ground truth.
- Adherence to the *Global Conventions*, *Storage Layout and Naming*, and *Ground-Truth
  Transform Format* defined above (Z-up right-handed frame, meters, float32 storage,
  canonical PCD `binary_compressed`, dual PLY+PCD for sensor clouds, recorded seeds).

**Out of scope (delegate to existing third-party tools — do not reimplement):**

- Mesh and point-cloud file I/O, sampling, downsampling, normal estimation, and
  transforms — use **Open3D** (already a dependency) and `scene_common.mesh_util`
  (`extractTriangleMesh`, `extractMeshFromGLB`, `extractMeshFromPointCloud`).
- GLB/PLY parsing and mesh math — use **trimesh** / Open3D as `mesh_util` already does.
- Point-cloud visualization / inspection — rely on Open3D or external viewers; the tool
  does not ship its own GUI.
- The registration algorithm itself — the tool consumes the service/algorithm under
  test for verification; it must not fork or reimplement it.
- Authoring hand-modeled scene meshes — the tool may synthesize simple primitives, but
  complex art assets are provided as inputs, not generated.

### Functional Requirements

- **F1 — Catalog coverage:** Generate each artifact class in the *Dataset Catalog* via
  named, parameterized recipes so a single invocation can (re)produce the full fixture set
  or a selected subset.
- **F2 — Transform derivation:** Given scene geometry and a transform specification
  (explicit 4x4, or sampled rotation-axis/angle + translation bounds under a seed), sample
  the mesh to a cloud, apply the transform to produce `sensor_cloud`, and write the
  applied transform to `expected_transform.json` with `rotation_convention:
  "scene_from_sensor"`.
- **F3 — Noise injection:** Optionally add zero-mean Gaussian noise with a configurable
  per-axis standard deviation (meters); record `noise_stddev_m` in the manifest.
- **F4 — Format emission:** Write `scene_cloud` as PCD `binary_compressed` (float32,
  normals persisted); write `sensor_cloud` in both PLY and PCD; include at least one ASCII
  fixture to exercise the ASCII path.
- **F5 — Negative fixtures:** Deterministically emit empty, malformed (bad header / wrong
  magic bytes), degenerate (identical / collinear points), optional oversized-payload, and
  invalid-mesh fixtures.
- **F6 — Manifest:** Emit `manifest.json` with all per-artifact fields required by the
  *Metadata Manifest* section, computed from the actual generated files.
- **F7 — Validation mode:** Re-load every generated artifact with `scene_common.mesh_util`
  / Open3D and assert the *Acceptance Criteria*; fail with a clear, actionable report if
  any check fails.
- **F8 — Verification mode:** For a registration pair, run the registration under test (or
  apply a supplied transform), and report fitness, inlier RMSE, and rotation (degrees) /
  translation (meters) error versus `expected_transform.json`.
- **F9 — KPI generation:** Generate the >1,000,000-point KPI pair on demand from recorded
  parameters (seed, point count, transform) without committing large binaries.

### Non-Functional Requirements

- **N1 — Reproducibility:** All randomness is seeded; identical inputs and seed yield
  byte-stable geometry (subject to library determinism) and identical manifests.
- **N2 — No new dependencies:** Use only libraries already available to the project
  (Open3D, trimesh, numpy, `scene_common`). Introducing a new runtime dependency requires
  explicit approval.
- **N3 — Determinism of layout:** Honor the *Storage Layout and Naming* pattern exactly so
  tests can locate fixtures without hard-coded values (read them from the manifest).
- **N4 — Performance:** CI-tier fixtures generate quickly; the KPI pair generation is
  bounded and documented but need not meet the 30 s registration KPI itself.
- **N5 — Safety:** Synthetic geometry only — no secrets, no PII, no network access
  required to generate the core fixtures.
- **N6 — Standards:** Follow Scenescape Python conventions (2-space indentation, SPDX +
  copyright headers) and place code and tests per the project's service/test layout.

### Interface (CLI)

The tool is invoked as a Python module / console script with subcommands. Exact flag names
are to be refined, but the shape is:

- `generate` — produce fixtures. Options: `--dataset <id|all>`, `--out <dir>`,
  `--seed <int>`, `--points <n>`, `--noise-stddev-m <float>`, `--transform <json|spec>`,
  `--formats ply,pcd`, `--include-kpi`.
- `validate` — load generated artifacts and assert the *Acceptance Criteria* against a
  `manifest.json`.
- `verify` — run/verify registration for a pair and report error versus ground truth.
  Options: `--pair <dataset-id>`, `--transform <json>` (bypass the algorithm).

All subcommands accept `--manifest <path>` and exit non-zero on failure with a concise
summary suitable for CI logs.

### Open Questions (to refine iteratively)

- Where should the tool live (e.g. `autocalibration/tools/` vs `tools/`) and what console
  entry-point name?
- Should `verify` call the service HTTP API, the in-process `PointCloudRegistration`
  class, or both behind a common adapter?
- Which simple primitive(s) does the tool synthesize for the box/room fixtures, and do we
  also commit small GLB/PLY source meshes as inputs?
- Should the manifest be a single top-level file or one-per-dataset, and do we version it?

## References

- Implementation plan: docs/design/point-cloud-autocalibration-plan.md
- Autocalibration API and flows: docs/design/autocalibration-api-flow-summary.md
- Lidar calibration Epic: docs/jira/ITEP-92856.xml
- Initial Story: docs/jira/ITEP-93047.xml
