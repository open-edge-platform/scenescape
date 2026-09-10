// SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import {
  APP_NAME,
  CMD_CAMERA,
  DATA_CAMERA,
  DATA_REGULATED,
  IMAGE_CALIBRATE,
  IMAGE_CAMERA,
  SYS_CHILDSCENE_STATUS,
  REST_URL,
  SUCCESS,
} from "/static/js/constants.js";
import {
  metersToPixels,
  pixelsToMeters,
  checkMqttConnection,
} from "/static/js/utils.js";
import { plot } from "/static/js/marks.js";
import {
  initializeCalibration,
  initializeCalibrationSettings,
  startCameraCalibration,
  updateCalibrationView,
  handleAutoCalibrationPose,
} from "/static/js/calibration.js";

var svgCanvas = Snap("#svgout");
import RESTClient from "/static/js/restclient.js";

// Prefer React toast/confirm hosts when present (ViPPET in-page flows).
function ssToastApi() {
  return (
    (window.ssToast && typeof window.ssToast.show === "function"
      ? window.ssToast
      : null) ||
    (window.parent &&
    window.parent !== window &&
    window.parent.ssToast &&
    typeof window.parent.ssToast.show === "function"
      ? window.parent.ssToast
      : null)
  );
}

function ssShowToast(msg, tone) {
  const api = ssToastApi();
  if (api) {
    api.show(String(msg), tone || "info");
    return;
  }
  window.__ssNativeAlert
    ? window.__ssNativeAlert(String(msg))
    : window.alert(String(msg));
}

function ssAskConfirm(message, options) {
  const opts = options || {};
  const req = {
    title: opts.title || "Confirm",
    message: String(message),
    confirmLabel: opts.confirmLabel || "OK",
    cancelLabel: opts.cancelLabel || "Cancel",
    danger: opts.danger !== false,
  };
  const confirmFn =
    (typeof window.ssConfirm === "function" && window.ssConfirm) ||
    (window.parent &&
      window.parent !== window &&
      typeof window.parent.ssConfirm === "function" &&
      window.parent.ssConfirm);
  if (confirmFn) {
    return confirmFn(req);
  }
  return Promise.resolve(
    window.__ssNativeConfirm
      ? window.__ssNativeConfirm(req.message)
      : window.confirm(req.message),
  );
}

(function bridgeAlertToToast() {
  if (!window.__ssNativeAlert) {
    window.__ssNativeAlert = window.alert.bind(window);
  }
  if (!window.__ssNativeConfirm) {
    window.__ssNativeConfirm = window.confirm.bind(window);
  }
  window.alert = function (msg) {
    const text = String(msg);
    const bad =
      /fail|error|invalid|not found|unable|cannot|must/i.test(text) &&
      !/successfully/i.test(text);
    const ok = /success|updated|generated successfully/i.test(text);
    ssShowToast(text, bad ? "bad" : ok ? "ok" : "info");
  };
})();

var points, maps, rois, tripwires, child_rois, child_tripwires, child_sensors;
var dragging, drawing, adding, editing, fullscreen;
var g;
var radius = 5;
var scale = 30.0; // Default map scale in pixels/meter
var scene_id = $("#scene").val();
var icon_size = 24;
var show_telemetry = false;
var show_trails = false;
var pendingCalibrateMsg = null;

function isCalibratePage() {
  return window.location.href.includes("/cam/calibrate/");
}

function calibrateSensorId() {
  return $("#sensor_id").val() || "";
}

function requestCalibrateFrames(client) {
  var sensorId = calibrateSensorId();
  var mqttClient = client || window.ssMqttClient;
  if (!mqttClient || !sensorId) {
    return;
  }
  mqttClient.publish(APP_NAME + CMD_CAMERA + sensorId, "getcalibrationimage");
}

function applyCalibrationImage(msg) {
  if (!msg || !msg.image) {
    return false;
  }
  if (!window.camera_calibration || !window.camera_calibration.camCanvas) {
    pendingCalibrateMsg = msg;
    return false;
  }
  pendingCalibrateMsg = null;
  updateCalibrationView(msg);
  return true;
}

function flushPendingCalibrationImage(client) {
  if (pendingCalibrateMsg) {
    applyCalibrationImage(pendingCalibrateMsg);
  }
  requestCalibrateFrames(client);
}

function cameraPreviewIsLive(sensorId) {
  if (!sensorId) {
    return false;
  }
  var escaped =
    typeof CSS !== "undefined" && CSS.escape
      ? CSS.escape(String(sensorId))
      : String(sensorId);
  var img =
    document.querySelector('[data-ss-card-sensor="' + escaped + '"]') ||
    document.getElementById("card-preview-" + sensorId);
  if (!img || img.classList.contains("display-none")) {
    return false;
  }
  var src = img.currentSrc || img.getAttribute("src") || "";
  if (!src || src.indexOf("offline.png") !== -1) {
    return false;
  }
  return img.naturalWidth > 0 || src.indexOf("data:image") === 0;
}

function applyCameraRate(sensorId, rateText) {
  if (!cameraPreviewIsLive(sensorId)) {
    return false;
  }
  var rateEl = document.getElementById("rate-" + sensorId);
  var rateFilmEl = document.getElementById("rate-film-" + sensorId);
  if (rateEl) {
    rateEl.innerText = rateText;
    rateEl.classList.remove("telemetry-hide");
  }
  if (rateFilmEl) {
    rateFilmEl.innerText = rateText;
    rateFilmEl.classList.remove("telemetry-hide");
  }
  if (
    window.ssSceneTelemetry &&
    typeof window.ssSceneTelemetry.setCameraRate === "function"
  ) {
    window.ssSceneTelemetry.setCameraRate(sensorId, rateText);
  }
  window.dispatchEvent(
    new CustomEvent("ss-camera-rate", {
      detail: { sensorId: sensorId, text: rateText },
    }),
  );
  return true;
}
var scene_y_max = 480; // Scene image height in SVG user units
var scene_map_width = 0; // Scene image width in SVG user units
// Extra viewBox room so labels above/beside edge markers are not clipped.
var MAP_LABEL_PAD_TOP = 32;
var MAP_LABEL_PAD_SIDE = 72;
var MAP_LABEL_PAD_BOTTOM = 12;

function sceneMapViewBox(width, height) {
  var w = Number(width) || 0;
  var h = Number(height) || 0;
  return (
    -MAP_LABEL_PAD_SIDE +
    " " +
    -MAP_LABEL_PAD_TOP +
    " " +
    (w + MAP_LABEL_PAD_SIDE * 2) +
    " " +
    (h + MAP_LABEL_PAD_TOP + MAP_LABEL_PAD_BOTTOM)
  );
}

var is_coloring_enabled = false; // Default state of the coloring feature
var assetMarkColors = {}; // Object Library mark_color per type, e.g. {person: "#888888"}
var roi_color_sectors = {};
var singleton_color_sectors = {};

points = maps = rois = tripwires = [];
dragging = drawing = adding = editing = fullscreen = false;

const socket = io({
  path: "/api/v1/autocalibration/socket.io",
  transports: ["websocket"],
});

socket.on("connect", async () => {
  console.log("Connected to WebSocket:", socket.id);
  socket.emit("register_scene", { scene_id });
});

socket.on("calibration_result", async (notification) => {
  console.log("Calibration result received:", notification);
  if (notification.result && notification.result.status === "success") {
    handleAutoCalibrationPose(notification.result);
  } else if (notification.result) {
    alert("Calibration failed: " + notification.result.message);
  }
});

// Force page reload on back button press
if (window.performance && window.performance.navigation.type == 2) {
  location.reload();
}

function isSceneDetailMap() {
  return (
    !!document.querySelector(".scene-map-stage") &&
    !$("#map").hasClass("singletonCal")
  );
}

function svgPointerToScene(e) {
  var svg = document.getElementById("svgout");
  if (!svg) {
    return [0, 0];
  }
  var ctm = svg.getScreenCTM();
  if (ctm) {
    var pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    pt = pt.matrixTransform(ctm.inverse());
    return [Math.round(pt.x), Math.round(pt.y)];
  }
  var offset = $("#svgout").offset();
  return [parseInt(e.pageX - offset.left), parseInt(e.pageY - offset.top)];
}

function syncReactMapOverlay() {
  var reactSvg = document.querySelector("svg.ss-react-scene-map");
  var snap = document.querySelector("svg.ss-snap-legacy, svg#svgout-snap");
  if (!reactSvg || !snap) {
    return;
  }
  var vb =
    reactSvg.getAttribute("viewBox") ||
    (scene_map_width && scene_y_max
      ? "0 0 " + scene_map_width + " " + scene_y_max
      : "");
  var par = reactSvg.getAttribute("preserveAspectRatio") || "xMidYMid meet";
  if (vb) {
    snap.setAttribute("viewBox", vb);
  }
  snap.setAttribute("preserveAspectRatio", par);
  snap.removeAttribute("width");
  snap.removeAttribute("height");
  snap.style.width = "100%";
  snap.style.height = "100%";
}

