// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { r as o, j as n, c as Ye } from "./chunks/tokens-C2Ju3rc_.js";
import { P as Ve } from "./chunks/PageHeader-Dke5XNFH.js";
import {
  r as Y,
  u as ge,
  C as He,
  T as Ke,
} from "./chunks/ConfirmDialog-DanZpjzY.js";
import { L as Qe } from "./chunks/LegacyConfirmHost-VsPlnSjJ.js";
import {
  r as Xe,
  c as Ze,
  m as et,
  p as xe,
  O as tt,
  C as st,
  S as nt,
  a as it,
  b as rt,
  u as at,
  W as ot,
} from "./chunks/SensorCalibratePanel-6g-riw34.js";
import { B as je } from "./chunks/Button-CDF7QSMd.js";
import {
  c as Ne,
  s as ct,
  p as lt,
  C as dt,
  S as ut,
} from "./chunks/SceneManagePanel-wsgpQWOS.js";
import { A as J } from "./chunks/actionIcons-BIxtFbWH.js";
import { a as q, u as mt } from "./chunks/rest-CiiNoWNe.js";
import { p as ft } from "./chunks/djangoDelete-BfD_c0xv.js";
const qe = "ss-scene-tab:",
  pe = "ss-scene-tab",
  he = "ss-tab-counts";
function Oe(e) {
  typeof window > "u" ||
    window.dispatchEvent(new CustomEvent(he, { detail: e }));
}
const pt = {
  "cam-create": "cameras",
  "cam-edit": "cameras",
  "calibrate-cam": "cameras",
  "sensor-create": "sensors",
  "sensor-edit": "sensors",
  "calibrate-sensor": "sensors",
  "child-create": "children",
  "child-edit": "children",
};
function ce(e) {
  return (e && pt[e]) || null;
}
function ht(e, s = "cameras") {
  if (!e || typeof sessionStorage > "u") return s;
  try {
    const t = sessionStorage.getItem(qe + e);
    if (
      t === "cameras" ||
      t === "sensors" ||
      t === "regions" ||
      t === "tripwires" ||
      t === "children" ||
      t === "mqtt"
    )
      return t;
  } catch {}
  return s;
}
function wt(e, s) {
  if (!(!e || typeof sessionStorage > "u"))
    try {
      sessionStorage.setItem(qe + e, s);
    } catch {}
}
function le(e) {
  typeof window > "u" ||
    window.dispatchEvent(new CustomEvent(pe, { detail: { tabId: e } }));
}
const de = { host: "ss-map-host" };
function gt() {
  (window.dispatchEvent(new CustomEvent("ss-map-host-ready")),
    typeof window.fitSceneMapDisplay == "function" &&
      window.fitSceneMapDisplay());
}
let P = new Map(),
  F = new Map();
