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
} from "/static/js/constants.js";
import {
  metersToPixels,
  pixelsToMeters,
  checkMqttConnection,
  updateElements,
} from "/static/js/utils.js";
import { plot } from "/static/js/marks.js";
import { setupChildScene } from "/static/js/childscene.js";
import {
  initializeCalibration,
  initializeCalibrationSettings,
  startCameraCalibration,
  updateCalibrationView,
  handleAutoCalibrationPose,
} from "/static/js/calibration.js";

var svgCanvas = Snap("#svgout");
import RESTClient from "/static/js/restclient.js";
var points, maps, rois, tripwires, child_rois, child_tripwires, child_sensors;
var dragging, drawing, adding, editing, fullscreen;
var wasDragging = false;
var g;
var radius = 5;
var scale = 30.0; // Default map scale in pixels/meter
// The single region currently in edit mode (only one may be edited at a time)
var activeEditGroup = null;
// Vertices picked with ctrl+click for merging: two on one region, then two on another
var mergeVertexSelection = [];
// Max pixel distance from a polygon edge for a click to be treated as "insert a point here"
var EDGE_INSERT_THRESHOLD_PX = 15;
// Window for two right-clicks on a region to count as a double right-click
var RIGHT_DOUBLE_CLICK_MS = 400;
// Pointer movement past this is a drag, not a click
var DRAG_SLOP_PX = 2;
var scene_id = $("#scene").val();
var icon_size = 24;
var show_telemetry = false;
var show_trails = false;
var scene_y_max = 480; // Scene image height in pixels
var savedElements = [];
var is_coloring_enabled = false; // Default state of the coloring feature
var roi_color_sectors = {};
var singleton_color_sectors = {};
var scene_rotation_translation_config;
// ROI type-group keys the user has deselected (persists across regroupRoiFields() re-renders)
var deselectedRoiGroups = new Set();
// User-picked colors (group key -> "#rrggbb") that override getRoiGroupColor()'s default
var roiGroupColorOverrides = {};
// Label shown for the group of ROIs with no type set
var UNCATEGORIZED_ROI_TYPE_LABEL = "Uncategorized";

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