function fitSceneMapDisplay() {
  var stage = document.querySelector(".scene-map-stage");
  if (!stage || !isSceneDetailMap()) {
    return;
  }

  // React map fills the stage; marks live on the Snap overlay. Both must
  // share the same viewBox so resize only changes display scale.
  if (document.body.classList.contains("ss-use-react-map")) {
    syncReactMapOverlay();
    return;
  }

  var svg = document.getElementById("svgout");
  if (!svg || !scene_map_width || !scene_y_max) {
    return;
  }

  svg.setAttribute("viewBox", sceneMapViewBox(scene_map_width, scene_y_max));
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

  var maxW;
  var maxH;
  if (document.body.classList.contains("is-map-fullscreen")) {
    maxW = Math.max(stage.clientWidth || window.innerWidth - 24, 100);
    maxH = Math.max(window.innerHeight - 96, 200);
  } else {
    // Prefer the laid-out stage box so the map never overflows into tabs/controls.
    maxW = Math.max(stage.clientWidth || window.innerWidth - 48, 100);
    var stageH = stage.clientHeight;
    if (stageH >= 80) {
      maxH = stageH;
    } else {
      maxH = Math.round(window.innerHeight * 0.55);
    }
  }

  var scaleFit = Math.min(maxW / scene_map_width, maxH / scene_y_max);
  if (!Number.isFinite(scaleFit) || scaleFit <= 0) {
    return;
  }

  var displayW = Math.round(scene_map_width * scaleFit);
  var displayH = Math.round(scene_y_max * scaleFit);
  svg.setAttribute("width", displayW);
  svg.setAttribute("height", displayH);
  $(svg).width(displayW).height(displayH);
}

window.fitSceneMapDisplay = fitSceneMapDisplay;

/** Re-request camera strip snapshots (React cards may mount after MQTT connect). */
window.ssRefreshCameraSnapshots = function () {
  var client = window.ssMqttClient;
  if (!client) {
    return;
  }
  if (!$(".snapshot-image").length) {
    return;
  }
  if (!window.location.href.includes("/cam/calibrate/")) {
    try {
      client.subscribe(APP_NAME + IMAGE_CAMERA + "+");
    } catch (e) {
      /* already subscribed */
    }
  }
  $(".snapshot-image").each(function () {
    var topics = {};
    var primary =
      this.getAttribute("data-topic") ||
      this.getAttribute("topic") ||
      $(this).attr("topic");
    var byName = this.getAttribute("data-topic-name");
    if (primary) {
      topics[primary] = true;
    }
    if (byName) {
      topics[byName] = true;
    }
    Object.keys(topics).forEach(function (topic) {
      client.publish(topic, "getimage");
    });
  });
};

function sensorHasMapGeometry(sensor) {
  if (!sensor || !sensor.area || sensor.area === "scene") {
    return false;
  }
  if (sensor.area === "circle") {
    return (
      Number.isFinite(Number(sensor.x)) &&
      Number.isFinite(Number(sensor.y)) &&
      Number.isFinite(Number(sensor.radius))
    );
  }
  if (sensor.area === "poly") {
    return Array.isArray(sensor.points) && sensor.points.length >= 3;
  }
  return false;
}

/** Draw / refresh singleton sensors from React-rendered .singleton cards. */
window.ssDrawSingletonSensors = function () {
  if (typeof svgCanvas === "undefined" || !svgCanvas) {
    return;
  }
  $(".singleton").each(function () {
    var raw = $(".area-json", this).val();
    if (!raw) {
      return;
    }
    var sensor;
    try {
      sensor = $.parseJSON(raw);
    } catch (e) {
      return;
    }
    if (!sensorHasMapGeometry(sensor)) {
      return;
    }
    var i = $(".sensor-id", this).text();
    if (!i) {
      return;
    }
    var title =
      ($(this).attr("data-sensor-name") || "").trim() ||
      $(".card-header", this).clone().children().remove().end().text().trim();
    if (title) {
      sensor.title = title;
    }
    drawSensor(sensor, i, "sensor");
    if (sensor.sectors && sensor.sectors.thresholds.length > 0) {
      singleton_color_sectors[i] = sensor.sectors;
    }
  });
};

window.ssRemoveSingletonSensor = function (sensorId) {
  if (!sensorId) {
    return;
  }
  var sel = "#sensor_" + sensorId;
  if (svgCanvas && typeof svgCanvas.select === "function") {
    var snapEl = svgCanvas.select(sel);
    if (snapEl) {
      snapEl.remove();
      return;
    }
  }
  var el = document.getElementById("sensor_" + sensorId);
  if (el) {
    el.remove();
  }
};

if (isCalibratePage()) {
  // distortion available only for supporting video analytics microservice
  initializeCalibration(scene_id, socket);
}

function getColorForValue(roi_id, value, sectors) {
  let color_for_occupancy = "white";
  if (sectors[roi_id]) {
    const { thresholds, range_max } = sectors[roi_id];
    if (value <= range_max) {
      for (const sector of thresholds) {
        if (value >= sector.color_min) {
          color_for_occupancy = sector.color;
        }
      }
    }
  }
  return color_for_occupancy;
}

