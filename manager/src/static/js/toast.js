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

  function updateToast(id, message, type = "default") {
    const toastDiv = document.getElementById(id);
    if (!toastDiv) {
      console.warn(`Toast "${id}" not found; recreating.`);
      showToast(message, type, id, 10000);
      return;
    }

    const textSpan = toastDiv.querySelector(".toast-text-overflow");
    const alertDiv = toastDiv.querySelector(".alert");

    if (!textSpan || !alertDiv) {
      console.warn(`Toast structure missing for "${id}"; rebuilding.`);
      toastDiv.remove();
      showToast(message, type, id, 10000);
      return;
    }

    textSpan.innerHTML = message;

    Object.values(alertClasses).forEach((cls) =>
      alertDiv.classList.remove(cls),
    );
    alertDiv.classList.add(alertClasses[type] || alertClasses.default);
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
