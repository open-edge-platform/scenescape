// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/* Test harness for the Apply all GLBs switch in js/geospatial/apply-all-glbs.js (uses requestJson from js/request.js) */

"use strict";

const vm = require("vm");
const fs = require("fs");
const path = require("path");

const staticDir = path.join(
  __dirname,
  "../../../manager/src/manager/static/js",
);
const requestCode = fs.readFileSync(path.join(staticDir, "request.js"), "utf8");
const applyCode = fs.readFileSync(
  path.join(staticDir, "geospatial/apply-all-glbs.js"),
  "utf8",
);

const input = JSON.parse(fs.readFileSync(0, "utf-8"));

const sent = [];
const alerts = [];
const domReady = [];
const changeListeners = [];
let reloads = 0;

const toggle = {
  checked: input.checked,
  disabled: false,
  dataset: { url: input.url },
  addEventListener(type, fn) {
    if (type === "change") changeListeners.push(fn);
  },
};

const fakeDocument = {
  querySelector: () => (input.csrf == null ? null : { value: input.csrf }),
  getElementById: (id) => (id === "apply-all-glbs" ? toggle : null),
  addEventListener(type, fn) {
    if (type === "DOMContentLoaded") domReady.push(fn);
  },
};

const fakeWindow = {
  location: {
    reload() {
      reloads += 1;
    },
  },
  alert(message) {
    alerts.push(message);
  },
};

class FakeFormData {}

const ctx = vm.createContext({
  document: fakeDocument,
  window: fakeWindow,
  FormData: FakeFormData,
  fetch: async (url, init) => {
    sent.push({
      url,
      method: init.method,
      headers: init.headers,
      body: init.body ?? null,
      toggleDisabledWhileSending: toggle.disabled,
    });
    const resp = input.response || { status: 200, body: {} };
    if (resp.networkError) throw new TypeError(resp.networkError);
    return {
      ok: resp.status < 400,
      status: resp.status,
      json: async () => {
        if (resp.nonJson) throw new SyntaxError("Unexpected token <");
        return resp.body;
      },
    };
  },
});

vm.runInContext(requestCode, ctx);
vm.runInContext(applyCode, ctx);

(async () => {
  const out = {};
  try {
    domReady.forEach((fn) => fn());
    toggle.checked = input.click;
    await Promise.all(changeListeners.map((fn) => fn({ target: toggle })));
  } catch (error) {
    out.unexpected = String(error);
  }
  out.sent = sent;
  out.checked = toggle.checked;
  out.disabled = toggle.disabled;
  out.reloads = reloads;
  out.alerts = alerts;
  process.stdout.write(JSON.stringify(out));
})();