async function checkBrokerConnections() {
  const urlSecure = "wss://" + window.location.host + "/mqtt";

  try {
    await checkMqttConnection(urlSecure);
  } catch (error) {
    console.error("MQTT port not available:", error);
    return;
  }

  const currentBroker = $("#broker").val();
  const updatedBroker = currentBroker.replace(
    "localhost",
    window.location.host,
  );
  $("#broker").val(updatedBroker);
  console.log(`Url ${urlSecure} is open`);

  $("#connect")
    .off("click.ssMqttConnect")
    .on("click.ssMqttConnect", function () {
      var brokerInput = document.getElementById("broker");
      var brokerUrl =
        brokerInput && "value" in brokerInput
          ? brokerInput.value
          : $("#broker").val();
      console.log("Attempting to connect to " + brokerUrl);
      if (
        window.ssMqttClient &&
        typeof window.ssMqttClient.end === "function"
      ) {
        try {
          window.ssMqttClient.end(true);
        } catch (e) {
          /* ignore */
        }
      }
      var client = mqtt.connect(brokerUrl);
      window.ssMqttClient = client;
      sessionStorage.setItem("connectToMqtt", true);

      client.on("connect", function () {
        console.log("Connected to " + brokerUrl);
        if ($("#topic").val() !== undefined) {
          client.subscribe($("#topic").val());
          console.log("Subscribed to " + $("#topic").val());
        }

        client.subscribe(APP_NAME + "/event/" + "+/" + scene_id + "/+/+");
        console.log(
          "Subscribed to " + APP_NAME + "/event/" + "+/" + scene_id + "/+/+",
        );

        if (document.getElementById("scene_children")?.value !== "0") {
          client.subscribe(APP_NAME + SYS_CHILDSCENE_STATUS + "/+");
          console.log(
            "Subscribed to " + APP_NAME + SYS_CHILDSCENE_STATUS + "/+",
          );
          var remote_childs = $("[id^='mqtt_status_remote']")
            .map((_, el) => el.id.split("_").slice(3).join("_"))
            .get();
          remote_childs.forEach((e) => {
            client.publish(
              APP_NAME + SYS_CHILDSCENE_STATUS + "/" + e,
              "isConnected",
            );
          });
        }

        $("#mqtt_status").addClass("connected");

        // Camera strip may mount via React after connect — always wire live-view + subscribe.
        if (isCalibratePage()) {
          var calSensor = calibrateSensorId();
          if (calSensor) {
            client.subscribe(APP_NAME + IMAGE_CALIBRATE + calSensor);
          }
          requestCalibrateFrames(client);
        } else {
          client.subscribe(APP_NAME + IMAGE_CAMERA + "+");
        }
        window.ssRefreshCameraSnapshots();
        // React camera cards may portal in after this connect callback.
        window.setTimeout(function () {
          window.ssRefreshCameraSnapshots();
        }, 500);
        window.setTimeout(function () {
          window.ssRefreshCameraSnapshots();
        }, 1500);
        $("input#live-view")
          .off("change.ssLiveView")
          .on("change.ssLiveView", function () {
            if ($(this).is(":checked")) {
              window.ssRefreshCameraSnapshots();
              $("#cameras-tab").click();
              $(".camera-card").addClass("live-view");
            } else {
              $(".camera-card").removeClass("live-view");
            }
          });
      });

      client.on("close", function () {
        $("[id^='mqtt_status']").removeClass("connected");
        $(".rate").text("--");
        $("#scene-rate").text("--");
        if (
          window.ssSceneTelemetry &&
          typeof window.ssSceneTelemetry.clearRates === "function"
        ) {
          window.ssSceneTelemetry.clearRates();
        }
        if (
          window.ssSceneTelemetry &&
          typeof window.ssSceneTelemetry.setSceneRate === "function"
        ) {
          window.ssSceneTelemetry.setSceneRate("--");
        }
        window.dispatchEvent(new CustomEvent("ss-telemetry-clear"));
      });

      client.on("message", function (topic, data) {
        var msg;
        try {
          msg = JSON.parse(data);
        } catch (error) {
          msg = String(data);
        }
        var img;

        if (topic.includes(DATA_REGULATED)) {
          if (show_telemetry) {
            // Show the FPS for each camera that currently has a live preview.
            // scene.rate is a sticky cache and still lists cameras that went offline.
            if (msg.rate && typeof msg.rate === "object") {
              for (const [key, value] of Object.entries(msg.rate)) {
                var fps = Number(value);
                var rateText =
                  (Number.isFinite(fps) ? fps.toFixed(2) : "--") + " FPS";
                applyCameraRate(key, rateText);
              }
            }

            // Show the scene controller update rate
            var sceneRateEl = document.getElementById("scene-rate");
            var sceneRate = Number(msg.scene_rate);
            if (Number.isFinite(sceneRate)) {
              var sceneRateText = sceneRate.toFixed(1);
              if (sceneRateEl) {
                sceneRateEl.innerText = sceneRateText;
              }
              if (
                window.ssSceneTelemetry &&
                typeof window.ssSceneTelemetry.setSceneRate === "function"
              ) {
                window.ssSceneTelemetry.setSceneRate(sceneRateText);
              }
              window.dispatchEvent(
                new CustomEvent("ss-scene-rate", {
                  detail: { hz: sceneRateText },
                }),
              );
            }
          }

          // Plot the marks
          plot(
            msg.objects,
            scale,
            scene_y_max,
            svgCanvas,
            show_telemetry,
            show_trails,
            assetMarkColors,
          );
        } else if (topic.includes("event")) {
          var etype = topic.split("/")[2];
          if (etype == "region") {
            if (msg["metadata"]?.fromSensor == true) {
              drawSensor(
                msg["metadata"],
                msg["metadata"]["title"],
                "child_sensor",
              );
            } else {
              drawRoi(msg["metadata"], msg["metadata"]["uuid"], "child_roi");
            }
            var counts = msg["counts"];
            var occupancy = 0;
            if (counts && typeof counts === "object") {
              Object.keys(counts).forEach(function (category) {
                var count = counts[category];
                if (typeof count === "number") {
                  occupancy += count;
                }
              });
              setROIColor(msg["metadata"]["uuid"], occupancy);
            }

            var value = msg["value"];
            if (value) {
              setSensorColor(
                msg["metadata"]["title"],
                value,
                msg["metadata"]["area"],
              );
            }
          } else if (etype == "tripwire") {
            var trip = msg["metadata"];
            trip.points[0] = metersToPixels(trip.points[0], scale, scene_y_max);
            trip.points[1] = metersToPixels(trip.points[1], scale, scene_y_max);
            newTripwire(trip, msg["metadata"]["uuid"], "child_tripwire");
          }
        } else if (topic.includes("singleton")) {
          plotSingleton(msg);
        } else if (topic.includes(IMAGE_CALIBRATE)) {
          applyCalibrationImage(msg);
        } else if (topic.includes(IMAGE_CAMERA)) {
          if (isCalibratePage()) {
            return;
          }
          // Use native JS since jQuery.load() pukes on data URI's
          if ($(".snapshot-image").length) {
            var id = topic.split("camera/")[1];
            var previewImgs = document.querySelectorAll(
              "[id='" +
                id +
                "'], [id='card-preview-" +
                id +
                "'], [data-ss-card-sensor='" +
                id +
                "'], [data-ss-card-name='" +
                id +
                "']",
            );
            previewImgs.forEach(function (img) {
              img.setAttribute("src", "data:image/jpeg;base64," + msg.image);
              img.classList.remove("display-none");
              var offline = img.parentElement
                ? img.parentElement.querySelectorAll(".cam-offline")
                : [];
              offline.forEach(function (el) {
                el.style.display = "none";
                el.hidden = true;
              });
            });

            if ($("input#live-view").is(":checked")) {
              client.publish(APP_NAME + CMD_CAMERA + id, "getimage");
            }
          }
        } else if (topic.includes(DATA_CAMERA)) {
          var id = topic.slice(topic.lastIndexOf("/") + 1);
          if (show_telemetry) {
            var camFps = Number(msg.rate);
            var camRateText =
              (Number.isFinite(camFps) ? camFps.toFixed(2) : "--") + " FPS";
            applyCameraRate(id, camRateText);
          }
          $("#updated-" + id).text(msg.timestamp);
        } else if (topic.includes("/child/status")) {
          var child = topic.slice(topic.lastIndexOf("/") + 1);
          if (msg === "connected") {
            console.log(child + msg);
            $("#mqtt_status_remote_" + child).addClass("connected");
          } else if (msg === "disconnected") {
            $("#mqtt_status_remote_" + child).removeClass("connected");
          }
        }
      });

      client.on("error", function (e) {
        console.log("MQTT error: " + e);
      });

      $("#disconnect")
        .off("click.ssMqttDisconnect")
        .on("click.ssMqttDisconnect", function () {
          sessionStorage.setItem("connectToMqtt", false);
          client.end();
        });

      var topic = APP_NAME + CMD_CAMERA + $("#sensor_id").val();
      $("#snapshot").on("click", function () {
        client.publish(topic, "getcalibrationimage");
      });
    });

  // Connect by default
  var connectToMqtt = sessionStorage.getItem("connectToMqtt");
  if (connectToMqtt === null || connectToMqtt) {
    $("#connect").trigger("click");
    if ($("#snapshot").length != 0) {
      $("#snapshot").trigger("click");
    }
  }
}

$("#auto-autocalibration").on("click", async function () {
  const camera_id = $("#sensor_id").val();
  document.getElementById("auto-autocalibration").disabled = true;

  if (socket.connected) {
    socket.emit("register_camera", { camera_id: camera_id });
    console.log("Registered camera with WebSocket:", camera_id);
  } else {
    console.warn(
      "WebSocket not connected, calibration results will not be received via WebSocket",
    );
  }
  var camera_intrinsics = [
    [
      parseFloat($("#id_intrinsics_fx").val()),
      0,
      parseFloat($("#id_intrinsics_cx").val()),
    ],
    [
      0,
      parseFloat($("#id_intrinsics_fy").val()),
      parseFloat($("#id_intrinsics_cy").val()),
    ],
    [0, 0, 1],
  ];

  let image = camera_calibration.camCanvas.image.src;
  if (image.startsWith("data:image/")) {
    image = image.split(",")[1];
  }

  const data = await startCameraCalibration(
    camera_id,
    image,
    camera_intrinsics,
  );
  if (data.status === "error") {
    console.log("Calibration failed");
  } else {
    console.log("Calibration started:", data);
  }
});

function plotSingleton(m) {
  var $sensor = $("#sensor_" + m.id);

  $(".area", $sensor).css("fill", m.status);
  $("text.value", $sensor).text(m.value.toString());
}

function addPoly() {
  $("#svgout").addClass("adding-roi");
  adding = true;
}

function cancelAddPoly() {
  $("#svgout").removeClass("adding-roi");
  adding = false;
}

function addTripwire() {
  $("#svgout").addClass("adding-tripwire");
  adding = true;
}

function cancelAddTripwire() {
  $("#svgout").removeClass("adding-tripwire");
  adding = false;
}

function initArea(a) {
  cancelAddPoly();

  $(".autoshow").each(function () {
    var $pane = $(this).closest(".radio").find(".autoshow-pane");

    if ($(this).is(":checked")) {
      $pane.show();
    } else {
      $pane.hide();
    }
  });

  if ($(a).val() == "poly") {
    if (!$("#id_rois").val() || $("#id_rois").val() == "[]") {
      addPoly();
    }
    $(".roi").show();
  } else {
    $(".roi").hide();
  }

  if ($(a).val() == "circle") {
    $(".sensor_r").show();
  } else {
    $(".sensor_r").hide();
  }
}

function numberRois() {
  if (window.ssUseReactMap) {
    $(".form-roi").each(function (n) {
      $(this)
        .find(".roi-number")
        .text(String(n + 1));
    });
    if ($(".form-roi").length > 0) {
      $("#no-regions").hide();
    } else {
      $("#no-regions").show();
    }
    numberTabs();
    return;
  }
  if (!svgCanvas) {
    return;
  }
  var groups = svgCanvas.selectAll("g.roi");

  groups.forEach(function (e, n) {
    var id = e.attr("id");
    var title = $("#form-" + id + " input.roi-title").val();
    var text = e.select("text");

    var isNewlyCreated = title.trim() === "";

    if (isNewlyCreated) {
      if (text) {
        text.remove();
      }
    } else {
      if (text) {
        text.node.innerText = title;
      } else {
        const roi_group_points = e.select("polygon").attr("points");
        var center = polyCenter(roi_group_points);

        text = e.text(center[0], center[1], title);
      }
    }

    $("#form-" + id)
      .find(".roi-number")
      .text(String(n + 1));
  });

  if (groups.length > 0) {
    $("#no-regions").hide();
  } else {
    $("#no-regions").show();
  }

  numberTabs();
}

window.numberRois = numberRois;

