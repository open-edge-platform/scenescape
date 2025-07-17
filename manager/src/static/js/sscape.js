// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

"use strict";

import {
  APP_NAME,
  CMD_AUTOCALIB_SCENE,
  CMD_CAMERA,
  DATA_AUTOCALIB_CAM_POSE,
  DATA_CAMERA,
  DATA_REGULATED,
  IMAGE_CALIBRATE,
  IMAGE_CAMERA,
  SYS_AUTOCALIB_STATUS,
  SYS_CHILDSCENE_STATUS,
  SYS_PERCEBRO_STATUS,
  REST_URL,
} from "/static/js/constants.js";
import {
  metersToPixels,
  pixelsToMeters,
  checkWebSocketConnection,
  updateElements,
  importScene,
} from "/static/js/utils.js";
import { plot } from "/static/js/marks.js";
import { setupChildScene } from "/static/js/childscene.js";
import {
  initializeCalibration,
  registerAutoCameraCalibration,
  manageCalibrationState,
  initializeCalibrationSettings,
  updateCalibrationView,
  handleAutoCalibrationPose,
  setMqttForCalibration,
} from "/static/js/calibration.js";

var svgCanvas = Snap("#svgout");
import RESTClient from "/static/js/restclient.js";
var points, maps, rois, tripwires, child_rois, child_tripwires, child_sensors;
var dragging, drawing, adding, editing, fullscreen;
var g;
var radius = 5;
var scale = 30.0; // Default map scale in pixels/meter
var scene_id = $("#scene").val();
var icon_size = 24;
var show_telemetry = false;
var scene_y_max = 480; // Scene image height in pixels
var savedElements = [];
var is_coloring_enabled = false; // Default state of the coloring feature
var roi_color_sectors = {};
var singleton_color_sectors = {};
var scene_rotation_translation_config;

points = maps = rois = tripwires = [];
dragging = drawing = adding = editing = fullscreen = false;

