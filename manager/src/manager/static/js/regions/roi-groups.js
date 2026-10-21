// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Regions tab grouping of ROI form rows by type, with per-group visibility and color.

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
// Label shown for the group of ROIs with no type set
var UNCATEGORIZED_ROI_TYPE_LABEL = "Uncategorized";
// ROI type-group keys the user has deselected (persists across regroupRoiFields() re-renders)
var deselectedRoiGroups = new Set();
// User-picked colors (group key -> "#rrggbb") that override getRoiGroupColor()'s default
var roiGroupColorOverrides = {};
// Sticky auto-assigned colors (group key -> color), set the first time a key
// is resolved in regroupRoiFields() so each type keeps its look across re-renders.
var roiGroupAutoColors = {};

var hooks = {
  onChange: function () {},
  isColoringEnabled: function () {
    return false;
  },
};

/** Register callbacks into sscape.js: re-serialize ROIs, and whether occupancy coloring is on. */
function initRoiGroups(options) {
  Object.assign(hooks, options);
}

/** Last-resort deterministic color for a key, used only once every palette color is already taken by another active group. */
function getRoiGroupColor(key) {
  var hash = 0;
  for (var idx = 0; idx < key.length; idx++) {
    hash = (hash * 31 + key.charCodeAt(idx)) >>> 0;
  }
  return ROI_GROUP_COLOR_PALETTE[hash % ROI_GROUP_COLOR_PALETTE.length];
}

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
      if (!hooks.isColoringEnabled()) {
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
  hooks.onChange();
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
  hooks.onChange();
});

export { initRoiGroups, regroupRoiFields, roiGroupColorForKey };
