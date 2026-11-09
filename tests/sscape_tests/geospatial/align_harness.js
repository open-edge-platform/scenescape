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
    this.children = [];
    this._text = "";
    this.disabled = false;
    this.dataset = {};
    this.files = [];
    this.listeners = {};
  }

  get textContent() {
    return this._text + this.children.map((c) => c.textContent).join("");
  }

  set textContent(v) {
    this._text = String(v);
    this.children = [];
  }

  appendChild(el) {
    el.parent = this;
    this.children.push(el);
    return el;
  }

  replaceChildren(...els) {
    this.children = [];
    els.forEach((el) => this.appendChild(el));
  }

  addEventListener(type, fn) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(fn);
  }

  fire(type, ev) {
    if (this.listeners[type])
      for (const fn of this.listeners[type]) fn.call(this, ev);
  }

  remove() {
    if (this.parent)
      this.parent.children = this.parent.children.filter((c) => c !== this);
  }

  getBoundingClientRect() {
    return { left: 0, top: 0 };
  }
}

class FakeForm extends FakeEl {
  constructor() {
    super();
    this.children = [];
  }

  appendChild(el) {
    el.parent = this;
    this.children.push(el);
    return el;
  }

  querySelector(sel) {
    const name = sel.match(/name="([^"]+)"/)?.[1];
    return this.children.find((c) => c.name === name) ?? null;
  }
}

