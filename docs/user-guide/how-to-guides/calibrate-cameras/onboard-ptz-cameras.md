<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Onboard PTZ Cameras

Each PTZ camera needs a measured `ptz_calibration` block in Manager before Positioning
can publish a valid pose for it. This procedure produces and imports that block. Run it
once per physical camera, and again after a remount, firmware change, or lens change.

Measure and fit the calibration offline, with your own measurement and fitting tools,
outside the production deployment. Do not write calibration from a measurement tool
directly into production; import the result through the validated Manager API. The
block format is defined in the
[Positioning API Reference](../../positioning-api-reference.md#ptz-calibration-json).

## Reference Pose, Movement Model, and Version

AprilTag/manual calibration establishes the camera's scene pose at one reference
pan/tilt position. The separate `ptz_calibration` movement model describes how to
transform that pose when pan/tilt changes. Its `calibration_version` is an
operator/export-tool label stored in Manager, not the date of the latest UI
calibration. Positioning reads this label; it does not create or refit the model.
See [Understanding the Model Version](../../positioning-api-reference.md#understanding-the-model-version).

For learning or simulation, use the complete
[ideal-camera example](../../positioning-api-reference.md#ideal-camera-example).
It demonstrates linear scales with zero backlash and no mounting corrections,
not an accepted calibration for arbitrary hardware.

### Keeping the Reference Consistent

Normal pan/tilt motion on a fixed mount requires no new static calibration:
Positioning transforms the saved reference pose. Returning to a device preset
does not establish or change the PTZ reference automatically.

If you recalibrate and save the pose at the existing recorded home, the reference
remains consistent. If you save at a different pan/tilt, explicitly prepare and
import a matching PTZ reference with a new version, including correct axis frames
and backlash approach state. Reuse measured curves only where still valid;
Positioning does not automatically rebase or infer home from current telemetry.
Do not use a static pose saved at one position with home coordinates from another.
When collecting calibration at other stops, retain the original home record and
restore the matching pose/model pair before evaluating runtime projection.

## Prerequisites

- The camera is assigned to its scene in Manager and its static home pose is
  calibrated. Euler and point-correspondence cameras are both supported.
- A way to calibrate the camera pose at each measured stop. Use one of these methods:
  - [AprilTag auto-calibration](./autocalibrate-cameras-using-apriltags.md) or
    [visual-feature auto-calibration](./autocalibrate-cameras-using-visual-features.md).
    Enough tags or features must be visible across the pan and tilt range you plan
    to use.
  - Manual calibration of each pose with the
    [2D UI](./use-2D-UI-for-calibration.md) or [3D UI](./use-3D-UI-for-calibration.md).
    This needs no tags in the scene, but each stop takes longer.
- A tool that drives the camera over ONVIF and records its raw pan/tilt position, and
  a fitting tool that estimates the model parameters in step 4. Record the name and
  exact version of both; they go into `provenance`.
- Manager's `PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX` (image default `12.0`) suits your
  accuracy requirement.
- An administrator API token for the import step.

## 1. Record the Position Space and Home

1. Read the ONVIF pan/tilt position-space URI and ranges that the camera advertises.
   These become `position_space`.
2. For each axis, drive the camera to the home pose from one fixed direction of travel.
   Record the raw ONVIF value as `home_position` and the direction as
   `approach_direction` (`increasing` or `decreasing`). Use the same approach
   direction for every later return to home.
3. Check that the camera view at home matches the static pose stored in Manager.
   If it does not, recalibrate the home pose before you continue.

## 2. Collect Sweep Samples

1. Choose at least three pan positions spread across the travel you plan to use.
2. At each pan position, sweep tilt across the supported range in **both**
   directions, first increasing and then decreasing. Sweep pan in both directions at
   more than one tilt position.
3. At each stop, wait until the camera settles, then record the raw ONVIF position,
   the direction of travel, a timestamp, and the calibration observations: the image
   points and their matching scene points. Get them from Auto-Calibration or by
   calibrating that pose manually. Record which method you used for each stop.
   Manual calibration usually allows fewer stops, so make sure the held-out set in
   the next step still covers both sweep directions.
4. Store the samples as a versioned dataset with an identifier. You will reference it
   in `provenance`.

## 3. Split Held-Out Samples

Before fitting, set aside a held-out set that the fit never sees. Include at least one
complete pan position, sampled in both tilt directions, plus samples from each sweep
direction. Use the remaining samples for fitting.

## 4. Fit the Model

Use your fitting tool on the fitting samples to estimate, for each axis:

- the `curve` polynomial. Its sign encodes axis inversion.
- the calibrated rotation `axis`, its `frame`, and the `composition_order`,
  including the tilt-axis mounting correction.
- the `backlash`, either one value or position-dependent nodes. Treat the starting
  backlash band as a nuisance parameter.

Also fit the nominal-axis model, with pan about the scene up axis and tilt about the
camera X axis, so you can compare the two.

## 5. Validate on Held-Out Samples

1. Compute the reprojection RMS, in pixels, of the fitted model on the held-out
   samples only.
2. Compute the same value for the nominal-axis model. Keep the mounting correction
   only if it lowers the held-out residual.
3. The held-out residual must not exceed `PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX`.
   If it does, collect more samples or refit. Do not raise the threshold to make one
   camera pass.
4. Report the held-out value, not the fitting residual, as
   `quality.reprojection_rms_px`.

## 6. Choose Motion and Backlash Parameters

Use the measured settle behavior and backlash to set:

- `settle_angular_threshold_deg` and `settle_interval_s`.
- `backlash_home_tolerance_deg` and `backlash_history_s` for each axis.

All four must be greater than zero. The angular values must not exceed the calibrated
travel of the axis.

## 7. Assemble and Import

1. Build the `ptz_calibration` block with a new, unique `calibration_version`.
2. Fill `provenance` with at least the following values: measurement and fitting
   tool names and versions, pose calibration method (AprilTag, visual features, or
   manual), camera model and
   firmware, measurement date, operator, and dataset identifier. Do not include
   device credentials.
3. Import the block:

   ```bash
   curl -X PUT "https://<manager>/api/v1/camera/<camera_uid>" \
     -H "Authorization: Token <admin_token>" \
     -H "Content-Type: application/json" \
     -d '{"name": "<camera_name>", "ptz_calibration": <calibration_json>}'
   ```

   A `400` response returns a stable `<path>: <code>` error. Fix the reported field
   and import again.

4. Using the read-only Positioning client, check that `GET /api/v1/camera/<camera_uid>`
   returns the imported `ptz_calibration` and the home `pose_matrix`.

Manager publishes a camera configuration invalidation after the import commits, and
Positioning reloads the calibration. Keep the dataset, the fit output, and the
held-out residuals together with the `calibration_version` for shadow validation.
