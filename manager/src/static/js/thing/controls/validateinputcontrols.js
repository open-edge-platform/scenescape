// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

let validateInputControls = {
  addFieldWarning(fieldName) {
    this.executeOnControl('save', function (control) {
      control[0].domElement.classList.add('disabled');
    });
    this.executeOnControl(fieldName, function (control) {
      control[0].domElement.classList.add('text-danger');
      control[0].$input.classList.add('border');
      control[0].$input.classList.add('border-danger');
      control[0].$widget.setAttribute('data-toggle', 'tooltip');
      control[0].$widget.setAttribute('title', 'Enter camera name to save the camera');
    });
    this.controlsFolder.$title.classList.add('text-danger');
    this.controlsFolder.$title.setAttribute('data-toggle', 'tooltip');
    this.controlsFolder.$title.setAttribute('title', 'Enter camera name to save the camera');
  },
  removeFieldWarning(fieldName) {
    this.executeOnControl('save', function (control) {
      control[0].domElement.classList.remove('disabled');
    });
    this.executeOnControl(fieldName, function (control) {
      control[0].domElement.classList.remove('text-danger');
      control[0].$input.classList.remove('border');
      control[0].$input.classList.remove('border-danger');
      control[0].$widget.setAttribute('data-toggle', '');
      control[0].$widget.setAttribute('title', '');
    });
    this.controlsFolder.$title.classList.remove('text-danger');
    this.controlsFolder.$title.setAttribute('data-toggle', '');
    this.controlsFolder.$title.setAttribute('title', '');
  },
  validateField(fieldName, validateLambda) {
    if (validateLambda()) this.addFieldWarning(fieldName);
    else this.removeFieldWarning(fieldName);
  },
  executeOnControl(controlName, lambda) {
    const controllers = this.controlsFolder.controllersRecursive();
    const control = controllers.filter((item) => item.property === controlName);
    if (control) lambda(control);
  },
  disableFields(fields) {
    for (const field of fields) {
      this.executeOnControl(field, (control) => { control[0].domElement.classList.add('disabled')});
    }
  }
};

export default validateInputControls;