const we = new Set();
function O() {
  we.forEach((e) => {
    try {
      e();
    } catch {}
  });
}
function Se(e, s) {
  const t = document.getElementById(e);
  t && (t.value = s);
}
function bt(e) {
  return (
    we.add(e),
    () => {
      we.delete(e);
    }
  );
}
function Z() {
  return Array.from(P.values());
}
function ee() {
  return Array.from(F.values());
}
function be(e, s) {
  const t = P.get(e),
    i = {
      uuid: e,
      title: s.title ?? (t == null ? void 0 : t.title) ?? "",
      points: s.points ?? (t == null ? void 0 : t.points) ?? [],
      volumetric: s.volumetric ?? (t == null ? void 0 : t.volumetric) ?? !1,
      height: s.height ?? (t == null ? void 0 : t.height) ?? 1,
      buffer_size: s.buffer_size ?? (t == null ? void 0 : t.buffer_size) ?? 0,
      range_max: s.range_max ?? (t == null ? void 0 : t.range_max) ?? 10,
      sectors: s.sectors ??
        (t == null ? void 0 : t.sectors) ?? [
          { color: "green", color_min: 0 },
          { color: "yellow", color_min: 2 },
          { color: "red", color_min: 5 },
        ],
    };
  (P.set(e, i), H(), O());
}
function ae(e, s) {
  const t = F.get(e),
    i = {
      uuid: e,
      title: s.title ?? (t == null ? void 0 : t.title) ?? "",
      points: s.points ?? (t == null ? void 0 : t.points) ?? [],
    };
  (F.set(e, i), H(), O());
}
function yt(e) {
  (P.delete(e), H(), O());
}
function vt(e) {
  (F.delete(e), H(), O());
}
function xt(e, s) {
  if (!e || !s || e === s) return !1;
  const t = P.get(e);
  return t ? (P.delete(e), P.set(s, { ...t, uuid: s }), !0) : !1;
}
function jt(e, s) {
  if (!e || !s || e === s) return !1;
  const t = F.get(e);
  return t ? (F.delete(e), F.set(s, { ...t, uuid: s }), !0) : !1;
}
function Nt() {
  (H(), O());
}
function St(e, s) {
  const t = P.get(e);
  (t
    ? P.set(e, { ...t, points: s })
    : P.set(e, {
        uuid: e,
        title: "",
        points: s,
        volumetric: !1,
        height: 1,
        buffer_size: 0,
        range_max: 10,
        sectors: [
          { color: "green", color_min: 0 },
          { color: "yellow", color_min: 2 },
          { color: "red", color_min: 5 },
        ],
      }),
    H(),
    O());
}
function Et(e, s) {
  const t = F.get(e);
  (t
    ? F.set(e, { ...t, points: s })
    : F.set(e, { uuid: e, title: "", points: s }),
    H(),
    O());
}
function _t(e) {
  const s = new Set();
  for (const t of e) {
    const i = String(t.uuid || "").trim();
    if (!i) continue;
    s.add(i);
    const r = (t.points || []).map((a) => [Number(a[0]), Number(a[1])]);
    be(i, {
      title: t.title,
      points: r,
      volumetric: t.volumetric,
      height: t.height,
      buffer_size: t.buffer_size,
      range_max: t.range_max,
      sectors: t.sectors,
    });
  }
  for (const t of Array.from(P.keys())) s.has(t) || P.delete(t);
  (H(), O());
}
function Ct(e) {
  const s = new Set();
  for (const t of e) {
    const i = String(t.uuid || "").trim();
    if (!i) continue;
    s.add(i);
    const r = (t.points || []).map((a) => [Number(a[0]), Number(a[1])]);
    ae(i, { title: t.title, points: r });
  }
  for (const t of Array.from(F.keys())) s.has(t) || F.delete(t);
  (H(), O());
}
function H() {
  const e = Z().map((t) => ({
      title: t.title,
      uuid: t.uuid,
      points: t.points,
      volumetric: t.volumetric,
      height: t.height,
      buffer_size: t.buffer_size,
      range_max: t.range_max,
      sectors: t.sectors,
    })),
    s = ee().map((t) => ({ title: t.title, uuid: t.uuid, points: t.points }));
  (Se("id_rois", JSON.stringify(e)), Se("tripwires", JSON.stringify(s)));
}
const se = { top: 32, right: 72, bottom: 12, left: 72 };
function Mt(e, s) {
  const t = e + se.left + se.right,
    i = s + se.top + se.bottom;
  return `-72 -32 ${t} ${i}`;
}
const Rt = o.memo(function ({ href: s, width: t, height: i }) {
  return n.jsx("image", {
    href: s,
    x: 0,
    y: 0,
    width: t,
    height: i,
    preserveAspectRatio: "none",
  });
});
function Ee() {
  return `tmp${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
function It(e, s, t = 22) {
  const i = s[0] - e[0],
    r = s[1] - e[1],
    a = Math.hypot(i, r);
  if (a < 1) return null;
  const f = (-t * r) / a,
    p = (t * i) / a,
    c = (e[0] + s[0]) / 2,
    d = (e[1] + s[1]) / 2,
    h = c + f,
    N = d + p,
    v = f / t,
    j = p / t,
    S = -j,
    A = v,
    b = [
      `${h},${N}`,
      `${h - v * 8 + S * 4},${N - j * 8 + A * 4}`,
      `${h - v * 8 - S * 4},${N - j * 8 - A * 4}`,
    ].join(" ");
  return { arrow: { x1: c, y1: d, x2: h, y2: N }, head: b };
}
function Tt(e) {
  if (!e.length) return null;
  let s = 0,
    t = 0;
  return (
    e.forEach((i) => {
      ((s += i[0]), (t += i[1]));
    }),
    [s / e.length, t / e.length]
  );
}
const $t = o.memo(function ({ mapHref: s, mapWidth: t, mapHeight: i }) {
  const [r, a] = o.useState(() => Z()),
    [f, p] = o.useState(() => ee()),
    [c, d] = o.useState("idle"),
    [h, N] = o.useState([]),
    v = Xe(),
    j = i || Ze(i);
  (o.useEffect(
    () =>
      bt(() => {
        (a(Z()), p(ee()));
      }),
    [],
  ),
    o.useEffect(() => {
      const g = () => {
          (d("add-roi"), N([]));
        },
        y = () => {
          (d("add-trip"), N([]));
        };
      window.ssMapReact = { startAddRoi: g, startAddTripwire: y };
      const l = (_) => {
        const x = _.target;
        if (!x) return;
        const $ = x.closest(
          "#new-roi, #empty-new-roi, #new-tripwire, #empty-new-tripwire",
        );
        $ && (_.preventDefault(), $.id.includes("trip") ? y() : g());
      };
      return (
        document.addEventListener("click", l, !0),
        () => {
          (document.removeEventListener("click", l, !0),
            delete window.ssMapReact);
        }
      );
    }, []));
  const S = o.useCallback((g) => et(g[0], g[1], v, j), [v, j]),
    A = (g) => {
      if (c === "idle") return;
      const y = g.currentTarget,
        l = y.createSVGPoint();
      ((l.x = g.clientX), (l.y = g.clientY));
      const _ = y.getScreenCTM();
      if (!_) return;
      const x = l.matrixTransform(_.inverse()),
        $ = xe(x.x, x.y, v, j);
      if (c === "add-roi") {
        if (h.length >= 3) {
          const R = S(h[0]),
            u = x.x - R[0],
            E = x.y - R[1];
          if (Math.hypot(u, E) < 12) {
            const C = Ee();
            (be(C, {
              title: "",
              points: h,
              volumetric: !1,
              height: 1,
              buffer_size: 0,
              range_max: 10,
              sectors: [
                { color: "green", color_min: 0 },
                { color: "yellow", color_min: 2 },
                { color: "red", color_min: 5 },
              ],
            }),
              window.dispatchEvent(
                new CustomEvent("ss-roi-form-add", {
                  detail: { svgId: `roi_${C}`, uuid: C, title: "" },
                }),
              ),
              N([]),
              d("idle"));
            return;
          }
        }
        N((R) => [...R, $]);
        return;
      }
      if (c === "add-trip") {
        const R = [...h, $];
        if (R.length >= 2) {
          const u = Ee();
          (ae(u, { title: "", points: R.slice(0, 2) }),
            window.dispatchEvent(
              new CustomEvent("ss-tripwire-form-add", {
                detail: { svgId: `tripwire_${u}`, uuid: u, title: "" },
              }),
            ),
            N([]),
            d("idle"));
        } else N(R);
      }
    },
    b = (g, y, l, _) => {
      (_.stopPropagation(), _.preventDefault());
      const x = _.target.ownerSVGElement;
      if (!x) return;
      const $ = (u) => {
          const E = x.createSVGPoint();
          ((E.x = u.clientX), (E.y = u.clientY));
          const C = x.getScreenCTM();
          if (!C) return;
          const B = E.matrixTransform(C.inverse()),
            m = xe(B.x, B.y, v, j);
          if (g === "roi") {
            const w = Z().find((k) => k.uuid === y);
            if (!w) return;
            const L = w.points.map((k, I) => (I === l ? m : k));
            St(y, L);
          } else {
            const w = ee().find((k) => k.uuid === y);
            if (!w) return;
            const L = w.points.map((k, I) => (I === l ? m : k));
            Et(y, L);
          }
        },
        R = () => {
          (window.removeEventListener("mousemove", $),
            window.removeEventListener("mouseup", R));
        };
      (window.addEventListener("mousemove", $),
        window.addEventListener("mouseup", R));
    },
    M = o.useMemo(() => h.map(S), [h, S]);
  return n.jsxs("svg", {
    id: "svgout",
    className: `ss-react-scene-map${c !== "idle" ? ` is-${c}` : ""}`,
    viewBox: Mt(t, i),
    preserveAspectRatio: "xMidYMid meet",
    width: "100%",
    height: "100%",
    onClick: A,
    children: [
      n.jsx(Rt, { href: s, width: t, height: i }),
      r.map((g) => {
        const y = g.points.map(S),
          l = y.map((x) => x.join(",")).join(" "),
          _ = Tt(y);
        return n.jsxs(
          "g",
          {
            id: `roi_${g.uuid}`,
            className: "roi",
            children: [
              n.jsx("polygon", { points: l, className: "ss-react-roi-poly" }),
              g.title && _
                ? n.jsx("text", {
                    className: "ss-react-roi-title",
                    x: _[0],
                    y: _[1],
                    pointerEvents: "none",
                    children: g.title,
                  })
                : null,
              y.map((x, $) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: x[0],
                    cy: x[1],
                    r: 6,
                    onMouseDown: (R) => b("roi", g.uuid, $, R),
                  },
                  $,
                ),
              ),
            ],
          },
          g.uuid,
        );
      }),
      f.map((g) => {
        const y = g.points.map(S);
        if (y.length < 2) return null;
        const l = It(y[0], y[1]);
        return n.jsxs(
          "g",
          {
            id: `tripwire_${g.uuid}`,
            className: "tripwire",
            children: [
              n.jsx("line", {
                className: "tripline ss-react-trip-line",
                x1: y[0][0],
                y1: y[0][1],
                x2: y[1][0],
                y2: y[1][1],
              }),
              l
                ? n.jsxs("g", {
                    className: "ss-react-trip-dir",
                    pointerEvents: "none",
                    children: [
                      n.jsx("line", {
                        className: "ss-react-trip-arrow",
                        x1: l.arrow.x1,
                        y1: l.arrow.y1,
                        x2: l.arrow.x2,
                        y2: l.arrow.y2,
                      }),
                      n.jsx("polygon", {
                        className: "ss-react-trip-arrowhead",
                        points: l.head,
                      }),
                    ],
                  })
                : null,
              g.title
                ? n.jsx("text", {
                    className: "ss-react-trip-title",
                    x: (y[0][0] + y[1][0]) / 2,
                    y: (y[0][1] + y[1][1]) / 2 - 14,
                    pointerEvents: "none",
                    children: g.title,
                  })
                : null,
              y.map((_, x) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: _[0],
                    cy: _[1],
                    r: 6,
                    onMouseDown: ($) => b("trip", g.uuid, x, $),
                  },
                  x,
                ),
              ),
            ],
          },
          g.uuid,
        );
      }),
      M.length > 0
        ? n.jsxs("g", {
            className: "ss-react-draft",
            children: [
              c === "add-roi" && M.length >= 2
                ? n.jsx("polyline", {
                    points: M.map((g) => g.join(",")).join(" "),
                    className: "ss-react-draft-line",
                  })
                : null,
              M.map((g, y) =>
                n.jsx(
                  "circle",
                  { cx: g[0], cy: g[1], r: 5, className: "ss-react-draft-pt" },
                  y,
                ),
              ),
            ],
          })
        : null,
    ],
  });
});
function _e() {
  typeof window.fitSceneMapDisplay == "function" && window.fitSceneMapDisplay();
}
function Ce(e) {
  const s = e.querySelector("svg.ss-react-scene-map"),
    t = e.querySelector("svg.ss-snap-legacy, svg#svgout-snap");
  if (!s || !t) return;
  const i = s.getAttribute("viewBox"),
    r = s.getAttribute("preserveAspectRatio") || "xMidYMid meet";
  (i && t.setAttribute("viewBox", i),
    t.setAttribute("preserveAspectRatio", r),
    t.removeAttribute("width"),
    t.removeAttribute("height"),
    (t.style.width = "100%"),
    (t.style.height = "100%"));
}
const kt = o.memo(function ({
    mapUrl: s = null,
    mapWidth: t = 1280,
    mapHeight: i = 720,
    setupHelper: r = null,
  }) {
    const a = o.useRef(null),
      [f, p] = o.useState(!1),
      [c, d] = o.useState(null),
      h = !!window.ssUseReactMap && !!s;
    (o.useEffect(() => {
      if (!h || !s) {
        d(null);
        return;
      }
      let j = !1;
      const S = new Image();
      return (
        (S.onload = () => {
          !j &&
            S.naturalWidth > 0 &&
            S.naturalHeight > 0 &&
            d({ width: S.naturalWidth, height: S.naturalHeight });
        }),
        (S.src = s),
        () => {
          j = !0;
        }
      );
    }, [h, s]),
      o.useEffect(() => {
        const j = a.current,
          S = document.getElementById(de.host);
        if (!j || !S) return;
        if ((j.appendChild(S), (S.hidden = !1), h)) {
          document.body.classList.add("ss-use-react-map");
          const l = S.querySelector(
            "svg#svgout, svg.ss-snap-legacy, svg#svgout-snap",
          );
          l &&
            (l.classList.add("ss-snap-legacy"),
            l.id === "svgout" && (l.id = "svgout-snap"));
        }
        (gt(), p(!0));
        let A = 0,
          b = -1,
          M = -1;
        const g = () => {
          A ||
            (A = window.requestAnimationFrame(() => {
              A = 0;
              const l = Math.round(j.clientWidth),
                _ = Math.round(j.clientHeight);
              if (!(l === b && _ === M && b >= 0))
                if (((b = l), (M = _), !h)) _e();
                else {
                  const x = S.querySelector(".scene-map-stage");
                  (x && Ce(x), _e());
                }
            }));
        };
        window.addEventListener("resize", g);
        let y = null;
        return (
          typeof ResizeObserver < "u" &&
            ((y = new ResizeObserver(() => g())), y.observe(j)),
          g(),
          () => {
            (A && window.cancelAnimationFrame(A),
              window.removeEventListener("resize", g),
              y == null || y.disconnect(),
              document.body.classList.remove("ss-use-react-map"));
            const l = S.querySelector("svg#svgout-snap, svg.ss-snap-legacy");
            if (l && l.id === "svgout-snap") {
              const x = S.querySelector("svg.ss-react-scene-map");
              (!x || x.id !== "svgout") && (l.id = "svgout");
            }
            const _ = document.getElementById("ss-legacy-map-parking");
            _ && S.parentElement === j && (_.appendChild(S), (S.hidden = !0));
          }
        );
      }, [h]),
      o.useEffect(() => {
        if (!h || !f) return;
        const j = document.getElementById(de.host),
          S = j == null ? void 0 : j.querySelector(".scene-map-stage");
        S && Ce(S);
      }, [h, f, c]));
    const N = f ? document.getElementById(de.host) : null,
      v = (N == null ? void 0 : N.querySelector(".scene-map-stage")) ?? null;
    return n.jsxs("div", {
      className: "ss-scene-map-pane",
      children: [
        n.jsx("div", { ref: a, className: "ss-scene-map-slot" }),
        h && v && s && c
          ? Y.createPortal(
              n.jsx("div", {
                className: "ss-react-map-layer",
                children: n.jsx($t, {
                  mapHref: s,
                  mapWidth: c.width || t,
                  mapHeight: c.height || i,
                }),
              }),
              v,
            )
          : null,
        r,
      ],
    });
  }),
  Lt =
    "Start mapping with: docker compose --profile mapping up -d  (or make demo-all)";
function At({
  sceneId: e,
  authToken: s,
  cameraCount: t,
  setupReconstruct: i = !1,
  onMeshComplete: r,
}) {
  const a = ge(),
    [f, p] = o.useState("checking"),
    [c, d] = o.useState(!1),
    [h, N] = o.useState(!1),
    [v, j] = o.useState(null),
    S = o.useCallback(async () => {
      d(!0);
      const $ = await Ne(s);
      (p($ ? "available" : "unavailable"), d(!1));
    }, [s]);
  o.useEffect(() => {
    let $ = !1;
    const R = async () => {
      const E = await Ne(s);
      $ || p(E ? "available" : "unavailable");
    };
    R();
    const u = window.setInterval(() => {
      R();
    }, 15e3);
    return () => {
      (($ = !0), window.clearInterval(u));
    };
  }, [s]);
  const A = async () => {
      (N(!0), j(null));
      try {
        const $ = await ct(e);
        (a.show("Mesh generation started…", "info"),
          await lt(e, $),
          a.show("Mesh generated — map and cameras updated", "ok"),
          r == null || r());
      } catch ($) {
        const R = $ instanceof Error ? $.message : "Mesh generation failed";
        (j(R), a.show(R, "bad"));
      } finally {
        N(!1);
      }
    },
    b = i,
    M = f === "available",
    g = f === "unavailable",
    y = t >= 1;
  let l = "Scene map required",
    _ =
      "This scene has no map yet. Provide a floor plan or geospatial basemap, or reconstruct from cameras when mapping is available.",
    x = null;
  return (
    y && g
      ? ((l = b ? "Finish setup — tracking is blocked" : "Tracking is blocked"),
        (_ =
          "Cameras are connected, but this scene has no map and the mapping service is not available. Tracking needs a map and calibrated cameras. Upload or position a geospatial map (then calibrate manually), or start the mapping service and generate a mesh to create the map and calibrate automatically."),
        (x = n.jsxs(n.Fragment, {
          children: [
            n.jsx("a", {
              className: "ss-btn ss-btn--primary",
              href: "?ss=scene-manage&map=map_upload",
              children: "Upload a map",
            }),
            n.jsx("a", {
              className: "ss-btn ss-btn--secondary",
              href: "?ss=scene-manage&map=geospatial_map",
              children: "Use geospatial map",
            }),
          ],
        })))
      : y && M
        ? ((l = b ? "Finish setup — generate mesh" : "Ready to generate map"),
          (_ =
            "Cameras are connected and the mapping service is available. Generate a mesh to create the scene map and auto-calibrate cameras. Tracking cannot run until this completes (or you upload a map and calibrate manually)."),
          (x = n.jsxs(n.Fragment, {
            children: [
              n.jsx(je, {
                type: "button",
                variant: "primary",
                id: "generate_mesh",
                disabled: h,
                onClick: () => void A(),
                children: h ? "Generating…" : "Generate Mesh",
              }),
              n.jsx("a", {
                className: "ss-btn ss-btn--secondary",
                href: "?ss=scene-manage&map=map_upload",
                children: "Upload a map instead",
              }),
            ],
          })))
        : !y && M
          ? ((l = b
              ? "Finish setup — add cameras"
              : "Add cameras to reconstruct"),
            (_ =
              "This scene has no map. Add cameras that cover the space, then generate a mesh to create the map and calibrate. You can also upload a floor plan or use a geospatial basemap."),
            (x = n.jsxs(n.Fragment, {
              children: [
                n.jsx("a", {
                  className: "ss-btn ss-btn--primary",
                  href: "?ss=cam-create",
                  children: "+ New Camera",
                }),
                n.jsx("a", {
                  className: "ss-btn ss-btn--secondary",
                  href: "?ss=scene-manage&map=map_upload",
                  children: "Upload a map",
                }),
                n.jsx("a", {
                  className: "ss-btn ss-btn--secondary",
                  href: "?ss=scene-manage&map=geospatial_map",
                  children: "Geospatial map",
                }),
              ],
            })))
          : !y &&
            g &&
            ((l = "Provide a scene map"),
            (_ =
              "This scene has no map, and the mapping service is not running. Upload a floor plan or geospatial basemap to enable calibration and tracking, or start mapping if you plan to reconstruct from cameras."),
            (x = n.jsxs(n.Fragment, {
              children: [
                n.jsx("a", {
                  className: "ss-btn ss-btn--primary",
                  href: "?ss=scene-manage&map=map_upload",
                  children: "Upload a map",
                }),
                n.jsx("a", {
                  className: "ss-btn ss-btn--secondary",
                  href: "?ss=scene-manage&map=geospatial_map",
                  children: "Use geospatial map",
                }),
              ],
            }))),
    n.jsx("div", {
      className: "ss-map-setup-helper",
      role: "region",
      "aria-label": "Scene map setup",
      "data-mapping": f,
      "data-cameras": t,
      children: n.jsxs("div", {
        className: "ss-map-setup-helper-card ss-empty-state",
        children: [
          n.jsx("h3", { className: "ss-map-setup-helper-title", children: l }),
          n.jsx("p", { className: "ss-map-setup-helper-body", children: _ }),
          v
            ? n.jsx("p", {
                className: "ss-map-setup-helper-error",
                children: v,
              })
            : null,
          n.jsx("div", {
            className: "ss-map-setup-helper-actions",
            children: x,
          }),
          g
            ? n.jsxs("div", {
                className: "ss-map-setup-helper-secondary",
                children: [
                  n.jsx("p", {
                    className: "ss-map-setup-helper-hint",
                    children: Lt,
                  }),
                  n.jsx(je, {
                    type: "button",
                    variant: "secondary",
                    disabled: c || h,
                    onClick: () => void S(),
                    children: c ? "Checking…" : "Check again",
                  }),
                ],
              })
            : null,
          f === "checking"
            ? n.jsx("p", {
                className: "ss-map-setup-helper-hint",
                children: "Checking mapping service…",
              })
            : null,
        ],
      }),
    })
  );
}
const ze = "ss-camera-strip-fit";
function Bt() {
  try {
    const e = window.localStorage.getItem(ze);
    if (e === "cover" || e === "contain") return e;
  } catch {}
  return "contain";
}
function Dt(e) {
  try {
    window.localStorage.setItem(ze, e);
  } catch {}
}
function Ge(e) {
  if (!e || e.classList.contains("display-none")) return !1;
  const s = e.currentSrc || e.getAttribute("src") || "";
  return !s || s.includes("offline.png")
    ? !1
    : e.naturalWidth > 0 || s.startsWith("data:image");
}
function ue(e) {
  const s = e.querySelector(
      "img[data-ss-card-sensor], img[id^='card-preview-']",
    ),
    t = e.querySelector(".cam-offline"),
    i = e.querySelector(".rate"),
    r = Ge(s);
  !r &&
    i &&
    ((i.textContent || "").trim() !== "--" && (i.textContent = "--"),
    i.classList.add("telemetry-hide"));
  const a = ((i == null ? void 0 : i.textContent) || "").trim(),
    f = r ? "1" : "0";
  (e.dataset.ssOnline !== f &&
    ((e.dataset.ssOnline = f),
    e.classList.toggle("is-online", r),
    e.classList.toggle("is-offline", !r)),
    e.dataset.ssRate !== (a || "--") && (e.dataset.ssRate = a || "--"));
  let p = e.querySelector(".ss-camera-strip-badge");
  p ||
    ((p = document.createElement("span")),
    (p.className = "ss-camera-strip-badge"),
    p.setAttribute("aria-hidden", "true"),
    (e.querySelector(".card-header") || e).appendChild(p));
  const c = r ? "Live" : "Offline";
  (p.textContent !== c && (p.textContent = c),
    p.classList.toggle("is-online", r),
    p.classList.toggle("is-offline", !r),
    t && t.hidden !== r && (t.hidden = r));
}
function Pt({ rates: e = {} }) {
  const [s, t] = o.useState(() => (typeof window < "u" ? Bt() : "contain"));
  return (
    o.useEffect(() => {
      const i = document.documentElement;
      ((i.dataset.ssCameraFit = s), Dt(s));
      const r = document.getElementById("cameras");
      r && ((r.dataset.ssCameraFit = s), r.classList.add("ss-camera-strip"));
    }, [s]),
    o.useEffect(() => {
      Object.entries(e).forEach(([i, r]) => {
        var c;
        const a =
            (c = document.querySelector(
              `[data-ss-card-sensor="${CSS.escape(i)}"]`,
            )) == null
              ? void 0
              : c.closest(".camera-card"),
          f =
            a == null
              ? void 0
              : a.querySelector(
                  "img[data-ss-card-sensor], img[id^='card-preview-']",
                ),
          p = document.getElementById(`rate-${i}`);
        if (!Ge(f)) {
          (p &&
            ((p.textContent || "").trim() !== "--" && (p.textContent = "--"),
            p.classList.add("telemetry-hide")),
            a && ue(a));
          return;
        }
        (p &&
          p.textContent !== r &&
          ((p.textContent = r), p.classList.remove("telemetry-hide")),
          a && ue(a));
      });
    }, [e]),
    o.useEffect(() => {
      const i = document.getElementById("cameras");
      if (!i) return;
      i.classList.add("ss-camera-strip");
      let r = 0,
        a = !1;
      const f = () => {
          if (!a) {
            a = !0;
            try {
              i.querySelectorAll(".camera-card").forEach(ue);
            } finally {
              a = !1;
            }
          }
        },
        p = () => {
          r ||
            (r = window.requestAnimationFrame(() => {
              ((r = 0), f());
            }));
        };
      f();
      const c = new MutationObserver(p);
      c.observe(i, {
        subtree: !0,
        childList: !0,
        attributes: !0,
        attributeFilter: ["class", "src"],
      });
      const d = window.setInterval(f, 2e3);
      return () => {
        (c.disconnect(),
          window.clearInterval(d),
          r && window.cancelAnimationFrame(r));
      };
    }, []),
    n.jsxs("div", {
      className: "ss-camera-strip-controls",
      role: "group",
      "aria-label": "Camera thumbnail fit",
      children: [
        n.jsx("button", {
          type: "button",
          className: `ss-camera-strip-fit${s === "contain" ? " is-active" : ""}`,
          "aria-pressed": s === "contain",
          title: "Fit entire frame (contain)",
          onClick: () => t("contain"),
          children: "Contain",
        }),
        n.jsx("button", {
          type: "button",
          className: `ss-camera-strip-fit${s === "cover" ? " is-active" : ""}`,
          "aria-pressed": s === "cover",
          title: "Fill card (cover)",
          onClick: () => t("cover"),
          children: "Cover",
        }),
      ],
    })
  );
}
async function ye(e) {
  var t, i;
  const s = e.trim();
  if (!s) return !1;
  try {
    return (
      await navigator.clipboard.writeText(s),
      (t = window.ssToast) == null || t.show("Copied to clipboard", "ok"),
      !0
    );
  } catch {
    return (
      (i = window.ssToast) == null ||
        i.show("Could not copy to clipboard", "bad"),
      !1
    );
  }
}
function Ft({ cameras: e, isSuperuser: s }) {
  return (
    o.useEffect(() => {
      const t = () => {
        var a;
        return (a = window.ssRefreshCameraSnapshots) == null
          ? void 0
          : a.call(window);
      };
      t();
      const i = window.setTimeout(t, 400),
        r = window.setTimeout(t, 1200);
      return () => {
        (window.clearTimeout(i), window.clearTimeout(r));
      };
    }, [e]),
    e.length === 0
      ? n.jsxs("div", {
          className: "ss-empty-state",
          children: [
            n.jsx("p", { children: "No cameras in this scene yet." }),
            s
              ? n.jsx("a", {
                  className: "btn btn-primary btn-sm",
                  href: "?ss=cam-create",
                  children: "+ New Camera",
                })
              : null,
          ],
        })
      : n.jsx(n.Fragment, {
          children: e.map((t) =>
            n.jsxs(
              "div",
              {
                className: "card count-item camera-card",
                children: [
                  n.jsxs("h6", {
                    className: "card-header",
                    children: [
                      n.jsx("span", {
                        className: "rate telemetry-hide",
                        id: `rate-${t.sensorId}`,
                        children: "--",
                      }),
                      t.name,
                    ],
                  }),
                  n.jsx("div", {
                    className: "card-image",
                    children: n.jsxs("a", {
                      className: "snapshot-image",
                      href: s ? t.calibrateHref : void 0,
                      id: `cam_calibrate_${t.id}`,
                      "data-topic": t.cmdTopic,
                      "data-topic-name": `scenescape/cmd/camera/${t.name}`,
                      children: [
                        n.jsx("div", {
                          className: "cam-offline",
                          children: "Camera Offline",
                        }),
                        n.jsx("img", {
                          id: `card-preview-${t.sensorId}`,
                          className: "display-none",
                          alt: `${t.name} View`,
                          "data-ss-card-sensor": t.sensorId,
                          "data-ss-card-name": t.name,
                        }),
                      ],
                    }),
                  }),
                  n.jsx("div", {
                    className: "card-body hide-live",
                    children: s
                      ? n.jsxs("div", {
                          className: "text-right ss-entity-actions",
                          children: [
                            n.jsx("a", {
                              className: "ss-icon-btn",
                              href: t.calibrateHref,
                              title: `Configure ${t.name}`,
                              "aria-label": `Configure ${t.name}`,
                              children: n.jsx("i", {
                                className: `bi ${J.configure}`,
                                "aria-hidden": "true",
                              }),
                            }),
                            t.deleteUrl
                              ? n.jsx("a", {
                                  className: "ss-icon-btn ss-icon-btn--danger",
                                  href: t.deleteUrl,
                                  title: `Delete ${t.name}`,
                                  "aria-label": `Delete ${t.name}`,
                                  children: n.jsx("i", {
                                    className: `bi ${J.delete}`,
                                    "aria-hidden": "true",
                                  }),
                                })
                              : null,
                          ],
                        })
                      : null,
                  }),
                ],
              },
              t.id,
            ),
          ),
        })
  );
}
function Ut({ sensors: e, isSuperuser: s, onDelete: t }) {
  return (
    o.useEffect(() => {
      var i;
      (i = window.ssDrawSingletonSensors) == null || i.call(window);
    }, [e]),
    e.length === 0
      ? n.jsxs("div", {
          className: "ss-empty-state",
          children: [
            n.jsx("p", { children: "No sensors in this scene yet." }),
            s
              ? n.jsx("a", {
                  className: "btn btn-primary btn-sm",
                  href: "?ss=sensor-create",
                  children: "+ New Sensor",
                })
              : null,
          ],
        })
      : n.jsx("div", {
          className: "ss-tab-list",
          children: e.map((i) =>
            n.jsxs(
              "div",
              {
                className: "ss-tab-row singleton count-item",
                "data-sensor-name": i.name,
                children: [
                  i.iconUrl
                    ? n.jsx("img", {
                        className: "sensor-icon ss-tab-row__icon",
                        width: 20,
                        height: 20,
                        src: i.iconUrl,
                        alt: "",
                      })
                    : n.jsx("span", {
                        className: "ss-tab-row__icon ss-tab-row__icon--empty",
                        "aria-hidden": "true",
                      }),
                  n.jsxs("div", {
                    className: "ss-tab-row__main",
                    children: [
                      n.jsx("span", {
                        className: "ss-tab-row__title",
                        children: i.name,
                      }),
                      n.jsx("button", {
                        type: "button",
                        className:
                          "ss-tab-row__meta sensor-id ss-tab-row__copy-id",
                        title: "Click to copy ID",
                        onClick: () => void ye(i.sensorId),
                        children: i.sensorId,
                      }),
                    ],
                  }),
                  n.jsx("input", {
                    type: "hidden",
                    className: "area-json",
                    value: i.areaJson,
                    readOnly: !0,
                  }),
                  s
                    ? n.jsxs("div", {
                        className: "ss-tab-row__actions ss-entity-actions",
                        children: [
                          n.jsx("a", {
                            className: "ss-icon-btn sensor_calibrate",
                            href: i.calibrateHref,
                            id: `sensor_calibrate_${i.id}`,
                            title: `Configure ${i.name}`,
                            "aria-label": `Configure ${i.name}`,
                            children: n.jsx("i", {
                              className: `bi ${J.configure}`,
                              "aria-hidden": "true",
                            }),
                          }),
                          t
                            ? n.jsx("button", {
                                type: "button",
                                className: "ss-icon-btn ss-icon-btn--danger",
                                title: `Delete ${i.name}`,
                                "aria-label": `Delete ${i.name}`,
                                onClick: () => t(i),
                                children: n.jsx("i", {
                                  className: `bi ${J.delete}`,
                                  "aria-hidden": "true",
                                }),
                              })
                            : i.deleteUrl
                              ? n.jsx("a", {
                                  className: "ss-icon-btn ss-icon-btn--danger",
                                  href: i.deleteUrl,
                                  title: `Delete ${i.name}`,
                                  "aria-label": `Delete ${i.name}`,
                                  children: n.jsx("i", {
                                    className: `bi ${J.delete}`,
                                    "aria-hidden": "true",
                                  }),
                                })
                              : null,
                        ],
                      })
                    : null,
                ],
              },
              i.id,
            ),
          ),
        })
  );
}
function Ht({ childrenLinks: e, isSuperuser: s }) {
  return e.length === 0
    ? n.jsxs("div", {
        className: "ss-empty-state",
        children: [
          n.jsx("p", { children: "No child scenes linked yet." }),
          s
            ? n.jsx("a", {
                className: "btn btn-primary btn-sm",
                href: "?ss=child-create",
                children: "+ Link Child",
              })
            : null,
        ],
      })
    : n.jsx(n.Fragment, {
        children: e.map((t) => {
          const i = t.thumbnailUrl || t.mapUrl,
            r = i
              ? n.jsx("img", { src: i, alt: `${t.name} map` })
              : n.jsx("div", {
                  className: "blank-container border",
                  "aria-hidden": "true",
                });
          return n.jsxs(
            "div",
            {
              className: "card count-item camera-card child-card",
              children: [
                n.jsxs("h6", {
                  className: "card-header",
                  children: [
                    t.childType === "remote" && t.remoteChildId
                      ? n.jsx("span", {
                          id: `mqtt_status_remote_${t.remoteChildId}`,
                          className: "child_mqtt_status btn-sm btn",
                          children: n.jsx("i", {
                            className: "bi bi-arrow-down-up",
                            "aria-hidden": "true",
                          }),
                        })
                      : null,
                    t.childType === "remote"
                      ? n.jsx("span", {
                          className: "ss-child-card-badge",
                          children: "Remote",
                        })
                      : null,
                    t.name,
                  ],
                }),
                n.jsx("div", {
                  className: "card-image",
                  children: t.detailUrl
                    ? n.jsx("a", {
                        href: t.detailUrl,
                        title: `Open ${t.name}`,
                        children: r,
                      })
                    : r,
                }),
                n.jsx("div", {
                  className: "card-body",
                  children: s
                    ? n.jsxs("div", {
                        className: "text-right ss-entity-actions",
                        children: [
                          n.jsx("a", {
                            className: "ss-icon-btn",
                            href: t.editHref,
                            title: `Configure ${t.name}`,
                            "aria-label": `Configure ${t.name}`,
                            id: `child-update-${t.name}`,
                            children: n.jsx("i", {
                              className: `bi ${J.configure}`,
                              "aria-hidden": "true",
                            }),
                          }),
                          t.deleteUrl
                            ? n.jsx("a", {
                                className: "ss-icon-btn ss-icon-btn--danger",
                                href: t.deleteUrl,
                                title: `Delete ${t.name}`,
                                "aria-label": `Delete ${t.name}`,
                                id: `child-delete-${t.name}`,
                                children: n.jsx("i", {
                                  className: `bi ${J.delete}`,
                                  "aria-hidden": "true",
                                }),
                              })
                            : null,
                        ],
                      })
                    : null,
                }),
              ],
            },
            t.id,
          );
        }),
      });
}
function qt({
  cameras: e,
  sensors: s,
  childrenLinks: t,
  isSuperuser: i,
  panelsReady: r,
  authToken: a = "",
  onSensorsChange: f,
}) {
  const p = ge(),
    [c, d] = o.useState(null),
    [h, N] = o.useState(!1),
    [v, j] = o.useState(null);
  o.useEffect(() => {
    var l;
    r &&
      (Oe({ cameras: e.length, sensors: s.length, children: t.length }),
      (l = window.numberTabs) == null || l.call(window));
  }, [r, e, s, t]);
  const S = o.useCallback(async () => {
      var l;
      if (!(!c || !a || !f)) {
        (N(!0), j(null));
        try {
          (await q.deleteSensor(a, c.sensorId),
            (l = window.ssRemoveSingletonSensor) == null ||
              l.call(window, c.sensorId),
            f((_) =>
              _.filter((x) => x.id !== c.id && x.sensorId !== c.sensorId),
            ),
            p.show("Sensor deleted", "ok"),
            d(null));
        } catch (_) {
          j(_.message || "Delete failed");
        } finally {
          N(!1);
        }
      }
    }, [a, f, c, p]),
    A = o.useCallback((l) => {
      (j(null), d(l));
    }, []);
  if (!r) return null;
  const b = document.getElementById("ss-cameras-mount"),
    M = document.getElementById("ss-sensors-mount"),
    g = document.getElementById("ss-children-mount"),
    y = !!(a && f);
  return n.jsxs(n.Fragment, {
    children: [
      b ? Y.createPortal(n.jsx(Ft, { cameras: e, isSuperuser: i }), b) : null,
      M
        ? Y.createPortal(
            n.jsx(Ut, { sensors: s, isSuperuser: i, onDelete: y ? A : void 0 }),
            M,
          )
        : null,
      g
        ? Y.createPortal(n.jsx(Ht, { childrenLinks: t, isSuperuser: i }), g)
        : null,
      n.jsxs(He, {
        open: !!c,
        title: "Delete sensor?",
        confirmLabel: "Delete",
        danger: !0,
        busy: h,
        onConfirm: S,
        onCancel: () => {
          h || (d(null), j(null));
        },
        children: [
          n.jsxs("p", {
            children: [
              "Are you sure you want to delete",
              " ",
              n.jsx("strong", {
                children: (c == null ? void 0 : c.name) || "this sensor",
              }),
              "?",
            ],
          }),
          n.jsx("p", { children: "This action cannot be undone." }),
          v ? n.jsx("p", { className: "ss-confirm-error", children: v }) : null,
        ],
      }),
    ],
  });
}
function Ot({ wssConnection: e, sceneId: s, panelsReady: t }) {
  return (
    o.useEffect(() => {
      var a;
      if (!t) return;
      const i = document.getElementById("broker"),
        r = document.getElementById("topic");
      (i && e && !i.value && (i.value = e),
        r && s && !r.value && (r.value = `scenescape/regulated/scene/${s}`),
        (a = window.ssEnsureMqttScene) == null || a.call(window));
    }, [t, e, s]),
    null
  );
}
function zt({ id: e, title: s, children: t, footer: i, onClose: r }) {
  return n.jsx("div", {
    className: "modal fade ss-modal",
    id: e,
    tabIndex: -1,
    role: "dialog",
    "aria-labelledby": `${e}-title`,
    "aria-hidden": "true",
    children: n.jsx("div", {
      className: "modal-dialog modal-dialog-centered",
      role: "document",
      children: n.jsxs("div", {
        className: "modal-content",
        children: [
          n.jsxs("div", {
            className: "modal-header",
            children: [
              n.jsx("h5", {
                className: "modal-title",
                id: `${e}-title`,
                children: s,
              }),
              n.jsx("button", {
                type: "button",
                className: "close",
                "data-dismiss": "modal",
                "aria-label": "Close",
                onClick: r,
                children: n.jsx("span", {
                  "aria-hidden": "true",
                  children: "×",
                }),
              }),
            ],
          }),
          n.jsx("div", { className: "modal-body", children: t }),
          i ? n.jsx("div", { className: "modal-footer", children: i }) : null,
        ],
      }),
    }),
  });
}
const Gt = [
  {
    id: "cameraHelpModal",
    title: "Camera Help",
    items: [
      "All cameras and sensors must be associated with a scene.",
      "Use Configure to calibrate camera pose against the scene map.",
      "Live View requests fresh snapshots over MQTT while enabled.",
    ],
  },
  {
    id: "sensorHelpModal",
    title: "Sensor Help",
    items: [
      "Generic sensors report scalar or area occupancy on the map.",
      "Use Configure to place and size the sensor coverage area.",
    ],
  },
  {
    id: "roiHelpModal",
    title: "Region Help",
    items: [
      "Draw a region on the map, then set thresholds and topic.",
      "Save writes all regions for this scene in one submit.",
      "Occupancy coloring uses the configured sector thresholds.",
    ],
  },
  {
    id: "tripwireHelpModal",
    title: "Tripwire Help",
    items: [
      "Draw a tripwire line on the map between two endpoints.",
      "The green flag points toward +1 crossings.",
      "Name the tripwire in the side panel, then Save.",
      "Save writes all tripwires for this scene in one submit.",
      "Crossing events publish on the configured MQTT topic.",
    ],
  },
  {
    id: "childrenHelpModal",
    title: "Children Help",
    items: [
      "Child scenes aggregate detections into this parent scene.",
      "A scene may have any number of children but only one parent.",
      "The child scene must already exist before creating the link.",
    ],
  },
];
function Wt() {
  return n.jsx(n.Fragment, {
    children: Gt.map((e) =>
      n.jsx(
        zt,
        {
          id: e.id,
          title: e.title,
          children: n.jsx("ul", {
            children: e.items.map((s) => n.jsx("li", { children: s }, s)),
          }),
        },
        e.id,
      ),
    ),
  });
}
function Me(e) {
  var s;
  (e.preventDefault(),
    e.stopPropagation(),
    (s = window.ssPersistGeometry) == null || s.call(window));
}
function K({ id: e, modalId: s, title: t }) {
  return n.jsx("button", {
    type: "button",
    className: "scene-detail-help",
    id: e,
    "data-toggle": "modal",
    "data-target": `#${s}`,
    title: t,
    "aria-label": t,
    children: n.jsx("i", {
      className: "bi bi-question-circle",
      "aria-hidden": "true",
    }),
  });
}
function Re({ id: e, labelId: s, label: t, title: i }) {
  return n.jsxs("div", {
    className: "custom-control custom-switch switch scene-detail-live-toggle",
    children: [
      n.jsx("input", {
        type: "checkbox",
        className: "custom-control-input",
        id: e,
        "aria-labelledby": s,
      }),
      n.jsx("label", {
        className: "custom-control-label",
        htmlFor: e,
        title: i,
        id: s,
        children: t,
      }),
    ],
  });
}
function Jt({ activeTab: e, isSuperuser: s }) {
  const [t, i] = o.useState(() => !!window.ssRoiDirty),
    [r, a] = o.useState(() => !!window.ssTripDirty);
  return (
    o.useEffect(() => {
      const f = (c) => {
          i(!!c.detail);
        },
        p = (c) => {
          a(!!c.detail);
        };
      return (
        window.addEventListener("ss-roi-dirty", f),
        window.addEventListener("ss-trip-dirty", p),
        i(!!window.ssRoiDirty),
        a(!!window.ssTripDirty),
        () => {
          (window.removeEventListener("ss-roi-dirty", f),
            window.removeEventListener("ss-trip-dirty", p));
        }
      );
    }, []),
    n.jsxs("div", {
      className: "ss-tab-toolbar-inner",
      "data-active-tab": e,
      children: [
        e === "cameras"
          ? n.jsxs(n.Fragment, {
              children: [
                n.jsx(K, {
                  id: "camera-help",
                  modalId: "cameraHelpModal",
                  title: "How cameras work in this scene",
                }),
                n.jsx(Re, {
                  id: "live-view",
                  labelId: "live-view-label",
                  label: "Live View",
                  title: "Toggle Live View",
                }),
                n.jsx(Re, {
                  id: "show-telemetry",
                  labelId: "show-telemetry-label",
                  label: "Show Telemetry",
                  title: "Toggle Show Telemetry",
                }),
                s
                  ? n.jsx("a", {
                      className: "btn btn-primary btn-sm",
                      id: "new-camera",
                      title: "Add a new camera",
                      href: "?ss=cam-create",
                      children: "+ New Camera",
                    })
                  : null,
              ],
            })
          : null,
        e === "sensors"
          ? n.jsxs(n.Fragment, {
              children: [
                n.jsx(K, {
                  id: "sensor-help",
                  modalId: "sensorHelpModal",
                  title: "How sensors work in this scene",
                }),
                s
                  ? n.jsx("a", {
                      className: "btn btn-primary btn-sm",
                      id: "new-sensor",
                      title: "Add a new sensor",
                      href: "?ss=sensor-create",
                      children: "+ New Sensor",
                    })
                  : null,
              ],
            })
          : null,
        e === "regions"
          ? n.jsxs(n.Fragment, {
              children: [
                n.jsx(K, {
                  id: "roi-help",
                  modalId: "roiHelpModal",
                  title: "How regions of interest work",
                }),
                s
                  ? n.jsxs(n.Fragment, {
                      children: [
                        n.jsx("button", {
                          type: "button",
                          className: "btn btn-primary btn-sm",
                          id: "new-roi",
                          title: "Create a new region",
                          children: "+ New Region",
                        }),
                        n.jsx("button", {
                          type: "button",
                          className: `btn btn-sm btn-primary${t ? " ss-save-dirty" : " ss-save-clean"}`,
                          id: "save-rois",
                          title: t
                            ? "Save unsaved changes"
                            : "No unsaved changes",
                          disabled: !t,
                          "aria-disabled": t ? "false" : "true",
                          onClick: Me,
                          children: "Save",
                        }),
                      ],
                    })
                  : null,
              ],
            })
          : null,
        e === "tripwires"
          ? n.jsxs(n.Fragment, {
              children: [
                n.jsx(K, {
                  id: "tripwire-help",
                  modalId: "tripwireHelpModal",
                  title: "How tripwires work",
                }),
                s
                  ? n.jsxs(n.Fragment, {
                      children: [
                        n.jsx("button", {
                          type: "button",
                          className: "btn btn-primary btn-sm",
                          id: "new-tripwire",
                          title: "Create a new tripwire",
                          children: "+ New Tripwire",
                        }),
                        n.jsx("button", {
                          type: "button",
                          className: `btn btn-sm btn-primary${r ? " ss-save-dirty" : " ss-save-clean"}`,
                          id: "save-trips",
                          title: r
                            ? "Save unsaved changes"
                            : "No unsaved changes",
                          disabled: !r,
                          "aria-disabled": r ? "false" : "true",
                          onClick: Me,
                          children: "Save",
                        }),
                      ],
                    })
                  : null,
              ],
            })
          : null,
        e === "children"
          ? n.jsxs(n.Fragment, {
              children: [
                n.jsx(K, {
                  id: "children-help",
                  modalId: "childrenHelpModal",
                  title: "How child scenes work",
                }),
                s
                  ? n.jsx("a", {
                      className: "btn btn-primary btn-sm",
                      id: "new-child",
                      title: "Add a new child scene",
                      href: "?ss=child-create",
                      children: "+ Link Child",
                    })
                  : null,
              ],
            })
          : null,
      ],
    })
  );
}
const Ie = {
    cameras: "cameras",
    sensors: "sensors",
    regions: "regions",
    tripwires: "trips",
    children: "children",
    mqtt: "mqtt",
  },
  Yt = {
    cameras: "cameras-tab",
    sensors: "sensors-tab",
    regions: "regions-tab",
    tripwires: "tripwires-tab",
    children: "children-tab",
    mqtt: "settings-tab",
  };
