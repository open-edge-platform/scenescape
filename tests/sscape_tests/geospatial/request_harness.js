// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/* Test harness for requestJson/getCsrfToken from js/request.js */

"use strict";

const vm = require("vm");
const fs = require("fs");
const path = require("path");

const code = fs.readFileSync(
  path.join(__dirname, "../../../manager/src/manager/static/js/request.js"),
  "utf8",
);

const input = JSON.parse(fs.readFileSync(0, "utf-8"));

class FakeFormData {}

const sent = [];
const ctx = vm.createContext({
  document: {
    querySelector: () => (input.csrf == null ? null : { value: input.csrf }),
  },
  FormData: FakeFormData,
  fetch: async (url, init) => {
    sent.push({
      url,
      method: init.method,
      headers: init.headers,
      body:
        init.body instanceof FakeFormData
          ? "<FormData>"
          : init.body === undefined
            ? null
            : init.body,
    });
    const resp = input.response;
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
vm.runInContext(code, ctx);

const options = { ...(input.options || {}) };
if (options.body === "<FormData>") options.body = new FakeFormData();
const template = options.errorMessageTemplate;
delete options.errorMessageTemplate;
if (template) {
  options.errorMessage = (status) => template.replace("{status}", status);
}

(async () => {
  const out = {};
  try {
    out.result = await ctx.requestJson(input.url, options);
  } catch (error) {
    out.error = {
      message: error.message,
      status: error.status ?? null,
      data: error.data ?? null,
    };
  }
  out.sent = sent;
  process.stdout.write(JSON.stringify(out));
})();
