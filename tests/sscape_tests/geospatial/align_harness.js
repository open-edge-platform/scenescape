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

// Scene-edit form inputs that a server scene_fields payload writes into.
const SCENE_FORM_IDS = [
  "id_scale",
  "id_rotation_x",
  "id_rotation_y",
  "id_rotation_z",
  "id_translation_x",
  "id_translation_y",
  "id_translation_z",
  "id_map_corners_lla",
];

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
    this.attrs = {};
    this.parentNode = null;
    this.captured = null;
    const classes = new Set();
    this.classList = {
      toggle: (name, force) => {
        if (force) classes.add(name);
        else classes.delete(name);
      },
      contains: (name) => classes.has(name),
    };
  }

  setAttribute(name, value) {
    this.attrs[name] = String(value);
  }

  getAttribute(name) {
    return this.attrs[name] ?? null;
  }

  contains(el) {
    return el === this || this.children.some((c) => c.contains(el));
  }

  setPointerCapture(id) {
    this.captured = id;
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
    el.parentNode = this;
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

  querySelectorAll() {
    return [];
  }

  cloneNode() {
    return new FakeEl();
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
  const confirms = [];
  const docGetElementById = (id) => {
    if (!fakeEls[id]) {
      fakeEls[id] = new FakeEl();
      if (id === "glbAlignRow") {
        fakeEls[id].dataset.sceneId = "scene-1";
        fakeEls[id].dataset.maxLayers = String(args.maxLayers ?? 1);
        if (args.maxUploadBytes)
          fakeEls[id].dataset.maxUploadBytes = String(args.maxUploadBytes);
        fakeEls[id].closest = () => fakeForm;
      }
      if (id === "glbPanelTemplate")
        fakeEls[id].content = { firstElementChild: new FakeEl() };
      if (id === "glbSavePosition") fakeEls[id].style.display = "none";
      if (id === "glbCancel") fakeEls[id].style.display = "none";
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
    // Inverse of pointToLatLng under the current pan/zoom `view`.
    view: { scale: 1, dx: 0, dy: 0 },
    viewCallbacks: new Set(),
    latLngToPoint(lat, lng) {
      if (this.view.notReady) throw new Error("Map overlay is not ready");
      return {
        x: ((lng + 122) / 1e-5) * this.view.scale + this.view.dx,
        y: ((37 - lat) / 1e-5) * this.view.scale + this.view.dy,
      };
    },
    onViewChange(cb) {
      this.viewCallbacks.add(cb);
      return () => this.viewCallbacks.delete(cb);
    },
    setView(view) {
      Object.assign(this.view, view);
      this.viewCallbacks.forEach((cb) => cb());
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

  let src = fs.readFileSync(path.join(jsDir, "../request.js"), "utf8") + "\n";
  src +=
    fs.readFileSync(path.join(jsDir, "geo-overlay-math.js"), "utf8") + "\n";
  src += fs.readFileSync(path.join(jsDir, "glb-alignment.js"), "utf8") + "\n";
  src +=
    ";this.__api = {GlbAlignment, pointInPolygon, clampHeading, dragAnchor, wrapDegrees180: _wrapDegrees180};";

  vm.runInContext(src, ctx);

  return {
    ctx,
    fakeEls,
    fakeForm,
    fetches,
    strategy,
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
    const { ctx, fakeEls, fakeForm, fetches, strategy, confirms } = load(args);
    const ctl = new ctx.__api.GlbAlignment();
    const a = ctl.panels[0];
    if (args.geomapReady) ctx.window.fire("geomap-ready", {});
    const events = [];
    const clicks = [];

    const savePosShown = () =>
      fakeEls["glbSavePosition"]?.style?.display ?? null;
    const savePosTrail = [];
    const frameState = () => strategy.frame;
    const frameTrail = [];
    const submits = [];
    const sceneForm = () =>
      Object.fromEntries(
        SCENE_FORM_IDS.map((id) => [id, fakeEls[id]?.value ?? null]),
      );
    const sceneFormTrail = [];
    // Fires the form submit like a browser would, recording whether the handler prevented it.
    const submit = () => {
      const ev = {
        type: "submit",
        preventDefault() {
          this.prevented = true;
        },
      };
      fakeForm.fire("submit", ev);
      submits.push({
        prevented: !!ev.prevented,
        status: fakeEls["glbAlignStatus"]?.textContent || "",
      });
    };
    const press = (from) => {
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
      return ev0;
    };
    const drag = (from, to) => {
      if (press(from).prevented) {
        ctx.window.fire("pointermove", { clientX: to[0], clientY: to[1] });
        ctx.window.fire("pointerup", {});
      }
    };
    const dialState = () =>
      a.dial && {
        display: a.dial.root.style.display,
        left: a.dial.root.style.left,
        top: a.dial.root.style.top,
        width: a.dial.root.style.width,
        height: a.dial.root.style.height,
        knobLeft: a.dial.knob.style.left,
        knobTop: a.dial.knob.style.top,
        attrs: a.dial.knob.attrs,
        attached: a.dial.root.parentNode === fakeEls["map"],
        captured: a.dial.knob.captured,
        active: a.dial.root.classList.contains("glb-rot-dial--active"),
      };
    const dialTrail = [];
    const dialEvents = [];
    const lastOpacity = () =>
      strategy.calls.filter((c) => c[0] === "setOverlayOpacity").at(-1)?.[1];
    const dialPointer = (type, pt, opts = {}) => ({
      type,
      clientX: pt[0],
      clientY: pt[1],
      pointerId: 7,
      button: 0,
      shiftKey: !!opts.shift,
      target: a.dial.knob,
      preventDefault() {
        this.prevented = true;
      },
      stopPropagation() {
        this.stopped = true;
      },
    });
    // Grabs the dial at `from` and moves to `to`; opts.hold keeps the pointer down.
    const dialDrag = (from, to, opts = {}) => {
      const down = dialPointer("pointerdown", from, opts);
      a.dial.root.fire("pointerdown", down);
      const rec = {
        prevented: !!down.prevented,
        stopped: !!down.stopped,
        opacityOnGrab: lastOpacity(),
      };
      // `to` is one point, or a list of points whose optional third value is the Shift state.
      const path = Array.isArray(to[0]) ? to : [to];
      for (const pt of path)
        ctx.window.fire(
          "pointermove",
          dialPointer("pointermove", pt, { shift: pt[2] ?? opts.shift }),
        );
      rec.opacityOnMove = lastOpacity();
      if (!opts.hold) ctx.window.fire("pointerup", {});
      dialEvents.push(rec);
    };

    await new Promise((r) => setImmediate(r));
    savePosTrail.push(savePosShown());
    frameTrail.push(frameState());
    sceneFormTrail.push(sceneForm());
    dialTrail.push(dialState()?.display ?? null);
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
          // The dial is the only heading control, so tests set a heading through its code path.
          a._setHeading(ctx.__api.clampHeading(Number(step[1])));
        } else if (step[0] === "cancelClick") {
          fakeEls["glbCancel"].fire("click", {});
        } else if (step[0] === "cancel") {
          a._cancel?.();
        } else if (step[0] === "press") {
          press(step[1]);
        } else if (step[0] === "release") {
          ctx.window.fire("pointerup", {});
        } else if (step[0] === "dialDrag") {
          dialDrag(step[1], step[2], step[3]);
        } else if (step[0] === "dialLegacy") {
          const ev = dialPointer(step[1], [0, 0]);
          a.dial.root.fire(step[1], ev);
          dialEvents.push({ stopped: !!ev.stopped, prevented: !!ev.prevented });
        } else if (step[0] === "dialKey") {
          const ev = {
            key: step[1],
            shiftKey: !!step[2],
            preventDefault() {
              this.prevented = true;
            },
          };
          a.dial.knob.fire("keydown", ev);
          dialEvents.push({ prevented: !!ev.prevented });
        } else if (step[0] === "view") {
          strategy.setView(step[1]);
        } else if (step[0] === "detachDial") {
          a.dial.root.parentNode.children = [];
          a.dial.root.parentNode = null;
        } else if (step[0] === "mapPressOnDial") {
          const ev = dialPointer("pointerdown", step[1]);
          fakeEls["map"].fire("pointerdown", ev);
          dialEvents.push({ prevented: !!ev.prevented, stopped: !!ev.stopped });
        } else if (step[0] === "geomapReady") {
          ctx.window.fire("geomap-ready", {});
        } else if (step[0] === "hover") {
          fakeEls["map"].fire("pointermove", {
            clientX: step[1][0],
            clientY: step[1][1],
          });
        } else if (step[0] === "leave") {
          fakeEls["map"].fire("pointerleave", {});
        } else if (step[0] === "dialFocus") {
          a.dial.knob.fire("focus", {});
        } else if (step[0] === "dialBlur") {
          a.dial.knob.fire("blur", {});
        } else if (step[0] === "mapType") {
          fakeEls["id_map_type"].value = step[1];
          fakeEls["id_map_type"].fire("change", {});
        } else if (step[0] === "addPanel") {
          ctl._addPanel();
        } else if (step[0] === "stagePanel") {
          await ctl.panels[step[1]]._handleFileUpload({
            target: { files: [{ name: step[2] }], value: "" },
          });
        } else if (step[0] === "markDirty") {
          ctl.panels[step[1]].dirty = true;
        } else if (step[0] === "submit") {
          submit();
        } else if (step[0] === "saveAndSubmit") {
          const inflight = a._savePosition?.();
          submit();
          await inflight;
        }
        await new Promise((r) => setImmediate(r));
        savePosTrail.push(savePosShown());
        frameTrail.push(frameState());
        sceneFormTrail.push(sceneForm());
        dialTrail.push(dialState()?.display ?? null);
      }
    }

    const mapPoint = (c) => {
      const pt = strategy.latLngToPoint(c.lat, c.lng);
      return { left: `${pt.x}px`, top: `${pt.y}px` };
    };
    return {
      ok: true,
      fetches,
      calls: strategy.calls,
      events,
      clicks,
      confirms,
      staged: a.staged?.token ?? null,
      savePosTrail,
      frameTrail,
      sceneFormTrail,
      sceneForm: sceneForm(),
      stateToken: fakeEls["id_glb_state_token"]?.value ?? null,
      submits,
      mapFrame: frameState(),
      savedBlockDisplay: fakeEls["glbSavedBlock"]?.style?.display ?? null,
      useChecked: fakeEls["glbUse"]?.checked ?? null,
      savedAnchor: a.saved?.anchor ?? null,
      status: fakeEls["glbAlignStatus"]?.textContent || "",
      statusList: statusListOf(fakeEls["glbAlignStatus"]),
      cancelDisplay: fakeEls["glbCancel"]?.style?.display ?? "none",
      footprintText: fakeEls["glbFootprint"]?.textContent ?? "",
      dial: dialState(),
      dialTrail,
      dialEvents,
      viewSubscribers: strategy.viewCallbacks.size,
      fileDisabled: fakeEls["glbFileInput"]?.disabled ?? false,
      filePointerEvents: fakeEls["glbFileInput"]?.style?.pointerEvents ?? "",
      fileTitle: fakeEls["glbFileWrap"]?.title ?? "",
      rowDisplay: fakeEls["glbAlignRow"]?.style?.display ?? "",
      hint: fakeEls["glbAlignHint"]?.textContent || "",
      anchor: a.anchor,
      dirty: a.dirty,
      formInputs: fakeForm.children.map((c) => ({
        name: c.name,
        type: c.type,
        value: c.value,
      })),
      glbChanges: fakeForm.children
        .filter((c) => c.name === "glb_changes")
        .flatMap((c) => JSON.parse(c.value)),
      panelCount: ctl.panels.length,
      panelState: ctl.panels.map((p) => ({
        status: p.ui.fileStatus.textContent,
        badge: p.ui.layerBadge.textContent,
        badgeLabel: p.ui.layerBadge.attrs["aria-label"] ?? null,
        badgeDisplay: p.ui.layerBadge.style.display,
        numbered: p.root.classList.contains("glb-layer-panel--numbered"),
        layerId: p.ui.layerId.textContent,
        layerIdTitle: p.ui.layerId.title ?? "",
        // The NW corner is where the map badge goes; corners are ordered SW, SE, NE, NW.
        nwPoint:
          p.anchor && p._corners().length ? mapPoint(p._corners()[3]) : null,
        mapBadge: p.mapBadge && {
          text: p.mapBadge.textContent,
          label: p.mapBadge.attrs["aria-label"] ?? null,
          display: p.mapBadge.style.display,
          left: p.mapBadge.style.left,
          top: p.mapBadge.style.top,
          attached: p.mapBadge.parentNode === fakeEls["map"],
        },
      })),
      panelDirty: ctl.panels.map((p) => p.dirty),
      addDisplay: fakeEls["glbAddLayer"]?.style?.display ?? null,
      addDisabled: fakeEls["glbAddLayer"]?.disabled ?? null,
    };
  },

  // Panel index of the topmost layer under each [lat, lng] point, or -1 for none.
  async panelHits(args) {
    const { ctx } = load(args);
    const ctl = new ctx.__api.GlbAlignment();
    await new Promise((r) => setImmediate(r));
    return {
      ok: true,
      panelCount: ctl.panels.length,
      hits: args.points.map(([lat, lng]) => {
        const hit = ctl._topmostAt({ lat, lng });
        return hit ? ctl.panels.indexOf(hit) : -1;
      }),
    };
  },

  async savedOverlay(args) {
    const { ctx, strategy } = load({ ...args, mapReady: false });
    const ctl = new ctx.__api.GlbAlignment();
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
    ctl.panels[0]._render();
    return { ok: true, calls: strategy.calls };
  },

  helpers(args) {
    const { ctx } = load(args);
    const { pointInPolygon, clampHeading, dragAnchor, wrapDegrees180 } =
      ctx.__api;
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
    if (args.fn === "wrapDegrees180") {
      const result = wrapDegrees180(args.args[0]);
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
