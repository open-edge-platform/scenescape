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

function numOrNaN(x) {
  if (typeof x === "string" && x === "NaN") return NaN;
  if (typeof x === "string" && x === "Infinity") return Infinity;
  if (typeof x === "string" && x === "-Infinity") return -Infinity;
  return x;
}

function fakeElement() {
  return {
    style: {},
    src: null,
    appendChild() {},
    removeChild() {},
    children: [],
  };
}

function fakeDocument(createElCb) {
  return {
    getElementById() {
      return null;
    },
    createElement(tag) {
      if (tag === "img") {
        createElCb?.();
      }
      return fakeElement();
    },
    head: { appendChild() {} },
    body: { className: "", appendChild() {} },
    querySelector() {
      return null;
    },
  };
}

function load(files, extra = {}) {
  const ctx = vm.createContext({
    console: { log() {}, error() {}, warn() {} },
    document: fakeDocument(extra._createElCb),
    window: {},
    globalThis: {},
    alert() {},
    ...extra,
  });
  ctx.globalThis = ctx;

  let src = "";
  for (const f of files) {
    src += fs.readFileSync(path.join(jsDir, f), "utf8") + "\n";
  }
  src += `
;this.__exports = {
  GeoOverlayMath: typeof GeoOverlayMath !== "undefined" ? GeoOverlayMath : undefined,
  MapInterface: typeof MapInterface !== "undefined" ? MapInterface : undefined,
  MapboxPlugin: typeof MapboxPlugin !== "undefined" ? MapboxPlugin : undefined,
  GoogleMapsPlugin: typeof GoogleMapsPlugin !== "undefined" ? GoogleMapsPlugin : undefined
};`;
  vm.runInContext(src, ctx);
  return ctx;
}

const GOOGLE_CORNERS = [
  { lat: 10, lng: 20 },
  { lat: 10, lng: 30 },
  { lat: 20, lng: 30 },
  { lat: 20, lng: 20 },
];

// Google fake whose projection offers both div and container pixels, and that draws on setMap.
function loadGooglePlugin(noGoogle = false) {
  const googleMaps = {
    OverlayView: class {
      setMap(map) {
        this.map = map;
        if (map) {
          this.panes = { overlayLayer: { appendChild() {}, removeChild() {} } };
          this.proj = {
            fromLatLngToDivPixel(ll) {
              return { x: (ll.lng() - 10) * 1000, y: (50 - ll.lat()) * 1000 };
            },
            fromLatLngToContainerPixel(ll) {
              return {
                x: (ll.lng() + 100) / 0.001,
                y: (40 - ll.lat()) / 0.001,
              };
            },
          };
          this.onAdd?.();
          this.draw?.();
        } else {
          this.onRemove?.();
        }
      }
      getPanes() {
        return this.panes;
      }
      getProjection() {
        return this.proj;
      }
    },
    LatLng: class {
      constructor(lat, lng) {
        this._lat = lat;
        this._lng = lng;
      }
      lat() {
        return this._lat;
      }
      lng() {
        return this._lng;
      }
    },
  };
  const ctx = load(
    ["map-interface.js", "geo-overlay-math.js", "google-maps-plugin.js"],
    { google: noGoogle ? undefined : { maps: googleMaps } },
  );
  const plugin = new ctx.__exports.GoogleMapsPlugin();
  plugin.map = {};
  return { ctx, plugin };
}