function numberTripwires() {
  if (window.ssUseReactMap) {
    $(".form-tripwire").each(function (n) {
      $(this)
        .find(".tripwire-number")
        .text(String(n + 1));
    });
    if ($(".form-tripwire").length > 0) {
      $("#no-tripwires").hide();
    } else {
      $("#no-tripwires").show();
    }
    numberTabs();
    return;
  }
  if (!svgCanvas) {
    return;
  }
  var groups = svgCanvas.selectAll("g.tripwire");

  groups.forEach(function (e, n) {
    var text = e.select("text");
    var id = e.attr("id");
    var title = $("#form-" + id + " input.tripwire-title").val();
    var isNewlyCreated = title.trim() === "";

    if (isNewlyCreated) {
      if (text) {
        text.remove();
      }
    } else {
      if (text) {
        text.node.innerHTML = title;
      } else {
        var line = e.select("line");
        var mid = [
          (parseInt(line.attr("x1")) + parseInt(line.attr("x2"))) / 2,
          (parseInt(line.attr("y1")) + parseInt(line.attr("y2"))) / 2,
        ];
        text = e.text(mid[0], mid[1], title).addClass("label");
      }
    }

    $("#form-" + id)
      .find(".tripwire-number")
      .text(String(n + 1));
  });

  if (groups.length > 0) {
    $("#no-tripwires").hide();
  } else {
    $("#no-tripwires").show();
  }

  stringifyTripwires();
  numberTabs();
}

window.numberTripwires = numberTripwires;

function liveMountCount(mountId, itemSelector) {
  var mount = document.getElementById(mountId);
  if (!mount || mount.childElementCount === 0) {
    return undefined;
  }
  return mount.querySelectorAll(itemSelector).length;
}

// Show number of child cards in a tab
function numberTabs() {
  $(".show-count").each(function () {
    var href = $(this).closest("a").attr("href");
    if (!href) {
      return;
    }
    var numCards = $(".count-item", href).length;
    $(this).text("(" + numCards + ")");
  });
  var counts = {};
  var cameras = liveMountCount("ss-cameras-mount", ".count-item");
  var sensors = liveMountCount("ss-sensors-mount", ".count-item");
  var children = liveMountCount("ss-children-mount", ".ss-control-card");
  if (cameras !== undefined) {
    counts.cameras = cameras;
  }
  if (sensors !== undefined) {
    counts.sensors = sensors;
  }
  if (children !== undefined) {
    counts.children = children;
  }
  if (Object.keys(counts).length) {
    window.dispatchEvent(new CustomEvent("ss-tab-counts", { detail: counts }));
  }
}

window.numberTabs = numberTabs;

// Turn the regions of interest into a string for saving to the database
function stringifyRois() {
  if (window.ssUseReactMap) {
    if (window.ssMap && typeof window.ssMap.flushHidden === "function") {
      window.ssMap.flushHidden();
    }
    return;
  }
  rois = [];
  var groups = svgCanvas.selectAll(".roi");

  groups.forEach(function (g) {
    var i = g.attr("id");
    var title = $("#form-" + i + " input.roi-title").val();
    var p = g.select("polygon");
    var region_uuid = i.split("_")[1];
    points = p.attr("points");

    // Back end expects array of [x,y] tuples, so compose tuples array from poly points
    var tuples = [];
    var tuple = [];

    // Convert from pixels to meters and change origin to bottom left
    points.forEach(function (point, n) {
      if (n % 2 === 0) {
        tuple = [];
        tuple[0] = parseFloat(point / scale);
      } else {
        tuple[1] = parseFloat((scene_y_max - point) / scale);
        tuples.push(tuple);
      }
    });

    var roi_sectors = [];
    var input_mins = document.querySelectorAll(
      "#form-" + i + " [class$='_min']",
    );
    for (var j = 0; j < input_mins.length; j++) {
      var sector = {};
      var color = input_mins[j].className.split("_")[0];
      sector.color = color;
      sector.color_min = parseInt(input_mins[j].value);
      roi_sectors.push(sector);
    }

    // Compose ROI entry as a polygon
    var entry = {
      title: title,
      points: tuples,
      uuid: region_uuid,
    };

    if ($("#form-" + i).length) {
      const $formElement = $("#form-" + i);
      const volumetric =
        $formElement.find(".roi-volumetric").prop("checked") || false;
      const height = parseFloat($formElement.find(".roi-height").val()) || 1.0;
      const buffer = parseFloat($formElement.find(".roi-buffer").val()) || 0.0;
      entry = {
        ...entry,
        volumetric: volumetric,
        height: height,
        buffer_size: buffer,
      };
    }

    const range_max_element = document.querySelector(
      "#form-" + i + " [class$='_max']",
    );
    if (range_max_element) {
      var range_max = parseInt(range_max_element.value);
      entry.range_max = range_max;
      entry.sectors = roi_sectors;
    }

    rois.push(entry);
  });

  // Update hidden field
  $("#id_rois").val(JSON.stringify(rois));
  try {
    window.dispatchEvent(
      new CustomEvent("ss-geometry-stringified", { detail: { kind: "rois" } }),
    );
  } catch (e) {
    /* ignore */
  }
}

window.stringifyRois = stringifyRois;

function stringifyTripwires() {
  if (window.ssUseReactMap) {
    if (window.ssMap && typeof window.ssMap.flushHidden === "function") {
      window.ssMap.flushHidden();
    }
    return;
  }
  tripwires = [];
  var groups = svgCanvas.selectAll(".tripwire");

  groups.forEach(function (g) {
    var i = g.attr("id");
    var title = $("#form-" + i + " input.tripwire-title").val();
    var l = g.select(".tripline");
    var trip_uuid = i.split("_")[1];

    // Compose tripwire entry just like polygons
    var entry = {
      title: title,
      uuid: trip_uuid,
      points: [
        pixelsToMeters(
          [l.node.x1.baseVal.value, l.node.y1.baseVal.value],
          scale,
          scene_y_max,
        ),
        pixelsToMeters(
          [l.node.x2.baseVal.value, l.node.y2.baseVal.value],
          scale,
          scene_y_max,
        ),
      ],
    };

    tripwires.push(entry);
  });

  // Update hidden field
  $("#tripwires").val(JSON.stringify(tripwires));
  try {
    window.dispatchEvent(
      new CustomEvent("ss-geometry-stringified", { detail: { kind: "trips" } }),
    );
  } catch (e) {
    /* ignore */
  }
}

window.stringifyTripwires = stringifyTripwires;

// Get the center coordinate of a polygon
function polyCenter(pts) {
  var center = [0, 0];
  var numPts = 0;

  if (typeof pts !== "undefined") {
    numPts = pts.length / 2;

    pts.forEach(function (p, i) {
      p = parseInt(p); // Force integer math :(

      if (i % 2 === 0) center[0] = center[0] + p;
      else center[1] = center[1] + p;
    });

    center[0] = parseInt(center[0] / numPts);
    center[1] = parseInt(center[1] / numPts);
  }

  return center;
}

function editPolygon(group) {
  var circles = group.selectAll("circle");
  if (editing) {
    editing = false;

    circles.forEach(function (c) {
      c.undrag();
      c.removeClass("is-handle");
    });

    stringifyRois();
  } else {
    editing = true;

    circles.forEach(function (c) {
      c.drag(move, start, stop);
      c.addClass("is-handle");
    });
  }
}

function closePolygon() {
  var group = Snap.select("g.drawPoly");
  var i = "roi_" + $(".roi-number").length;

  adding = false;
  $("#svgout").removeClass("adding-roi");

  group
    .attr("id", i)
    .removeClass("drawPoly")
    .addClass("poly roi")
    .select(".start-point")
    .removeClass("start-point");

  group.dblclick(function () {
    editPolygon(this);
  });

  if ($(".sensor").length) group.insertBefore(svgCanvas.select(".sensor"));

  points = [];
  drawing = false;

  if (!$("#map").hasClass("singletonCal")) {
    var roiFormPayload = {
      svgId: i,
      uuid: i.split("_")[1],
      title: "",
    };
    if (
      window.ssRoiEditors &&
      typeof window.ssRoiEditors.addRoi === "function"
    ) {
      window.ssRoiEditors.addRoi(roiFormPayload);
    } else {
      window.dispatchEvent(
        new CustomEvent("ss-roi-form-add", { detail: roiFormPayload }),
      );
    }

    numberRois();
  }

  stringifyRois();
}

function move(dx, dy) {
  var group = this.parent();
  var circles = group.selectAll("circle");
  group.select("polygon").remove();
  points = [];

  this.attr({
    cx: this.data("origX") + dx,
    cy: this.data("origY") + dy,
  });

  circles.forEach(function (c) {
    points.push(c.attr("cx"), c.attr("cy"));
  });

  var poly = group.polygon(points);
  poly.prependTo(poly.node.parentElement);

  var text = group.select("text");
  var center = polyCenter(points);
  if (text) {
    text.attr({
      x: center[0],
      y: center[1],
    });
  }
}

function move1(dx, dy) {
  // Circles use cx, cy instead of x, y
  if (this.type === "circle") {
    this.attr({
      cx: this.data("origX") + dx,
      cy: this.data("origY") + dy,
    });

    // Move the circle measurement area as well
    svgCanvas
      .select(".sensor_r")
      .attr("cx", this.attr("cx"))
      .attr("cy", this.attr("cy"));
  }
  // If not a circle, must be an icon image
  else {
    this.attr({
      x: this.data("origX") + dx,
      y: this.data("origY") + dy,
    });

    // Move the circle measurement area as well, centered on the icon
    svgCanvas
      .select(".sensor_r")
      .attr("cx", parseInt(this.attr("x")) + icon_size / 2)
      .attr("cy", parseInt(this.attr("y")) + icon_size / 2);
  }
}

