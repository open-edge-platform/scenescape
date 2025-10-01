"use strict";

// Geospatial demo functionality
document.addEventListener("DOMContentLoaded", function () {
  // Add event listeners for geospatial buttons
  const actionButtons = document.querySelectorAll("button[data-action]");
  actionButtons.forEach((button) => {
    const action = button.getAttribute("data-action");
    button.addEventListener("click", function () {
      if (window.mapManager && typeof mapManager[action] === "function") {
        mapManager[action]();
      }
    });
  });

  // Add event listener for map provider changes
  const mapProviderSelect = document.getElementById("mapProvider");
  if (mapProviderSelect) {
    mapProviderSelect.addEventListener("change", function () {
      if (window.switchMapProvider && typeof switchMapProvider === "function") {
        switchMapProvider();
      }
    });
  }
});
