// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import {
  APP_NAME,
  CMD_AUTOCALIB_SCENE,
  IMAGE_CALIBRATE,
  SYS_AUTOCALIB_STATUS,
} from "/static/js/constants.js";
import { updateElements } from "/static/js/utils.js";
import { ConvergedCameraCalibration } from "/static/js/cameracalibrate.js";

var calibration_strategy;
var advanced_calibration_fields = [];
const camera_calibration = new ConvergedCameraCalibration();
window.camera_calibration = camera_calibration;

function initializeCalibration(client, scene_id) {
  document.getElementById("lock_distortion_k1").style.visibility = "hidden";
  advanced_calibration_fields = $("#kubernetes-fields").val().split(",");
  updateElements(
    advanced_calibration_fields.map((e) => e + "_wrapper"),
    "hidden",
    true,
  );

  calibration_strategy = document.getElementById("calib_strategy").value;

  if (calibration_strategy === "Manual") {
    document.getElementById("auto-camcalibration").hidden = true;
  } else {
    client.subscribe(APP_NAME + SYS_AUTOCALIB_STATUS);
    console.log("Subscribed to " + SYS_AUTOCALIB_STATUS);
    client.publish(APP_NAME + SYS_AUTOCALIB_STATUS, "isAlive");
    client.subscribe(APP_NAME + CMD_AUTOCALIB_SCENE + scene_id);
    console.log("Subscribed to " + CMD_AUTOCALIB_SCENE);
  }
}

function registerAutoCameraCalibration(client, scene_id) {
  if (document.getElementById("auto-camcalibration")) {
    document.getElementById("auto-camcalibration").disabled = true;
    document.getElementById("auto-camcalibration").title =
      "Initializing auto camera calibration";
    document.getElementById("calib-spinner").classList.remove("hide-spinner");
  }
  client.publish(APP_NAME + CMD_AUTOCALIB_SCENE + scene_id, "register");
}

function manageCalibrationState(msg, client, scene_id) {
  if (document.getElementById("auto-camcalibration")) {
    if (msg.status == "registering") {
      document.getElementById("calib-spinner").classList.remove("hide-spinner");
      document.getElementById("auto-camcalibration").title =
        "Registering the scene";
    } else if (msg.status == "busy") {
      document.getElementById("calib-spinner").classList.remove("hide-spinner");
      document.getElementById("auto-camcalibration").disabled = true;
      var button_message =
        msg?.scene_id == scene_id
          ? "Scene updated, Registering the scene"
          : "Unavailable, registering scene : " + msg?.scene_name;
      document.getElementById("auto-camcalibration").title = button_message;
    } else if (msg.status == "success") {
      document.getElementById("calib-spinner").classList.add("hide-spinner");
      if (calibration_strategy == "Markerless") {
        document.getElementById("auto-camcalibration").title =
          "Go to 3D view for Markerless auto camera calibration.";
      } else {
        document.getElementById("auto-camcalibration").disabled = false;
        document.getElementById("auto-camcalibration").title =
          "Click to calibrate the camera automatically";
      }
    } else if (msg.status == "re-register") {
      client.publish(APP_NAME + CMD_AUTOCALIB_SCENE + scene_id, "register");
    } else {
      document.getElementById("calib-spinner").classList.add("hide-spinner");
      document.getElementById("auto-camcalibration").title = msg.status;
    }
  }
}

function initializeCalibrationSettings() {
  if ($(".cameraCal").length) {
    camera_calibration.initializeCamCanvas(
      $("#camera_img_canvas")[0],
      $("#video")[0],
    );
    camera_calibration.initializeViewport(
      $("#map_canvas_3D")[0],
      $("#scale").val(),
      $("#scene").val(),
      $("#video")[0],
      `Token ${$("#auth-token").val()}`,
    );

    const transformType = $("#id_transform_type").val();
    const initialTransforms = $("#initial-id_transforms").val().split(",");
    camera_calibration.addInitialCalibrationPoints(
      initialTransforms,
      transformType,
    );

    // Set up callbacks for buttons in the calibration interface
    camera_calibration.setupResetPointsButton();
    camera_calibration.setupResetViewButton();
    camera_calibration.setupSaveCameraButton();
    camera_calibration.setupOpacitySlider();

    // Set all inputs with the id id_{{ field_name }} and distortion or intrinsic in the name to disabled
    $(
      "input[id^='id_'][name*='distortion'], input[id^='id_'][name*='intrinsic']",
    ).prop("disabled", true);

    // for all elements with the id enabled_{{ field_name }}
    // when the input is checked, disable the input with the id id_{{ field_name }}
    // otherwise, enable the input
    $("input[id^='enabled_']").on("change", function () {
      const field = $(this).attr("id").replace("enabled_", "");
      const input = $(`#id_${field}`);
      input.prop("disabled", $(this).is(":checked"));
    });
  }
}


function handleAutoCalibrationPose(msg) {
  if (msg.error === "False") {
    camera_calibration.clearCalibrationPoints();
    camera_calibration.addAutocalibrationPoints(msg);
  } else {
    alert(
      `${msg.message} Please try again.\n\nIf you keep getting this error, please check the documentation for known issues.`,
    );
  }

  document.getElementById("auto-camcalibration").disabled = false;
  document.getElementById("reset_points").disabled = false;
  document.getElementById("top_save").disabled = false;
}

function setMqttForCalibration(client) {
  camera_calibration.setMqttClient(
    client,
    APP_NAME + IMAGE_CALIBRATE + $("#sensor_id").val(),
  );
  document.getElementById("lock_distortion_k1").style.visibility = "visible";
  updateElements(
    advanced_calibration_fields.map((e) => e + "_wrapper"),
    "hidden",
    false,
  );
}

export {
  initializeCalibration,
  registerAutoCameraCalibration,
  manageCalibrationState,
  initializeCalibrationSettings,
  handleAutoCalibrationPose,
  setMqttForCalibration,
};
