// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import { updateElements } from "/static/js/utils.js";

function setupChildScene() {
  $("#id_transform_type").on("change", function () {
    setupChildTransform();
  });

  if (document.getElementById("manage_child")) {
    setupChildSceneType();
    var childTypes = document.querySelectorAll('input[name="child_type"]');
    childTypes.forEach((radioButton) => {
      radioButton.addEventListener("change", setupChildSceneType);
    });

    $("#id_parent").closest(".transform-group").removeClass("transform-group");

    setupChildTransform();

    var parent_id = $("#view_parent_id").val();

    // Set parent automatically
    $('#id_parent>option[value="' + parent_id + '"]')
      .prop("selected", true)
      .closest(".form-group")
      .addClass("display-none");

    // Remove the parent from the child dropdown
    // FIXME: Have backend do this, as well as remove any options that
    // are already assigned to this or another parent
    $('#id_child>option[value="' + parent_id + '"]').remove();

    // Add event handler to the tranform type field
    $("#id_transform_type").on("change", setupChildTransform);
    $("#id_transform8").on("change", setYZScale);
    $("#id_transform7").on("change", setYZScale);
  }
}

function setupChildSceneType() {
  var childType = document.querySelector(
    'input[name="child_type"]:checked',
  ).value;
  var isChildLocal = childType === "local";

  document.getElementById("child_wrapper")["hidden"] = !isChildLocal;

  var remoteChildElements = [
    "child_name_wrapper",
    "remote_child_id_wrapper",
    "host_name_wrapper",
    "mqtt_username_wrapper",
    "mqtt_password_wrapper",
  ];
  var elementsRequired = [
    "id_child_name",
    "id_remote_child_id",
    "id_host_name",
    "id_mqtt_username",
    "id_mqtt_password",
  ];

  updateElements(remoteChildElements, "hidden", isChildLocal);
  updateElements(elementsRequired, "required", !isChildLocal);

  return;
}

function setYZScale() {
  var transformType = $("#id_transform_type").val();

  switch (transformType) {
    case "quaternion":
      var scale = $("#id_transform8").val();

      $("#id_transform9").val(scale);
      $("#id_transform10").val(scale);

      break;
    case "euler":
      var scale = $("#id_transform7").val();

      $("#id_transform8").val(scale);
      $("#id_transform9").val(scale);

      break;
  }
}

// Set up form for child-to-parent relationships
function setupChildTransform() {
  var transformType = $("#id_transform_type").val();

  // Reset visibility and disabled flags
  $(".transform-group")
    .removeClass("display-none")
    .find("input")
    .prop("disabled", false);

  switch (transformType) {
    case "matrix":
      // Update labels based on matrix (row,column)
      $("#label_transform1").text("Matrix (1,1)");
      $("#label_transform2").text("Matrix (1,2)");
      $("#label_transform3").text("Matrix (1,3)");
      $("#label_transform4").text("Matrix (1,4)");
      $("#label_transform5").text("Matrix (2,1)");
      $("#label_transform6").text("Matrix (2,2)");
      $("#label_transform7").text("Matrix (2,3)");
      $("#label_transform8").text("Matrix (2,4)");
      $("#label_transform9").text("Matrix (3,1)");
      $("#label_transform10").text("Matrix (3,2)");
      $("#label_transform11").text("Matrix (3,3)");
      $("#label_transform12").text("Matrix (3,4)");
      $("#label_transform13").text("Matrix (4,1)");
      $("#label_transform14").text("Matrix (4,2)");
      $("#label_transform15").text("Matrix (4,3)");
      $("#label_transform16").text("Matrix (4,4)");

      // Disable fields that shouldn't ever change
      $("#id_transform13").val("0.0").prop("disabled", true);

      $("#id_transform14").val("0.0").prop("disabled", true);

      $("#id_transform15").val("0.0").prop("disabled", true);

      $("#id_transform16").val("1.0").prop("disabled", true);

      break;
    case "euler":
      // Update labels with Translation, Euler Angles, and Scale
      $("#label_transform1").text("X Translation (meters)");
      $("#label_transform2").text("Y Translation (meters)");
      $("#label_transform3").text("Z Translation (meters)");
      $("#label_transform4").text("X Rotation (degrees)");
      $("#label_transform5").text("Y Rotation (degrees)");
      $("#label_transform6").text("Z Rotation (degrees)");
      $("#label_transform7").text("Scale");

      $("#label_transform8").closest(".form-group").addClass("display-none");
      $("#label_transform9").closest(".form-group").addClass("display-none");
      $("#label_transform10").closest(".form-group").addClass("display-none");
      $("#label_transform11").closest(".form-group").addClass("display-none");
      $("#label_transform12").closest(".form-group").addClass("display-none");
      $("#label_transform13").closest(".form-group").addClass("display-none");
      $("#label_transform14").closest(".form-group").addClass("display-none");
      $("#label_transform15").closest(".form-group").addClass("display-none");
      $("#label_transform16").closest(".form-group").addClass("display-none");

      // Set scale fields to 1.0 by default
      if ($("#id_transform7").val() === "0.0") $("#id_transform7").val("1.0");

      // Make Y and Z transform match the X transform value
      $("#id_transform8").val($("#id_transform7").val());
      $("#id_transform9").val($("#id_transform7").val());

      break;
    case "quaternion":
      // Update labels with Translation, Quaternion, and Scale
      $("#label_transform1").text("X Translation (meters)");
      $("#label_transform2").text("Y Translation (meters)");
      $("#label_transform3").text("Z Translation (meters)");
      $("#label_transform4").text("X Quaternion");
      $("#label_transform5").text("Y Quaternion");
      $("#label_transform6").text("Z Quaternion");
      $("#label_transform7").text("W Quaternion");
      $("#label_transform8").text("Scale");

      $("#label_transform9").closest(".form-group").addClass("display-none");
      $("#label_transform10").closest(".form-group").addClass("display-none");
      $("#label_transform11").closest(".form-group").addClass("display-none");
      $("#label_transform12").closest(".form-group").addClass("display-none");
      $("#label_transform13").closest(".form-group").addClass("display-none");
      $("#label_transform14").closest(".form-group").addClass("display-none");
      $("#label_transform15").closest(".form-group").addClass("display-none");
      $("#label_transform16").closest(".form-group").addClass("display-none");

      // Set scale fields to 1.0 by default
      if ($("#id_transform8").val() === "0.0") $("#id_transform8").val("1.0");

      // Make Y and Z transform match the X transform value
      $("#id_transform9").val($("#id_transform8").val());
      $("#id_transform10").val($("#id_transform8").val());

      break;
  }
}

export { setupChildScene };