const scenarios = {
  corners(args) {
    const ctx = load(["geo-overlay-math.js"]);
    const { GeoOverlayMath } = ctx.__exports;
    const [lat, lng, h, w, ht] = args.map(numOrNaN);
    const result = GeoOverlayMath.footprintCornersLLA(lat, lng, h, w, ht);
    return { ok: true, result };
  },

  matrix(args) {
    const ctx = load(["geo-overlay-math.js"]);
    const { GeoOverlayMath } = ctx.__exports;
    const [nw, ne, sw] = args;
    const result = GeoOverlayMath.overlayCssMatrix(nw, ne, sw);
    return { ok: true, result };
  },

  abstract(method) {
    const ctx = load(["map-interface.js"]);
    const { MapInterface } = ctx.__exports;
    class X extends MapInterface {}
    const obj = new X();
    try {
      obj[method]();
      return { ok: false, error: `Method ${method} did not throw` };
    } catch (e) {
      return { ok: true, threw: e.name };
    }
  },

  mapboxPointToLatLng(steps) {
    const ctx = load([
      "map-interface.js",
      "geo-overlay-math.js",
      "mapbox-plugin.js",
    ]);
    const { MapboxPlugin } = ctx.__exports;
    const points = [];
    const fakeMap = {
      unproject([x, y]) {
        return { lat: 40 - y * 0.001, lng: -100 + x * 0.001 };
      },
      addSource() {},
      getSource() {
        return null;
      },
      addLayer() {},
      getLayer() {
        return null;
      },
      setPaintProperty() {},
      removeLayer() {},
      removeSource() {},
    };
    const plugin = new MapboxPlugin();
    plugin.map = fakeMap;
    for (const [x, y] of steps) {
      const res = plugin.pointToLatLng(x, y);
      points.push(res);
    }
    return { ok: true, points };
  },

  googlePointToLatLng(args) {
    const steps = args.steps || [];
    const noGoogle = args.noGoogle;
    const points = [];
    let googleMaps = null;
    if (!noGoogle) {
      googleMaps = {
        Point: class {
          constructor(x, y) {
            this.x = x;
            this.y = y;
          }
        },
        OverlayView: class {
          setMap(map) {
            this.map = map;
            if (map) {
              this.panes = {
                overlayLayer: {
                  children: [],
                  appendChild(e) {
                    this.children.push(e);
                  },
                  removeChild(e) {
                    const i = this.children.indexOf(e);
                    if (i >= 0) this.children.splice(i, 1);
                  },
                },
              };
              this.proj = {
                fromContainerPixelToLatLng(pt) {
                  return {
                    lat() {
                      return 40 - pt.y * 0.001;
                    },
                    lng() {
                      return -100 + pt.x * 0.001;
                    },
                  };
                },
              };
              this.onAdd?.();
            }
          }
          getPanes() {
            return this.panes;
          }
          getProjection() {
            return this.proj;
          }
        },
        LatLng: class {
          constructor(lat, lng) {
            this._lat = lat;
            this._lng = lng;
          }
          lat() {
            return this._lat;
          }
          lng() {
            return this._lng;
          }
        },
      };
    }
    const ctx = load(
      ["map-interface.js", "geo-overlay-math.js", "google-maps-plugin.js"],
      { google: googleMaps ? { maps: googleMaps } : undefined },
    );
    const { GoogleMapsPlugin } = ctx.__exports;
    const plugin = new GoogleMapsPlugin();
    plugin.map = {};
    plugin.setOverlay(
      "test.jpg",
      [
        { lat: 10, lng: 20 },
        { lat: 10, lng: 30 },
        { lat: 20, lng: 30 },
        { lat: 20, lng: 20 },
      ],
      0.5,
    );
    for (const [x, y] of steps) {
      const res = plugin.pointToLatLng(x, y);
      points.push(res);
    }
    return { ok: true, points };
  },

  mapbox(steps) {
    const ctx = load([
      "map-interface.js",
      "geo-overlay-math.js",
      "mapbox-plugin.js",
    ]);
    const { MapboxPlugin } = ctx.__exports;
    const calls = [];
    const sources = {};
    const layers = {};
    const fakeMap = {
      addSource(id, cfg) {
        calls.push("addSource");
        sources[id] = {
          ...cfg,
          setCoordinates(c) {
            calls.push("setCoordinates");
            this.coordinates = c;
          },
        };
      },
      getSource(id) {
        calls.push("getSource");
        return sources[id] || null;
      },
      addLayer(cfg) {
        calls.push("addLayer");
        layers[cfg.id] = cfg;
      },
      getLayer(id) {
        calls.push("getLayer");
        return layers[id] || null;
      },
      setPaintProperty(id, p, v) {
        calls.push("setPaintProperty");
        if (layers[id]) layers[id].paint = { ...layers[id].paint, [p]: v };
      },
      removeLayer(id) {
        calls.push("removeLayer");
        delete layers[id];
      },
      removeSource(id) {
        calls.push("removeSource");
        delete sources[id];
      },
    };
    const plugin = new MapboxPlugin();
    plugin.map = fakeMap;
    for (const step of steps) {
      const op = step[0];
      if (op === "setOverlay")
        plugin.setOverlay(
          step[1],
          step[2],
          step[3],
          null,
          step[4] ?? "glb-overlay",
        );
      else if (op === "updateOverlay") plugin.updateOverlay(step[1]);
      else if (op === "setOverlayOpacity") plugin.setOverlayOpacity(step[1]);
      else if (op === "setOverlayFrameColor")
        plugin.setOverlayFrameColor(step[1]);
      else if (op === "removeOverlay")
        plugin.removeOverlay(step[1] ?? "glb-overlay");
    }
    return {
      ok: true,
      calls,
      sources: Object.keys(sources),
      layers: Object.keys(layers),
      opacity: layers["glb-overlay"]?.paint["raster-opacity"] ?? null,
      frameWidth: layers["glb-overlay-frame"]?.paint["line-width"] ?? null,
    };
  },

  mapboxLatLngToPoint(steps) {
    const ctx = load([
      "map-interface.js",
      "geo-overlay-math.js",
      "mapbox-plugin.js",
    ]);
    const { MapboxPlugin } = ctx.__exports;
    const plugin = new MapboxPlugin();
    plugin.map = {
      project([lng, lat]) {
        return { x: (lng + 100) / 0.001, y: (40 - lat) / 0.001, extra: 1 };
      },
    };
    return {
      ok: true,
      points: steps.map(([lat, lng]) => plugin.latLngToPoint(lat, lng)),
    };
  },

  mapboxViewChange() {
    const ctx = load([
      "map-interface.js",
      "geo-overlay-math.js",
      "mapbox-plugin.js",
    ]);
    const { MapboxPlugin } = ctx.__exports;
    const handlers = {};
    const plugin = new MapboxPlugin();
    plugin.map = {
      on(name, cb) {
        (handlers[name] ||= new Set()).add(cb);
      },
      off(name, cb) {
        handlers[name]?.delete(cb);
      },
    };
    let calls = 0;
    const off = plugin.onViewChange(() => calls++);
    const registered = Object.keys(handlers).sort();
    const fire = (name) => handlers[name].forEach((cb) => cb());
    fire("move");
    fire("zoom");
    fire("resize");
    const whileSubscribed = calls;
    off();
    const remaining = Object.values(handlers).reduce((n, s) => n + s.size, 0);
    return { ok: true, registered, whileSubscribed, remaining };
  },

  googleLatLngToPoint(args) {
    const { plugin } = loadGooglePlugin(args.noGoogle);
    if (!args.noOverlay) plugin.setOverlay("test.jpg", GOOGLE_CORNERS, 0.5);
    return {
      ok: true,
      points: args.steps.map(([lat, lng]) => plugin.latLngToPoint(lat, lng)),
    };
  },

  googleViewChange() {
    const { plugin } = loadGooglePlugin();
    const listeners = [];
    plugin.map = {
      addListener(name, cb) {
        const l = {
          name,
          cb,
          removed: false,
          remove() {
            this.removed = true;
          },
        };
        listeners.push(l);
        return l;
      },
    };
    let calls = 0;
    const off = plugin.onViewChange(() => calls++);
    const registered = listeners.map((l) => l.name).sort();
    listeners.forEach((l) => l.cb());
    const afterMapEvents = calls;
    plugin.setOverlay("test.jpg", GOOGLE_CORNERS, 0.5);
    const afterDraw = calls;
    off();
    plugin.setOverlay("test.jpg", GOOGLE_CORNERS, 0.5);
    return {
      ok: true,
      registered,
      afterMapEvents,
      afterDraw,
      afterOff: calls,
      allRemoved: listeners.every((l) => l.removed),
    };
  },

  google(args) {
    const steps = args.steps || [];
    const noGoogle = args.noGoogle;
    let setMapCalls = 0;
    let created = 0;
    const snapshots = [];
    const createElCb = () => {
      created++;
    };
    let googleMaps = null;
    if (!noGoogle) {
      googleMaps = {
        OverlayView: class {
          setMap(map) {
            setMapCalls++;
            this.map = map;
            if (map) {
              this.panes = {
                overlayLayer: {
                  children: [],
                  appendChild(e) {
                    e.parentNode = this;
                    this.children.push(e);
                  },
                  removeChild(e) {
                    const i = this.children.indexOf(e);
                    if (i >= 0) this.children.splice(i, 1);
                  },
                },
              };
              this.proj = {
                fromLatLngToDivPixel(ll) {
                  return {
                    x: (ll.lng() - 10) * 1000,
                    y: (50 - ll.lat()) * 1000,
                  };
                },
              };
              this.onAdd?.();
              this.draw?.();
            } else {
              this.onRemove?.();
            }
          }
          getPanes() {
            return this.panes;
          }
          getProjection() {
            return this.proj;
          }
        },
        LatLng: class {
          constructor(lat, lng) {
            this._lat = lat;
            this._lng = lng;
          }
          lat() {
            return this._lat;
          }
          lng() {
            return this._lng;
          }
        },
      };
    }
    const ctx = load(
      ["map-interface.js", "geo-overlay-math.js", "google-maps-plugin.js"],
      {
        google: googleMaps ? { maps: googleMaps } : undefined,
        _createElCb: createElCb,
      },
    );
    const { GoogleMapsPlugin } = ctx.__exports;
    const plugin = new GoogleMapsPlugin();
    plugin.map = {};
    const firstOverlay = () => plugin.overlays.values().next().value;
    for (const step of steps) {
      const op = step[0];
      if (op === "setOverlay")
        plugin.setOverlay(
          step[1],
          step[2],
          step[3],
          null,
          step[4] ?? "glb-overlay",
        );
      else if (op === "updateOverlay") plugin.updateOverlay(step[1]);
      else if (op === "setOverlayOpacity") plugin.setOverlayOpacity(step[1]);
      else if (op === "removeOverlay")
        plugin.removeOverlay(step[1] ?? "glb-overlay");
      const layer = firstOverlay()?.getPanes?.()?.overlayLayer;
      snapshots.push({ len: layer?.children.length || 0, created });
    }
    const layer = firstOverlay()?.getPanes?.()?.overlayLayer;
    const children =
      layer?.children.map((img) => ({
        src: img.src,
        style: {
          width: img.style.width,
          height: img.style.height,
          transform: img.style.transform,
          opacity: img.style.opacity,
        },
      })) || [];
    const sameImg =
      snapshots.length <= 1 ||
      snapshots.every(
        (s) => s.len === snapshots[0].len && s.created === snapshots[0].created,
      );
    return {
      ok: true,
      hasOverlay: plugin.overlays.size > 0,
      overlayIds: [...plugin.overlays.keys()],
      layer: { children },
      sameImg,
      created,
      setMapCalls,
    };
  },
};

let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  try {
    const { scenario, args } = JSON.parse(input);
    const fn = scenarios[scenario];
    if (!fn) throw new Error(`Unknown scenario: ${scenario}`);
    const result = fn(args);
    console.log(JSON.stringify(result));
  } catch (e) {
    console.log(
      JSON.stringify({ ok: false, error: `${e.name}: ${e.message}` }),
    );
  }
});