function start() {
  dragging = true;

  if (this.type === "circle") {
    this.data("origX", parseInt(this.attr("cx")));
    this.data("origY", parseInt(this.attr("cy")));
  } else {
    this.data("origX", parseInt(this.attr("x")));
    this.data("origY", parseInt(this.attr("y")));
  }
}

function stop() {
  dragging = false;
  points = [];
}

function stop1() {
  dragging = false;

  var sensor_px = [];
  if (this.type === "circle") {
    sensor_px = [parseFloat(this.attr("cx")), parseFloat(this.attr("cy"))];
  } else {
    sensor_px = [
      parseInt(this.attr("x")) + icon_size / 2,
      parseInt(this.attr("y")) + icon_size / 2,
    ];
  }

  // Persist sensor location in meters in form fields
  var sensor_m = pixelsToMeters(sensor_px, scale, scene_y_max);
  $("#id_sensor_x").val(sensor_m[0]);
  $("#id_sensor_y").val(sensor_m[1]);
}

function dragTripwire(dx, dy) {
  var group = this.parent();
  var line = group.select("line");

  this.attr({
    cx: this.data("origX") + dx,
    cy: this.data("origY") + dy,
  });

  if (this.attr("point") == 0) {
    line.attr({
      x1: this.data("origX") + dx,
      y1: this.data("origY") + dy,
    });
  } else if (this.attr("point") == 1) {
    line.attr({
      x2: this.data("origX") + dx,
      y2: this.data("origY") + dy,
    });
  }

  updateArrow(group);
}

function startDragTripwire() {
  this.data("origX", parseInt(this.attr("cx")));
  this.data("origY", parseInt(this.attr("cy")));
}

function stopDragTripwire() {
  stringifyTripwires();
}

function newTripwire(e, index, type = "tripwire") {
  var i = type + "_" + index;

  if (type == "child_tripwire" && document.getElementById(i)) {
    var line = document.getElementById(i).querySelector("line");
    line.setAttribute("x1", e.points[0][0]);
    line.setAttribute("y1", e.points[0][1]);
    line.setAttribute("x2", e.points[1][0]);
    line.setAttribute("y2", e.points[1][1]);
    document
      .getElementById(i)
      .querySelectorAll("circle")
      .forEach(function (c, idx) {
        c.setAttribute("cx", e.points[idx][0]);
        c.setAttribute("cy", e.points[idx][1]);
      });
    updateArrow(svgCanvas.select("#" + i));
    var text = document.getElementById(i).querySelector("text");
    text.textContent = e.from_child_scene + " " + e.title;
  } else if (
    document.getElementById("tripwire_" + index) === null &&
    svgCanvas
  ) {
    var g = svgCanvas.group();
    if (e.title) {
      e.title = e.title.trim();
    }
    g.attr("id", i).addClass(type);

    var line = g.line(
      e.points[0][0],
      e.points[0][1],
      e.points[1][0],
      e.points[1][1],
    );
    line.addClass("tripline");

    e.points.forEach(function (p, n) {
      var cir = g.circle(p[0], p[1], radius);

      cir.attr("point", n).addClass("point_" + n);
      cir.drag(dragTripwire, startDragTripwire, stopDragTripwire);
    });

    updateArrow(g);

    if (type == "tripwire") {
      var tripPayload = {
        svgId: i,
        uuid: String(index),
        title: e.title || "",
        topic:
          APP_NAME + "/event/tripwire/" + scene_id + "/" + index + "/objects",
      };
      if (
        window.ssRoiEditors &&
        typeof window.ssRoiEditors.addTripwire === "function" &&
        (!window.ssRoiEditors.hasTripwire ||
          !window.ssRoiEditors.hasTripwire(i))
      ) {
        window.ssRoiEditors.addTripwire(tripPayload);
      } else {
        window.dispatchEvent(
          new CustomEvent("ss-tripwire-form-add", { detail: tripPayload }),
        );
      }
    } else {
      var text = g.select("text");
      text.textContent = e.from_child_scene + " " + e.title;
    }
  }
  numberTripwires();
}

// Function to get tripwire/roi form values
function getRoiValues(id, roi) {
  var cur_rois = [];
  var form_rois = document.getElementsByClassName(id);
  for (var i = 0; i < form_rois.length - 1; i++) {
    cur_rois.push(form_rois[i].value.trim());
  }
  return cur_rois;
}

window.getRoiValues = getRoiValues;

function find_duplicates(curr_roi) {
  const nameCounts = new Map();
  const duplicates = new Set();

  for (const name of curr_roi) {
    const trimmedName = name.trim();
    if (trimmedName) {
      if (nameCounts.has(trimmedName)) {
        duplicates.add(trimmedName);
      } else {
        nameCounts.set(trimmedName, 1);
      }
    }
  }

  return Array.from(duplicates);
}

function updateArrow(group) {
  var arrow = group.select(".arrow");
  var label = group.select(".label");
  var x1, x2, y1, y2;
  var l = 20; // Length of arrow in pixels
  var n = parseInt(group.attr("id").split("_")[1]);

  x1 = parseInt(group.select(".point_0").attr("cx"));
  y1 = parseInt(group.select(".point_0").attr("cy"));
  x2 = parseInt(group.select(".point_1").attr("cx"));
  y2 = parseInt(group.select(".point_1").attr("cy"));

  var v = [x2 - x1, y2 - y1];
  var magV = Math.sqrt(v[0] * v[0] + v[1] * v[1]);

  var a = [-l * (v[1] / magV), l * (v[0] / magV)];
  var mid = [x1 + (x2 - x1) / 2, y1 + (y2 - y1) / 2];

  if (arrow == null) {
    arrow = group
      .line(mid[0], mid[1], mid[0] + a[0], mid[1] + a[1])
      .addClass("arrow");
    label = group.text(mid[0] - a[0], mid[1] - a[1], "").addClass("label");
  } else {
    arrow.attr({
      x1: mid[0],
      y1: mid[1],
      x2: mid[0] + a[0],
      y2: mid[1] + a[1],
    });

    label.attr({
      x: mid[0] - a[0],
      y: mid[1] - a[1],
    });
  }
}

// Function to save roi and tripwires (React REST persist required)
async function saveRois(roi_values) {
  var duplicates = find_duplicates(roi_values);
  if (duplicates.length > 0) {
    alert(duplicates.toString() + " already exists. Try a different name");
    return;
  }
  if (typeof window.ssPersistGeometry !== "function") {
    alert("Save is unavailable — React geometry persist is not mounted.");
    return;
  }
  try {
    await window.ssPersistGeometry(roi_values);
  } catch (err) {
    console.error(err);
    alert("Failed to save regions: " + (err?.message || String(err)));
  }
}

window.saveRois = saveRois;

if (svgCanvas) {
  svgCanvas.mouseup(function (e) {
    if (dragging || !adding) return;
    drawing = true;

    var thisPoint = svgPointerToScene(e);

    var circle;

    if ($("#svgout").hasClass("adding-roi")) {
      // Create group or add point to existing group
      if (!Snap.select("g.drawPoly")) {
        points = [];
        g = svgCanvas.group();
        g.addClass("drawPoly");
        circle = g
          .circle(thisPoint[0], thisPoint[1], radius)
          .addClass("start-point vertex");
      } else {
        if (Snap(e.target).hasClass("start-point")) {
          closePolygon();
          return;
        } else {
          g.select("polygon").remove();
          circle = g
            .circle(thisPoint[0], thisPoint[1], radius)
            .addClass("vertex");
        }
      }

      // Compose the polygon
      points.push(thisPoint[0], thisPoint[1]);
      var poly = g.polygon(points);

      // Reorder so the polygon is on the bottom
      poly.prependTo(poly.node.parentElement);
    }
    if ($("#svgout").hasClass("adding-tripwire")) {
      if (!Snap.select("g.drawTripwire")) {
        // This makes a tripwire 50 pixels long by default
        var defaultLength = 50;
        var tempPoints = {
          points: [
            [thisPoint[0] - defaultLength / 2, thisPoint[1]],
            [thisPoint[0] + defaultLength / 2, thisPoint[1]],
          ],
        };
        var tripwireIndex = $(".tripwire").length;

        var imageWidth = $("#svgout image")[0].width.baseVal.value;
        var imageHeight = $("#svgout image")[0].height.baseVal.value;

        // Keep tripwire from falling outside the image
        if (tempPoints.points[1][0] > imageWidth) {
          tempPoints.points[0][0] = imageWidth - defaultLength;
          tempPoints.points[1][0] = imageWidth;
        } else if (tempPoints.points[0][0] < 0) {
          tempPoints.points[0][0] = 0;
          tempPoints.points[1][0] = defaultLength;
        }

        newTripwire(tempPoints, tripwireIndex);
        adding = false;
        $("#svgout").removeClass("adding-tripwire");
      }
    }
  });
}

