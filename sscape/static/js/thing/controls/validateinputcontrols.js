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