if (window.location.href.includes("/cam/calibrate/")) {
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

  $("#connect").on("click", function () {
    console.log("Attempting to connect to " + broker.value);
    var client = mqtt.connect(broker.value);
    sessionStorage.setItem("connectToMqtt", true);

    client.on("connect", function () {
      console.log("Connected to " + broker.value);
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
        console.log("Subscribed to " + APP_NAME + SYS_CHILDSCENE_STATUS + "/+");
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

      // Capture thumbnail snapshots
      if ($(".snapshot-image").length) {
        // Only subscribe to regular camera images if NOT on calibration page
        if (!window.location.href.includes("/cam/calibrate/")) {
          client.subscribe(APP_NAME + IMAGE_CAMERA + "+");
        }

        $(".snapshot-image").each(function () {
          client.publish($(this).attr("topic"), "getimage");
        });

        $("input#live-view").on("change", function () {
          if ($(this).is(":checked")) {
            $(".snapshot-image").each(function () {
              client.publish($(this).attr("topic"), "getimage");
            });
            $("#cameras-tab").click(); // Select the cameras tab
            $(".camera-card").addClass("live-view");
            // $(".hide-live").hide();
          } else {
            $(".camera-card").removeClass("live-view");
            // $(".hide-live").show();
          }
        });
      }
    });

    client.on("close", function () {
      $("[id^='mqtt_status']").removeClass("connected");
      $(".rate").text("--");
      $("#scene-rate").text("--");
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
          // Show the FPS for each camera
          for (const [key, value] of Object.entries(msg.rate)) {
            document.getElementById("rate-" + key).innerText = value + " FPS";
          }

          // Show the scene controller update rate
          document.getElementById("scene-rate").innerText =
            msg.scene_rate.toFixed(1);
        }

        // Plot the marks
        plot(
          msg.objects,
          scale,
          scene_y_max,
          svgCanvas,
          show_telemetry,
          show_trails,
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
        updateCalibrationView(msg);
      } else if (topic.includes(IMAGE_CAMERA)) {
        // Skip processing regular camera images on calibration page
        if (window.location.href.includes("/cam/calibrate/")) {
          return;
        }
        // Use native JS since jQuery.load() pukes on data URI's
        if ($(".snapshot-image").length) {
          var id = topic.split("camera/")[1];
          img = document.getElementById(id);
          if (img !== undefined && img !== null) {
            img.setAttribute("src", "data:image/jpeg;base64," + msg.image);
          }

          if ($("input#live-view").is(":checked")) {
            client.publish(APP_NAME + CMD_CAMERA + id, "getimage");
          }

          // If ID contains special characters, selector $("#" + id) fails
          $("[id='" + id + "']")
            .stop()
            .show()
            .css("opacity", 1)
            .animate({ opacity: 0.6 }, 5000, function () {})
            .prevAll(".cam-offline")
            .hide();
        }
      } else if (topic.includes(DATA_CAMERA)) {
        var id = topic.slice(topic.lastIndexOf("/") + 1);
        $("#rate-" + id).text(msg.rate + " FPS");
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

    $("#disconnect").on("click", function () {
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
  $("text", $sensor).text(m.value.toString());
}

function addPoly() {
  // Prevent conflicts with the region being manually drawn: exit edit mode on
  // whichever region was active and drop any in-progress vertex-merge picks.
  if (activeEditGroup) {
    exitEditMode(activeEditGroup);
  }
  clearMergeSelection();

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

  regroupRoiFields();
  numberTabs();
}

// Bold, highly saturated colors assigned per ROI type so a group's box in the
// Regions tab is relatable to its outline on the map, and each ROI's edges
// stand out clearly against the (mostly neutral-toned) map background.
var ROI_GROUP_COLOR_PALETTE = [
  "#e6194b",
  "#3cb44b",
  "#ffe119",
  "#4363d8",
  "#f58231",
  "#911eb4",
  "#42d4f4",
  "#f032e6",
  "#469990",
  "#000075",
  "#800000",
];

/** Last-resort deterministic color for a key, used only once every palette color is already taken by another active group. */
function getRoiGroupColor(key) {
  var hash = 0;
  for (var idx = 0; idx < key.length; idx++) {
    hash = (hash * 31 + key.charCodeAt(idx)) >>> 0;
  }
  return ROI_GROUP_COLOR_PALETTE[hash % ROI_GROUP_COLOR_PALETTE.length];
}

// Sticky auto-assigned colors (group key -> color), set the first time a key
// is resolved in regroupRoiFields() so each type keeps its look across re-renders.
var roiGroupAutoColors = {};

/** Resolve a group key's color: user override, then its previously-assigned sticky color, then a hash fallback. */
function roiGroupColorForKey(key) {
  return (
    roiGroupColorOverrides[key] ||
    roiGroupAutoColors[key] ||
    getRoiGroupColor(key)
  );
}

/**
 * Like roiGroupColorForKey(), but guarantees a color distinct from every other
 * key already resolved in the same pass (tracked via usedColors), as long as
 * there are enough palette colors to go around. Reassigns a key's sticky
 * color only when it collides with another currently active group's color.
 */
function resolveUniqueRoiGroupColor(key, usedColors) {
  if (roiGroupColorOverrides[key]) {
    return roiGroupColorOverrides[key];
  }

  var sticky = roiGroupAutoColors[key];
  if (sticky && !usedColors.has(sticky)) {
    return sticky;
  }

  for (var i = 0; i < ROI_GROUP_COLOR_PALETTE.length; i++) {
    var candidate = ROI_GROUP_COLOR_PALETTE[i];
    if (!usedColors.has(candidate)) {
      roiGroupAutoColors[key] = candidate;
      return candidate;
    }
  }

  // More distinct types than palette colors: no free slot left, so a repeat is unavoidable.
  var fallback = getRoiGroupColor(key);
  roiGroupAutoColors[key] = fallback;
  return fallback;
}

/**
 * Organize ROI form rows in #roi-fields into collapsible boxes keyed by
 * their .roi-type value. Moves existing rows (via appendTo, no clone) so
 * jQuery data/handlers survive. No-op on the read-only (non-superuser) form,
 * which has no .roi-type inputs.
 */
function regroupRoiFields() {
  var $container = $("#roi-fields");
  var $rows = $container.find(".form-roi");

  if ($rows.length === 0 || $rows.find(".roi-type").length === 0) {
    return;
  }

  var groupsByKey = {};
  var orderedKeys = [];

  $rows.each(function () {
    var $row = $(this);
    var key = $row.find(".roi-type").val().trim();

    if (!groupsByKey[key]) {
      groupsByKey[key] = [];
      orderedKeys.push(key);
    }
    groupsByKey[key].push($row.detach());
  });

  orderedKeys.sort(function (a, b) {
    if (a === "") return 1;
    if (b === "") return -1;
    return a.localeCompare(b);
  });

  $container.find(".roi-group-box").remove();

  var usedColors = new Set();

  orderedKeys.forEach(function (key) {
    var rowsInGroup = groupsByKey[key];
    var selected = !deselectedRoiGroups.has(key);
    var color = resolveUniqueRoiGroupColor(key, usedColors);
    usedColors.add(color);

    var $box = $('<div class="roi-group-box"></div>')
      .data("group-key", key)
      .css("border-left-color", color);
    var $header = $('<div class="roi-group-header"></div>');
    var $toggle = $(
      '<input type="checkbox" class="roi-group-toggle" title="Show/hide this group on the map and include it when saving">',
    ).prop("checked", selected);
    var $colorInput = $(
      '<input type="color" class="roi-group-color-input" title="Change this group\'s color">',
    ).val(color);
    var $typeInput = $(
      '<input type="text" class="roi-group-type-input" maxlength="150">',
    )
      .attr("placeholder", UNCATEGORIZED_ROI_TYPE_LABEL)
      .val(key);
    var $count = $('<span class="roi-group-count"></span>').text(
      "(" + rowsInGroup.length + ")",
    );
    var $body = $('<div class="roi-group-body"></div>');

    rowsInGroup.forEach(function ($row) {
      $row.appendTo($body);
    });

    $header.append($toggle, $colorInput, $typeInput, $count);
    $box.append($header, $body);
    $container.append($box);

    applyRoiGroupSelectionState($box, selected);
    applyRoiGroupColor($box, color);
  });
}

/**
 * Show/hide a group's ROIs on the map and mark them (via SVG group .data())
 * so stringifyRois() excludes deselected ROIs from what gets saved.
 */
function applyRoiGroupSelectionState($groupBox, selected) {
  $groupBox.find(".form-roi").each(function () {
    var $row = $(this);
    var svgGroup = Snap.select("#" + $row.attr("for"));

    $row.toggleClass("roi-row-deselected", !selected);
    if (svgGroup) {
      if (selected) {
        svgGroup.removeClass("roi-hidden");
      } else {
        svgGroup.addClass("roi-hidden");
      }
      svgGroup.data("deselected", !selected);
    }
  });
}

/**
 * Tint a group's on-map polygons with its group color (outline always, fill
 * too when occupancy coloring is off) so proposed/saved ROIs on the map are
 * distinguishable by category, matching the Regions tab box.
 */
function applyRoiGroupColor($groupBox, color) {
  $groupBox.find(".form-roi").each(function () {
    var svgGroup = Snap.select("#" + $(this).attr("for"));
    var poly = svgGroup && svgGroup.select("polygon");
    if (poly) {
      poly.node.style.stroke = color;
      if (!is_coloring_enabled) {
        poly.node.style.fill = color;
      }
    }
  });
}

// Toggle a whole group's selection: hides its ROIs on the map and excludes
// them from the next save, without removing their form rows.
$(document).on("change", ".roi-group-toggle", function () {
  var $box = $(this).closest(".roi-group-box");
  var key = $box.data("group-key");
  var selected = $(this).is(":checked");

  if (selected) {
    deselectedRoiGroups.delete(key);
  } else {
    deselectedRoiGroups.add(key);
  }
  applyRoiGroupSelectionState($box, selected);
  stringifyRois();
});

// Let the user override a group's auto-assigned color. Live-updates the box
// and map outlines as the picker is dragged, without a full regroup/rebuild.
$(document).on("input", ".roi-group-color-input", function () {
  var $box = $(this).closest(".roi-group-box");
  var key = $box.data("group-key");
  var color = $(this).val();

  roiGroupColorOverrides[key] = color;
  $box.css("border-left-color", color);
  applyRoiGroupColor($box, color);
});

// Renaming a group's type reassigns that type to every ROI currently in it,
// then regroups so rows move into (or merge with) the matching box.
$(document).on("change", ".roi-group-type-input", function () {
  var $box = $(this).closest(".roi-group-box");
  var oldKey = $box.data("group-key");
  var newKey = $(this).val().trim();

  $box.find(".form-roi .roi-type").val(newKey);

  if (deselectedRoiGroups.has(oldKey)) {
    deselectedRoiGroups.delete(oldKey);
    deselectedRoiGroups.add(newKey);
  }
  if (Object.prototype.hasOwnProperty.call(roiGroupColorOverrides, oldKey)) {
    roiGroupColorOverrides[newKey] = roiGroupColorOverrides[oldKey];
    delete roiGroupColorOverrides[oldKey];
  }
  if (Object.prototype.hasOwnProperty.call(roiGroupAutoColors, oldKey)) {
    roiGroupAutoColors[newKey] = roiGroupAutoColors[oldKey];
    delete roiGroupAutoColors[oldKey];
  }

  regroupRoiFields();
  stringifyRois();
});

function numberTripwires() {
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

// Show number of child cards in a tab
function numberTabs() {
  $(".show-count").each(function () {
    var numCards = $(".count-item", $(this).closest("a").attr("href")).length;
    $(this).text("(" + numCards + ")");
  });
}

// Turn the regions of interest into a string for saving to the database
function stringifyRois() {
  rois = [];
  var groups = svgCanvas.selectAll(".roi");

  groups.forEach(function (g) {
    // Deselected (via its type-group checkbox) ROIs are hidden on the map
    // and excluded from the save payload entirely.
    if (g.data("deselected")) {
      return;
    }

    var i = g.attr("id");
    var title = $("#form-" + i + " input").val();
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

    // Get ROI type if present
    const typeElement = document.querySelector("#form-" + i + " .roi-type");
    if (typeElement) {
      entry.type = typeElement.value || "";
    }

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

    // Include osm_derived flag if this ROI was generated from OSM
    if (g.data("osm_derived")) {
      entry.osm_derived = true;
    }

    rois.push(entry);
  });

  // Update hidden field
  $("#id_rois").val(JSON.stringify(rois));
}

function stringifyTripwires() {
  tripwires = [];
  var groups = svgCanvas.selectAll(".tripwire");

  groups.forEach(function (g) {
    var i = g.attr("id");
    var title = $("#form-" + i + " input").val();
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
}

function stringifySingletonColorRange() {
  let color_ranges = [];

  var input_min = document.querySelectorAll(
    "#singleton_sectors > input[id$='_min']",
  );

  for (const input_ele of input_min) {
    color_ranges.push({
      color: input_ele.className.split("_")[0],
      color_min: parseInt(input_ele.value),
    });
  }

  const range_max_value = document.getElementById("range_max").value;
  const range_max = parseInt(range_max_value);

  color_ranges.push({
    range_max: range_max,
  });

  $("#id_sectors").val(JSON.stringify(color_ranges));
}

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

/**
 * Select a region for editing. Only one region may be edited at a time:
 * entering edit mode on a group exits it on whichever other group was active.
 */
function editPolygon(group) {
  if (group.data("editing")) return;

  if (activeEditGroup && activeEditGroup.node !== group.node) {
    exitEditMode(activeEditGroup);
  }

  enterEditMode(group);
  stringifyRois();
}

function enterEditMode(group) {
  group.data("editing", true);
  activeEditGroup = group;
  editing = true;

  // Bring the selected region to the front (among other regions) so its
  // vertices/edges stay reachable, without covering sensor markers (which
  // must stay on top per the layering drawRoi() establishes on creation)
  var firstSensor = svgCanvas.selectAll(".sensor")[0];
  if (firstSensor) {
    group.insertBefore(firstSensor);
  } else {
    group.appendTo(group.parent());
  }

  group.selectAll("circle").forEach(function (c) {
    bindVertexHandlers(group, c);
  });
}

function exitEditMode(group) {
  group.selectAll("circle").forEach(unbindVertexHandlers);

  group.data("editing", false);
  if (activeEditGroup && activeEditGroup.node === group.node) {
    activeEditGroup = null;
  }
  editing = false;
}

function bindVertexHandlers(group, circle) {
  circle.addClass("is-handle");
  circle.drag(move, start, stop);

  circle.click(function (evt) {
    if (!evt.ctrlKey && !evt.metaKey) return;
    evt.stopPropagation();
    if (wasDragging) return;
    handleVertexMergeClick(group, circle);
  });

  var onContextMenu = function (evt) {
    evt.preventDefault();
    evt.stopPropagation(); // Don't count toward the region's double right-click
    if (wasDragging) return;
    handleVertexDelete(circle, group);
  };
  circle.node.addEventListener("contextmenu", onContextMenu);
  circle.data("onContextMenu", onContextMenu);
}

/** Vertices stay in the DOM but invisible outside edit mode, so unbind to keep them inert. */
function unbindVertexHandlers(circle) {
  circle.undrag();
  circle.unclick();
  circle.removeClass("is-handle");

  var onContextMenu = circle.data("onContextMenu");
  if (onContextMenu) {
    circle.node.removeEventListener("contextmenu", onContextMenu);
    circle.removeData("onContextMenu");
  }
}

/**
 * Bind the polygon body handlers, for the region's lifetime:
 *   left click -> select (or insert a point when near an edge while editing),
 *   double right click -> delete the region.
 */
function bindPolygonClickHandler(group, poly) {
  if (!poly) return;

  poly.click(function (evt) {
    evt.stopPropagation();

    var closest = group.data("editing")
      ? findClosestEdgePoint(group, evt)
      : null;
    if (closest && closest.distance <= EDGE_INSERT_THRESHOLD_PX) {
      insertVertexOnEdge(group, closest);
    } else {
      editPolygon(group);
    }
  });

  poly.node.addEventListener("contextmenu", function (evt) {
    evt.preventDefault();
    evt.stopPropagation();

    var now = Date.now();
    if (now - (group.data("lastRightClick") || 0) <= RIGHT_DOUBLE_CLICK_MS) {
      group.removeData("lastRightClick");
      handleRegionDelete(group);
      return;
    }

    group.data("lastRightClick", now);
  });
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

  bindPolygonClickHandler(group, group.select("polygon"));

  if ($(".sensor").length) group.insertBefore(svgCanvas.select(".sensor"));

  points = [];
  drawing = false;

  if (!$("#map").hasClass("singletonCal")) {
    $("#roi-template")
      .clone(true)
      .removeAttr("id")
      .attr("id", "form-" + i)
      .attr("for", i)
      .appendTo("#roi-fields");

    numberRois();
  }

  stringifyRois();
}

/** Map image extent in pixels, or null if the image isn't rendered yet. */
function mapBoundsPx() {
  var image = $("#svgout image")[0];
  if (!image) return null;

  return {
    width: image.width.baseVal.value,
    height: image.height.baseVal.value,
  };
}

/**
 * Clamp a point to the map image. Region vertices outside the map can't be
 * clicked, which would put parts of a region beyond the user's control.
 */
function clampPointToMap(x, y) {
  var bounds = mapBoundsPx();
  if (!bounds) return [x, y];

  return [
    Math.min(Math.max(x, 0), bounds.width),
    Math.min(Math.max(y, 0), bounds.height),
  ];
}

function move(dx, dy) {
  var group = this.parent();
  var clamped = clampPointToMap(
    this.data("origX") + dx,
    this.data("origY") + dy,
  );

  if (Math.abs(dx) > DRAG_SLOP_PX || Math.abs(dy) > DRAG_SLOP_PX) {
    wasDragging = true;
  }

  this.attr({
    cx: clamped[0],
    cy: clamped[1],
  });

  rebuildPolygon(group);
  updateRegionLabel(group);
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
  wasDragging = false;

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
  // wasDragging is set by move(); clear it once the ensuing click has been handled
  setTimeout(function () {
    wasDragging = false;
  }, 10);
  points = [];
}

/**
 * Remove a single vertex (right-clicked). Guards against false positives after a
 * drag, and falls back to deleting the region when too few vertices would remain.
 */
function handleVertexDelete(circle, group) {
  // Guard: don't delete if we just finished dragging this vertex
  if (wasDragging) {
    return;
  }

  var circleCount = group.selectAll("circle").length;

  // If removing this vertex would leave < 3 points, delete the entire region instead
  if (circleCount <= 3) {
    handleRegionDelete(group);
    return;
  }

  // Remove the clicked circle from the DOM
  circle.remove();

  rebuildPolygon(group);
  updateRegionLabel(group);

  // Sync the hidden #id_rois field (local update only, no form submission)
  stringifyRois();
}

/**
 * Handle whole-region deletion (used by both polygon-click and vertex-underflow paths).
 * Removes SVG group and form row, updates numbering and hidden field.
 */
function handleRegionDelete(group) {
  var groupId = group.attr("id");

  dropMergeSelectionsFor(group);

  // Remove SVG group
  group.remove();

  // Remove corresponding form row
  var formRow = $("#form-" + groupId);
  if (formRow.length) {
    formRow.remove();
  }

  // Update numbering and sync hidden field (local update only)
  numberRois();
  stringifyRois();
}

/**
 * Rebuild a region's <polygon> from its current circle vertices (in DOM order).
 * Replacing the element drops its click listener, so the body click handler
 * (merge / edge-insert / delete) is re-bound. Preserve the polygon's inline
 * stroke and fill styles so the region color is maintained across vertex edits.
 */
function rebuildPolygon(group) {
  var oldPoly = group.select("polygon");
  var stroke = oldPoly ? oldPoly.node.style.stroke : "";
  var fill = oldPoly ? oldPoly.node.style.fill : "";
  if (oldPoly) oldPoly.remove();

  var poly = group.polygon(flattenVertexPoints(group));
  poly.prependTo(poly.node.parentElement);
  if (stroke) poly.node.style.stroke = stroke;
  if (fill) poly.node.style.fill = fill;

  bindPolygonClickHandler(group, poly);

  return poly;
}

/** Vertex centers of a region, as [[x, y], ...] in DOM (winding) order. */
function vertexPoints(group) {
  var pts = [];
  group.selectAll("circle").forEach(function (c) {
    pts.push([parseFloat(c.attr("cx")), parseFloat(c.attr("cy"))]);
  });
  return pts;
}

/** Same as vertexPoints(), flattened to [x1, y1, x2, y2, ...] for <polygon>. */
function flattenVertexPoints(group) {
  var flat = [];
  vertexPoints(group).forEach(function (p) {
    flat.push(p[0], p[1]);
  });
  return flat;
}

/** Re-center a region's name label on its current vertices. */
function updateRegionLabel(group) {
  var text = group.select("text");
  if (!text) return;

  var center = polyCenter(flattenVertexPoints(group));
  text.attr({
    x: center[0],
    y: center[1],
  });
}

/**
 * Ctrl+click vertex selection for merging: pick two vertices on one region, then
 * two on another. The picked pairs mark where each outline opens up; the regions
 * are then joined along those openings into one continuous outline.
 */
function handleVertexMergeClick(group, circle) {
  if (!group.hasClass("roi")) return;

  for (var i = 0; i < mergeVertexSelection.length; i++) {
    if (mergeVertexSelection[i].circle.node === circle.node) {
      mergeVertexSelection[i].circle.removeClass("merge-vertex");
      mergeVertexSelection.splice(i, 1);
      return;
    }
  }

  if (mergeVertexSelection.length >= 4) return;

  // Picks 1-2 must share a region; picks 3-4 must share a different one
  var expectedGroup = null;
  if (mergeVertexSelection.length === 1) {
    expectedGroup = mergeVertexSelection[0].group;
  } else if (mergeVertexSelection.length === 3) {
    expectedGroup = mergeVertexSelection[2].group;
  }
  if (expectedGroup && expectedGroup.node !== group.node) return;

  if (
    mergeVertexSelection.length === 2 &&
    mergeVertexSelection[0].group.node === group.node
  ) {
    return;
  }

  mergeVertexSelection.push({ group: group, circle: circle });
  circle.addClass("merge-vertex");

  if (mergeVertexSelection.length === 4) {
    mergeSelectedVertices();
  }
}

function clearMergeSelection() {
  mergeVertexSelection.forEach(function (sel) {
    sel.circle.removeClass("merge-vertex");
  });
  mergeVertexSelection = [];
}

function dropMergeSelectionsFor(group) {
  mergeVertexSelection = mergeVertexSelection.filter(function (sel) {
    if (sel.group.node !== group.node) return true;
    sel.circle.removeClass("merge-vertex");
    return false;
  });
}

/** Position of a circle within its region's vertex ring, or -1. */
function vertexIndex(group, circle) {
  var index = -1;
  var i = 0;
  group.selectAll("circle").forEach(function (c) {
    if (c.node === circle.node) index = i;
    i++;
  });
  return index;
}

/**
 * Join the two selected regions into one continuous region. The first region
 * keeps its form row (name, settings); the second is removed.
 */
function mergeSelectedVertices() {
  var groupA = mergeVertexSelection[0].group;
  var groupB = mergeVertexSelection[2].group;
  var A = vertexPoints(groupA);
  var B = vertexPoints(groupB);

  var ring = unionPolygons(A, B);

  // Overlapping outlines can't be bridged without self-intersecting, so they are
  // unioned above; separated ones are joined at the picked vertices instead.
  if (!ring) {
    ring = bridgeRings(
      A,
      vertexIndex(groupA, mergeVertexSelection[0].circle),
      vertexIndex(groupA, mergeVertexSelection[1].circle),
      B,
      vertexIndex(groupB, mergeVertexSelection[2].circle),
      vertexIndex(groupB, mergeVertexSelection[3].circle),
    );
  }

  clearMergeSelection();

  if (!ring) {
    alert(
      "Those regions can't be joined into one shape. If they are apart, pick the " +
        "vertices on the sides that face each other.",
    );
    return;
  }

  if (groupA.data("editing")) exitEditMode(groupA);
  if (groupB.data("editing")) exitEditMode(groupB);

  groupA.selectAll("circle").forEach(function (c) {
    c.remove();
  });
  ring.forEach(function (p) {
    groupA.circle(p[0], p[1], radius).addClass("vertex");
  });

  handleRegionDelete(groupB);

  rebuildPolygon(groupA);
  updateRegionLabel(groupA);

  numberRois();
  stringifyRois();
}

/**
 * Outer ring of the union of two overlapping outlines, or null when they are
 * disjoint (nothing to union) or the result can't be trusted.
 */
function unionPolygons(ringA, ringB) {
  var areaA = Math.abs(ringSignedArea(ringA));
  var areaB = Math.abs(ringSignedArea(ringB));

  // A real union covers every input vertex, adds no area beyond A+B, and is simple
  var acceptable = function (ring) {
    if (!ring || ring.length < 3) return false;

    var a = Math.abs(ringSignedArea(ring));
    if (a < Math.max(areaA, areaB) - 0.5 || a > areaA + areaB + 0.5)
      return false;
    if (!isSimplePolygon(ring)) return false;

    return ringA.concat(ringB).every(function (p) {
      return pointInRing(ring, p) || pointOnRingBoundary(ring, p);
    });
  };

  var result = unionAttempt(ringA, ringB);
  if (acceptable(result)) return result;

  // Shared/collinear edges make the walk degenerate; a sub-pixel nudge breaks
  // the tie without visibly moving the outline.
  var nudged = ringB.map(function (p) {
    return [p[0] + 1e-4, p[1] + 1e-4];
  });
  result = unionAttempt(ringA, nudged);

  return acceptable(result) ? result : null;
}

/** One union walk: insert crossings into both rings, then trace the outer boundary. */
function unionAttempt(ringA, ringB) {
  var A = ensureCCW(ringA);
  var B = ensureCCW(ringB);

  var perEdgeA = A.map(function () {
    return [];
  });
  var perEdgeB = B.map(function () {
    return [];
  });
  var found = 0;

  for (var i = 0; i < A.length; i++) {
    for (var j = 0; j < B.length; j++) {
      var hit = segmentIntersection(
        A[i],
        A[(i + 1) % A.length],
        B[j],
        B[(j + 1) % B.length],
      );
      if (!hit) continue;

      var key = pointKey(hit.point);
      perEdgeA[i].push({ t: hit.t, pt: hit.point, key: key });
      perEdgeB[j].push({ t: hit.u, pt: hit.point, key: key });
      found++;
    }
  }

  if (!found) {
    if (pointInRing(B, A[0])) return B.slice();
    if (pointInRing(A, B[0])) return A.slice();
    return null; // disjoint
  }

  var augA = augmentRing(A, perEdgeA);
  var augB = augmentRing(B, perEdgeB);
  var indexA = crossingIndex(augA);
  var indexB = crossingIndex(augB);

  // Start somewhere guaranteed to be on the union's outer boundary
  var start = -1;
  for (var k = 0; k < augA.length; k++) {
    if (!augA[k].inter && !pointInRing(B, augA[k].pt)) {
      start = k;
      break;
    }
  }
  if (start < 0) return B.slice(); // A lies entirely within B

  var result = [];
  var onA = true;
  var idx = start;
  var maxSteps = (augA.length + augB.length) * 4;

  for (var step = 0; step < maxSteps; step++) {
    var node = (onA ? augA : augB)[idx];

    if (!result.length || !samePoint(result[result.length - 1], node.pt)) {
      result.push(node.pt);
    }

    // At a crossing, hand over to the other outline to stay on the outside
    if (node.inter) {
      var target = (onA ? indexB : indexA)[node.key];
      if (target !== undefined) {
        onA = !onA;
        idx = target;
      }
    }

    idx = (idx + 1) % (onA ? augA : augB).length;

    if (onA && idx === start) {
      if (
        result.length > 1 &&
        samePoint(result[0], result[result.length - 1])
      ) {
        result.pop();
      }
      return result.length >= 3 ? result : null;
    }
  }

  return null; // walk never closed
}

/** Ring vertices with crossing points spliced in, in order along each edge. */
function augmentRing(ring, perEdge) {
  var out = [];

  for (var i = 0; i < ring.length; i++) {
    out.push({ pt: ring[i], inter: false, key: null });

    perEdge[i]
      .slice()
      .sort(function (a, b) {
        return a.t - b.t;
      })
      .forEach(function (hit) {
        var last = out[out.length - 1];
        if (samePoint(last.pt, hit.pt)) {
          last.inter = true;
          last.key = hit.key;
          return;
        }
        out.push({ pt: hit.pt, inter: true, key: hit.key });
      });
  }

  while (out.length > 1 && samePoint(out[0].pt, out[out.length - 1].pt)) {
    if (out[out.length - 1].inter) {
      out[0].inter = true;
      out[0].key = out[out.length - 1].key;
    }
    out.pop();
  }

  return out;
}

function crossingIndex(augmented) {
  var index = {};
  augmented.forEach(function (node, i) {
    if (node.inter && index[node.key] === undefined) index[node.key] = i;
  });
  return index;
}

function ensureCCW(ring) {
  return ringSignedArea(ring) < 0 ? ring.slice().reverse() : ring;
}

function pointKey(p) {
  return p[0].toFixed(6) + "|" + p[1].toFixed(6);
}

function samePoint(a, b) {
  return Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6;
}

/** Intersection of two segments with both parameters, or null if they don't meet. */
function segmentIntersection(p1, p2, p3, p4) {
  var d1x = p2[0] - p1[0];
  var d1y = p2[1] - p1[1];
  var d2x = p4[0] - p3[0];
  var d2y = p4[1] - p3[1];

  var denom = d1x * d2y - d1y * d2x;
  if (Math.abs(denom) < 1e-12) return null; // parallel or collinear

  var t = ((p3[0] - p1[0]) * d2y - (p3[1] - p1[1]) * d2x) / denom;
  var u = ((p3[0] - p1[0]) * d1y - (p3[1] - p1[1]) * d1x) / denom;
  if (t < -1e-9 || t > 1 + 1e-9 || u < -1e-9 || u > 1 + 1e-9) return null;

  return { point: [p1[0] + t * d1x, p1[1] + t * d1y], t: t, u: u };
}

function pointInRing(ring, p) {
  var inside = false;

  for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    var xi = ring[i][0],
      yi = ring[i][1];
    var xj = ring[j][0],
      yj = ring[j][1];

    if (yi > p[1] !== yj > p[1]) {
      var xint = ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi;
      if (p[0] < xint) inside = !inside;
    }
  }

  return inside;
}

function pointOnRingBoundary(ring, p) {
  for (var i = 0; i < ring.length; i++) {
    var a = ring[i];
    var b = ring[(i + 1) % ring.length];
    var len = Math.sqrt(
      (b[0] - a[0]) * (b[0] - a[0]) + (b[1] - a[1]) * (b[1] - a[1]),
    );
    if (len < 1e-9) continue;

    var cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]);
    if (Math.abs(cross) / len > 1e-3) continue;

    var dot = (p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1]);
    if (dot >= -1e-6 && dot <= len * len + 1e-6) return true;
  }

  return false;
}

/**
 * Build one ring out of two, opening each at the span between its selected
 * vertices and connecting the loose ends. Each outline can open on either of the
 * two spans between its picks, so all combinations are tried and the largest
 * non-self-intersecting result wins (i.e. the one that discards the least area).
 */
function bridgeRings(A, ai1, ai2, B, bi1, bi2) {
  if (ai1 < 0 || ai2 < 0 || bi1 < 0 || bi2 < 0) return null;
  if (ai1 === ai2 || bi1 === bi2) return null;

  var aArcs = [ringArc(A, ai2, ai1), ringArc(A, ai1, ai2)];
  var bArcs = [];
  [ringArc(B, bi1, bi2), ringArc(B, bi2, bi1)].forEach(function (arc) {
    bArcs.push(arc, arc.slice().reverse());
  });

  var best = null;

  aArcs.forEach(function (aArc) {
    bArcs.forEach(function (bArc) {
      var ring = aArc.concat(bArc);
      if (ring.length < 3 || !isSimplePolygon(ring)) return;

      var area = Math.abs(ringSignedArea(ring));
      if (!best || area > best.area) {
        best = { ring: ring, area: area };
      }
    });
  });

  return best ? best.ring : null;
}

/** Ring vertices from index `from` forward to `to`, both inclusive. */
function ringArc(pts, from, to) {
  var arc = [];
  var i = from;

  for (;;) {
    arc.push(pts[i]);
    if (i === to) break;
    i = (i + 1) % pts.length;
  }

  return arc;
}

function ringSignedArea(ring) {
  var sum = 0;
  for (var i = 0; i < ring.length; i++) {
    var next = ring[(i + 1) % ring.length];
    sum += ring[i][0] * next[1] - next[0] * ring[i][1];
  }
  return sum / 2;
}

/** True when no two non-adjacent edges of the ring cross. */
function isSimplePolygon(ring) {
  var n = ring.length;

  for (var i = 0; i < n; i++) {
    for (var j = i + 1; j < n; j++) {
      // Skip edges sharing an endpoint (consecutive, plus the closing wrap-around)
      if (j === i + 1 || (i === 0 && j === n - 1)) continue;

      if (
        segmentsCross(ring[i], ring[(i + 1) % n], ring[j], ring[(j + 1) % n])
      ) {
        return false;
      }
    }
  }

  return true;
}

/** Proper segment intersection (shared endpoints and collinear touching don't count). */
function segmentsCross(p1, p2, p3, p4) {
  var orientation = function (a, b, c) {
    var v = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1]);
    if (v > 1e-9) return 1;
    if (v < -1e-9) return 2;
    return 0;
  };

  var o1 = orientation(p1, p2, p3);
  var o2 = orientation(p1, p2, p4);
  var o3 = orientation(p3, p4, p1);
  var o4 = orientation(p3, p4, p2);

  return o1 !== 0 && o2 !== 0 && o3 !== 0 && o4 !== 0 && o1 !== o2 && o3 !== o4;
}

/**
 * Insert a new, draggable vertex at the clicked point on the polygon boundary,
 * directly after the preceding vertex in winding order.
 */
function insertVertexOnEdge(group, closest) {
  var clamped = clampPointToMap(closest.point[0], closest.point[1]);
  var newCircle = group
    .circle(clamped[0], clamped[1], radius)
    .addClass("vertex");

  newCircle.insertAfter(closest.before);
  bindVertexHandlers(group, newCircle);

  rebuildPolygon(group);
  stringifyRois();
}

/**
 * Find the point on the polygon's boundary (nearest edge segment) closest to a click.
 * Returns {point: [x, y], before: <circle preceding this edge>, distance} or null.
 */
function findClosestEdgePoint(group, evt) {
  var circleArr = [];
  group.selectAll("circle").forEach(function (c) {
    circleArr.push(c);
  });

  if (circleArr.length < 2) return null;

  var offset = $("#svgout").offset();
  var clickPoint = [evt.pageX - offset.left, evt.pageY - offset.top];

  var closest = null;

  circleArr.forEach(function (circle, i) {
    var next = circleArr[(i + 1) % circleArr.length];
    var a = [parseFloat(circle.attr("cx")), parseFloat(circle.attr("cy"))];
    var b = [parseFloat(next.attr("cx")), parseFloat(next.attr("cy"))];
    var projected = closestPointOnSegment(clickPoint, a, b);
    var dx = clickPoint[0] - projected[0];
    var dy = clickPoint[1] - projected[1];
    var distance = Math.sqrt(dx * dx + dy * dy);

    if (!closest || distance < closest.distance) {
      closest = { point: projected, before: circle, distance: distance };
    }
  });

  return closest;
}

/** Project point `p` onto segment [a, b], clamped to the segment's endpoints. */
function closestPointOnSegment(p, a, b) {
  var abx = b[0] - a[0];
  var aby = b[1] - a[1];
  var lengthSq = abx * abx + aby * aby;

  if (lengthSq === 0) return a;

  var t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / lengthSq;
  t = Math.max(0, Math.min(1, t));

  return [a[0] + t * abx, a[1] + t * aby];
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
      $("#tripwire-template")
        .clone(true)
        .attr({
          id: "form-" + i,
          for: i,
        })
        .appendTo("#tripwire-fields")
        .find("input.tripwire-title")
        .val(e.title)
        .attr({
          id: "input-" + i,
          "aria-labelledby": "label-" + i,
        })
        .closest(".input-group")
        .find("label")
        .attr({
          id: "label-" + i,
          for: "input-" + i,
        })
        .closest(".input-group")
        .find(".topic")
        .text(
          APP_NAME + "/event/tripwire/" + scene_id + "/" + index + "/objects",
        );
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

function removeFormElementsForUI(id) {
  id = id + "_wrapper";
  if (document.getElementById(id)) {
    savedElements.push(document.getElementById(id));
    document.getElementById(id).remove();
  }
}

function toggleAsset3D() {
  var model3D = $("#id_model_3d").val();
  var hasAsset = $("#model_3d_wrapper").find("a").length;

  var assetForm =
    document.getElementById("asset_create_form") ||
    document.getElementById("asset_update_form");
  var saveButton = document.getElementById("save_asset");
  saveButton.remove();
  savedElements.push(saveButton);
  savedElements.forEach((element) => {
    assetForm.append(element);
  });
  savedElements = [];

  var asset_fields_with_no_model = ["mark_color"];
  var asset_fields_with_model = [
    "scale",
    "rotation_x",
    "rotation_y",
    "rotation_z",
    "translation_x",
    "translation_y",
    "translation_z",
  ];

  if (model3D || hasAsset) {
    asset_fields_with_no_model.map(removeFormElementsForUI);
    updateElements(
      asset_fields_with_model.map((v) => "id_" + v),
      "required",
      true,
    );
  } else {
    asset_fields_with_model.map(removeFormElementsForUI);
    updateElements(
      asset_fields_with_no_model.map((v) => "id_" + v),
      "required",
      true,
    );
  }
}

function addSavedCalibrationFields() {
  var sceneUpdateForm = document.getElementById("scene_update_form");
  var saveButton = document.getElementById("save_scene_updates");
  saveButton.remove();
  savedElements.push(saveButton);
  savedElements.forEach((element) => {
    sceneUpdateForm.append(element);
  });
  savedElements = [];
}

function setupCalibrationType() {
  var calibrationType = $("#id_camera_calibration").val();
  var listOfMarkerlessComponents = [
    "polycam_data",
    "matcher",
    "number_of_localizations",
    "global_feature",
    "local_feature",
    "minimum_number_of_matches",
    "inlier_threshold",
  ];
  var listofApriltagComponents = ["apriltag_size"];

  switch (calibrationType) {
    case "AprilTag":
      addSavedCalibrationFields();
      listOfMarkerlessComponents.map(removeFormElementsForUI);
      break;
    case "Manual":
      addSavedCalibrationFields();
      listOfMarkerlessComponents.map(removeFormElementsForUI);
      listofApriltagComponents.map(removeFormElementsForUI);
      break;
    case "Markerless":
      addSavedCalibrationFields();
      listofApriltagComponents.map(removeFormElementsForUI);
      break;
  }

  return;
}

// Function to save roi and tripwires
function saveRois(roi_values) {
  $("#roi-form").submit();
}

if (svgCanvas) {
  // Clicking empty canvas deselects the region being edited and drops merge picks
  svgCanvas.click(function () {
    if (adding || dragging || wasDragging) return;
    clearMergeSelection();
    if (!activeEditGroup) return;
    exitEditMode(activeEditGroup);
    stringifyRois();
  });

  svgCanvas.mouseup(function (e) {
    if (dragging || !adding) return;
    drawing = true;

    var offset = $("#svgout").offset();
    var thisPoint = [
      parseInt(e.pageX - offset.left),
      parseInt(e.pageY - offset.top),
    ];

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
    // Keep editable regions on the map so every vertex stays clickable
    if (type === "roi") {
      p = clampPointToMap(p[0], p[1]);
    }
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

    for (var pt = 0; pt < roi_points.length; pt += 2) {
      g.circle(roi_points[pt], roi_points[pt + 1], radius).addClass("vertex");
    }

    var poly = g.polygon(roi_points);
    poly.addClass("poly");

    // Reorder so the polygon is on the bottom
    poly.prependTo(poly.node.parentElement);

    bindPolygonClickHandler(g, poly);

    // Set ROI before (and below) sensor circle if on sensor page
    if ($(".sensor").length) {
      g.insertBefore(svgCanvas.selectAll(".sensor")[0]);
    }

    // Hide ROI if on the calibration page and it isn't selected
    if ($("#calibrate").length && !$("#id_area_2").is(":checked")) {
      $(".roi").hide();
    }

    if (type == "roi") {
      $("#roi-template")
        .clone(true)
        .attr({
          id: "form-" + i,
          for: i,
        })
        .appendTo("#roi-fields")
        .find("input.roi-title")
        .val(e.title)
        .attr({
          id: "input-" + i,
          "aria-labelledby": "label-" + i,
        })
        .closest(".input-group")
        .find("label")
        .attr({
          id: "label-" + i,
          for: "input-" + i,
        });

      $("#form-" + i)
        .find(".roi-topic > label")
        .text("Topic:  ");
      $("#form-" + i)
        .find(".roi-topic > .topic-text")
        .text(APP_NAME + "/event/region/" + scene_id + "/" + index + "/count");

      // Set volumetric checkbox and related fields
      if (e.volumetric !== undefined) {
        $("#form-" + i)
          .find(".roi-volumetric")
          .prop("checked", e.volumetric);
      }

      // Set height field
      if (e.height !== undefined) {
        $("#form-" + i)
          .find(".roi-height")
          .val(e.height);
      }

      // Set buffer size field
      if (e.buffer_size !== undefined) {
        $("#form-" + i)
          .find(".roi-buffer")
          .val(e.buffer_size);
      }

      // Set ROI type field
      if (e.type !== undefined) {
        $("#form-" + i)
          .find(".roi-type")
          .val(e.type);
      }

      for (var sector in e.sectors.thresholds) {
        var color = e.sectors.thresholds[sector].color;
        var min = e.sectors.thresholds[sector].color_min;
        $("#form-" + i)
          .find("input." + color + "_min")
          .val(min);
      }
      $("#form-" + i)
        .find("input." + "range_max")
        .val(e.sectors.range_max);

      document.querySelectorAll(".topic-text").forEach((element) => {
        element.addEventListener("click", () => {
          const text = element.textContent;
          if (navigator.clipboard !== undefined) {
            navigator.clipboard.writeText(text);
          }
        });
      });
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

function drawSensor(sensor, index, type) {
  var i = type + "_" + index;

  if (type === "child_sensor" && document.getElementById(i)) {
    var name_text = document.getElementById(i).querySelector("#name");
    var hierarchy_text = document.getElementById(i).querySelector("#hierarchy");
    if (sensor.x && sensor.y) {
      var p = metersToPixels([sensor.x, sensor.y], scale, scene_y_max);
      sensor.x = p[0];
      sensor.y = p[1];
      var sensor_circle = document.querySelector("#" + i + " > .sensor");
      sensor_circle.setAttribute("cx", sensor?.x);
      sensor_circle.setAttribute("cy", sensor?.y);
      name_text.setAttribute("x", sensor?.x);
      name_text.setAttribute("y", sensor?.y - 7);
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
      sensor.points.forEach(function (m) {
        var p = metersToPixels(m, scale, scene_y_max);
        area_points.push(p[0], p[1]);
      });
      var points_string = area_points.join(",");
      var polygon = document.querySelector("#" + i + " > .area");
      if (polygon.getAttribute("points") != points_string) {
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

      sensor.points.forEach(function (p) {
        p = metersToPixels(p, scale, scene_y_max);
        tempPoints.push(p[0], p[1]);
      });

      var center = polyCenter(tempPoints);
      var poly = g.polygon(tempPoints).addClass("area");
      var text = g.text(center[0], center[1], "").addClass("value");
    }

    if ($(".sensor-icon", this).length) {
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

    var nameText = g
      .text(sensor.x, sensor.y - 7, sensor.title)
      .attr({ id: "name" });
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
      var typeInput = document.querySelector(
        '.form-roi[for="roi_' + roi_id + '"] .roi-type',
      );
      roi_polygon.style.fill = typeInput
        ? roiGroupColorForKey(typeInput.value.trim())
        : "white";
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

function setupSceneRotationTranslationFields(event = null) {
  var map_file_name;
  if (event) {
    map_file_name = event.target.files[0].name;
  } else {
    var map_file_url = document.querySelector("#map_wrapper a");
    if (map_file_url) {
      map_file_name = map_file_url.getAttribute("href").split("/").pop();
    } else {
      map_file_name = "";
    }
  }
  var uploaded_file_ext = map_file_name.split(".").pop();
  if (uploaded_file_ext == "glb" || uploaded_file_ext == "zip") {
    scene_rotation_translation_config = false;
  } else {
    scene_rotation_translation_config = true;
  }

  var rotation_translation_elements = [
    "rotation_x_wrapper",
    "rotation_y_wrapper",
    "rotation_z_wrapper",
    "translation_x_wrapper",
    "translation_y_wrapper",
    "translation_z_wrapper",
  ];
  updateElements(
    rotation_translation_elements,
    "hidden",
    scene_rotation_translation_config,
  );
}

function setupGenerateMesh() {
  const generateMeshButton = document.getElementById("generate_mesh");
  const saveButton = document.getElementById("save");
  const mapInput = document.getElementById("id_map");

  saveButton?.addEventListener("click", async (e) => {
    const allowedExtensions = ["mp4", "mov", "avi", "webm", "mkv"];

    const file = mapInput?.files?.[0];
    if (!file) {
      // No file selected; nothing to validate here.
      return;
    }
    const extension = file.name.split(".").pop().toLowerCase();

    const isVideoMime = file.type.startsWith("video/");
    const isVideoExt = allowedExtensions.includes(extension);

    if (isVideoMime && isVideoExt) {
      e.preventDefault();
      alert("Please click generate mesh when uploading video file.");
      return;
    }
  });

  if (!generateMeshButton) return;

  // Start monitoring mapping service status
  startMappingServiceStatusMonitoring();

  generateMeshButton?.addEventListener("click", async (e) => {
    e.preventDefault();

    const sceneId = document.getElementById("sceneUID")?.value;
    const form = document.getElementById("scene_update_form");

    if (!sceneId) return alert("Scene ID not found");
    if (!form) return alert("Form not found");

    // Show loading state
    const spinner = document.getElementById("mesh_spinner");

    spinner?.classList.remove("d-none");
    generateMeshButton.dataset.meshRunning = "1";
    generateMeshButton.disabled = true;

    try {
      const startResult = await generateMeshFromCameras(sceneId, form);

      const requestId = startResult.request_id;
      if (!requestId) {
        throw new Error("Backend did not return request_id");
      }

      const statusResult = await pollMeshStatus(sceneId, requestId);

      if (statusResult?.unanchored_cameras?.length) {
        alert(
          "Mesh generated successfully! The scene map has been updated.\n\n" +
            "Warning: the following cameras had no prior calibration and were " +
            "placed automatically, review their position before relying on them: " +
            statusResult.unanchored_cameras.join(", "),
        );
      } else {
        alert("Mesh generated successfully! The scene map has been updated.");
      }

      $("#id_rotation_x").val(0);
      $("#id_rotation_y").val(0);
      $("#id_rotation_z").val(0);
      $("#id_translation_x").val(0);
      $("#id_translation_y").val(0);
      $("#id_translation_z").val(0);
      window.location.reload();
    } catch (err) {
      console.error(err);
      alert("Mesh generation failed: " + (err?.message ?? String(err)));
    } finally {
      // Hide loading state
      spinner?.classList.add("d-none");
      generateMeshButton.dataset.meshRunning = "0";
      generateMeshButton.disabled = false;
    }
  });
}

async function pollMeshStatus(sceneId, requestId) {
  const timeout = 15 * 60 * 1000; // 15 minutes
  const start = Date.now();

  while (true) {
    if (Date.now() - start > timeout) {
      throw new Error("Timed out waiting for mesh generation.");
    }

    const resp = await fetch(
      `/scene/generate-mesh-status/${sceneId}/?request_id=${encodeURIComponent(requestId)}`,
    );

    const data = await resp.json();

    if (!resp.ok) {
      throw new Error(data?.error || "Status check failed");
    }

    if (data.success === false) {
      throw new Error(data?.error || "Mesh generation failed");
    }

    if (data.state === "complete") {
      return data;
    }

    if (data.state === "failed") {
      throw new Error(data.error || "Mesh generation failed");
    }

    // Wait before next poll
    await new Promise((r) => setTimeout(r, 1500));
  }
}

async function generateMeshFromCameras(sceneId, form) {
  const url = `/scene/generate-mesh/${sceneId}/`;

  const formData = new FormData(form);

  // Make sure CSRF is sent (Django)
  const csrfToken =
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    getCookie("csrftoken");

  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "X-CSRFToken": csrfToken,
      Accept: "application/json",
    },
    body: formData,
  });

  const data = await resp.json().catch(() => ({}));

  if (!resp.ok || data.success === false) {
    throw new Error(
      data?.error || `Generate mesh failed (HTTP ${resp.status})`,
    );
  }

  // expects { success: true, request_id: "..." }
  if (!data.request_id) {
    throw new Error("Generate mesh response missing request_id");
  }

  return data;
}

// Optional cookie helper if you don't already have one:
function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
}

async function checkMappingServiceStatus() {
  const generateMeshButton = document.getElementById("generate_mesh");
  if (!generateMeshButton) return;

  const tokenElement = document.getElementById("auth-token");
  if (!tokenElement) {
    console.warn(
      "Authentication token not found for mapping service status check",
    );
    return;
  }

  const authToken = `Token ${tokenElement.value}`;

  try {
    const response = await fetch("/mapping-service/status/", {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        Authorization: authToken,
      },
    });

    if (response.ok) {
      const status = await response.json();

      if (status.available) {
        // Service is available, show the button
        generateMeshButton.style.display = "inline-block";
        const running = generateMeshButton.dataset.meshRunning === "1";
        if (!running) {
          generateMeshButton.disabled = false;
        }
        generateMeshButton.title =
          "Generate 3D mesh from camera images using mapping service";

        console.log("Mapping service is available:", status);
      } else {
        // Service is not available, hide the button
        generateMeshButton.style.display = "none";
        console.warn("Mapping service is not available:", status.error);
      }
    } else {
      // Error response, hide the button
      generateMeshButton.style.display = "none";
      console.error("Failed to check mapping service status:", response.status);
    }
  } catch (error) {
    // Network error or other issue, hide the button
    generateMeshButton.style.display = "none";
    console.error("Error checking mapping service status:", error);
  }
}

// Set up periodic status check
function startMappingServiceStatusMonitoring() {
  // Check immediately
  checkMappingServiceStatus();

  // Then check every 30 seconds
  setInterval(checkMappingServiceStatus, 30000);
}

$(document).ready(function () {
  const exportScene = document.getElementById("export-scene");
  const importButton = document.getElementById("scene-import");
  const tokenElement = document.getElementById("auth-token");

  if (importButton) {
    importButton.onclick = async function (e) {
      e.preventDefault();

      const inputElement = e.target;
      const authToken = `Token ${tokenElement.value}`;
      const restclient = new RESTClient(REST_URL, authToken);
      const importSpinner = document.getElementById("import-spinner");
      const zipFileInput = document.getElementById("id_zipFile");
      const errorList = document.getElementById("global-error-list");
      const errorContainer = document.getElementById("top-error-list");
      const warningList = document.getElementById("global-warning-list");
      const warningContainer = document.getElementById("top-warning-list");

      const showError = (messages) => {
        errorList.innerHTML = "";
        warningContainer.style.display = "none";

        for (const key in messages) {
          if (Array.isArray(messages[key])) {
            messages[key].forEach((msg) => {
              errorList.insertAdjacentHTML("beforeend", `<li>${msg}</li>`);
            });
          } else {
            errorList.insertAdjacentHTML(
              "beforeend",
              `<li>${messages[key]}</li>`,
            );
          }
          errorContainer.style.display = "block";
        }
      };

      const showWarnings = async (warnings, restClient) => {
        warningList.innerHTML = "";
        for (const key in warnings) {
          if (Array.isArray(warnings[key])) {
            for (const msg of warnings[key]) {
              let messageText = "";
              let message = msg[0];

              if (message && (message["name"] || message["sensor_id"])) {
                messageText = message["name"]
                  ? message["name"][0]
                  : message["sensor_id"][0];
              }
              if (
                messageText.includes("orphaned camera") ||
                messageText.includes(
                  "sensor with this Sensor ID already exists",
                )
              ) {
                const isCamera = key === "cameras";
                const userConfirmed = confirm(
                  `Do you want to orphan "${msg[1].name}" to the imported scene?`,
                );
                if (userConfirmed) {
                  try {
                    let updateResponse;
                    if (isCamera) {
                      updateResponse = await restClient.updateCamera(
                        msg[1].sensor_id,
                        { scene: msg[1].scene },
                      );
                    } else {
                      let sensorData = {
                        scene: msg[1].scene,
                        center: msg[1].center,
                      };
                      if (msg[1].area === "circle") {
                        sensorData.radius = msg[1].radius;
                        sensorData.area = msg[1].area;
                      }
                      if (msg[1].area === "poly" || msg[1].area === "scene") {
                        sensorData.points = msg[1].points;
                        sensorData.area = msg[1].area;
                      }
                      updateResponse = await restClient.updateSensor(
                        msg[1].name,
                        sensorData,
                      );
                    }
                    console.log("Update successful:", updateResponse);
                  } catch (err) {
                    warningList.insertAdjacentHTML(
                      "beforeend",
                      `<li>Failed to orphan: ${messageText}</li>`,
                    );
                  }
                } else {
                  warningList.insertAdjacentHTML(
                    "beforeend",
                    `<li>${messageText}</li>`,
                  );
                  warningContainer.style.display = "block";
                }
              } else {
                warningList.insertAdjacentHTML(
                  "beforeend",
                  `<li>${messageText}</li>`,
                );
                warningContainer.style.display = "block";
              }
            }
          }
        }
      };

      if (!zipFileInput.files.length) {
        showError("ZipFile field cannot be empty");
        return;
      }

      try {
        importSpinner.style.display = "block";

        // Directly upload the ZIP to import-scene endpoint
        const response = await fetch("/api/v1/import-scene/", {
          method: "POST",
          headers: { Authorization: authToken },
          body: new FormData(inputElement.form),
        });

        importSpinner.style.display = "none";
        const result = await response.json();
        if (result.scene) {
          showError(result.scene);
          return;
        }

        if (
          result.cameras ||
          result.calibration_markers ||
          result.tripwires ||
          result.regions ||
          result.sensors
        ) {
          await showWarnings(result, restclient);
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }

        // Redirect or refresh after successful import
        window.location.href = window.location.origin;
      } catch (error) {
        importSpinner.style.display = "none";
        showError(error);
      }
    };
  }

  if (exportScene) {
    exportScene.onclick = async function () {
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
    };
  }
  async function fetchFileAsBlob(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Failed to fetch: ${url}`);
    return await response.blob();
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
    if (window.location.href.includes("/cam/calibrate/")) {
      initializeCalibrationSettings();
    }

    // SVG scene implementation
    if (svgCanvas) {
      var $image = $("#map img");
      var image_w = $image.width();
      var $rois = $("#id_rois");
      var $tripwires = $("#tripwires");
      var $child_rois = $("#id_child_rois");
      var $child_tripwires = $("#child_tripwires");
      var $child_sensors = $("#child_sensors");

      var image_src = $image.attr("src");

      // Save image height as global for use in plotting
      scene_y_max = $image.height();
      $image.remove();

      $("#svgout").width(image_w).height(scene_y_max);
      var image = svgCanvas.image(image_src, 0, 0, image_w, scene_y_max);

      $("#svgout").show();

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

      $(".singleton").each(function () {
        var sensor = $.parseJSON($(".area-json", this).val());
        var i = $(".sensor-id", this).text();
        var g = svgCanvas.group();
        drawSensor(sensor, i, "sensor");
        if (sensor.sectors.thresholds.length > 0) {
          singleton_color_sectors[i] = sensor.sectors;
        }
      });

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

        // Save ROI's
        $("#save-rois, #save-trips").on("click", function (event) {
          var tripwire_values = getRoiValues(
            "form-control tripwire-title",
            "tripwire",
          );
          var rois_values = getRoiValues("form-control roi-title", "roi");
          rois_values = rois_values.concat(tripwire_values);
          if (event.target.id == "save-trips") {
            saveRois(rois_values);
          } else if (event.target.id == "save-rois") {
            saveRois(rois_values);
          }
        });
      }

      $("#new-roi").on("click", function () {
        addPoly();
      });

      $("#new-tripwire").on("click", function () {
        addTripwire();
      });

      $(".roi-remove").on("click", function () {
        var $group = $(this).closest(".form-roi");
        var r = confirm("Are you sure you wish to remove this ROI?");

        if (r == true) {
          var groupId = $group.attr("for");
          var svgGroup = Snap.select("#" + groupId);

          // Local-only removal: no form submission
          if (svgGroup) {
            handleRegionDelete(svgGroup);
          } else {
            // Fallback if SVG group not found (shouldn't happen in normal flow)
            $group.remove();
            numberRois();
            stringifyRois();
          }
        }
      });

      $(".tripwire-remove").on("click", function () {
        var $group = $(this).closest(".form-tripwire");
        var r = confirm("Are you sure you wish to remove this tripwire?");

        if (r == true) {
          var groupId = $group.attr("for");
          var svgGroup = Snap.select("#" + groupId);

          // Remove both SVG and form representations
          if (svgGroup) {
            svgGroup.remove();
          }
          $group.remove();

          // Update tripwire numbering and serialization
          numberTripwires();
          stringifyTripwires();
        }
      });
    }

    setColorForAllROIs();
  });

  // MQTT management (see https://github.com/mqttjs/MQTT.js)
  if ($("#broker").length != 0) {
    // Set broker value to the hostname of the current page
    // since broker runs on web server by default
    var host = window.location.hostname;
    var port = window.location.port;
    var broker = $("#broker").val();
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

    $("#broker-address").text(host);
    checkBrokerConnections()
      .then(() => {
        console.log("Broker connections checked");
      })
      .catch((error) => {
        console.log("An error occurred:", error);
      });
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

  $("#roi-form").submit(function (event) {
    stringifyRois();
    stringifyTripwires();
  });

  $("#fullscreen").on("click", function () {
    if (fullscreen) {
      $(".scene-map, .wrapper").addClass("container-fluid");
      $("#svgout").removeClass("fullscreen");
      $("body").css({
        "padding-top": "5rem",
        "padding-bottom": "5rem",
      });
      $(".hide-fullscreen").show();
      $(this).val("^");
      fullscreen = false;
    } else {
      $(".scene-map, .wrapper").removeClass("container-fluid");
      $("body").css({
        "padding-top": "0",
        "padding-bottom": "0",
      });
      $("#svgout").addClass("fullscreen");
      $(".hide-fullscreen").hide();
      $(this).val("v");
      fullscreen = true;
    }
  });

  $("input#show-trails").on("change", function () {
    if ($(this).is(":checked")) show_trails = true;
    else show_trails = false;
  });

  $("input#show-telemetry").on("change", function () {
    if ($(this).is(":checked")) show_telemetry = true;
    else show_telemetry = false;
  });

  $(".form-group")
    .find("input[type=text], input[type=number], select")
    .addClass("form-control");

  $(".form-group").each(function () {
    var label = $(this).find("label").first().attr("id");

    $("input", this).attr("aria-labelledby", label);
  });

  setupChildScene();

  if (
    document.getElementById("assetCreateForm") ||
    document.getElementById("assetUpdateForm")
  ) {
    if (document.getElementById("assetCreateForm"))
      $("#assetCreateForm").ready(toggleAsset3D);
    if (document.getElementById("assetUpdateForm"))
      $("#assetUpdateForm").ready(toggleAsset3D);
    $("#id_model_3d").on("change", toggleAsset3D);
  }

  if (document.getElementById("updateSceneForm")) {
    $("#updateSceneForm").ready(setupCalibrationType);
    $("#id_camera_calibration").on("change", setupCalibrationType);

    setupSceneRotationTranslationFields();
    $("#id_map").on("change", (e) => {
      setupSceneRotationTranslationFields(e);
    });

    // Setup Generate Mesh button
    setupGenerateMesh();
  }

  if (document.getElementById("createSceneForm")) {
    document.getElementById("id_scale").required = true;
    $("#id_map").on("change", (e) => {
      var uploaded_file_name = e.target.files[0].name;
      var uploaded_file_ext = uploaded_file_name.split(".").pop();
      if (uploaded_file_ext == "glb" || uploaded_file_ext == "zip") {
        document.getElementById("scale_wrapper").hidden = true;
        document.getElementById("id_scale").required = false;
      } else {
        document.getElementById("scale_wrapper").hidden = false;
        document.getElementById("id_scale").required = true;
      }
    });
  }

  $("#calibrate form").submit(function (event) {
    stringifySingletonColorRange();

    /* Checks that polygon is closed before submitting. */
    var poly_checked = $("#id_area_2").is(":checked");
    var poly_val = $("#id_rois").val();
    var poly_error_message =
      "Polygon area is not properly configured. Make sure it has at least 3 vertices.";

    if (poly_checked) {
      if (adding) {
        alert("Please close the polygon area prior to saving.");
        return false;
      }
      try {
        var poly_parsed = JSON.parse(poly_val);
        if (poly_parsed[0].points.length > 2) {
          return true; // Go ahead and submit the form
        } else {
          alert(poly_error_message);
          $("#redraw").click();
          return false;
        }
      } catch (error) {
        alert(poly_error_message);
        return false;
      }
    }
    return true; // Normally submit the form
  });
});

// Export functions for ES module consumers (e.g., scene-update-osm-roi.js)
export { drawRoi, numberRois, stringifyRois, editPolygon };