function drawRoi(e, index, type) {
  var i = type + "_" + index;

  if (e.title) {
    e.title = e.title.trim();
  }

  let roi_points = [];

  e.points.forEach(function (m) {
    var p = metersToPixels(m, scale, scene_y_max);
    roi_points.push(p[0], p[1]);
  });

  // Convert points array to string for comparison
  var points_string = roi_points.join(",");

  // Update the child roi if changed
  if (type == "child_roi" && document.getElementById(i)) {
    var name_text = document.getElementById(i).querySelector("#name");
    var hierarchy_text = document.getElementById(i).querySelector("#hierarchy");
    var child_polygon = document.getElementById(i).querySelector("polygon");

    if (child_polygon.getAttribute("points") != points_string) {
      child_polygon.setAttribute("points", points_string);
      document
        .getElementById(i)
        .querySelectorAll("circle")
        .forEach(function (c, i) {
          var newCenter = metersToPixels(e.points[i], scale, scene_y_max);
          c.setAttribute("cx", newCenter[0]);
          c.setAttribute("cy", newCenter[1]);
        });

      var center = polyCenter(roi_points);
      name_text.setAttribute("x", center[0]);
      name_text.setAttribute("y", center[1]);
      hierarchy_text.setAttribute("x", center[0]);
      hierarchy_text.setAttribute("y", center[1] + 15);
    }
    name_text.textContent = e.title;
    hierarchy_text.textContent = e.from_child_scene;
  } else if (document.getElementById("roi_" + index) === null && svgCanvas) {
    var g = svgCanvas.group();
    g.attr("id", i).addClass(type);

    e.points.forEach(function (m) {
      var p = metersToPixels(m, scale, scene_y_max);
      var cir = g.circle(p[0], p[1], radius).addClass("vertex");
    });

    var poly = g.polygon(roi_points);
    poly.addClass("poly");

    // Reorder so the polygon is on the bottom
    poly.prependTo(poly.node.parentElement);

    g.dblclick(function () {
      editPolygon(this);
    });

    // Set ROI before (and below) sensor circle if on sensor page
    if ($(".sensor").length) {
      g.insertBefore(svgCanvas.selectAll(".sensor")[0]);
    }

    // Hide ROI if on the calibration page and it isn't selected
    if ($("#calibrate").length && !$("#id_area_2").is(":checked")) {
      $(".roi").hide();
    }

    if (type == "roi") {
      // React scene-detail island owns editor cards (hydrated from bootstrap).
      var greenMin = 0;
      var yellowMin = 2;
      var redMin = 5;
      var rangeMax = 10;
      if (e.sectors && e.sectors.thresholds) {
        e.sectors.thresholds.forEach(function (sector) {
          if (sector.color === "green") greenMin = Number(sector.color_min);
          if (sector.color === "yellow") yellowMin = Number(sector.color_min);
          if (sector.color === "red") redMin = Number(sector.color_min);
        });
        if (e.sectors.range_max !== undefined) {
          rangeMax = Number(e.sectors.range_max);
        }
      }
      var roiPayload = {
        svgId: i,
        uuid: index,
        title: e.title || "",
        volumetric: Boolean(e.volumetric),
        height: e.height !== undefined ? Number(e.height) : 1.0,
        buffer_size: e.buffer_size !== undefined ? Number(e.buffer_size) : 0.0,
        greenMin: greenMin,
        yellowMin: yellowMin,
        redMin: redMin,
        rangeMax: rangeMax,
        topic: APP_NAME + "/event/region/" + scene_id + "/" + index + "/count",
      };
      if (
        window.ssRoiEditors &&
        typeof window.ssRoiEditors.addRoi === "function" &&
        (!window.ssRoiEditors.hasRoi || !window.ssRoiEditors.hasRoi(i))
      ) {
        window.ssRoiEditors.addRoi(roiPayload);
      } else {
        window.dispatchEvent(
          new CustomEvent("ss-roi-form-add", { detail: roiPayload }),
        );
      }
    } else {
      var center = polyCenter(roi_points);
      var nameText = g.text(center[0], center[1], e.title).attr({ id: "name" });
      var hierarchyText = g
        .text(center[0], center[1] + 15, e.from_child_scene)
        .attr({ id: "hierarchy" });
    }
    numberRois();
  }
}

/**
 * Label sits above the marker (red dot / icon). Side anchors keep long names
 * inside the map near left/right edges; top/side room comes from padded viewBox.
 */
function sensorNameAnchor(x, y) {
  var nameY = y - 14;
  var nameX = x;
  var anchor = "middle";
  var sidePad = 48;
  if (x < sidePad) {
    anchor = "start";
  } else if (scene_map_width && x > scene_map_width - sidePad) {
    anchor = "end";
  }
  return { x: nameX, y: nameY, anchor: anchor };
}

function applySensorNameAnchor(nameEl, x, y) {
  if (!nameEl) {
    return;
  }
  var a = sensorNameAnchor(x, y);
  nameEl.setAttribute("x", a.x);
  nameEl.setAttribute("y", a.y);
  nameEl.setAttribute("text-anchor", a.anchor);
  // CSS sets text-anchor on .area-group text; inline style must win.
  nameEl.style.textAnchor = a.anchor;
}

function sensorGroupCenter(groupEl) {
  if (!groupEl) {
    return null;
  }
  var icon = groupEl.querySelector("image");
  if (icon) {
    var ix = parseFloat(icon.getAttribute("x"));
    var iy = parseFloat(icon.getAttribute("y"));
    if (Number.isFinite(ix) && Number.isFinite(iy)) {
      return { x: ix + icon_size / 2, y: iy + icon_size / 2 };
    }
  }
  var circle = groupEl.querySelector("circle.sensor, circle.area");
  if (circle) {
    var cx = parseFloat(circle.getAttribute("cx"));
    var cy = parseFloat(circle.getAttribute("cy"));
    if (Number.isFinite(cx) && Number.isFinite(cy)) {
      return { x: cx, y: cy };
    }
  }
  return null;
}

function drawSensor(sensor, index, type) {
  var i = type + "_" + index;
  var existing = document.getElementById(i);

  if (type === "sensor" && existing) {
    var nameEl = existing.querySelector("#name");
    if (nameEl && sensor.title) {
      nameEl.textContent = sensor.title;
    }
    var center = sensorGroupCenter(existing);
    if (center) {
      applySensorNameAnchor(nameEl, center.x, center.y);
    }
    return;
  }

  if (type === "child_sensor" && existing) {
    var name_text = existing.querySelector("#name");
    var hierarchy_text = existing.querySelector("#hierarchy");
    if (sensor.x && sensor.y) {
      var p = metersToPixels([sensor.x, sensor.y], scale, scene_y_max);
      sensor.x = p[0];
      sensor.y = p[1];
      var sensor_circle = document.querySelector("#" + i + " > .sensor");
      sensor_circle.setAttribute("cx", sensor?.x);
      sensor_circle.setAttribute("cy", sensor?.y);
      applySensorNameAnchor(name_text, sensor.x, sensor.y);
      hierarchy_text.setAttribute("x", sensor?.x);
      hierarchy_text.setAttribute("y", sensor?.y + 15);
    }
    if (sensor.area === "circle") {
      var outer_circle = document.querySelector("#" + i + " > .area");
      outer_circle.setAttribute("cx", sensor.x);
      outer_circle.setAttribute("cy", sensor.y);
      outer_circle.setAttribute("r", sensor.radius * scale);
    } else if (sensor.area === "poly") {
      let area_points = [];
      (sensor.points || []).forEach(function (m) {
        var p = metersToPixels(m, scale, scene_y_max);
        area_points.push(p[0], p[1]);
      });
      var points_string = area_points.join(",");
      var polygon = document.querySelector("#" + i + " > .area");
      if (polygon && polygon.getAttribute("points") != points_string) {
        polygon.setAttribute("points", points_string);
      }
    }
  } else if (document.getElementById("sensor_" + index) === null && svgCanvas) {
    var g = svgCanvas.group();
    g.attr("id", i).addClass("area-group");

    if (sensor.area === "circle") {
      var p = metersToPixels([sensor.x, sensor.y], scale, scene_y_max);
      sensor.x = p[0];
      sensor.y = p[1];
      sensor.radius = sensor.radius * scale;
      var circle = g.circle(sensor.x, sensor.y, sensor.radius).addClass("area");
      var text = g.text(sensor.x, sensor.y, "").addClass("value");
    } else if (sensor.area === "poly") {
      var tempPoints = [];
      (sensor.points || []).forEach(function (p) {
        p = metersToPixels(p, scale, scene_y_max);
        tempPoints.push(p[0], p[1]);
      });

      if (tempPoints.length >= 6) {
        var center = polyCenter(tempPoints);
        var poly = g.polygon(tempPoints).addClass("area");
        var text = g.text(center[0], center[1], "").addClass("value");
        if (
          sensor.x == null ||
          sensor.y == null ||
          (Number(sensor.x) === 0 && Number(sensor.y) === 0)
        ) {
          sensor.x = center[0] / scale;
          sensor.y = (scene_y_max - center[1]) / scale;
        }
      }
    }

    if ($(".sensor-icon", this).length) {
      // Circle branch already converted to pixels; poly/scene still in meters.
      if (sensor.area === "poly" || sensor.area === "scene") {
        var ip = metersToPixels([sensor.x, sensor.y], scale, scene_y_max);
        sensor.x = ip[0];
        sensor.y = ip[1];
      }
      var image = g.image(
        $(".sensor-icon", this).attr("src"),
        sensor.x - icon_size / 2,
        sensor.y - icon_size / 2,
        icon_size,
        icon_size,
      );
    } else {
      if (sensor.area === "poly" || sensor.area === "scene") {
        var p = metersToPixels([sensor.x, sensor.y], scale, scene_y_max);
        sensor.x = p[0];
        sensor.y = p[1];
      }
      var circle = g.circle(sensor.x, sensor.y, 7).addClass("sensor");
    }

    var namePos = sensorNameAnchor(sensor.x, sensor.y);
    var nameText = g.text(namePos.x, namePos.y, sensor.title).attr({ id: "name" });
    if (nameText && nameText.node) {
      nameText.node.setAttribute("text-anchor", namePos.anchor);
      nameText.node.style.textAnchor = namePos.anchor;
    }
    var hierarchyText = g
      .text(sensor.x, sensor.y + 15, sensor.from_child_scene)
      .attr({ id: "hierarchy" });
  }
}

