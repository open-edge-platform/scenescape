// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
/* global $ */

"use strict";

$(document).on("scene-qr-open", function () {
  const $data = $("#scene-qr-data");
  const uri = $data.attr("data-qr");
  if (!uri) return;
  $("#scene-qr-image").html($data.html());
  $("#scene-qr-uri").text(uri);
  $("#scene-qr-modal").modal("show");
});
