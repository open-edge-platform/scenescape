// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

const vm = require("vm");
const fs = require("fs");
const path = require("path");

const jsDir = path.join(
  __dirname,
  "../../../manager/src/manager/static/js/geospatial",
);

class FakeEl {
  constructor() {
    this.style = {};
    this.value = "";
    this.textContent = "";
    this.disabled = false;
    this.dataset = {};
    this.files = [];
    this.listeners = {};
  }

  addEventListener(type, fn) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(fn);
  }

  fire(type, ev) {
    if (this.listeners[type])
      for (const fn of this.listeners[type]) fn.call(this, ev);
  }

  getBoundingClientRect() {
    return { left: 0, top: 0 };
  }
}

function load(args) {
  const fakeEls = {};
  const docGetElementById = (id) => {
    if (!fakeEls[id]) {
      fakeEls[id] = new FakeEl();
      if (id === "glbAlignRow") fakeEls[id].dataset.sceneId = "scene-1";
      if (id === "id_map_type")
        fakeEls[id].value = args.mapType ?? "geospatial_map";
      if (id === "id_map_center_lat")
        fakeEls[id].value = args.center?.[0] ?? "37";
      if (id === "id_map_center_lng")
        fakeEls[id].value = args.center?.[1] ?? "-122";
    }
    return fakeEls[id];
  };

  let fetches = [];
  let fetchIdx = 0;
  const responses = (
    args.responses || [{ status: 404, body: { error: "x" } }]
  ).slice();

  class FakeFormData {
    constructor() {
      this.entries = [];
    }
    append(k, v) {
      this.entries.push([k, v]);
    }
  }

  const fakeFetch = async (url, opts = {}) => {
    const record = {
      url,
      method: opts.method || "GET",
      headers: opts.headers || {},
    };
    if (opts.body instanceof FakeFormData) {
      record.body = { formData: opts.body.entries };
    } else if (typeof opts.body === "string") {
      record.body = JSON.parse(opts.body);
    }
    fetches.push(record);
    const resp = responses[fetchIdx] || { status: 404, body: { error: "x" } };
    fetchIdx++;
    return {
      ok: resp.status < 400,
      status: resp.status,
      json: async () => resp.body,
    };
  };

  const strategy = {
    pointToLatLng(x, y) {
      return { lat: 37 - y * 1e-5, lng: -122 + x * 1e-5 };
    },
    calls: [],
    setOverlay(...a) {
      this.calls.push(["setOverlay", ...a]);
    },
    updateOverlay(...a) {
      this.calls.push(["updateOverlay", ...a]);
    },
    setOverlayOpacity(...a) {
      this.calls.push(["setOverlayOpacity", ...a]);
    },
    removeOverlay(...a) {
      this.calls.push(["removeOverlay", ...a]);
    },
  };

  const ctx = vm.createContext({
    console: { log() {}, error() {} },
    document: {
      getElementById: docGetElementById,
      querySelector: () => ({ value: "tok" }),
      addEventListener: () => {},
    },
    window: {
      listeners: {},
      addEventListener(t, fn) {
        (this.listeners[t] ||= []).push(fn);
      },
      removeEventListener(t, fn) {
        this.listeners[t] = (this.listeners[t] || []).filter((f) => f !== fn);
      },
      fire(t, ev) {
        (this.listeners[t] || []).forEach((fn) => fn(ev));
      },
      confirm: () => args.confirm ?? true,
      location: { reload() {} },
      mapManager: { getMapStrategy: () => strategy },
    },
    setTimeout: () => {},
    FormData: FakeFormData,
    fetch: fakeFetch,
  });

  ctx.globalThis = ctx;

  let src =
    fs.readFileSync(path.join(jsDir, "geo-overlay-math.js"), "utf8") + "\n";
  src += fs.readFileSync(path.join(jsDir, "glb-alignment.js"), "utf8") + "\n";
  src +=
    ";this.__api = {GlbAlignment, pointInPolygon, normalizeHeading, dragAnchor};";

  vm.runInContext(src, ctx);

  return { ctx, fakeEls, fetches, strategy };
}

const scenarios = {
  async align(args) {
    const { ctx, fakeEls, fetches, strategy } = load(args);
    const a = new ctx.__api.GlbAlignment();
    const events = [];

    await new Promise((r) => setImmediate(r));
    {
      for (const step of args.steps || []) {
        if (step[0] === "upload") {
          const fileEl = fakeEls["glbFileInput"];
          fileEl.files = [{ name: "a.glb" }];
          fileEl.fire("change", { target: fileEl });
        } else if (step[0] === "drag") {
          const [x0, y0] = step[1];
          const [x1, y1] = step[2];
          const ev0 = {
            type: "pointerdown",
            clientX: x0,
            clientY: y0,
            preventDefault() {
              this.prevented = true;
            },
            stopPropagation() {},
          };
          const mapEl = fakeEls["map"];
          mapEl.fire("pointerdown", ev0);
          events.push({ prevented: !!ev0.prevented });
          if (ev0.prevented) {
            ctx.window.fire("pointermove", { clientX: x1, clientY: y1 });
            ctx.window.fire("pointerup", {});
          }
        } else if (step[0] === "heading") {
          const headEl = fakeEls["glbHeadingNumber"];
          headEl.value = step[1];
          headEl.fire("input", { target: headEl });
        } else if (step[0] === "accept") {
          await a._accept?.();
        } else if (step[0] === "reset") {
          a._reset?.();
        } else if (step[0] === "cancel") {
          a._cancel?.();
        }
        await new Promise((r) => setImmediate(r));
      }
    }

    return {
      ok: true,
      fetches,
      calls: strategy.calls,
      events,
      status: fakeEls["glbAlignStatus"]?.textContent || "",
      controlsDisplay: fakeEls["glbAlignControls"]?.style?.display ?? "none",
      fileDisabled: fakeEls["glbFileInput"]?.disabled ?? false,
      rowDisplay: fakeEls["glbAlignRow"]?.style?.display ?? "",
      hint: fakeEls["glbAlignHint"]?.textContent || "",
      anchor: a.anchor,
      dirty: a.dirty,
    };
  },

  helpers(args) {
    const { ctx } = load(args);
    const { pointInPolygon, normalizeHeading, dragAnchor } = ctx.__api;
    if (args.fn === "pointInPolygon") {
      const result = pointInPolygon(args.args[0], args.args[1]);
      return { ok: true, result };
    }
    if (args.fn === "normalizeHeading") {
      const result = normalizeHeading(args.args[0]);
      return { ok: true, result };
    }
    if (args.fn === "dragAnchor") {
      const result = dragAnchor(args.args[0], args.args[1], args.args[2]);
      return { ok: true, result };
    }
    return { ok: false, error: "Unknown helper" };
  },
};

let input = "";
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", async () => {
  try {
    const { scenario, args } = JSON.parse(input);
    const handler = scenarios[scenario];
    if (!handler) throw new Error(`Unknown scenario: ${scenario}`);
    const result = await handler(args);
    console.log(JSON.stringify(result));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, error: e.message }));
  }
});