function load(args) {
  const fakeEls = {};
  const fakeForm = new FakeForm();
  const sessionStore = new Map();
  const mapCalls = [];
  const confirms = [];
  const docGetElementById = (id) => {
    if (!fakeEls[id]) {
      fakeEls[id] = new FakeEl();
      if (id === "glbAlignRow") {
        fakeEls[id].dataset.sceneId = "scene-1";
        fakeEls[id].closest = () => fakeForm;
      }
      if (id === "glbSavePosition") fakeEls[id].style.display = "none";
      if (id === "mapProvider") fakeEls[id].value = args.provider ?? "google";
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
      ui: {
        fileDisabled: fakeEls.glbFileInput?.disabled ?? null,
        filePointerEvents: fakeEls.glbFileInput?.style.pointerEvents ?? null,
        fileWrapTitle: fakeEls.glbFileWrap?.title ?? null,
        acceptDisabled: fakeEls.glbAccept?.disabled ?? null,
        acceptPointerEvents: fakeEls.glbAccept?.style.pointerEvents ?? null,
        acceptTitle: fakeEls.glbAcceptWrap?.title ?? null,
      },
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
      json: async () => {
        if (resp.nonJson) throw new SyntaxError("Unexpected token <");
        return resp.body;
      },
    };
  };

  const strategy = {
    pointToLatLng(x, y) {
      return { lat: 37 - y * 1e-5, lng: -122 + x * 1e-5 };
    },
    calls: [],
    frame: null,
    setOverlay(...a) {
      this.calls.push(["setOverlay", ...a]);
      this.frame = a[3] ?? null;
    },
    setOverlayFrameColor(color) {
      this.frame = color;
    },
    updateOverlay(...a) {
      this.calls.push(["updateOverlay", ...a]);
    },
    setOverlayOpacity(...a) {
      this.calls.push(["setOverlayOpacity", ...a]);
    },
    removeOverlay(...a) {
      this.calls.push(["removeOverlay", ...a]);
      this.frame = null;
    },
    fitToCorners(...a) {
      this.calls.push(["fitToCorners", ...a]);
    },
  };

  const ctx = vm.createContext({
    console: { log() {}, error() {} },
    document: {
      getElementById: docGetElementById,
      querySelector: () => ({ value: "tok" }),
      createElement: (tag) =>
        Object.assign(new FakeEl(), { tagName: String(tag).toUpperCase() }),
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
      confirm: (msg) => {
        confirms.push(msg);
        return args.confirm ?? true;
      },
      location: { reload() {}, pathname: "/scene/s1/update/" },
      sessionStorage: {
        getItem: (k) => sessionStore.get(k) ?? null,
        setItem: (k, v) => sessionStore.set(k, String(v)),
        removeItem: (k) => sessionStore.delete(k),
      },
      saveCurrentMapSettings: () => mapCalls.push("save"),
      loadSavedGeospatialSettings: () => {
        mapCalls.push("load");
        return { lat: 37.5, lng: -121.5, zoom: 17.5, rotation: 12 };
      },
      mapManager:
        args.mapReady === false
          ? undefined
          : { getMapStrategy: () => strategy },
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
    ";this.__api = {GlbAlignment, pointInPolygon, clampHeading, dragAnchor};";

  vm.runInContext(src, ctx);

  return {
    ctx,
    fakeEls,
    fakeForm,
    fetches,
    strategy,
    sessionStore,
    mapCalls,
    confirms,
  };
}

function statusListOf(statusEl) {
  const box = statusEl?.children[0];
  if (!box) return null;
  return {
    tagName: box.tagName,
    className: box.className,
    items: box.children.map((li) => li.textContent),
  };
}

const scenarios = {
  async align(args) {
    const {
      ctx,
      fakeEls,
      fakeForm,
      fetches,
      strategy,
      sessionStore,
      mapCalls,
      confirms,
    } = load(args);
    const a = new ctx.__api.GlbAlignment();
    if (args.geomapReady) ctx.window.fire("geomap-ready", {});
    const events = [];
    const takes = [];
    const clicks = [];

    const savePosShown = () =>
      fakeEls["glbSavePosition"]?.style?.display ?? null;
    const savePosTrail = [];
    const frameState = () => strategy.frame;
    const frameTrail = [];
    const drag = (from, to) => {
      const ev0 = {
        type: "pointerdown",
        clientX: from[0],
        clientY: from[1],
        preventDefault() {
          this.prevented = true;
        },
        stopPropagation() {},
      };
      fakeEls["map"].fire("pointerdown", ev0);
      events.push({ prevented: !!ev0.prevented });
      if (ev0.prevented) {
        ctx.window.fire("pointermove", { clientX: to[0], clientY: to[1] });
        ctx.window.fire("pointerup", {});
      }
    };

    await new Promise((r) => setImmediate(r));
    savePosTrail.push(savePosShown());
    frameTrail.push(frameState());
    {
      for (const step of args.steps || []) {
        if (step[0] === "upload") {
          const fileEl = fakeEls["glbFileInput"];
          fileEl.files = [{ name: "a.glb" }];
          fileEl.fire("change", { target: fileEl });
        } else if (step[0] === "click") {
          const fileEl = fakeEls["glbFileInput"];
          const ev = {
            type: "click",
            preventDefault() {
              this.prevented = true;
            },
          };
          fileEl.fire("click", ev);
          clicks.push({ prevented: !!ev.prevented });
        } else if (step[0] === "drag") {
          drag(step[1], step[2]);
        } else if (step[0] === "save") {
          await a._savePosition?.();
        } else if (step[0] === "saveAndDrag") {
          const inflight = a._savePosition?.();
          drag(step[1], step[2]);
          await inflight;
        } else if (step[0] === "remove") {
          await a._remove?.();
        } else if (step[0] === "toggleUse") {
          fakeEls["glbUse"].checked = step[1];
          await a._toggleUse?.();
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
        } else if (step[0] === "take") {
          if (step[2]) ctx.window.location.pathname = step[2];
          takes.push(ctx.window.takeGlbAcceptedView(step[1]));
        } else if (step[0] === "submit") {
          fakeForm.fire("submit", {});
        }
        await new Promise((r) => setImmediate(r));
        savePosTrail.push(savePosShown());
        frameTrail.push(frameState());
      }
    }

    return {
      ok: true,
      fetches,
      calls: strategy.calls,
      events,
      takes,
      clicks,
      confirms,
      staged: a.staged?.token ?? null,
      mapCalls,
      stored: sessionStore.has("glbAcceptedView")
        ? JSON.parse(sessionStore.get("glbAcceptedView"))
        : null,
      savePosTrail,
      frameTrail,
      mapFrame: frameState(),
      savedBlockDisplay: fakeEls["glbSavedBlock"]?.style?.display ?? null,
      savedAnchor: a.saved?.anchor ?? null,
      status: fakeEls["glbAlignStatus"]?.textContent || "",
      statusList: statusListOf(fakeEls["glbAlignStatus"]),
      controlsDisplay: fakeEls["glbAlignControls"]?.style?.display ?? "none",
      fileDisabled: fakeEls["glbFileInput"]?.disabled ?? false,
      filePointerEvents: fakeEls["glbFileInput"]?.style?.pointerEvents ?? "",
      fileTitle: fakeEls["glbFileWrap"]?.title ?? "",
      acceptDisabled: fakeEls["glbAccept"]?.disabled ?? false,
      acceptPointerEvents: fakeEls["glbAccept"]?.style?.pointerEvents ?? "",
      acceptTitle: fakeEls["glbAcceptWrap"]?.title ?? "",
      rowDisplay: fakeEls["glbAlignRow"]?.style?.display ?? "",
      hint: fakeEls["glbAlignHint"]?.textContent || "",
      anchor: a.anchor,
      dirty: a.dirty,
      formInputs: fakeForm.children.map((c) => ({
        name: c.name,
        type: c.type,
        value: c.value,
      })),
    };
  },

  async savedOverlay(args) {
    const { ctx, strategy } = load({ ...args, mapReady: false });
    const a = new ctx.__api.GlbAlignment();
    const flush = () => new Promise((r) => setImmediate(r));
    const becomeReady = () => {
      ctx.window.mapManager = { getMapStrategy: () => strategy };
      ctx.window.fire("geomap-ready", {});
    };
    if (args.order === "mapFirst") {
      becomeReady();
      await flush();
    } else {
      await flush();
      becomeReady();
    }
    a._render();
    return { ok: true, calls: strategy.calls };
  },

  helpers(args) {
    const { ctx } = load(args);
    const { pointInPolygon, clampHeading, dragAnchor } = ctx.__api;
    if (args.fn === "pointInPolygon") {
      const result = pointInPolygon(args.args[0], args.args[1]);
      return { ok: true, result };
    }
    if (args.fn === "clampHeading") {
      const result = clampHeading(args.args[0]);
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
