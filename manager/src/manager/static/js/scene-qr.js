// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
/* global $ */

"use strict";

$(document).on("click", ".scene-qr-button", function (event) {
  event.preventDefault();
  const $button = $(this);
  const uri = $button.attr("data-qr") || "";
  const target = $button.attr("data-qr-target");
  const svg = target ? $("#" + target).html() : "";
  $("#scene-qr-image").html(svg);
  $("#scene-qr-uri").text(uri);
  $("#scene-qr-modal").modal("show");
});