function Vt({
  tabs: e,
  cameraRates: s = {},
  cameras: t = [],
  sensors: i = [],
  childrenLinks: r = [],
  isSuperuser: a = !1,
  sceneId: f = "",
  wssConnection: p = "",
  authToken: c = "",
  onSensorsChange: d,
}) {
  const [h, N] = o.useState(() => ht(f)),
    [v, j] = o.useState(!1),
    S = o.useRef(null);
  (o.useEffect(() => {
    const b = S.current,
      M = document.getElementById("scene-detail-panels");
    if (!(!b || !M))
      return (
        b.appendChild(M),
        (M.hidden = !1),
        M.classList.add("ss-legacy-panels-adopted"),
        j(!0),
        () => {
          j(!1);
          const g = document.getElementById("ss-legacy-panels-parking");
          g && M.parentElement === b && (g.appendChild(M), (M.hidden = !0));
        }
      );
  }, []),
    o.useEffect(() => {
      Object.entries(Ie).forEach(([b, M]) => {
        const g = document.getElementById(M);
        if (!g) return;
        const y = b === h;
        (g.classList.toggle("show", y), g.classList.toggle("active", y));
      });
    }, [h]),
    o.useEffect(() => {
      wt(f, h);
    }, [f, h]),
    o.useEffect(() => {
      const b = (M) => {
        const g = M.detail,
          y = g == null ? void 0 : g.tabId;
        (y === "cameras" ||
          y === "sensors" ||
          y === "regions" ||
          y === "tripwires" ||
          y === "children" ||
          y === "mqtt") &&
          N(y);
      };
      return (
        window.addEventListener(pe, b),
        () => window.removeEventListener(pe, b)
      );
    }, []));
  const A = (b) => {
    (b === "cameras" ||
      b === "sensors" ||
      b === "regions" ||
      b === "tripwires" ||
      b === "children" ||
      b === "mqtt") &&
      N(b);
  };
  return n.jsxs("aside", {
    className: "ss-scene-side hide-fullscreen",
    children: [
      n.jsxs("div", {
        className: "ss-tabs",
        children: [
          n.jsxs("div", {
            className: "ss-tabs-chrome",
            children: [
              n.jsx("div", {
                className: "ss-tabs-list",
                role: "tablist",
                id: "myTab",
                children: e.map((b) => {
                  const M = b.id === h,
                    g = Yt[b.id] || `ss-tab-${b.id}`;
                  return n.jsxs(
                    "button",
                    {
                      type: "button",
                      role: "tab",
                      id: g,
                      "aria-selected": M,
                      "aria-controls": Ie[b.id] || b.id,
                      className: `ss-tabs-tab${M ? " is-active" : ""}`,
                      onClick: () => A(b.id),
                      children: [
                        n.jsx("span", {
                          className: "ss-tabs-label",
                          children: b.label,
                        }),
                        b.count !== void 0 && b.count !== null
                          ? n.jsx("span", {
                              className: "ss-tabs-count",
                              children: b.count,
                            })
                          : null,
                        b.extra,
                      ],
                    },
                    b.id,
                  );
                }),
              }),
              n.jsx("div", {
                className: "ss-tabs-toolbar",
                "data-active-tab": h,
                children: n.jsx(Jt, { activeTab: h, isSuperuser: a }),
              }),
              h === "cameras" ? n.jsx(Pt, { rates: s }) : null,
            ],
          }),
          n.jsx("div", {
            className: "ss-tabs-panels",
            children: n.jsx("div", {
              ref: S,
              className: "ss-legacy-panels-slot",
            }),
          }),
        ],
      }),
      n.jsx(qt, {
        cameras: t,
        sensors: i,
        childrenLinks: r,
        isSuperuser: a,
        panelsReady: v,
        authToken: c,
        onSensorsChange: d,
      }),
      n.jsx(Ot, { wssConnection: p, sceneId: f, panelsReady: v }),
      n.jsx(Wt, {}),
    ],
  });
}
function Kt({ roi: e, index: s, isSuperuser: t, onChange: i, onRemove: r }) {
  const a = !t || e.readOnly,
    [f, p] = o.useState(!1),
    c = `roi-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-roi",
    id: `form-${e.svgId}`,
    ref: (d) => (d == null ? void 0 : d.setAttribute("for", e.svgId)),
    children: n.jsxs("div", {
      className: `ss-editor-row count-item col ss-editor-card${f ? " is-expanded" : ""}`,
      children: [
        n.jsxs("div", {
          className: "ss-editor-row__primary",
          children: [
            n.jsxs("div", {
              className: "ss-editor-row__fields",
              children: [
                n.jsx("span", {
                  className: "ss-editor-row__index input-group-text roi-number",
                  children: s + 1,
                }),
                n.jsx("input", {
                  type: "text",
                  className: "form-control roi-title ss-editor-row__title",
                  id: `input-${e.svgId}`,
                  "aria-labelledby": `label-${e.svgId}`,
                  placeholder: "ROI Name",
                  required: !0,
                  maxLength: 100,
                  disabled: a,
                  value: e.title,
                  onChange: (d) => i({ ...e, title: d.target.value }),
                  onBlur: () => {
                    var d, h;
                    if (window.ssUseReactMap) {
                      (h =
                        (d = window.ssMap) == null ? void 0 : d.numberRois) ==
                        null || h.call(d);
                      return;
                    }
                    typeof window.numberRois == "function" &&
                      window.numberRois();
                  },
                }),
                n.jsx("button", {
                  type: "button",
                  className: "ss-editor-row__toggle",
                  "aria-expanded": f,
                  "aria-controls": c,
                  title: f ? "Hide details" : "Show details",
                  onClick: () => p((d) => !d),
                  children: n.jsx("i", {
                    className: `bi ${f ? "bi-chevron-up" : "bi-chevron-down"}`,
                    "aria-hidden": "true",
                  }),
                }),
              ],
            }),
            t
              ? n.jsx("button", {
                  className:
                    "ss-icon-btn ss-icon-btn--danger roi-remove ss-editor-row__remove",
                  type: "button",
                  title: "Remove this ROI",
                  "aria-label": "Remove this ROI",
                  onClick: (d) => {
                    (d.preventDefault(), d.stopPropagation(), r(e.svgId));
                  },
                  children: n.jsx("i", {
                    className: "bi bi-trash",
                    "aria-hidden": "true",
                  }),
                })
              : null,
          ],
        }),
        f
          ? n.jsxs("div", {
              className: "ss-editor-row__details",
              id: c,
              children: [
                t
                  ? n.jsx("div", {
                      className: "ss-editor-geom",
                      children: n.jsxs("div", {
                        className: "ss-editor-geom__row ss-editor-card-meta",
                        children: [
                          n.jsxs("div", {
                            className:
                              "form-check form-check-inline ss-editor-geom__check",
                            children: [
                              n.jsx("input", {
                                className: "form-check-input roi-volumetric",
                                type: "checkbox",
                                id: `volumetric-${e.svgId}`,
                                checked: e.volumetric,
                                onChange: (d) =>
                                  i({ ...e, volumetric: d.target.checked }),
                              }),
                              n.jsx("label", {
                                className: "form-check-label",
                                htmlFor: `volumetric-${e.svgId}`,
                                children: "Volumetric",
                              }),
                            ],
                          }),
                          n.jsxs("label", {
                            className: "ss-editor-inline-field",
                            children: [
                              n.jsx("span", { children: "Height" }),
                              n.jsx("input", {
                                type: "number",
                                className: "form-control roi-height",
                                value: e.height,
                                min: 0.1,
                                step: 0.1,
                                onChange: (d) =>
                                  i({
                                    ...e,
                                    height: Number(d.target.value) || 1,
                                  }),
                              }),
                            ],
                          }),
                          n.jsxs("label", {
                            className: "ss-editor-inline-field",
                            children: [
                              n.jsx("span", { children: "Buffer" }),
                              n.jsx("input", {
                                type: "number",
                                className: "form-control roi-buffer",
                                value: e.buffer_size,
                                min: 0,
                                step: 0.1,
                                onChange: (d) =>
                                  i({
                                    ...e,
                                    buffer_size: Number(d.target.value) || 0,
                                  }),
                              }),
                            ],
                          }),
                        ],
                      }),
                    })
                  : null,
                n.jsx("div", {
                  className: "roi-visualization ss-editor-sectors",
                  children: n.jsx(tt, {
                    value: {
                      greenMin: e.greenMin,
                      yellowMin: e.yellowMin,
                      redMin: e.redMin,
                      rangeMax: e.rangeMax,
                    },
                    disabled: a,
                    legacyInputClasses: !0,
                    idPrefix: `roi-occ-${e.svgId}`,
                    onChange: (d) =>
                      i({
                        ...e,
                        greenMin: d.greenMin,
                        yellowMin: d.yellowMin,
                        redMin: d.redMin,
                        rangeMax: d.rangeMax,
                      }),
                  }),
                }),
                n.jsx("div", {
                  className:
                    "ss-editor-row__meta form-text text-muted roi-topic",
                  id: `label-${e.svgId}`,
                  children: n.jsx("button", {
                    type: "button",
                    className: "ss-editor-copy-id topic-text",
                    title: "Click to copy the topic",
                    onClick: () => void ye(e.topic),
                    children: e.topic,
                  }),
                }),
              ],
            })
          : n.jsx("span", {
              id: `label-${e.svgId}`,
              className: "sr-only",
              children: e.title || "ROI",
            }),
      ],
    }),
  });
}
function Qt({
  tripwire: e,
  index: s,
  isSuperuser: t,
  onChange: i,
  onRemove: r,
}) {
  const a = !!t && !e.readOnly,
    [f, p] = o.useState(!1),
    c = `trip-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-tripwire",
    id: `form-${e.svgId}`,
    ref: (d) => (d == null ? void 0 : d.setAttribute("for", e.svgId)),
    children: n.jsxs("div", {
      className: `ss-editor-row count-item col ss-editor-card${f ? " is-expanded" : ""}`,
      children: [
        n.jsxs("div", {
          className: "ss-editor-row__primary",
          children: [
            n.jsxs("div", {
              className: "ss-editor-row__fields",
              children: [
                n.jsx("span", {
                  className:
                    "ss-editor-row__index input-group-text tripwire-number",
                  children: s + 1,
                }),
                n.jsx("input", {
                  type: "text",
                  className: "form-control tripwire-title ss-editor-row__title",
                  id: `input-${e.svgId}`,
                  "aria-labelledby": `label-${e.svgId}`,
                  placeholder: "Tripwire Name",
                  required: !0,
                  maxLength: 100,
                  readOnly: !a,
                  disabled: !a,
                  value: e.title,
                  onChange: (d) => {
                    a && i({ ...e, title: d.target.value });
                  },
                  onBlur: () => {
                    var d, h, N;
                    if (window.ssUseReactMap) {
                      (h =
                        (d = window.ssMap) == null
                          ? void 0
                          : d.numberTripwires) == null || h.call(d);
                      return;
                    }
                    (N = window.numberTripwires) == null || N.call(window);
                  },
                }),
                n.jsx("button", {
                  type: "button",
                  className: "ss-editor-row__toggle",
                  "aria-expanded": f,
                  "aria-controls": c,
                  title: f ? "Hide details" : "Show details",
                  onClick: () => p((d) => !d),
                  children: n.jsx("i", {
                    className: `bi ${f ? "bi-chevron-up" : "bi-chevron-down"}`,
                    "aria-hidden": "true",
                  }),
                }),
              ],
            }),
            t
              ? n.jsx("button", {
                  className:
                    "ss-icon-btn ss-icon-btn--danger tripwire-remove ss-editor-row__remove",
                  type: "button",
                  title: "Remove this Tripwire",
                  "aria-label": "Remove this Tripwire",
                  onClick: (d) => {
                    (d.preventDefault(), d.stopPropagation(), r(e.svgId));
                  },
                  children: n.jsx("i", {
                    className: "bi bi-trash",
                    "aria-hidden": "true",
                  }),
                })
              : null,
          ],
        }),
        f
          ? n.jsx("div", {
              className: "ss-editor-row__details",
              id: c,
              children: n.jsx("div", {
                className: "ss-editor-row__meta form-text text-muted topic",
                id: `label-${e.svgId}`,
                children: n.jsx("button", {
                  type: "button",
                  className: "ss-editor-copy-id topic-text",
                  title: "Click to copy the topic",
                  onClick: () => void ye(e.topic),
                  children: e.topic,
                }),
              }),
            })
          : n.jsx("span", {
              id: `label-${e.svgId}`,
              className: "sr-only",
              children: e.title || "Tripwire",
            }),
      ],
    }),
  });
}
function Te(e) {
  if (typeof e != "string" || !e) return !1;
  try {
    return !!e.match(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  } catch {
    return !1;
  }
}
function $e(e) {
  return Array.isArray(e) ? e : e && Array.isArray(e.results) ? e.results : [];
}
function ne(e) {
  if (!e || typeof e != "object") return null;
  const s = e.uid;
  return typeof s == "string" && s ? s : null;
}
function ie(e) {
  const s = document.getElementById(e);
  if (!(s != null && s.value)) return [];
  try {
    const t = JSON.parse(s.value);
    return Array.isArray(t) ? t : [];
  } catch {
    return [];
  }
}
function Xt(e, s) {
  const i = {
    name: (s.title || "").trim() || `roi_${s.uuid || "new"}`,
    scene: e,
    points: s.points || [],
    volumetric: !!s.volumetric,
    height: typeof s.height == "number" ? s.height : 1,
    buffer_size: typeof s.buffer_size == "number" ? s.buffer_size : 0,
  };
  return (
    Array.isArray(s.sectors) &&
      typeof s.range_max == "number" &&
      (i.color_ranges = { sectors: s.sectors, range_max: s.range_max }),
    i
  );
}
function Zt(e, s) {
  return {
    name: (s.title || "").trim() || `tripwire_${s.uuid || "new"}`,
    scene: e,
    points: s.points || [],
    ...(typeof s.height == "number" ? { height: s.height } : {}),
  };
}
async function es(e, s, t) {
  var S, A, b, M, g, y;
  let i, r;
  if (t != null && t.preferHidden)
    ((i = ie("id_rois")),
      (r = ie("tripwires")),
      (A = (S = window.ssMap) == null ? void 0 : S.syncFromLegacyStringify) ==
        null || A.call(S));
  else {
    const l =
        (M = (b = window.ssMap) == null ? void 0 : b.getRois) == null
          ? void 0
          : M.call(b),
      _ =
        (y = (g = window.ssMap) == null ? void 0 : g.getTripwires) == null
          ? void 0
          : y.call(g);
    ((i = l
      ? l.map((x) => ({
          uuid: x.uuid,
          title: x.title,
          points: x.points,
          volumetric: x.volumetric,
          height: x.height,
          buffer_size: x.buffer_size,
          range_max: x.range_max,
          sectors: x.sectors,
        }))
      : ie("id_rois")),
      (r = _
        ? _.map((x) => ({ uuid: x.uuid, title: x.title, points: x.points }))
        : ie("tripwires")));
  }
  const [a, f] = await Promise.all([
      q.getRegions(e, s).then($e),
      q.getTripwires(e, s).then($e),
    ]),
    p = new Set(a.map(ne).filter((l) => !!l)),
    c = new Set(),
    d = {};
  for (const l of i) {
    const _ = Xt(s, l);
    if (Te(l.uuid) && p.has(l.uuid))
      (await q.updateRegion(e, l.uuid, _), c.add(l.uuid), (d[l.uuid] = l.uuid));
    else {
      const x = await q.createRegion(e, _),
        $ = ne(x);
      $ && (c.add($), l.uuid && (d[l.uuid] = $));
    }
  }
  for (const l of p) c.has(l) || (await q.deleteRegion(e, l));
  const h = new Set(f.map(ne).filter((l) => !!l)),
    N = new Set(),
    v = {};
  for (const l of r) {
    const _ = Zt(s, l);
    if (Te(l.uuid) && h.has(l.uuid))
      (await q.updateTripwire(e, l.uuid, _),
        N.add(l.uuid),
        (v[l.uuid] = l.uuid));
    else {
      const x = await q.createTripwire(e, _),
        $ = ne(x);
      $ && (N.add($), l.uuid && (v[l.uuid] = $));
    }
  }
  for (const l of h) N.has(l) || (await q.deleteTripwire(e, l));
  let j = !1;
  for (const [l, _] of Object.entries(d)) xt(l, _) && (j = !0);
  for (const [l, _] of Object.entries(v)) jt(l, _) && (j = !0);
  return (j && Nt(), { roiIds: d, tripIds: v });
}
function Q(e) {
  const s = window[e];
  typeof s == "function" && s();
}
function ts() {
  const e = {
    fit: () => Q("fitSceneMapDisplay"),
    numberRois: () => Q("numberRois"),
    numberTripwires: () => Q("numberTripwires"),
    stringifyRois: () => {
      (Q("stringifyRois"), e.syncFromLegacyStringify());
    },
    stringifyTripwires: () => {
      (Q("stringifyTripwires"), e.syncFromLegacyStringify());
    },
    syncFromLegacyStringify: () => {
      const s = document.getElementById("id_rois"),
        t = document.getElementById("tripwires");
      try {
        (s != null && s.value && _t(JSON.parse(s.value)),
          t != null && t.value && Ct(JSON.parse(t.value)));
      } catch {}
    },
    getRois: () => Z(),
    getTripwires: () => ee(),
    flushHidden: () => H(),
  };
  return ((window.ssMap = e), e);
}
function me(e, s, t) {
  const i = e == null ? void 0 : e.find((a) => a.color === s);
  if (!i) return t;
  const r = Number(i.color_min);
  return Number.isFinite(r) ? r : t;
}
function ke(e, s) {
  var r, a;
  const t = String(e.uuid || "").trim();
  if (!t) return null;
  const i = ((r = e.sectors) == null ? void 0 : r.thresholds) || [];
  return {
    svgId: `roi_${t}`,
    uuid: t,
    title: (e.title || "").trim(),
    volumetric: !!e.volumetric,
    height: Number(e.height ?? 1),
    buffer_size: Number(e.buffer_size ?? 0),
    greenMin: me(i, "green", 0),
    yellowMin: me(i, "yellow", 2),
    redMin: me(i, "red", 5),
    rangeMax: Number(((a = e.sectors) == null ? void 0 : a.range_max) ?? 10),
    topic: `scenescape/event/region/${s}/${t}/count`,
  };
}
function ss(e, s) {
  const t = String(e.uuid || "").trim();
  return t
    ? {
        svgId: `tripwire_${t}`,
        uuid: t,
        title: (e.title || "").trim(),
        topic: `scenescape/event/tripwire/${s}/${t}/objects`,
      }
    : null;
}
function Le(e, s, t) {
  return e.map((i) => {
    const r = s[i.uuid];
    return !r || r === i.uuid
      ? i
      : {
          ...i,
          uuid: r,
          svgId: `${t}_${r}`,
          topic: i.topic.split(i.uuid).join(r),
        };
  });
}
function re(e, s) {
  if (e === "roi") {
    ((window.ssRoiDirty = s),
      window.dispatchEvent(new CustomEvent("ss-roi-dirty", { detail: s })));
    return;
  }
  ((window.ssTripDirty = s),
    window.dispatchEvent(new CustomEvent("ss-trip-dirty", { detail: s })));
}
function Ae(e, s) {
  be(e.uuid, {
    title: e.title,
    volumetric: e.volumetric,
    height: e.height,
    buffer_size: e.buffer_size,
    range_max: e.rangeMax,
    sectors: [
      { color: "green", color_min: e.greenMin },
      { color: "yellow", color_min: e.yellowMin },
      { color: "red", color_min: e.redMin },
    ],
    ...(s ? { points: s.map((t) => [Number(t[0]), Number(t[1])]) } : {}),
  });
}
function ns({
  sceneId: e,
  isSuperuser: s,
  authToken: t,
  initialRegions: i,
  initialTripwires: r,
}) {
  const a = ge(),
    [f, p] = o.useState(() => i.map((u) => ke(u, e)).filter((u) => !!u)),
    [c, d] = o.useState(() => r.map((u) => ss(u, e)).filter((u) => !!u)),
    [h, N] = o.useState(!1),
    [v, j] = o.useState(!1),
    S = o.useRef(f),
    A = o.useRef(c),
    b = o.useRef(!1),
    M = o.useRef(a),
    g = o.useRef(""),
    y = o.useRef(""),
    l = o.useRef(() => {});
  ((M.current = a),
    (S.current = f),
    (A.current = c),
    o.useEffect(() => {
      (ts(),
        i.forEach((u) => {
          if (!String(u.uuid || "").trim()) return;
          const C = ke(u, e);
          C && Ae(C, u.points);
        }),
        r.forEach((u) => {
          const E = String(u.uuid || "").trim();
          E &&
            ae(E, {
              title: (u.title || "").trim(),
              points: (u.points || []).map((C) => [Number(C[0]), Number(C[1])]),
            });
        }));
    }, [i, r, e]),
    o.useEffect(() => {
      l.current = async (u) => {
        var C, B, m, w, L, k, I;
        if (b.current) return;
        b.current = !0;
        const E = u && !Array.isArray(u) ? u : void 0;
        E != null && E.preferHidden
          ? (B =
              (C = window.ssMap) == null
                ? void 0
                : C.syncFromLegacyStringify) == null || B.call(C)
          : window.ssUseReactMap
            ? (L = window.ssMap) == null || L.flushHidden()
            : ((m = window.ssMap) == null || m.stringifyRois(),
              (w = window.ssMap) == null || w.stringifyTripwires());
        try {
          const D = await es(t, e, E);
          (p((T) => Le(T, D.roiIds, "roi")),
            d((T) => Le(T, D.tripIds, "tripwire")),
            (g.current =
              ((k = document.getElementById("id_rois")) == null
                ? void 0
                : k.value) ?? g.current),
            (y.current =
              ((I = document.getElementById("tripwires")) == null
                ? void 0
                : I.value) ?? y.current),
            re("roi", !1),
            re("trip", !1),
            N(!1),
            j(!1),
            M.current.show("Regions saved", "ok"));
        } catch (D) {
          const T =
            D && typeof D == "object" && "message" in D
              ? String(D.message || "Save failed")
              : "Save failed";
          throw (M.current.show(T, "bad"), D);
        } finally {
          b.current = !1;
        }
      };
    }, [t, e]),
    o.useEffect(() => {
      const u = (E) => l.current(E);
      return (
        (window.ssPersistGeometry = u),
        () => {
          window.ssPersistGeometry === u && delete window.ssPersistGeometry;
        }
      );
    }, []),
    o.useEffect(() => {
      re("roi", h);
    }, [h]),
    o.useEffect(() => {
      re("trip", v);
    }, [v]),
    o.useEffect(() => {
      const u = document.getElementById("id_rois"),
        E = document.getElementById("tripwires");
      ((g.current = (u == null ? void 0 : u.value) ?? ""),
        (y.current = (E == null ? void 0 : E.value) ?? ""));
      const C = window.setTimeout(() => {
          var w;
          ((g.current = (u == null ? void 0 : u.value) ?? ""),
            (y.current = (E == null ? void 0 : E.value) ?? ""),
            (w = window.ssMap) == null || w.syncFromLegacyStringify());
        }, 1200),
        B = (w) => {
          var k;
          const L = (k = w.detail) == null ? void 0 : k.kind;
          if (L === "trips") {
            j(!0);
            return;
          }
          if (L === "rois") {
            N(!0);
            return;
          }
          (N(!0), j(!0));
        };
      window.addEventListener("ss-geometry-stringified", B);
      const m = window.setInterval(() => {
        (u && u.value !== g.current && N(!0),
          E && E.value !== y.current && j(!0));
      }, 600);
      return () => {
        (window.clearTimeout(C),
          window.clearInterval(m),
          window.removeEventListener("ss-geometry-stringified", B));
      };
    }, []),
    o.useEffect(() => {
      const u = (m) => {
          (p((w) =>
            w.some((L) => L.svgId === m.svgId)
              ? w
              : [
                  ...w,
                  {
                    svgId: m.svgId,
                    uuid: m.uuid,
                    title: m.title || "",
                    volumetric: m.volumetric ?? !1,
                    height: m.height ?? 1,
                    buffer_size: m.buffer_size ?? 0,
                    greenMin: m.greenMin ?? 0,
                    yellowMin: m.yellowMin ?? 2,
                    redMin: m.redMin ?? 5,
                    rangeMax: m.rangeMax ?? 10,
                    topic:
                      m.topic || `scenescape/event/region/${e}/${m.uuid}/count`,
                  },
                ],
          ),
            N(!0),
            window.requestAnimationFrame(() => {
              var w;
              (w = window.numberRois) == null || w.call(window);
            }));
        },
        E = (m) => {
          (d((w) =>
            w.some((L) => L.svgId === m.svgId)
              ? w
              : [
                  ...w,
                  {
                    svgId: m.svgId,
                    uuid: m.uuid,
                    title: m.title || "",
                    topic:
                      m.topic ||
                      `scenescape/event/tripwire/${e}/${m.uuid}/objects`,
                  },
                ],
          ),
            j(!0),
            window.requestAnimationFrame(() => {
              var w;
              (w = window.numberTripwires) == null || w.call(window);
            }));
        };
      window.ssRoiEditors = {
        addRoi: u,
        addTripwire: E,
        hasRoi: (m) => S.current.some((w) => w.svgId === m),
        hasTripwire: (m) => A.current.some((w) => w.svgId === m),
      };
      const C = (m) => {
          const w = m.detail;
          w != null && w.svgId && u(w);
        },
        B = (m) => {
          const w = m.detail;
          w != null && w.svgId && E(w);
        };
      return (
        window.addEventListener("ss-roi-form-add", C),
        window.addEventListener("ss-tripwire-form-add", B),
        () => {
          (window.removeEventListener("ss-roi-form-add", C),
            window.removeEventListener("ss-tripwire-form-add", B),
            delete window.ssRoiEditors);
        }
      );
    }, [e]),
    o.useEffect(() => {
      Oe({ regions: f.length, tripwires: c.length });
    }, [f.length, c.length]),
    o.useEffect(() => {
      const u = document.getElementById("no-regions");
      u && (u.style.display = f.length ? "none" : "");
    }, [f.length]),
    o.useEffect(() => {
      const u = document.getElementById("no-tripwires");
      u && (u.style.display = c.length ? "none" : "");
    }, [c.length]),
    o.useEffect(() => {
      const u = document.getElementById("no-regions");
      if (u && ((u.hidden = f.length > 0), f.length === 0)) {
        u.innerHTML = "";
        const E = document.createElement("p");
        if (
          ((E.textContent = "No regions of interest defined."),
          u.appendChild(E),
          s)
        ) {
          const C = document.createElement("button");
          ((C.type = "button"),
            (C.className = "btn btn-primary btn-sm"),
            (C.id = "empty-new-roi"),
            (C.textContent = "+ New Region"),
            u.appendChild(C));
        }
      }
    }, [f.length, s]),
    o.useEffect(() => {
      const u = document.getElementById("no-tripwires");
      if (u && ((u.hidden = c.length > 0), c.length === 0)) {
        u.innerHTML = "";
        const E = document.createElement("p");
        if (((E.textContent = "No tripwires defined."), u.appendChild(E), s)) {
          const C = document.createElement("button");
          ((C.type = "button"),
            (C.className = "btn btn-primary btn-sm"),
            (C.id = "empty-new-tripwire"),
            (C.textContent = "+ New Tripwire"),
            u.appendChild(C));
        }
      }
    }, [c.length, s]));
  const _ = async (u) => {
      var B;
      if (
        !(window.ssConfirm
          ? await window.ssConfirm({
              title: "Remove region?",
              message: "Are you sure you wish to remove this ROI?",
              confirmLabel: "Remove",
              danger: !0,
            })
          : window.confirm("Are you sure you wish to remove this ROI?"))
      )
        return;
      const C = u.replace(/^roi_/, "");
      (yt(C),
        p((m) => m.filter((w) => w.svgId !== u)),
        (B = window.ssMap) == null || B.flushHidden());
      try {
        await l.current();
      } catch {
        N(!0);
      }
    },
    x = async (u) => {
      var B;
      if (
        !(window.ssConfirm
          ? await window.ssConfirm({
              title: "Remove tripwire?",
              message: "Are you sure you wish to remove this tripwire?",
              confirmLabel: "Remove",
              danger: !0,
            })
          : window.confirm("Are you sure you wish to remove this tripwire?"))
      )
        return;
      const C = u.replace(/^tripwire_/, "");
      (vt(C),
        d((m) => m.filter((w) => w.svgId !== u)),
        (B = window.ssMap) == null || B.flushHidden());
      try {
        await l.current();
      } catch {
        j(!0);
      }
    },
    $ = document.getElementById("roi-fields"),
    R = document.getElementById("tripwire-fields");
  return n.jsxs(n.Fragment, {
    children: [
      $
        ? Y.createPortal(
            n.jsx(n.Fragment, {
              children: f.map((u, E) =>
                n.jsx(
                  Kt,
                  {
                    roi: u,
                    index: E,
                    isSuperuser: s,
                    onChange: (C) => {
                      (N(!0),
                        Ae(C),
                        p((B) => B.map((m) => (m.svgId === C.svgId ? C : m))));
                    },
                    onRemove: _,
                  },
                  u.svgId,
                ),
              ),
            }),
            $,
          )
        : null,
      R
        ? Y.createPortal(
            n.jsx(n.Fragment, {
              children: c.map((u, E) =>
                n.jsx(
                  Qt,
                  {
                    tripwire: u,
                    index: E,
                    isSuperuser: s,
                    onChange: (C) => {
                      (j(!0),
                        ae(C.uuid, { title: C.title }),
                        d((B) => B.map((m) => (m.svgId === C.svgId ? C : m))));
                    },
                    onRemove: x,
                  },
                  u.svgId,
                ),
              ),
            }),
            R,
          )
        : null,
    ],
  });
}
function U(e, s = "") {
  return e == null || e === "" ? s : String(e);
}
function We(e) {
  if (e == null || e === "") return null;
  const s = String(e);
  return /^\d+$/.test(s) ? s : null;
}
function is(e) {
  if (
    e.area == null &&
    e.center == null &&
    e.points == null &&
    e.radius == null
  )
    return null;
  const s = Array.isArray(e.center) ? e.center : null,
    t = e.color_ranges;
  return JSON.stringify({
    area: e.area ?? "scene",
    radius: e.radius ?? null,
    x: s ? s[0] : null,
    y: s ? s[1] : null,
    points: Array.isArray(e.points) ? e.points : [],
    sectors: {
      thresholds: (t == null ? void 0 : t.sectors) ?? [],
      range_max: (t == null ? void 0 : t.range_max) ?? null,
    },
  });
}
function fe(e, s) {
  return U(e[s]);
}
function rs(e) {
  const s = We(e.id),
    t = U(e.sensor_id || e.uid),
    i = U(e.name, t);
  if (!s && !t) return null;
  const r = s || t;
  return {
    id: r,
    sensorId: t || r,
    name: i || t || r,
    calibrateHref: `?ss=calibrate-cam&id=${r}`,
    cmdTopic: `scenescape/cmd/camera/${t || r}`,
    deleteUrl: s ? `/cam/delete/${s}/` : null,
  };
}
function as(e, s) {
  const t = We(e.id),
    i = U(e.sensor_id || e.uid),
    r = U(e.name, i);
  if (!t && !i) return null;
  const a = t || i;
  return {
    id: a,
    sensorId: i || a,
    name: r || i || a,
    iconUrl: (s == null ? void 0 : s.iconUrl) ?? null,
    areaJson: is(e) || (s == null ? void 0 : s.areaJson) || "{}",
    calibrateHref: `?ss=calibrate-sensor&id=${a}`,
    editHref: `?ss=sensor-edit&id=${i || a}`,
    deleteUrl: t
      ? `/singleton_sensor/delete/${t}/`
      : ((s == null ? void 0 : s.deleteUrl) ?? null),
  };
}
function os(e, s, t) {
  var h;
  const i = U(e.uid || e.id);
  if (!i) return null;
  const r = U(e.child_type || (t == null ? void 0 : t.childType), "local"),
    a = e.child != null ? U(e.child) : null,
    f =
      e.remote_child_id != null
        ? U(e.remote_child_id)
        : ((t == null ? void 0 : t.remoteChildId) ?? null),
    p = a
      ? (h = s.find((N) => N.id === a)) == null
        ? void 0
        : h.name
      : void 0,
    c = U(
      e.name || e.child_name || p || (t == null ? void 0 : t.name),
      "Child",
    ),
    d = r === "local" && a ? a : f || i;
  return {
    id: i,
    name: c,
    childType: r,
    remoteChildId: f,
    detailUrl: a ? `/${a}/` : ((t == null ? void 0 : t.detailUrl) ?? null),
    thumbnailUrl: (t == null ? void 0 : t.thumbnailUrl) ?? null,
    mapUrl: (t == null ? void 0 : t.mapUrl) ?? null,
    restUid: d,
    editHref: `?ss=child-edit&id=${d}`,
    deleteUrl: /^\d+$/.test(i)
      ? `/child/delete/${i}/`
      : ((t == null ? void 0 : t.deleteUrl) ?? null),
  };
}
function cs(e, s, t) {
  const i = e.findIndex(
    (a) =>
      a.id === s.id || a.sensorId === s.sensorId || !!(t && a.sensorId === t),
  );
  if (i < 0) return [...e, s];
  const r = e.slice();
  return (
    (r[i] = { ...e[i], ...s, deleteUrl: s.deleteUrl || e[i].deleteUrl }),
    r
  );
}
function ls(e, s, t) {
  const i = e.findIndex(
    (a) =>
      a.id === s.id || a.sensorId === s.sensorId || !!(t && a.sensorId === t),
  );
  if (i < 0) return [...e, s];
  const r = e.slice();
  return (
    (r[i] = {
      ...e[i],
      ...s,
      iconUrl: s.iconUrl ?? e[i].iconUrl,
      areaJson: s.areaJson || e[i].areaJson,
      deleteUrl: s.deleteUrl || e[i].deleteUrl,
    }),
    r
  );
}
function ds(e, s, t) {
  const i = e.findIndex(
    (a) => a.id === s.id || a.restUid === s.restUid || !!(t && a.restUid === t),
  );
  if (i < 0) return [...e, s];
  const r = e.slice();
  return (
    (r[i] = {
      ...e[i],
      ...s,
      thumbnailUrl: s.thumbnailUrl ?? e[i].thumbnailUrl,
      mapUrl: s.mapUrl ?? e[i].mapUrl,
      detailUrl: s.detailUrl ?? e[i].detailUrl,
      deleteUrl: s.deleteUrl || e[i].deleteUrl,
    }),
    r
  );
}
const us = new Set([
  "cam-create",
  "cam-edit",
  "sensor-create",
  "sensor-edit",
  "child-create",
  "child-edit",
  "calibrate-cam",
  "calibrate-sensor",
  "scene-manage",
]);
function ms(e) {
  return !!(e && us.has(e));
}
function fs({
  sceneId: e,
  authToken: s,
  isSuperuser: t,
  isKubernetes: i,
  scenes: r,
  cameras: a,
  sensors: f = [],
  onCamerasChange: p,
  onSensorsChange: c,
  onChildrenChange: d,
  mapUrl: h = null,
  mapScale: N = null,
}) {
  var B;
  const { sheet: v, open: j, close: S } = mt(),
    A = o.useCallback(
      (m, w = null) => {
        const L = ce(m);
        (L && le(L), j(m, w));
      },
      [j],
    ),
    b = o.useCallback(() => {
      const m = ce(v.action);
      (S(), m && le(m));
    }, [S, v.action]);
  (o.useEffect(() => {
    const m = (w) => {
      const L = w.target;
      if (!L) return;
      const k = L.closest("a[href]");
      if (!(k != null && k.href)) return;
      let I;
      try {
        I = new URL(k.href, window.location.origin);
      } catch {
        return;
      }
      if (I.origin !== window.location.origin) return;
      const D = I.searchParams.get("ss");
      !D ||
        !ms(D) ||
        ((I.pathname === window.location.pathname ||
          I.pathname === `/${e}/` ||
          I.pathname === `/${e}`) &&
          (w.preventDefault(),
          w.stopPropagation(),
          A(D, I.searchParams.get("id"))));
    };
    return (
      document.addEventListener("click", m, !0),
      () => document.removeEventListener("click", m, !0)
    );
  }, [A, e]),
    o.useEffect(() => {
      const m = ce(v.action);
      m && le(m);
    }, [v.action]));
  const M = o.useCallback(() => {
      window.location.reload();
    }, []),
    g = o.useCallback(
      (m) => {
        if (!m) return;
        const w = rs(m);
        if (!w) return;
        const L = fe(m, "scene"),
          k = v.action === "cam-edit" && v.id ? String(v.id) : null;
        p((I) =>
          L && L !== e
            ? I.filter(
                (D) =>
                  D.id !== w.id &&
                  D.sensorId !== w.sensorId &&
                  D.sensorId !== k,
              )
            : cs(I, w, k),
        );
      },
      [p, e, v.action, v.id],
    ),
    y = o.useCallback(
      (m) => {
        if (!m) return;
        const w = fe(m, "scene"),
          L = v.action === "sensor-edit" && v.id ? String(v.id) : null;
        c((k) => {
          const I = k.find(
              (T) =>
                T.sensorId === L ||
                T.sensorId === String(m.uid || "") ||
                T.id === String(m.id || ""),
            ),
            D = as(m, I);
          return D
            ? w && w !== e
              ? k.filter(
                  (T) =>
                    T.id !== D.id &&
                    T.sensorId !== D.sensorId &&
                    T.sensorId !== L,
                )
              : ls(k, D, L)
            : k;
        });
      },
      [c, e, v.action, v.id],
    ),
    l = o.useCallback(
      (m) => {
        if (!m) return;
        const w = fe(m, "parent"),
          L = v.action === "child-edit" && v.id ? String(v.id) : null;
        d((k) => {
          const I = k.find(
              (T) => T.id === String(m.uid || m.id || "") || T.restUid === L,
            ),
            D = os(m, r, I);
          return D
            ? w && w !== e
              ? k.filter(
                  (T) =>
                    T.id !== D.id && T.restUid !== D.restUid && T.restUid !== L,
                )
              : ds(k, D, L)
            : k;
        });
      },
      [d, e, r, v.action, v.id],
    ),
    _ = o.useMemo(() => {
      const m = new Map();
      return (a.forEach((w) => m.set(String(w.id), w)), m);
    }, [a]),
    x = o.useMemo(() => {
      const m = new Map();
      return (a.forEach((w) => m.set(String(w.sensorId), w)), m);
    }, [a]),
    $ = o.useMemo(() => {
      const m = new Map();
      return (f.forEach((w) => m.set(String(w.id), w)), m);
    }, [f]);
  if (!t) return null;
  const R = v.action,
    u = R === "calibrate-cam" && v.id ? _.get(String(v.id)) : null,
    E = R === "calibrate-sensor" && v.id ? $.get(String(v.id)) : null,
    C =
      R === "cam-edit" && v.id
        ? ((B = x.get(String(v.id))) == null ? void 0 : B.sensorId) ||
          String(v.id)
        : null;
  return n.jsxs(n.Fragment, {
    children: [
      n.jsx(st, {
        open: R === "cam-create" || R === "cam-edit",
        mode: R === "cam-edit" ? "edit" : "create",
        sceneId: e,
        scenes: r,
        sensorUid: R === "cam-edit" ? C : null,
        authToken: s,
        onClose: b,
        onSaved: g,
      }),
      n.jsx(nt, {
        open: R === "sensor-create" || R === "sensor-edit",
        mode: R === "sensor-edit" ? "edit" : "create",
        sceneId: e,
        scenes: r,
        sensorUid: R === "sensor-edit" ? v.id : null,
        authToken: s,
        onClose: b,
        onSaved: y,
      }),
      n.jsx(dt, {
        open: R === "child-create" || R === "child-edit",
        mode: R === "child-edit" ? "edit" : "create",
        parentSceneId: e,
        childUid: R === "child-edit" ? v.id : null,
        scenes: r,
        authToken: s,
        onClose: b,
        onSaved: l,
      }),
      n.jsx(ut, {
        open: R === "scene-manage",
        sceneId: e,
        authToken: s,
        onClose: b,
        onSaved: M,
      }),
      n.jsx(it, {
        open: !!u,
        cameraPk: (u == null ? void 0 : u.id) || "",
        sensorId: (u == null ? void 0 : u.sensorId) || "",
        cameraName: (u == null ? void 0 : u.name) || "",
        sceneId: e,
        authToken: s,
        isKubernetes: i,
        onClose: b,
        onSaved: M,
      }),
      n.jsx(rt, {
        open: !!E || R === "calibrate-sensor",
        sensorPk: (E == null ? void 0 : E.id) || v.id || "",
        sensorId: (E == null ? void 0 : E.sensorId) || "",
        sceneId: e,
        authToken: s,
        mapUrlHint: h,
        mapScale: N,
        onClose: b,
        onSaved: M,
      }),
    ],
  });
}
const Je = "ss-workspace-layout-mode",
  ps = 224,
  hs = 256,
  oe = 120;
function Be() {
  return {
    w: Math.max(window.innerWidth || 0, 320),
    h: Math.max(window.innerHeight || 0, 320),
  };
}
function ws() {
  try {
    const e = window.localStorage.getItem(Je);
    if (e === "auto" || e === "stack" || e === "row") return e;
  } catch {}
  return "auto";
}
function gs(e) {
  try {
    window.localStorage.setItem(Je, e);
  } catch {}
}
function bs() {
  const e = window;
  if (
    typeof e.scene_map_width == "number" &&
    e.scene_map_width > 0 &&
    typeof e.scene_y_max == "number" &&
    e.scene_y_max > 0
  )
    return { w: e.scene_map_width, h: e.scene_y_max };
  const s = document.getElementById("svgout");
  if (s) {
    const i = s.getAttribute("viewBox");
    if (i) {
      const r = i
        .trim()
        .split(/[\s,]+/)
        .map(Number);
      if (
        r.length === 4 &&
        Number.isFinite(r[2]) &&
        Number.isFinite(r[3]) &&
        r[2] > 0 &&
        r[3] > 0
      )
        return { w: r[2], h: r[3] };
    }
  }
  const t = document.querySelector("#ss-map-host #map img");
  return t && t.naturalWidth > 0 && t.naturalHeight > 0
    ? { w: t.naturalWidth, h: t.naturalHeight }
    : null;
}
function De(e, s, t) {
  const i = Math.max(s, oe),
    r = Math.max(t, oe),
    a = Math.min(i / e.w, r / e.h);
  return !Number.isFinite(a) || a <= 0 ? 0 : e.w * a * (e.h * a);
}
function Pe(e, s, t) {
  const i = Math.max(e.w - 32, oe),
    r = Math.max(e.h - t, oe);
  if (i < 720 || r / i > 1.25) return "stack";
  if (!s) return i / r >= 1.35 ? "stack" : "row";
  const a = s.w / s.h,
    f = De(s, i, r - ps),
    p = De(s, i - hs, r);
  return a >= 1.35
    ? f >= p * 0.92
      ? "stack"
      : "row"
    : a <= 1.05
      ? p >= f * 0.92
        ? "row"
        : "stack"
      : p > f
        ? "row"
        : "stack";
}
function ys(e = {}) {
  const s = e.chromeHeightPx ?? 112,
    [t, i] = o.useState(() => (typeof window < "u" ? ws() : "auto")),
    [r, a] = o.useState(() => Pe(Be(), null, s)),
    f = o.useCallback((c) => {
      (i(c), gs(c));
    }, []);
  return (
    o.useEffect(() => {
      let c = 0,
        d = null;
      const h = () => {
        (cancelAnimationFrame(c),
          (c = requestAnimationFrame(() => {
            const b = Pe(Be(), bs(), s);
            d !== b && ((d = b), a((M) => (M === b ? M : b)));
          })));
      };
      (h(),
        window.addEventListener("resize", h),
        window.addEventListener("ss-map-host-ready", h));
      const N = document.querySelector("#ss-map-host #map img");
      N && !N.complete && N.addEventListener("load", h);
      const v = document.getElementById("ss-map-host");
      let j = null;
      v &&
        typeof ResizeObserver < "u" &&
        ((j = new ResizeObserver(() => h())), j.observe(v));
      const S = window.setInterval(h, 500),
        A = window.setTimeout(() => window.clearInterval(S), 8e3);
      return () => {
        (cancelAnimationFrame(c),
          window.removeEventListener("resize", h),
          window.removeEventListener("ss-map-host-ready", h),
          N == null || N.removeEventListener("load", h),
          j == null || j.disconnect(),
          window.clearInterval(S),
          window.clearTimeout(A));
      };
    }, [s, t]),
    { layout: t === "auto" ? r : t, mode: t, setMode: f, autoLayout: r }
  );
}
function vs() {
  const [e, s] = o.useState(!1);
  return (
    o.useEffect(() => {
      const t = () => {
        const f = document.getElementById("mqtt_status"),
          p = !!(f != null && f.classList.contains("connected"));
        s((c) => (c === p ? c : p));
      };
      t();
      const i = document.getElementById("mqtt_status");
      let r = null;
      i &&
        ((r = new MutationObserver(t)),
        r.observe(i, { attributes: !0, attributeFilter: ["class"] }));
      const a = (f) => {
        const p = f.detail;
        typeof (p == null ? void 0 : p.connected) == "boolean"
          ? s((c) => (c === p.connected ? c : !!p.connected))
          : t();
      };
      return (
        window.addEventListener("ss-mqtt-status", a),
        () => {
          (r == null || r.disconnect(),
            window.removeEventListener("ss-mqtt-status", a));
        }
      );
    }, []),
    e
  );
}
function xs() {
  const [e, s] = o.useState({});
  return (
    o.useEffect(() => {
      const t = (p, c) => {
          s((d) => (d[p] === c ? d : { ...d, [p]: c }));
        },
        i = (p, c) => {
          t(p, c);
        },
        r = () => s({});
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setCameraRate: i,
        clearRates: r,
      };
      const a = (p) => {
          const c = p.detail;
          c != null && c.sensorId && t(c.sensorId, c.text || c.hz || "--");
        },
        f = () => r();
      return (
        window.addEventListener("ss-camera-rate", a),
        window.addEventListener("ss-telemetry-clear", f),
        () => {
          (window.removeEventListener("ss-camera-rate", a),
            window.removeEventListener("ss-telemetry-clear", f));
        }
      );
    }, []),
    e
  );
}
function X(e) {
  return String(e);
}
function js(e) {
  const s =
    typeof window < "u"
      ? new URLSearchParams(window.location.search).get("from")
      : null;
  return s === "cam-list" && e.camList
    ? { href: e.camList, label: "Cameras" }
    : s === "sensor-list" && e.sensorList
      ? { href: e.sensorList, label: "Sensors" }
      : { href: e.scenesHome, label: "Scenes" };
}
const Ns = [
  {
    mode: "auto",
    label: "Auto",
    title: "Automatic tab layout from map and screen size",
    icon: "bi-magic",
  },
  {
    mode: "stack",
    label: "Below",
    title: "Tabs below the map",
    icon: "bi-distribute-vertical",
  },
  {
    mode: "row",
    label: "Side",
    title: "Tabs beside the map",
    icon: "bi-layout-sidebar-reverse",
  },
];
function Ss({ bootstrap: e }) {
  const { scene: s, urls: t, isSuperuser: i } = e,
    { layout: r, mode: a, setMode: f, autoLayout: p } = ys(),
    {
      panelSizePx: c,
      setPanelSizePx: d,
      mapFocus: h,
      toggleMapFocus: N,
    } = at(r),
    [v, j] = o.useState("--"),
    [S, A] = o.useState(!1),
    [b, M] = o.useState(!1),
    [g, y] = o.useState(null),
    l = vs(),
    _ = xs(),
    [x, $] = o.useState(e.cameras),
    [R, u] = o.useState(e.sensors || []),
    [E, C] = o.useState(e.children || []),
    [B, m] = o.useState({
      cameras: e.cameras.length,
      sensors: e.counts.sensors,
      regions: e.counts.regions,
      tripwires: e.counts.tripwires,
      children: e.counts.children,
    });
  ((window.ssUseReactMap = !!s.mapUrl),
    o.useEffect(() => {
      const T = (V) => j(V || "--");
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setSceneRate: T,
      };
      const G = (V) => {
          const W = V.detail;
          (W == null ? void 0 : W.hz) !== void 0 && T(W.hz);
        },
        z = () => j("--");
      return (
        window.addEventListener("ss-scene-rate", G),
        window.addEventListener("ss-telemetry-clear", z),
        () => {
          (window.removeEventListener("ss-scene-rate", G),
            window.removeEventListener("ss-telemetry-clear", z));
        }
      );
    }, []),
    o.useEffect(() => {
      const T = (G) => {
        const z = G.detail;
        !z ||
          typeof z != "object" ||
          m((V) => {
            const W = { ...V };
            return (
              [
                "cameras",
                "sensors",
                "regions",
                "tripwires",
                "children",
              ].forEach((ve) => {
                const te = z[ve];
                typeof te == "number" &&
                  Number.isFinite(te) &&
                  te >= 0 &&
                  (W[ve] = te);
              }),
              W
            );
          });
      };
      return (
        window.addEventListener(he, T),
        () => window.removeEventListener(he, T)
      );
    }, []),
    o.useEffect(() => {
      const T = window.requestAnimationFrame(() => {
        typeof window.fitSceneMapDisplay == "function" &&
          window.fitSceneMapDisplay();
      });
      return () => window.cancelAnimationFrame(T);
    }, [h, c, r]));
  const w = o.useCallback(async () => {
      if (t.sceneDelete) {
        (M(!0), y(null));
        try {
          await ft(t.sceneDelete, t.scenesHome || "/");
        } catch (T) {
          (M(!1), y(T instanceof Error ? T.message : "Delete failed"));
        }
      }
    }, [t.sceneDelete, t.scenesHome]),
    L = [
      { id: "cameras", label: "Cameras", count: X(B.cameras) },
      { id: "sensors", label: "Sensors", count: X(B.sensors) },
      { id: "regions", label: "Regions", count: X(B.regions) },
      { id: "tripwires", label: "Tripwires", count: X(B.tripwires) },
      { id: "children", label: "Children", count: X(B.children) },
      {
        id: "mqtt",
        label: "MQTT",
        extra: n.jsxs("span", {
          id: "mqtt_status",
          className: `scene-detail-mqtt-pill${l ? " connected" : ""}`,
          title: l ? "MQTT connected" : "MQTT disconnected",
          "data-ss-mqtt": l ? "connected" : "disconnected",
          children: [
            n.jsx("i", {
              className: "bi bi-arrow-down-up",
              "aria-hidden": "true",
            }),
            n.jsx("span", { className: "ss-mqtt-label", children: "MQTT" }),
          ],
        }),
      },
    ],
    k = n.jsxs(n.Fragment, {
      children: [
        n.jsxs("div", {
          className: "scene-rate ss-scene-rate",
          children: [
            "Rate: ",
            n.jsx("span", { id: "scene-rate", children: v }),
            " Hz",
          ],
        }),
        n.jsx("div", {
          className: "ss-layout-toggle",
          role: "group",
          "aria-label": "Control panel layout",
          children: Ns.map((T) => {
            const G = a === T.mode,
              z = T.mode === "auto" ? ` (now ${p})` : "";
            return n.jsxs(
              "button",
              {
                type: "button",
                className: `ss-layout-toggle-btn${G ? " is-active" : ""}`,
                title: `${T.title}${z}`,
                "aria-pressed": G,
                onClick: () => f(T.mode),
                children: [
                  n.jsx("i", {
                    className: `bi ${T.icon}`,
                    "aria-hidden": "true",
                  }),
                  n.jsx("span", {
                    className: "ss-layout-toggle-label",
                    children: T.label,
                  }),
                ],
              },
              T.mode,
            );
          }),
        }),
        n.jsxs("button", {
          type: "button",
          className: `ss-layout-toggle-btn ss-map-focus-btn${h ? " is-active" : ""}`,
          title: h ? "Show control panel (Esc)" : "Map only focus",
          "aria-pressed": h,
          onClick: N,
          children: [
            n.jsx("i", {
              className: `bi ${h ? "bi-layout-sidebar" : "bi-arrows-fullscreen"}`,
              "aria-hidden": "true",
            }),
            n.jsx("span", {
              className: "ss-layout-toggle-label",
              children: h ? "Panel" : "Map",
            }),
          ],
        }),
        n.jsx("a", {
          className: "btn btn-secondary btn-sm",
          id: "export-scene",
          href: "#",
          title: `Export ${s.name}`,
          children: n.jsx("i", {
            className: "bi bi-box-arrow-up",
            "aria-hidden": "true",
          }),
        }),
        n.jsx("a", {
          className: "btn btn-secondary btn-sm",
          id: "3d-view",
          href: t.scene3d,
          title: `View ${s.name} in 3D`,
          children: "3D",
        }),
        i
          ? n.jsx("a", {
              className: "btn btn-secondary btn-sm",
              id: "scene-edit",
              href: "?ss=scene-manage",
              title: `Edit ${s.name}`,
              "aria-label": `Edit ${s.name}`,
              children: n.jsx("i", {
                className: "bi bi-pencil",
                "aria-hidden": "true",
              }),
            })
          : null,
        i && t.sceneDelete
          ? n.jsx("button", {
              type: "button",
              className: "btn btn-secondary btn-sm ss-icon-btn--danger",
              id: "scene-delete",
              title: `Delete ${s.name}`,
              "aria-label": `Delete ${s.name}`,
              onClick: () => {
                (y(null), A(!0));
              },
              children: n.jsx("i", {
                className: "bi bi-trash",
                "aria-hidden": "true",
              }),
            })
          : null,
      ],
    }),
    I = e.deleteImpact,
    D =
      typeof window < "u" &&
      new URLSearchParams(window.location.search).get("setup") ===
        "reconstruct";
  return n.jsxs("div", {
    className: `ss-scene-detail ss-scene-detail--workspace ss-workspace--${r}${h ? " ss-workspace--map-focus" : ""}`,
    "data-workspace-layout": r,
    "data-workspace-mode": a,
    "data-map-focus": h ? "1" : "0",
    style: { "--ss-panel-size": `${c}px` },
    children: [
      n.jsx(Ve, { title: s.name, back: js(t), actions: k }),
      n.jsxs("div", {
        className: "ss-workspace-body",
        children: [
          n.jsx("div", {
            className: "ss-workspace-main",
            children: n.jsx(kt, {
              mapUrl: s.mapUrl,
              setupHelper:
                !s.mapUrl && i
                  ? n.jsx(At, {
                      sceneId: s.id,
                      authToken: e.authToken,
                      cameraCount: x.length,
                      setupReconstruct: D,
                      onMeshComplete: () => {
                        window.location.href = window.location.pathname;
                      },
                    })
                  : null,
            }),
          }),
          n.jsx(ot, { layout: r, panelSizePx: c, onResize: d, disabled: h }),
          n.jsx(Vt, {
            tabs: L,
            cameraRates: _,
            cameras: x,
            sensors: R,
            childrenLinks: E,
            isSuperuser: i,
            sceneId: s.id,
            wssConnection: e.scene.wssConnection || "",
            authToken: e.authToken,
            onSensorsChange: u,
          }),
        ],
      }),
      n.jsx(ns, {
        sceneId: s.id,
        isSuperuser: i,
        authToken: e.authToken,
        initialRegions: e.regions || [],
        initialTripwires: e.tripwires || [],
      }),
      n.jsx(fs, {
        sceneId: s.id,
        authToken: e.authToken,
        isSuperuser: i,
        isKubernetes: !!e.isKubernetes,
        scenes: e.scenes || [],
        cameras: x,
        sensors: R,
        onCamerasChange: $,
        onSensorsChange: u,
        onChildrenChange: C,
        mapUrl: s.mapUrl,
        mapScale: s.scale,
      }),
      n.jsxs(He, {
        open: S,
        title: "Delete scene?",
        confirmLabel: "Delete scene",
        danger: !0,
        busy: b,
        onConfirm: w,
        onCancel: () => {
          b || A(!1);
        },
        children: [
          n.jsxs("p", {
            children: [
              "Are you sure you want to delete ",
              n.jsx("strong", { children: s.name }),
              "?",
            ],
          }),
          n.jsx("p", {
            children: "If you proceed, the following cannot be undone:",
          }),
          n.jsxs("ul", {
            children: [
              n.jsx("li", {
                children: "The scene will be permanently deleted",
              }),
              ((I == null ? void 0 : I.sensors) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      I == null ? void 0 : I.sensors,
                      " camera(s) and/or sensor(s) will be orphaned",
                    ],
                  })
                : null,
              ((I == null ? void 0 : I.regions) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      I == null ? void 0 : I.regions,
                      " region(s) will be deleted",
                    ],
                  })
                : null,
              ((I == null ? void 0 : I.tripwires) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      I == null ? void 0 : I.tripwires,
                      " tripwire(s) will be deleted",
                    ],
                  })
                : null,
            ],
          }),
          g ? n.jsx("p", { className: "ss-confirm-error", children: g }) : null,
        ],
      }),
    ],
  });
}
function Es({ bootstrap: e }) {
  return n.jsx(Ke, {
    children: n.jsx(Qe, { children: n.jsx(Ss, { bootstrap: e }) }),
  });
}
function _s({ bootstrap: e }) {
  return n.jsx(Es, { bootstrap: e });
}
function Cs() {
  const e = document.getElementById("ss-scene-detail-bootstrap");
  if (!(e != null && e.textContent)) return null;
  try {
    return JSON.parse(e.textContent);
  } catch {
    return (console.error("Failed to parse scene detail bootstrap JSON"), null);
  }
}
const Fe = Cs(),
  Ue = document.getElementById("ss-scene-detail-root");
Fe &&
  Ue &&
  (document.documentElement.classList.add("ss-scene-workspace"),
  document.body.classList.add("ss-scene-workspace"),
  Ye.createRoot(Ue).render(
    n.jsx(o.StrictMode, { children: n.jsx(_s, { bootstrap: Fe }) }),
  ));