function setColorForAllROIs() {
  const all_rois = getRoiValues("form-control roi-title", "roi");
  for (var roi of all_rois) {
    roi = roi.split("_")[1];
    setROIColor(roi, 0);
  }
}

// Toggle ROI/tripwire name label visibility (independent of whether the toggle UI exists on this page)
function setRoiNameVisibility(enabled) {
  $("#svgout").toggleClass("show-roi-names", enabled);
}

function setROIColor(roi_id, occupancy) {
  var roi_polygon = document.querySelector("#roi_" + roi_id + " polygon");
  if (roi_polygon) {
    if (is_coloring_enabled) {
      var color = getColorForValue(roi_id, occupancy, roi_color_sectors);
      roi_polygon.style.fill = color;
    } else {
      roi_polygon.style.fill = "";
    }
  }
}

function setSensorColor(sensor_id, value, area) {
  const sensor_area =
    area === "circle"
      ? document.querySelector(`#sensor_${sensor_id} circle`)
      : area === "poly"
        ? document.querySelector(`#sensor_${sensor_id} polygon`)
        : null;
  if (sensor_area) {
    if (is_coloring_enabled) {
      var color = getColorForValue(sensor_id, value, singleton_color_sectors);
      sensor_area.style.fill = color;
    } else {
      sensor_area.style.fill = "white";
    }
  }
}