// Force page reload on back button press
if (window.performance && window.performance.navigation.type == 2) {
  location.reload();
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
  const urlInsecure = "wss://" + window.location.host + "/mqtt-insecure";
  const urlSecure = "wss://" + window.location.host + "/mqtt";

  const promises = [
    checkWebSocketConnection(urlInsecure), // Check insecure port
    checkWebSocketConnection(urlSecure), // Check secure port
  ];

  const results = await Promise.allSettled(promises);

  let openPort = null;
  let isSecure = false;

  results.forEach((result) => {
    if (result.status === "fulfilled") {
      openPort = result.value;
    }
  });

  if (openPort) {
    if (openPort === urlInsecure) {
      isSecure = false;
      $("#broker").val(urlInsecure);
    } else if (openPort === urlSecure) {
      broker.value = broker.value.replace("localhost", window.location.host);
    }
    console.log(`Url ${openPort} is open`);

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

        if (window.location.href.includes("/cam/calibrate/")) {
          // distortion available only for percebro or supporting VA
          initializeCalibration(client, scene_id);
        }

        $("#mqtt_status").addClass("connected");

        // Capture thumbnail snapshots
        if ($(".snapshot-image").length) {
          client.subscribe(APP_NAME + IMAGE_CAMERA + "+");

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
        } else if ($("#auto-camcalibration").length) {
          var auto_topic =
            APP_NAME + DATA_AUTOCALIB_CAM_POSE + $("#sensor_id").val();
          client.subscribe(auto_topic);
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
          plot(msg.objects, scale, scene_y_max, svgCanvas, show_telemetry);
        } else if (topic.includes(SYS_PERCEBRO_STATUS)) {
          if (msg == "running") {
            setMqttForCalibration(client);
          }
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
        } else if (topic.includes(IMAGE_CAMERA)) {
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
        } else if (topic.includes(IMAGE_CALIBRATE)) {
          updateCalibrationView(msg);
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
        } else if (topic.includes(SYS_AUTOCALIB_STATUS)) {
          if (msg === "running") {
            registerAutoCameraCalibration(client, scene_id);
          }
        } else if (topic.includes(CMD_AUTOCALIB_SCENE + scene_id)) {
          if (msg !== "register") {
            manageCalibrationState(msg, client, scene_id);
          }
        } else if (topic.includes(DATA_AUTOCALIB_CAM_POSE)) {
          handleAutoCalibrationPose(msg);
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
      $("#auto-camcalibration").on("click", function () {
        client.publish(topic, "localize");
        document.getElementById("auto-camcalibration").disabled = true;
        document.getElementById("reset_points").disabled = true;
        document.getElementById("top_save").disabled = true;
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
  } else {
    console.log("Neither port is open.");
  }
}

function plotSingleton(m) {
  var $sensor = $("#sensor_" + m.id);

  $(".area", $sensor).css("fill", m.status);
  $("text", $sensor).text(m.value.toString());
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
  var groups = svgCanvas.selectAll("g.roi");

  groups.forEach(function (e, n) {
    var text = e.select("text");

    if (text) {
      text.node.innerText = n + 1;
    } else {
      var id = e.attr("id");
      const roi_group_points = e.select("polygon").attr("points");
      var center = polyCenter(roi_group_points);

      text = e.text(center[0], center[1], n + 1);
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

function numberTripwires() {
  var groups = svgCanvas.selectAll("g.tripwire");

  groups.forEach(function (e, n) {
    var text = e.select("text");
    var id = e.attr("id");

    text.node.innerHTML = n + 1;

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

  if (this.type === "circle") {
    $("#id_sensor_x").val(this.attr("cx"));
    $("#id_sensor_y").val(this.attr("cy"));
  } else {
    $("#id_sensor_x").val(parseInt(this.attr("x")) + icon_size / 2);
    $("#id_sensor_y").val(parseInt(this.attr("y")) + icon_size / 2);
  }
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
  var duplicates = find_duplicates(roi_values);
  if (duplicates.length > 0) {
    alert(duplicates.toString() + " already exists. Try a different name");
  } else {
    $("#roi-form").submit();
  }
}

if (svgCanvas) {
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

function setROIColor(roi_id, occupancy) {
  var roi_polygon = document.querySelector("#roi_" + roi_id + " polygon");
  if (roi_polygon) {
    if (is_coloring_enabled) {
      var color = getColorForValue(roi_id, occupancy, roi_color_sectors);
      roi_polygon.style.fill = color;
    } else {
      roi_polygon.style.fill = "white";
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

$(document).ready(function () {
  const loginButton = document.getElementById("login-submit");
  const spinner = document.getElementById("login-spinner");
  const loginText = document.getElementById("login-text");
  const exportScene = document.getElementById("export-scene");
  const importButton = document.getElementById("scene-import");
  const tokenElement = document.getElementById("auth-token");

  if (importButton) {
    importButton.onclick = async function (e) {
      e.preventDefault();

      const inputElement = e.target;
      const formData = new FormData(inputElement.form);
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
        if (Array.isArray(messages)) {
          messages.forEach((msg) =>
            errorList.insertAdjacentHTML("beforeend", `<li>${msg}</li>`),
          );
        } else {
          errorList.insertAdjacentHTML("beforeend", `<li>${messages}</li>`);
        }
        errorContainer.style.display = "block";
      };

      const showWarnings = (warnings) => {
        warningList.innerHTML = "";
        console.log(warnings);
        for (const key in warnings) {
          if (Array.isArray(warnings[key])) {
            for (const msg of warnings[key]) {
              warningList.insertAdjacentHTML("beforeend", `<li>${msg}</li>`);
            }
          }
        }
        warningContainer.style.display = "block";
      };

      if (!zipFileInput.value) {
        showError("ZipFile field cannot be empty");
        return;
      }

      try {
        importSpinner.style.display = "block";
        const response = await fetch("", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          importSpinner.style.display = "none";
          showError("Network response was not OK");
          return;
        }

        const zipFile = zipFileInput.value.split("\\").pop();
        const basename = zipFile.replace(/\.[^/.]+$/, "");
        const zipFileURL =
          "https://" + window.location.hostname + "/media/" + basename + "/";
        const errors = await importScene(
          zipFileURL,
          restclient,
          basename,
          window,
          authToken,
        );

        if (errors.scene) {
          importSpinner.style.display = "none";
          const sceneErrors = Object.values(errors.scene).map((e) => e[0]);
          showError(sceneErrors);
          return;
        }

        if (
          errors.cameras ||
          errors.tripwires ||
          errors.regions ||
          errors.sensors
        ) {
          importSpinner.style.display = "none";
          showWarnings(errors);
          return;
        }

        importSpinner.style.display = "none";
        window.location.href = window.location.origin;
      } catch (error) {
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

  const coloring_toggle = $("input#coloring-switch");
  if (coloring_toggle.length) {
    is_coloring_enabled = localStorage.getItem("visualize_rois") === "true";
    coloring_toggle.prop("checked", is_coloring_enabled);
    setColorForAllROIs();
  }

  coloring_toggle.on("change", function () {
    const isChecked = $(this).is(":checked");
    is_coloring_enabled = isChecked;
    localStorage.setItem("visualize_rois", isChecked);
    setColorForAllROIs();
  });

  // Operations to take after images are loaded
  $(".content").imagesLoaded(function () {
    // Camera calibration interface
    initializeCalibrationSettings();

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
        var sensor_x = $("#id_sensor_x").val();
        var sensor_y = $("#id_sensor_y").val();
        // Bug in slider -- .val() doesn't work right and seems to max at 100
        var sensor_r = $("#id_sensor_r").attr("value");

        // Place sensor in the middle of the scene by default
        if (!sensor_x | (sensor_x == "None")) {
          sensor_x = parseInt(image_w / 2);
          $("#id_sensor_x").val(sensor_x);
        }
        if (!sensor_y | (sensor_y == "None")) {
          sensor_y = parseInt(scene_y_max / 2);
          $("#id_sensor_y").val(sensor_y);
        }
        if (!sensor_r | (sensor_r == "None")) {
          sensor_r = parseInt(scene_y_max / 2);
        }

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
          $("#" + $group.attr("for")).remove();
          $group.remove();
          numberRois();
          saveRois(getRoiValues("form-control roi-title", "roi"));
        }
      });

      $(".tripwire-remove").on("click", function () {
        var $group = $(this).closest(".form-tripwire");
        var r = confirm("Are you sure you wish to remove this tripwire?");

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
