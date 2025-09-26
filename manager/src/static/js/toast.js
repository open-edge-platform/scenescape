// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

export default function Toast() {
  let alertClasses = {
    default: "alert-default",
    success: "alert-success",
    warning: "alert-warning",
    danger: "alert-danger",
  };

  function showToast(
    alertMessage,
    alertType = "default",
    id = "None",
    delay = 5000,
  ) {
    let epochTime = Date.now();
    let runtimeToastClass = "toast-" + epochTime;
    let runtimeCloseClass = "close-" + epochTime;
    let runtimeAlertType =
      alertType in alertClasses
        ? alertClasses[alertType]
        : alertClasses["default"];

    let toast = createToast(
      alertMessage,
      runtimeToastClass,
      runtimeCloseClass,
      runtimeAlertType,
      id,
    );

    document.getElementById("toast-area").appendChild(toast);
    $("." + runtimeToastClass).toast({ delay: delay });
    $("." + runtimeToastClass).toast("show");

    document
      .querySelector("." + runtimeCloseClass)
      .addEventListener("click", function () {
        $("." + runtimeToastClass).toast("hide");
      });
  }

  // New method to update existing toast
  function updateToast(id, alertMessage, alertType = "default", delay = 5000) {
    const toastDiv = document.getElementById(id);
    if (!toastDiv) {
      console.warn(`Toast with id "${id}" not found. Falling back to showToast.`);
      showToast(alertMessage, alertType, id, delay);
      return;
    }

    // Update message text
    const toastTextSpan = toastDiv.querySelector(".toast-text-overflow");
    if (toastTextSpan) {
      toastTextSpan.innerHTML = alertMessage;
    }

    // Update alert classes
    const alertDiv = toastDiv.querySelector(".alert");
    if (alertDiv) {
      // Remove all known alert classes first
      Object.values(alertClasses).forEach(cls => alertDiv.classList.remove(cls));

      // Add the new alert class
      const newAlertClass = alertType in alertClasses ? alertClasses[alertType] : alertClasses["default"];
      alertDiv.classList.add(newAlertClass);
    }

    // Restart/show the toast with updated content
    $(toastDiv).toast('dispose'); // Dispose old instance
    $(toastDiv).toast({ delay: delay }); // Re-init with new delay
    $(toastDiv).toast('show'); // Show updated toast
  }

  function createToast(
    alertMessage,
    runtimeToastClass,
    runtimeCloseClass,
    runtimeAlertType,
    id,
  ) {
    let buttonSpan = document.createElement("span");
    buttonSpan.ariaHidden = "true";
    buttonSpan.innerHTML = "&times;";

    let closeButton = document.createElement("button");
    closeButton.className = "close " + runtimeCloseClass;
    closeButton.ariaLabel = "Close";
    closeButton.appendChild(buttonSpan);

    let toastSpan = document.createElement("span");
    toastSpan.className = "toast-text-overflow";
    toastSpan.innerHTML = alertMessage;

    let alertDiv = document.createElement("div");
    alertDiv.className =
      "alert alert-dismissible toast-height " + runtimeAlertType;
    alertDiv.appendChild(toastSpan);
    alertDiv.appendChild(closeButton);

    let toastDiv = document.createElement("div");
    toastDiv.className =
      "toast toast-transparent toast-width mb-0 hide " + runtimeToastClass;
    if (id !== "None") toastDiv.setAttribute("id", id);
    toastDiv.role = "alert";
    toastDiv.ariaLive = "assertive";
    toastDiv.ariaAtomic = "true";
    toastDiv.appendChild(alertDiv);

    return toastDiv;
  }

  return { showToast, updateToast };
}
