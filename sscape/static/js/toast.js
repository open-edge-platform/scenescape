// Copyright (C) 2023 Intel Corporation
//
// This software and the related documents are Intel copyrighted materials,
// and your use of them is governed by the express license under which they
// were provided to you ("License"). Unless the License provides otherwise,
// you may not use, modify, copy, publish, distribute, disclose or transmit
// this software or the related documents without Intel's prior written permission.
//
// This software and the related documents are provided as is, with no express
// or implied warranties, other than those that are expressly stated in the License.

export default function Toast() {
  let alertClasses = {
    'default': 'alert-default',
    'success': 'alert-success',
    'warning': 'alert-warning',
    'danger': 'alert-danger',
  };

  function showToast(alertMessage, alertType = 'default', id = 'None', delay = 5000) {
    let epochTime = Date.now();
    let runtimeToastClass = 'toast-' + epochTime;
    let runtimeCloseClass = 'close-' + epochTime;
    let runtimeAlertType = alertType in alertClasses ? alertClasses[alertType] : alertClasses['default'];

    let toast = createToast(alertMessage, runtimeToastClass, runtimeCloseClass, runtimeAlertType, id)

    document.getElementById('toast-area').appendChild(toast);
    $('.'+runtimeToastClass).toast({ delay: delay });
    $('.'+runtimeToastClass).toast('show');

    document.querySelector('.'+runtimeCloseClass).addEventListener("click", function() {
      $('.'+runtimeToastClass).toast('hide');
    });
  }

  function createToast(alertMessage, runtimeToastClass, runtimeCloseClass, runtimeAlertType, id) {
    let buttonSpan = document.createElement('span');
    buttonSpan.ariaHidden = 'true';
    buttonSpan.innerHTML = '&times;';

    let closeButton = document.createElement('button');
    closeButton.className = 'close ' + runtimeCloseClass;
    closeButton.ariaLabel = 'Close';
    closeButton.appendChild(buttonSpan);

    let toastSpan = document.createElement('span');
    toastSpan.className = 'toast-text-overflow';
    toastSpan.innerHTML = alertMessage;

    let alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-dismissible toast-height ' + runtimeAlertType;
    alertDiv.appendChild(toastSpan);
    alertDiv.appendChild(closeButton);

    let toastDiv = document.createElement('div');
    toastDiv.className = 'toast toast-transparent toast-width mb-0 hide ' + runtimeToastClass;
    if (id !== 'None') toastDiv.setAttribute('id', id);
    toastDiv.role = 'alert';
    toastDiv.ariaLive = 'assertive';
    toastDiv.ariaAtomic = 'true';
    toastDiv.appendChild(alertDiv);

    return toastDiv
  }

  return {showToast};
}
