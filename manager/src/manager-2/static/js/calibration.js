// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import { APP_NAME, IMAGE_CALIBRATE } from "/static/js/constants.js";
import { ConvergedCameraCalibration } from "/static/js/cameracalibrate.js";

var calibration_strategy;
let camera_calibration;

// Initialize after DOM is ready
document.addEventListener("DOMContentLoaded", function () {
  camera_calibration = new ConvergedCameraCalibration();
  window.camera_calibration = camera_calibration;
});

async function startCameraCalibration(cameraUID, image, intrinsics) {
  try {
    const response = await fetch(`/v1/cameras/${cameraUID}/calibration`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image: image,
        intrinsics: intrinsics,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status} - ${response.statusText}`);
    }

    const data = await response.json();
    console.log(`Calibration started for ${cameraUID}:`, data);
    return data;
  } catch (error) {
    console.error(`Error starting calibration for ${cameraUID}:`, error);
    return { status: "error", message: error.message };
  }
}

async function getCalibrationServiceStatus() {
  try {
    const response = await fetch("/v1/status", {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      console.log(`HTTP status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.warn("Error:", error);
  }
}

async function registerScene(sceneId) {
  const url = `/v1/scenes/${sceneId}/registration`;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(
        `Error ${response.status}: ${errorData.message || response.statusText}`,
      );
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Failed to register scene:", error);
    throw error;
  }
}

async function initializeCalibration(scene_id, socket) {
  socket.on("service_ready", (notification) => {
    console.log("Calibration service is ready:", notification);
    if (document.getElementById("lock_distortion_k1")) {
      document.getElementById("lock_distortion_k1").style.visibility = "hidden";
    }

    calibration_strategy = document.getElementById("calib_strategy").value;

    if (calibration_strategy === "Manual") {
      document.getElementById("auto-autocalibration").hidden = true;
    } else {
      if (notification.status === "running") {
        registerAutoCameraCalibration(scene_id, socket);
      }
    }
  });
}

async function registerAutoCameraCalibration(scene_id, socket) {
  if (document.getElementById("auto-autocalibration")) {
    document.getElementById("auto-autocalibration").disabled = true;
    document.getElementById("auto-autocalibration").title =
      "Initializing auto camera calibration";
    document.getElementById("calib-spinner").classList.remove("hide-spinner");
  }

  socket.on("register_result", async (notification) => {
    manageCalibrationState(notification.data, scene_id);
  });
  const response = await registerScene(scene_id);
}

async function manageCalibrationState(msg, scene_id) {
  if (document.getElementById("auto-autocalibration")) {
    if (msg.status == "registering") {
      document.getElementById("calib-spinner").classList.remove("hide-spinner");
      document.getElementById("auto-autocalibration").title =
        "Registering the scene";
    } else if (msg.status == "busy") {
      document.getElementById("calib-spinner").classList.remove("hide-spinner");
      document.getElementById("auto-autocalibration").disabled = true;
      var button_message =
        msg?.scene_id == scene_id
          ? "Scene updated, Registering the scene"
          : "Unavailable, registering scene : " + msg?.scene_name;
      document.getElementById("auto-autocalibration").title = button_message;
    } else if (msg.status == "success") {
      document.getElementById("calib-spinner").classList.add("hide-spinner");
      if (calibration_strategy == "Markerless") {
        document.getElementById("auto-autocalibration").title =
          "Go to 3D view for Markerless auto camera calibration.";
      } else {
        document.getElementById("auto-autocalibration").disabled = false;
        document.getElementById("auto-autocalibration").title =
          "Click to calibrate the camera automatically";
      }
    } else if (msg.status == "re-register") {
      const response = await registerScene(scene_id);
    } else {
      document.getElementById("calib-spinner").classList.add("hide-spinner");
      document.getElementById("auto-autocalibration").title = msg.status;
    }
  }
}

function initializeCalibrationSettings() {
  if ($(".cameraCal").length) {
    camera_calibration.initializeCamCanvas(
      $("#camera_img_canvas")[0],
      $("#camera_img").attr("src"),
    );
    camera_calibration.initializeViewport(
      $("#map_canvas_3D")[0],
      $("#scale").val(),
      $("#scene").val(),
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

function updateCalibrationView(msg) {
  const image = "data:image/jpeg;base64," + msg.image;
  const cameraMatrix = [
    [$("#id_intrinsics_fx").val(), 0, $("#id_intrinsics_cx").val()],
    [0, $("#id_intrinsics_fy").val(), $("#id_intrinsics_cy").val()],
    [0, 0, 1],
  ];
  const distCoeffs = [
    $("#id_distortion_k1").val(),
    $("#id_distortion_k2").val(),
    $("#id_distortion_p1").val(),
    $("#id_distortion_p2").val(),
    $("#id_distortion_k3").val(),
  ];
  camera_calibration.updateCalibrationViews(image, cameraMatrix, distCoeffs);
  $("#snapshot").trigger("click");
}

function handleAutoCalibrationPose(msg) {
  if (msg.status == "success") {
    camera_calibration.clearCalibrationPoints();
    camera_calibration.addAutoCalibrationPoints(msg);
    camera_calibration.calculateCalibrationIntrinsics();
  } else {
    alert(
      `${msg.message} Please try again.\n\nIf you keep getting this error, please check the documentation for known issues.`,
    );
  }

  document.getElementById("auto-autocalibration").disabled = false;
  document.getElementById("reset_points").disabled = false;
  document.getElementById("top_save").disabled = false;
}

function setMqttForCalibration(client) {
  camera_calibration.setMqttClient(
    client,
    APP_NAME + IMAGE_CALIBRATE + $("#sensor_id").val(),
  );
  document.getElementById("lock_distortion_k1").style.visibility = "visible";
}

export {
  initializeCalibration,
  registerAutoCameraCalibration,
  manageCalibrationState,
  initializeCalibrationSettings,
  updateCalibrationView,
  handleAutoCalibrationPose,
  setMqttForCalibration,
  getCalibrationServiceStatus,
  startCameraCalibration,
  registerScene,
};