$(document).ready(function () {
  const loginButton = document.getElementById("login-submit");
  const spinner = document.getElementById("login-spinner");
  const loginText = document.getElementById("login-text");
  const tokenElement = document.getElementById("auth-token");

  $(document).on("click", "#export-scene", async function (e) {
    e.preventDefault();
    if (!tokenElement) {
      return;
    }
    const authToken = `Token ${tokenElement.value}`;
    const restclient = new RESTClient(REST_URL, authToken);
    try {
      const response = await restclient.getScene(scene_id);
      if (response.statusCode !== 200)
        throw new Error("Failed to fetch scenes");

      const scene = response.content;
      const zip = new JSZip();

      zip.file(scene.name + ".json", JSON.stringify(scene, null, 2));
      const sceneName = scene.name.replace(/\s+/g, "_");

      if (scene.map) {
        try {
          const mapBlob = await fetchFileAsBlob(scene.map);
          const mapExt = scene.map.split(".").pop();
          zip.file(`${sceneName}.${mapExt}`, mapBlob);

          if (Array.isArray(scene.children)) {
            for (const child of scene.children) {
              const mapBlob = await fetchFileAsBlob(child.map);
              const mapExt = child.map.split(".").pop();
              zip.file(`${child.name}.${mapExt}`, mapBlob);
            }
          }
        } catch (err) {
          console.warn(`Skipping map for ${sceneName}:`, err);
        }
      }

      // Download the zip
      const zipBlob = await zip.generateAsync({ type: "blob" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(zipBlob);
      link.download = scene.name + ".zip";
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      console.error("Error exporting scene:", error);
    }
  });
  async function fetchFileAsBlob(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Failed to fetch: ${url}`);
    return await response.blob();
  }

  function checkDatabaseReady() {
    fetch(`${REST_URL}/database-ready`)
      .then((response) => response.json())
      .then((data) => {
        if (data.databaseReady) {
          loginButton.disabled = false;
          loginText.textContent = "Sign In";
          spinner.classList.add("hide-spinner");
        } else {
          loginButton.disabled = true;
          loginText.textContent = "Database Initializing...";
          spinner.classList.remove("hide-spinner");
          setTimeout(checkDatabaseReady, 5000);
        }
      })
      .catch((error) =>
        console.error("Error checking database readiness:", error),
      );
  }
  if (loginButton) {
    checkDatabaseReady();
  }

  if ($("#scale").val() !== "") {
    scale = $("#scale").val();
  }

  is_coloring_enabled = localStorage.getItem("visualize_rois") === "true";
  setRoiNameVisibility(is_coloring_enabled);

  const coloring_toggle = $("input#coloring-switch");
  if (coloring_toggle.length) {
    coloring_toggle.prop("checked", is_coloring_enabled);
    setColorForAllROIs();
  }

  coloring_toggle.on("change", function () {
    const isChecked = $(this).is(":checked");
    is_coloring_enabled = isChecked;
    localStorage.setItem("visualize_rois", isChecked);
    setRoiNameVisibility(isChecked);
    setColorForAllROIs();
  });

  // Operations to take after images are loaded
  $(".content").imagesLoaded(function () {
    // Camera calibration interface
    if (isCalibratePage()) {
      initializeCalibrationSettings();
      flushPendingCalibrationImage(window.ssMqttClient);
      window.setTimeout(function () {
        flushPendingCalibrationImage(window.ssMqttClient);
      }, 400);
    }

    // SVG scene implementation
    if (svgCanvas) {
      var assetTokenElement = document.getElementById("auth-token");
      if (assetTokenElement) {
        var assetRestClient = new RESTClient(
          REST_URL,
          `Token ${assetTokenElement.value}`,
        );
        assetRestClient.getAssets({}).then(function (response) {
          if (response.statusCode === SUCCESS && response.content?.results) {
            response.content.results.forEach(function (asset) {
              assetMarkColors[asset.name] = asset.mark_color || "black";
            });
          }
        });
      }

      var $image = $("#map img");
      var imgEl = $image[0];
      var image_w;
      var $rois = $("#id_rois");
      var $tripwires = $("#tripwires");
      var $child_rois = $("#id_child_rois");
      var $child_tripwires = $("#child_tripwires");
      var $child_sensors = $("#child_sensors");

      var image_src = $image.attr("src");

      // Scene detail: keep SVG user units in native map pixels so metersToPixels
      // (scene.scale) stays correct. Display size is handled by fitSceneMapDisplay().
      if (
        $image.closest(".scene-map-stage").length &&
        !$("#map").hasClass("singletonCal") &&
        imgEl &&
        imgEl.naturalWidth > 0 &&
        imgEl.naturalHeight > 0
      ) {
        image_w = imgEl.naturalWidth;
        scene_y_max = imgEl.naturalHeight;
      } else {
        image_w = $image.width();
        scene_y_max = $image.height();
      }

      scene_map_width = image_w;
      $image.remove();

      $("#svgout").width(image_w).height(scene_y_max);
      if (isSceneDetailMap()) {
        document
          .getElementById("svgout")
          .setAttribute("viewBox", sceneMapViewBox(image_w, scene_y_max));
        document
          .getElementById("svgout")
          .setAttribute("preserveAspectRatio", "xMidYMid meet");
      }
      var image = svgCanvas.image(image_src, 0, 0, image_w, scene_y_max);

      $("#svgout").show();
      fitSceneMapDisplay();

      // Add circle for singleton sensors
      if ($("#map").hasClass("singletonCal")) {
        var sensor_x = parseFloat($("#id_sensor_x").val());
        var sensor_y = parseFloat($("#id_sensor_y").val());
        // Bug in slider -- .val() doesn't work right and seems to max at 100
        var sensor_r = $("#id_sensor_r").attr("value");

        // Form fields store meters. Default to scene center if values missing.
        if (isNaN(sensor_x) || isNaN(sensor_y)) {
          var center_m = pixelsToMeters(
            [parseInt(image_w / 2), parseInt(scene_y_max / 2)],
            scale,
            scene_y_max,
          );
          sensor_x = center_m[0];
          sensor_y = center_m[1];
          $("#id_sensor_x").val(sensor_x);
          $("#id_sensor_y").val(sensor_y);
        }
        if (!sensor_r || sensor_r == "None") {
          sensor_r = parseInt(scene_y_max / 2);
        }

        var sensor_px = metersToPixels(
          [sensor_x, sensor_y],
          scale,
          scene_y_max,
        );
        sensor_x = sensor_px[0];
        sensor_y = sensor_px[1];

        // Set max on sensor_r slider to half of the image width
        $("#id_sensor_r").attr({
          min: 0,
          max: parseInt(image_w / 2),
          value: sensor_r,
        });

        // Add the point
        var sensor_circle = svgCanvas.circle(sensor_x, sensor_y, sensor_r);
        var sensor_icon = $("#icon").val();

        if (!sensor_icon) {
          var sensor = svgCanvas.circle(sensor_x, sensor_y, 7);
        } else {
          var sensor = svgCanvas.image(
            sensor_icon,
            sensor_x - icon_size / 2,
            sensor_y - icon_size / 2,
            icon_size,
            icon_size,
          );
        }

        sensor.addClass("is-handle sensor");
        sensor.drag(move1, start, stop1);

        sensor_circle.addClass("sensor_r");

        initArea($("input:checked"));
      }

      /* React may finish mounting cards after this; allow a late pass. */
      window.ssDrawSingletonSensors();

      // ROI Management //
      if ($rois.val()) {
        rois = [];
        tripwires = [];

        rois = JSON.parse($rois.val());
        rois.forEach(function (e, index) {
          drawRoi(e, e.uuid, "roi");

          if (e.sectors.thresholds.length > 0) {
            roi_color_sectors[e.uuid] = e.sectors;
          }
        });

        if ($tripwires.length) {
          tripwires = JSON.parse($tripwires.val());

          // Convert meters to pixels for displaying the tripwire
          tripwires.forEach((t) => {
            t.points[0] = metersToPixels(t.points[0], scale, scene_y_max);
            t.points[1] = metersToPixels(t.points[1], scale, scene_y_max);
          });

          tripwires.forEach(function (e, index) {
            newTripwire(e, e.uuid, "tripwire");
          });
          numberTripwires();
        }

        // Initial Child ROI's //
        if ($child_rois.val()) {
          child_rois = JSON.parse($child_rois.val());
          child_tripwires = JSON.parse($child_tripwires.val());
          child_sensors = JSON.parse($child_sensors.val());

          child_rois.forEach(function (e, index) {
            drawRoi(e, e.uuid, "child_roi");
          });

          child_tripwires.forEach((t) => {
            t.points[0] = metersToPixels(t.points[0], scale, scene_y_max);
            t.points[1] = metersToPixels(t.points[1], scale, scene_y_max);
          });

          child_tripwires.forEach(function (e, index) {
            newTripwire(e, e.uuid, "child_tripwire");
          });

          child_sensors.forEach(function (e, index) {
            drawSensor(e, e.title, "child_sensor");
          });
        }

        if (!$("#map").hasClass("singletonCal")) {
          numberRois();
          numberTripwires();
        }

        // Save ROI / tripwire — delegated so React toolbar remounts keep working
        $(document)
          .off("click.ssRoiSave", "#save-rois, #save-trips")
          .on("click.ssRoiSave", "#save-rois, #save-trips", function (event) {
            var values;
            if (event.target.id === "save-trips") {
              values = getRoiValues("form-control tripwire-title", "tripwire");
            } else {
              values = getRoiValues("form-control roi-title", "roi");
            }
            saveRois(values);
          });
      }

      $(document)
        .off("click.ssNewRoi", "#new-roi, #empty-new-roi")
        .on("click.ssNewRoi", "#new-roi, #empty-new-roi", function () {
          if (window.ssUseReactMap) {
            return;
          }
          addPoly();
        });

      $(document)
        .off("click.ssNewTrip", "#new-tripwire, #empty-new-tripwire")
        .on(
          "click.ssNewTrip",
          "#new-tripwire, #empty-new-tripwire",
          function () {
            if (window.ssUseReactMap) {
              return;
            }
            addTripwire();
          },
        );

      $(document)
        .off("click.ssRoiRemove", ".roi-remove")
        .on("click.ssRoiRemove", ".roi-remove", async function (event) {
          if (window.ssUseReactMap) {
            return;
          }
          event.preventDefault();
          var $group = $(this).closest(".form-roi");
          var r = await ssAskConfirm(
            "Are you sure you wish to remove this ROI?",
            {
              title: "Remove region?",
              confirmLabel: "Remove",
              danger: true,
            },
          );

          if (r == true) {
            $("#" + $group.attr("for")).remove();
            $group.remove();
            numberRois();
            saveRois(getRoiValues("form-control roi-title", "roi"));
          }
        });

      $(document)
        .off("click.ssTripRemove", ".tripwire-remove")
        .on("click.ssTripRemove", ".tripwire-remove", async function (event) {
          if (window.ssUseReactMap) {
            return;
          }
          event.preventDefault();
          var $group = $(this).closest(".form-tripwire");
          var r = await ssAskConfirm(
            "Are you sure you wish to remove this tripwire?",
            {
              title: "Remove tripwire?",
              confirmLabel: "Remove",
              danger: true,
            },
          );

          if (r == true) {
            $("#" + $group.attr("for")).remove();
            $group.remove();
            numberTripwires();
            saveRois(getRoiValues("form-control tripwire-title", "tripwire"));
          }
        });
    }

    setColorForAllROIs();
  });

  // MQTT management (see https://github.com/mqttjs/MQTT.js)
  // #broker may appear after React adopts panels — also exposed as ssEnsureMqttScene.
  window.ssEnsureMqttScene = function () {
    if ($("#broker").length == 0) {
      return;
    }
    if (window.__ssMqttSceneReady) {
      if (
        !window.ssMqttClient &&
        sessionStorage.getItem("connectToMqtt") !== "false"
      ) {
        $("#connect").trigger("click");
      } else if (window.ssMqttClient) {
        window.ssRefreshCameraSnapshots();
      }
      return;
    }
    window.__ssMqttSceneReady = true;

    // Set broker value to the hostname of the current page
    // since broker runs on web server by default
    var host = window.location.hostname;
    var port = window.location.port;
    var broker = $("#broker").val() || "";
    var protocol = window.location.protocol;

    // If running HTTPS on a custom port, fix up the WSS connection string
    if (port && protocol == "https:") {
      broker = broker.replace("localhost", host + ":" + port);
    }
    // If running HTTPS without a port or HTTP in developer mode, fix up the host name only
    else {
      broker = broker.replace("localhost", host);
    }

    // Fix connection string for HTTP in developer mode
    if (protocol == "http:") {
      broker = broker.replace("wss:", "ws:");
      broker = broker.replace("/mqtt", ":1884");
    }

    $("#broker").val(broker);
    $("#broker-address").text(host);
    checkBrokerConnections()
      .then(() => {
        console.log("Broker connections checked");
      })
      .catch((error) => {
        console.log("An error occurred:", error);
      });
  };
  window.ssEnsureMqttScene();
  if (isCalibratePage()) {
    window.setTimeout(function () {
      if (!window.camera_calibration || !window.camera_calibration.camCanvas) {
        initializeCalibrationSettings();
      }
      flushPendingCalibrationImage(window.ssMqttClient);
    }, 800);
  }

  $("input[name='area']").on("focus change", function () {
    initArea(this);
  });

  // When slide is updated, also update svg and value in the form
  $("#id_sensor_r").on("input", function () {
    svgCanvas.select(".sensor_r").attr("r", $(this).val());
  });

  $("#redraw").on("click", function () {
    $(".roi").remove();
    addPoly();
  });

  $("#fullscreen").on("click", function () {
    var $btn = $(this);
    var $icon = $btn.find("i");
    if (fullscreen) {
      $("body").removeClass("is-map-fullscreen");
      $("#svgout").removeClass("fullscreen");
      $(".hide-fullscreen").show();
      $btn.attr({
        title: "Full screen map view",
        "aria-pressed": "false",
      });
      $icon.removeClass("bi-fullscreen-exit").addClass("bi-arrows-fullscreen");
      $btn.find(".sr-only").text("Full screen map view");
      fullscreen = false;
    } else {
      $("body").addClass("is-map-fullscreen");
      $("#svgout").addClass("fullscreen");
      $(".hide-fullscreen").hide();
      $btn.attr({
        title: "Exit full screen map view",
        "aria-pressed": "true",
      });
      $icon.removeClass("bi-arrows-fullscreen").addClass("bi-fullscreen-exit");
      $btn.find(".sr-only").text("Exit full screen map view");
      fullscreen = true;
    }
    requestAnimationFrame(function () {
      fitSceneMapDisplay();
    });
  });

  $(window).on("resize", function () {
    if (isSceneDetailMap()) {
      fitSceneMapDisplay();
    }
  });

  $("input#show-trails").on("change", function () {
    if ($(this).is(":checked")) show_trails = true;
    else show_trails = false;
  });

  $(document)
    .off("change.ssTelemetry", "input#show-telemetry")
    .on("change.ssTelemetry", "input#show-telemetry", function () {
      show_telemetry = $(this).is(":checked");
      if (!show_telemetry) {
        $("#scene-rate").text("--");
        $(".rate").text("--").addClass("telemetry-hide");
        if (
          window.ssSceneTelemetry &&
          typeof window.ssSceneTelemetry.clearRates === "function"
        ) {
          window.ssSceneTelemetry.clearRates();
        }
        if (
          window.ssSceneTelemetry &&
          typeof window.ssSceneTelemetry.setSceneRate === "function"
        ) {
          window.ssSceneTelemetry.setSceneRate("--");
        }
        window.dispatchEvent(new CustomEvent("ss-telemetry-clear"));
        document.querySelectorAll(".mark-tooltip").forEach(function (el) {
          el.classList.add("telemetry-hide");
        });
      } else {
        document.querySelectorAll(".mark-tooltip").forEach(function (el) {
          el.classList.remove("telemetry-hide");
        });
        document.querySelectorAll(".rate").forEach(function (el) {
          el.classList.add("telemetry-hide");
        });
      }
    });

  $(".form-group")
    .find("input[type=text], input[type=number], select")
    .addClass("form-control");

  $(".form-group").each(function () {
    var label = $(this).find("label").first().attr("id");

    $("input", this).attr("aria-labelledby", label);
  });
});
