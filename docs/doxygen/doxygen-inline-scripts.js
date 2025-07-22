// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

function doxygenInlineInit() {
  var pathArray = location.pathname.split("/");
  var depth = pathArray.length - pathArray.indexOf("docs") - 2;
  var relativeHopPath = "../".repeat(depth);
  var pageName = pathArray.slice(3).join("/");
  if (pageName.length == 0) pageName = "index.html";

  initMenu(relativeHopPath, true, false, "search.php", "Search");
  initNavTree(pageName, relativeHopPath);
  initResizable();

  $("#nav-sync").removeClass("sync");
}

document.addEventListener("DOMContentLoaded", async function () {
  doxygenInlineInit();
});
