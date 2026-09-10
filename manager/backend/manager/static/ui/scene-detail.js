// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { r as a, j as n, c as Ge } from "./chunks/tokens-C2Ju3rc_.js";
import { P as We } from "./chunks/PageHeader-Dke5XNFH.js";
import {
  r as J,
  u as De,
  C as Pe,
  T as Je,
} from "./chunks/ConfirmDialog-DanZpjzY.js";
import { L as Ye } from "./chunks/LegacyConfirmHost-VsPlnSjJ.js";
import {
  r as Ve,
  c as Ke,
  m as Qe,
  p as ye,
  O as Xe,
  C as Ze,
  S as et,
  a as tt,
  b as st,
  u as nt,
  W as it,
} from "./chunks/SensorCalibratePanel-6g-riw34.js";
import { A as W } from "./chunks/actionIcons-BIxtFbWH.js";
import { a as O, u as rt } from "./chunks/rest-CiiNoWNe.js";
import { C as ot, S as at } from "./chunks/SceneManagePanel-C7ukm3Qu.js";
import { p as ct } from "./chunks/djangoDelete-BfD_c0xv.js";
import "./chunks/Button-CDF7QSMd.js";
const Fe = "ss-scene-tab:",
  fe = "ss-scene-tab",
  he = "ss-tab-counts";
function He(e) {
  typeof window > "u" ||
    window.dispatchEvent(new CustomEvent(he, { detail: e }));
}
const lt = {
  "cam-create": "cameras",
  "cam-edit": "cameras",
  "calibrate-cam": "cameras",
  "sensor-create": "sensors",
  "sensor-edit": "sensors",
  "calibrate-sensor": "sensors",
  "child-create": "children",
  "child-edit": "children",
};
function ae(e) {
  return (e && lt[e]) || null;
}
function dt(e, s = "cameras") {
  if (!e || typeof sessionStorage > "u") return s;
  try {
    const t = sessionStorage.getItem(Fe + e);
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
function ut(e, s) {
  if (!(!e || typeof sessionStorage > "u"))
    try {
      sessionStorage.setItem(Fe + e, s);
    } catch {}
}
function ce(e) {
  typeof window > "u" ||
    window.dispatchEvent(new CustomEvent(fe, { detail: { tabId: e } }));
}
const le = { host: "ss-map-host" };
function mt() {
  (window.dispatchEvent(new CustomEvent("ss-map-host-ready")),
    typeof window.fitSceneMapDisplay == "function" &&
      window.fitSceneMapDisplay());
}
let P = new Map(),
  F = new Map();
const pe = new Set();
function q() {
  pe.forEach((e) => {
    try {
      e();
    } catch {}
  });
}
function ve(e, s) {
  const t = document.getElementById(e);
  t && (t.value = s);
}
function ft(e) {
  return (
    pe.add(e),
    () => {
      pe.delete(e);
    }
  );
}
function X() {
  return Array.from(P.values());
}
function Z() {
  return Array.from(F.values());
}
function we(e, s) {
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
  (P.set(e, i), U(), q());
}
function re(e, s) {
  const t = F.get(e),
    i = {
      uuid: e,
      title: s.title ?? (t == null ? void 0 : t.title) ?? "",
      points: s.points ?? (t == null ? void 0 : t.points) ?? [],
    };
  (F.set(e, i), U(), q());
}
function ht(e) {
  (P.delete(e), U(), q());
}
function pt(e) {
  (F.delete(e), U(), q());
}
function wt(e, s) {
  if (!e || !s || e === s) return !1;
  const t = P.get(e);
  return t ? (P.delete(e), P.set(s, { ...t, uuid: s }), !0) : !1;
}
function gt(e, s) {
  if (!e || !s || e === s) return !1;
  const t = F.get(e);
  return t ? (F.delete(e), F.set(s, { ...t, uuid: s }), !0) : !1;
}
function bt() {
  (U(), q());
}
function yt(e, s) {
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
    U(),
    q());
}
function vt(e, s) {
  const t = F.get(e);
  (t
    ? F.set(e, { ...t, points: s })
    : F.set(e, { uuid: e, title: "", points: s }),
    U(),
    q());
}
function xt(e) {
  const s = new Set();
  for (const t of e) {
    const i = String(t.uuid || "").trim();
    if (!i) continue;
    s.add(i);
    const r = (t.points || []).map((o) => [Number(o[0]), Number(o[1])]);
    we(i, {
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
  (U(), q());
}
function jt(e) {
  const s = new Set();
  for (const t of e) {
    const i = String(t.uuid || "").trim();
    if (!i) continue;
    s.add(i);
    const r = (t.points || []).map((o) => [Number(o[0]), Number(o[1])]);
    re(i, { title: t.title, points: r });
  }
  for (const t of Array.from(F.keys())) s.has(t) || F.delete(t);
  (U(), q());
}
function U() {
  const e = X().map((t) => ({
      title: t.title,
      uuid: t.uuid,
      points: t.points,
      volumetric: t.volumetric,
      height: t.height,
      buffer_size: t.buffer_size,
      range_max: t.range_max,
      sectors: t.sectors,
    })),
    s = Z().map((t) => ({ title: t.title, uuid: t.uuid, points: t.points }));
  (ve("id_rois", JSON.stringify(e)), ve("tripwires", JSON.stringify(s)));
}
const te = { top: 32, right: 72, bottom: 12, left: 72 };
function St(e, s) {
  const t = e + te.left + te.right,
    i = s + te.top + te.bottom;
  return `-72 -32 ${t} ${i}`;
}
const Nt = a.memo(function ({ href: s, width: t, height: i }) {
  return n.jsx("image", {
    href: s,
    x: 0,
    y: 0,
    width: t,
    height: i,
    preserveAspectRatio: "none",
  });
});
function xe() {
  return `tmp${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
function Et(e, s, t = 22) {
  const i = s[0] - e[0],
    r = s[1] - e[1],
    o = Math.hypot(i, r);
  if (o < 1) return null;
  const h = (-t * r) / o,
    f = (t * i) / o,
    c = (e[0] + s[0]) / 2,
    l = (e[1] + s[1]) / 2,
    y = c + h,
    N = l + f,
    w = h / t,
    x = f / t,
    T = -x,
    D = w,
    v = [
      `${y},${N}`,
      `${y - w * 8 + T * 4},${N - x * 8 + D * 4}`,
      `${y - w * 8 - T * 4},${N - x * 8 - D * 4}`,
    ].join(" ");
  return { arrow: { x1: c, y1: l, x2: y, y2: N }, head: v };
}
function _t(e) {
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
const Ct = a.memo(function ({ mapHref: s, mapWidth: t, mapHeight: i }) {
  const [r, o] = a.useState(() => X()),
    [h, f] = a.useState(() => Z()),
    [c, l] = a.useState("idle"),
    [y, N] = a.useState([]),
    w = Ve(),
    x = i || Ke(i);
  (a.useEffect(
    () =>
      ft(() => {
        (o(X()), f(Z()));
      }),
    [],
  ),
    a.useEffect(() => {
      const b = () => {
          (l("add-roi"), N([]));
        },
        g = () => {
          (l("add-trip"), N([]));
        };
      window.ssMapReact = { startAddRoi: b, startAddTripwire: g };
      const m = (_) => {
        const E = _.target;
        if (!E) return;
        const A = E.closest(
          "#new-roi, #empty-new-roi, #new-tripwire, #empty-new-tripwire",
        );
        A && (_.preventDefault(), A.id.includes("trip") ? g() : b());
      };
      return (
        document.addEventListener("click", m, !0),
        () => {
          (document.removeEventListener("click", m, !0),
            delete window.ssMapReact);
        }
      );
    }, []));
  const T = a.useCallback((b) => Qe(b[0], b[1], w, x), [w, x]),
    D = (b) => {
      if (c === "idle") return;
      const g = b.currentTarget,
        m = g.createSVGPoint();
      ((m.x = b.clientX), (m.y = b.clientY));
      const _ = g.getScreenCTM();
      if (!_) return;
      const E = m.matrixTransform(_.inverse()),
        A = ye(E.x, E.y, w, x);
      if (c === "add-roi") {
        if (y.length >= 3) {
          const I = T(y[0]),
            d = E.x - I[0],
            S = E.y - I[1];
          if (Math.hypot(d, S) < 12) {
            const j = xe();
            (we(j, {
              title: "",
              points: y,
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
                  detail: { svgId: `roi_${j}`, uuid: j, title: "" },
                }),
              ),
              N([]),
              l("idle"));
            return;
          }
        }
        N((I) => [...I, A]);
        return;
      }
      if (c === "add-trip") {
        const I = [...y, A];
        if (I.length >= 2) {
          const d = xe();
          (re(d, { title: "", points: I.slice(0, 2) }),
            window.dispatchEvent(
              new CustomEvent("ss-tripwire-form-add", {
                detail: { svgId: `tripwire_${d}`, uuid: d, title: "" },
              }),
            ),
            N([]),
            l("idle"));
        } else N(I);
      }
    },
    v = (b, g, m, _) => {
      (_.stopPropagation(), _.preventDefault());
      const E = _.target.ownerSVGElement;
      if (!E) return;
      const A = (d) => {
          const S = E.createSVGPoint();
          ((S.x = d.clientX), (S.y = d.clientY));
          const j = E.getScreenCTM();
          if (!j) return;
          const k = S.matrixTransform(j.inverse()),
            u = ye(k.x, k.y, w, x);
          if (b === "roi") {
            const p = X().find(($) => $.uuid === g);
            if (!p) return;
            const L = p.points.map(($, R) => (R === m ? u : $));
            yt(g, L);
          } else {
            const p = Z().find(($) => $.uuid === g);
            if (!p) return;
            const L = p.points.map(($, R) => (R === m ? u : $));
            vt(g, L);
          }
        },
        I = () => {
          (window.removeEventListener("mousemove", A),
            window.removeEventListener("mouseup", I));
        };
      (window.addEventListener("mousemove", A),
        window.addEventListener("mouseup", I));
    },
    M = a.useMemo(() => y.map(T), [y, T]);
  return n.jsxs("svg", {
    id: "svgout",
    className: `ss-react-scene-map${c !== "idle" ? ` is-${c}` : ""}`,
    viewBox: St(t, i),
    preserveAspectRatio: "xMidYMid meet",
    width: "100%",
    height: "100%",
    onClick: D,
    children: [
      n.jsx(Nt, { href: s, width: t, height: i }),
      r.map((b) => {
        const g = b.points.map(T),
          m = g.map((E) => E.join(",")).join(" "),
          _ = _t(g);
        return n.jsxs(
          "g",
          {
            id: `roi_${b.uuid}`,
            className: "roi",
            children: [
              n.jsx("polygon", { points: m, className: "ss-react-roi-poly" }),
              b.title && _
                ? n.jsx("text", {
                    className: "ss-react-roi-title",
                    x: _[0],
                    y: _[1],
                    pointerEvents: "none",
                    children: b.title,
                  })
                : null,
              g.map((E, A) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: E[0],
                    cy: E[1],
                    r: 6,
                    onMouseDown: (I) => v("roi", b.uuid, A, I),
                  },
                  A,
                ),
              ),
            ],
          },
          b.uuid,
        );
      }),
      h.map((b) => {
        const g = b.points.map(T);
        if (g.length < 2) return null;
        const m = Et(g[0], g[1]);
        return n.jsxs(
          "g",
          {
            id: `tripwire_${b.uuid}`,
            className: "tripwire",
            children: [
              n.jsx("line", {
                className: "tripline ss-react-trip-line",
                x1: g[0][0],
                y1: g[0][1],
                x2: g[1][0],
                y2: g[1][1],
              }),
              m
                ? n.jsxs("g", {
                    className: "ss-react-trip-dir",
                    pointerEvents: "none",
                    children: [
                      n.jsx("line", {
                        className: "ss-react-trip-arrow",
                        x1: m.arrow.x1,
                        y1: m.arrow.y1,
                        x2: m.arrow.x2,
                        y2: m.arrow.y2,
                      }),
                      n.jsx("polygon", {
                        className: "ss-react-trip-arrowhead",
                        points: m.head,
                      }),
                    ],
                  })
                : null,
              b.title
                ? n.jsx("text", {
                    className: "ss-react-trip-title",
                    x: (g[0][0] + g[1][0]) / 2,
                    y: (g[0][1] + g[1][1]) / 2 - 14,
                    pointerEvents: "none",
                    children: b.title,
                  })
                : null,
              g.map((_, E) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: _[0],
                    cy: _[1],
                    r: 6,
                    onMouseDown: (A) => v("trip", b.uuid, E, A),
                  },
                  E,
                ),
              ),
            ],
          },
          b.uuid,
        );
      }),
      M.length > 0
        ? n.jsxs("g", {
            className: "ss-react-draft",
            children: [
              c === "add-roi" && M.length >= 2
                ? n.jsx("polyline", {
                    points: M.map((b) => b.join(",")).join(" "),
                    className: "ss-react-draft-line",
                  })
                : null,
              M.map((b, g) =>
                n.jsx(
                  "circle",
                  { cx: b[0], cy: b[1], r: 5, className: "ss-react-draft-pt" },
                  g,
                ),
              ),
            ],
          })
        : null,
    ],
  });
});
function je() {
  typeof window.fitSceneMapDisplay == "function" && window.fitSceneMapDisplay();
}
function Se(e) {
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
const Mt = a.memo(function ({
    mapUrl: s = null,
    mapWidth: t = 1280,
    mapHeight: i = 720,
  }) {
    const r = a.useRef(null),
      [o, h] = a.useState(!1),
      [f, c] = a.useState(null),
      l = !!window.ssUseReactMap && !!s;
    (a.useEffect(() => {
      if (!l || !s) {
        c(null);
        return;
      }
      let w = !1;
      const x = new Image();
      return (
        (x.onload = () => {
          !w &&
            x.naturalWidth > 0 &&
            x.naturalHeight > 0 &&
            c({ width: x.naturalWidth, height: x.naturalHeight });
        }),
        (x.src = s),
        () => {
          w = !0;
        }
      );
    }, [l, s]),
      a.useEffect(() => {
        const w = r.current,
          x = document.getElementById(le.host);
        if (!w || !x) return;
        if ((w.appendChild(x), (x.hidden = !1), l)) {
          document.body.classList.add("ss-use-react-map");
          const g = x.querySelector(
            "svg#svgout, svg.ss-snap-legacy, svg#svgout-snap",
          );
          g &&
            (g.classList.add("ss-snap-legacy"),
            g.id === "svgout" && (g.id = "svgout-snap"));
        }
        (mt(), h(!0));
        let T = 0,
          D = -1,
          v = -1;
        const M = () => {
          T ||
            (T = window.requestAnimationFrame(() => {
              T = 0;
              const g = Math.round(w.clientWidth),
                m = Math.round(w.clientHeight);
              if (!(g === D && m === v && D >= 0))
                if (((D = g), (v = m), !l)) je();
                else {
                  const _ = x.querySelector(".scene-map-stage");
                  (_ && Se(_), je());
                }
            }));
        };
        window.addEventListener("resize", M);
        let b = null;
        return (
          typeof ResizeObserver < "u" &&
            ((b = new ResizeObserver(() => M())), b.observe(w)),
          M(),
          () => {
            (T && window.cancelAnimationFrame(T),
              window.removeEventListener("resize", M),
              b == null || b.disconnect(),
              document.body.classList.remove("ss-use-react-map"));
            const g = x.querySelector("svg#svgout-snap, svg.ss-snap-legacy");
            if (g && g.id === "svgout-snap") {
              const _ = x.querySelector("svg.ss-react-scene-map");
              (!_ || _.id !== "svgout") && (g.id = "svgout");
            }
            const m = document.getElementById("ss-legacy-map-parking");
            m && x.parentElement === w && (m.appendChild(x), (x.hidden = !0));
          }
        );
      }, [l]),
      a.useEffect(() => {
        if (!l || !o) return;
        const w = document.getElementById(le.host),
          x = w == null ? void 0 : w.querySelector(".scene-map-stage");
        x && Se(x);
      }, [l, o, f]));
    const y = o ? document.getElementById(le.host) : null,
      N = (y == null ? void 0 : y.querySelector(".scene-map-stage")) ?? null;
    return n.jsxs("div", {
      className: "ss-scene-map-pane",
      children: [
        n.jsx("div", { ref: r, className: "ss-scene-map-slot" }),
        l && N && s && f
          ? J.createPortal(
              n.jsx("div", {
                className: "ss-react-map-layer",
                children: n.jsx(Ct, {
                  mapHref: s,
                  mapWidth: f.width || t,
                  mapHeight: f.height || i,
                }),
              }),
              N,
            )
          : null,
      ],
    });
  }),
  Ue = "ss-camera-strip-fit";
function Rt() {
  try {
    const e = window.localStorage.getItem(Ue);
    if (e === "cover" || e === "contain") return e;
  } catch {}
  return "contain";
}
function It(e) {
  try {
    window.localStorage.setItem(Ue, e);
  } catch {}
}
function Oe(e) {
  if (!e || e.classList.contains("display-none")) return !1;
  const s = e.currentSrc || e.getAttribute("src") || "";
  return !s || s.includes("offline.png")
    ? !1
    : e.naturalWidth > 0 || s.startsWith("data:image");
}
function de(e) {
  const s = e.querySelector(
      "img[data-ss-card-sensor], img[id^='card-preview-']",
    ),
    t = e.querySelector(".cam-offline"),
    i = e.querySelector(".rate"),
    r = Oe(s);
  !r &&
    i &&
    ((i.textContent || "").trim() !== "--" && (i.textContent = "--"),
    i.classList.add("telemetry-hide"));
  const o = ((i == null ? void 0 : i.textContent) || "").trim(),
    h = r ? "1" : "0";
  (e.dataset.ssOnline !== h &&
    ((e.dataset.ssOnline = h),
    e.classList.toggle("is-online", r),
    e.classList.toggle("is-offline", !r)),
    e.dataset.ssRate !== (o || "--") && (e.dataset.ssRate = o || "--"));
  let f = e.querySelector(".ss-camera-strip-badge");
  f ||
    ((f = document.createElement("span")),
    (f.className = "ss-camera-strip-badge"),
    f.setAttribute("aria-hidden", "true"),
    (e.querySelector(".card-header") || e).appendChild(f));
  const c = r ? "Live" : "Offline";
  (f.textContent !== c && (f.textContent = c),
    f.classList.toggle("is-online", r),
    f.classList.toggle("is-offline", !r),
    t && t.hidden !== r && (t.hidden = r));
}
function Tt({ rates: e = {} }) {
  const [s, t] = a.useState(() => (typeof window < "u" ? Rt() : "contain"));
  return (
    a.useEffect(() => {
      const i = document.documentElement;
      ((i.dataset.ssCameraFit = s), It(s));
      const r = document.getElementById("cameras");
      r && ((r.dataset.ssCameraFit = s), r.classList.add("ss-camera-strip"));
    }, [s]),
    a.useEffect(() => {
      Object.entries(e).forEach(([i, r]) => {
        var c;
        const o =
            (c = document.querySelector(
              `[data-ss-card-sensor="${CSS.escape(i)}"]`,
            )) == null
              ? void 0
              : c.closest(".camera-card"),
          h =
            o == null
              ? void 0
              : o.querySelector(
                  "img[data-ss-card-sensor], img[id^='card-preview-']",
                ),
          f = document.getElementById(`rate-${i}`);
        if (!Oe(h)) {
          (f &&
            ((f.textContent || "").trim() !== "--" && (f.textContent = "--"),
            f.classList.add("telemetry-hide")),
            o && de(o));
          return;
        }
        (f &&
          f.textContent !== r &&
          ((f.textContent = r), f.classList.remove("telemetry-hide")),
          o && de(o));
      });
    }, [e]),
    a.useEffect(() => {
      const i = document.getElementById("cameras");
      if (!i) return;
      i.classList.add("ss-camera-strip");
      let r = 0,
        o = !1;
      const h = () => {
          if (!o) {
            o = !0;
            try {
              i.querySelectorAll(".camera-card").forEach(de);
            } finally {
              o = !1;
            }
          }
        },
        f = () => {
          r ||
            (r = window.requestAnimationFrame(() => {
              ((r = 0), h());
            }));
        };
      h();
      const c = new MutationObserver(f);
      c.observe(i, {
        subtree: !0,
        childList: !0,
        attributes: !0,
        attributeFilter: ["class", "src"],
      });
      const l = window.setInterval(h, 2e3);
      return () => {
        (c.disconnect(),
          window.clearInterval(l),
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
async function ge(e) {
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
function $t({ cameras: e, isSuperuser: s }) {
  return (
    a.useEffect(() => {
      const t = () => {
        var o;
        return (o = window.ssRefreshCameraSnapshots) == null
          ? void 0
          : o.call(window);
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
                                className: `bi ${W.configure}`,
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
                                    className: `bi ${W.delete}`,
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
function Lt({ sensors: e, isSuperuser: s, onDelete: t }) {
  return (
    a.useEffect(() => {
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
                        onClick: () => void ge(i.sensorId),
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
                              className: `bi ${W.configure}`,
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
                                  className: `bi ${W.delete}`,
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
                                    className: `bi ${W.delete}`,
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
function kt({ childrenLinks: e, isSuperuser: s }) {
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
                              className: `bi ${W.configure}`,
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
                                  className: `bi ${W.delete}`,
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
function At({
  cameras: e,
  sensors: s,
  childrenLinks: t,
  isSuperuser: i,
  panelsReady: r,
  authToken: o = "",
  onSensorsChange: h,
}) {
  const f = De(),
    [c, l] = a.useState(null),
    [y, N] = a.useState(!1),
    [w, x] = a.useState(null);
  a.useEffect(() => {
    var m;
    r &&
      (He({ cameras: e.length, sensors: s.length, children: t.length }),
      (m = window.numberTabs) == null || m.call(window));
  }, [r, e, s, t]);
  const T = a.useCallback(async () => {
      var m;
      if (!(!c || !o || !h)) {
        (N(!0), x(null));
        try {
          (await O.deleteSensor(o, c.sensorId),
            (m = window.ssRemoveSingletonSensor) == null ||
              m.call(window, c.sensorId),
            h((_) =>
              _.filter((E) => E.id !== c.id && E.sensorId !== c.sensorId),
            ),
            f.show("Sensor deleted", "ok"),
            l(null));
        } catch (_) {
          x(_.message || "Delete failed");
        } finally {
          N(!1);
        }
      }
    }, [o, h, c, f]),
    D = a.useCallback((m) => {
      (x(null), l(m));
    }, []);
  if (!r) return null;
  const v = document.getElementById("ss-cameras-mount"),
    M = document.getElementById("ss-sensors-mount"),
    b = document.getElementById("ss-children-mount"),
    g = !!(o && h);
  return n.jsxs(n.Fragment, {
    children: [
      v ? J.createPortal(n.jsx($t, { cameras: e, isSuperuser: i }), v) : null,
      M
        ? J.createPortal(
            n.jsx(Lt, { sensors: s, isSuperuser: i, onDelete: g ? D : void 0 }),
            M,
          )
        : null,
      b
        ? J.createPortal(n.jsx(kt, { childrenLinks: t, isSuperuser: i }), b)
        : null,
      n.jsxs(Pe, {
        open: !!c,
        title: "Delete sensor?",
        confirmLabel: "Delete",
        danger: !0,
        busy: y,
        onConfirm: T,
        onCancel: () => {
          y || (l(null), x(null));
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
          w ? n.jsx("p", { className: "ss-confirm-error", children: w }) : null,
        ],
      }),
    ],
  });
}
function Bt({ wssConnection: e, sceneId: s, panelsReady: t }) {
  return (
    a.useEffect(() => {
      var o;
      if (!t) return;
      const i = document.getElementById("broker"),
        r = document.getElementById("topic");
      (i && e && !i.value && (i.value = e),
        r && s && !r.value && (r.value = `scenescape/regulated/scene/${s}`),
        (o = window.ssEnsureMqttScene) == null || o.call(window));
    }, [t, e, s]),
    null
  );
}
function Dt({ id: e, title: s, children: t, footer: i, onClose: r }) {
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
const Pt = [
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
function Ft() {
  return n.jsx(n.Fragment, {
    children: Pt.map((e) =>
      n.jsx(
        Dt,
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
function Ne(e) {
  var s;
  (e.preventDefault(),
    e.stopPropagation(),
    (s = window.ssPersistGeometry) == null || s.call(window));
}
function V({ id: e, modalId: s, title: t }) {
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
function Ee({ id: e, labelId: s, label: t, title: i }) {
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
function Ht({ activeTab: e, isSuperuser: s }) {
  const [t, i] = a.useState(() => !!window.ssRoiDirty),
    [r, o] = a.useState(() => !!window.ssTripDirty);
  return (
    a.useEffect(() => {
      const h = (c) => {
          i(!!c.detail);
        },
        f = (c) => {
          o(!!c.detail);
        };
      return (
        window.addEventListener("ss-roi-dirty", h),
        window.addEventListener("ss-trip-dirty", f),
        i(!!window.ssRoiDirty),
        o(!!window.ssTripDirty),
        () => {
          (window.removeEventListener("ss-roi-dirty", h),
            window.removeEventListener("ss-trip-dirty", f));
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
                n.jsx(V, {
                  id: "camera-help",
                  modalId: "cameraHelpModal",
                  title: "How cameras work in this scene",
                }),
                n.jsx(Ee, {
                  id: "live-view",
                  labelId: "live-view-label",
                  label: "Live View",
                  title: "Toggle Live View",
                }),
                n.jsx(Ee, {
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
                n.jsx(V, {
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
                n.jsx(V, {
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
                          onClick: Ne,
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
                n.jsx(V, {
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
                          onClick: Ne,
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
                n.jsx(V, {
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
const _e = {
    cameras: "cameras",
    sensors: "sensors",
    regions: "regions",
    tripwires: "trips",
    children: "children",
    mqtt: "mqtt",
  },
  Ut = {
    cameras: "cameras-tab",
    sensors: "sensors-tab",
    regions: "regions-tab",
    tripwires: "tripwires-tab",
    children: "children-tab",
    mqtt: "settings-tab",
  };
function Ot({
  tabs: e,
  cameraRates: s = {},
  cameras: t = [],
  sensors: i = [],
  childrenLinks: r = [],
  isSuperuser: o = !1,
  sceneId: h = "",
  wssConnection: f = "",
  authToken: c = "",
  onSensorsChange: l,
}) {
  const [y, N] = a.useState(() => dt(h)),
    [w, x] = a.useState(!1),
    T = a.useRef(null);
  (a.useEffect(() => {
    const v = T.current,
      M = document.getElementById("scene-detail-panels");
    if (!(!v || !M))
      return (
        v.appendChild(M),
        (M.hidden = !1),
        M.classList.add("ss-legacy-panels-adopted"),
        x(!0),
        () => {
          x(!1);
          const b = document.getElementById("ss-legacy-panels-parking");
          b && M.parentElement === v && (b.appendChild(M), (M.hidden = !0));
        }
      );
  }, []),
    a.useEffect(() => {
      Object.entries(_e).forEach(([v, M]) => {
        const b = document.getElementById(M);
        if (!b) return;
        const g = v === y;
        (b.classList.toggle("show", g), b.classList.toggle("active", g));
      });
    }, [y]),
    a.useEffect(() => {
      ut(h, y);
    }, [h, y]),
    a.useEffect(() => {
      const v = (M) => {
        const b = M.detail,
          g = b == null ? void 0 : b.tabId;
        (g === "cameras" ||
          g === "sensors" ||
          g === "regions" ||
          g === "tripwires" ||
          g === "children" ||
          g === "mqtt") &&
          N(g);
      };
      return (
        window.addEventListener(fe, v),
        () => window.removeEventListener(fe, v)
      );
    }, []));
  const D = (v) => {
    (v === "cameras" ||
      v === "sensors" ||
      v === "regions" ||
      v === "tripwires" ||
      v === "children" ||
      v === "mqtt") &&
      N(v);
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
                children: e.map((v) => {
                  const M = v.id === y,
                    b = Ut[v.id] || `ss-tab-${v.id}`;
                  return n.jsxs(
                    "button",
                    {
                      type: "button",
                      role: "tab",
                      id: b,
                      "aria-selected": M,
                      "aria-controls": _e[v.id] || v.id,
                      className: `ss-tabs-tab${M ? " is-active" : ""}`,
                      onClick: () => D(v.id),
                      children: [
                        n.jsx("span", {
                          className: "ss-tabs-label",
                          children: v.label,
                        }),
                        v.count !== void 0 && v.count !== null
                          ? n.jsx("span", {
                              className: "ss-tabs-count",
                              children: v.count,
                            })
                          : null,
                        v.extra,
                      ],
                    },
                    v.id,
                  );
                }),
              }),
              n.jsx("div", {
                className: "ss-tabs-toolbar",
                "data-active-tab": y,
                children: n.jsx(Ht, { activeTab: y, isSuperuser: o }),
              }),
              y === "cameras" ? n.jsx(Tt, { rates: s }) : null,
            ],
          }),
          n.jsx("div", {
            className: "ss-tabs-panels",
            children: n.jsx("div", {
              ref: T,
              className: "ss-legacy-panels-slot",
            }),
          }),
        ],
      }),
      n.jsx(At, {
        cameras: t,
        sensors: i,
        childrenLinks: r,
        isSuperuser: o,
        panelsReady: w,
        authToken: c,
        onSensorsChange: l,
      }),
      n.jsx(Bt, { wssConnection: f, sceneId: h, panelsReady: w }),
      n.jsx(Ft, {}),
    ],
  });
}
function qt({ roi: e, index: s, isSuperuser: t, onChange: i, onRemove: r }) {
  const o = !t || e.readOnly,
    [h, f] = a.useState(!1),
    c = `roi-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-roi",
    id: `form-${e.svgId}`,
    ref: (l) => (l == null ? void 0 : l.setAttribute("for", e.svgId)),
    children: n.jsxs("div", {
      className: `ss-editor-row count-item col ss-editor-card${h ? " is-expanded" : ""}`,
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
                  disabled: o,
                  value: e.title,
                  onChange: (l) => i({ ...e, title: l.target.value }),
                  onBlur: () => {
                    var l, y;
                    if (window.ssUseReactMap) {
                      (y =
                        (l = window.ssMap) == null ? void 0 : l.numberRois) ==
                        null || y.call(l);
                      return;
                    }
                    typeof window.numberRois == "function" &&
                      window.numberRois();
                  },
                }),
                n.jsx("button", {
                  type: "button",
                  className: "ss-editor-row__toggle",
                  "aria-expanded": h,
                  "aria-controls": c,
                  title: h ? "Hide details" : "Show details",
                  onClick: () => f((l) => !l),
                  children: n.jsx("i", {
                    className: `bi ${h ? "bi-chevron-up" : "bi-chevron-down"}`,
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
                  onClick: (l) => {
                    (l.preventDefault(), l.stopPropagation(), r(e.svgId));
                  },
                  children: n.jsx("i", {
                    className: "bi bi-trash",
                    "aria-hidden": "true",
                  }),
                })
              : null,
          ],
        }),
        h
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
                                onChange: (l) =>
                                  i({ ...e, volumetric: l.target.checked }),
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
                                onChange: (l) =>
                                  i({
                                    ...e,
                                    height: Number(l.target.value) || 1,
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
                                onChange: (l) =>
                                  i({
                                    ...e,
                                    buffer_size: Number(l.target.value) || 0,
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
                  children: n.jsx(Xe, {
                    value: {
                      greenMin: e.greenMin,
                      yellowMin: e.yellowMin,
                      redMin: e.redMin,
                      rangeMax: e.rangeMax,
                    },
                    disabled: o,
                    legacyInputClasses: !0,
                    idPrefix: `roi-occ-${e.svgId}`,
                    onChange: (l) =>
                      i({
                        ...e,
                        greenMin: l.greenMin,
                        yellowMin: l.yellowMin,
                        redMin: l.redMin,
                        rangeMax: l.rangeMax,
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
                    onClick: () => void ge(e.topic),
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
function zt({
  tripwire: e,
  index: s,
  isSuperuser: t,
  onChange: i,
  onRemove: r,
}) {
  const o = !!t && !e.readOnly,
    [h, f] = a.useState(!1),
    c = `trip-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-tripwire",
    id: `form-${e.svgId}`,
    ref: (l) => (l == null ? void 0 : l.setAttribute("for", e.svgId)),
    children: n.jsxs("div", {
      className: `ss-editor-row count-item col ss-editor-card${h ? " is-expanded" : ""}`,
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
                  readOnly: !o,
                  disabled: !o,
                  value: e.title,
                  onChange: (l) => {
                    o && i({ ...e, title: l.target.value });
                  },
                  onBlur: () => {
                    var l, y, N;
                    if (window.ssUseReactMap) {
                      (y =
                        (l = window.ssMap) == null
                          ? void 0
                          : l.numberTripwires) == null || y.call(l);
                      return;
                    }
                    (N = window.numberTripwires) == null || N.call(window);
                  },
                }),
                n.jsx("button", {
                  type: "button",
                  className: "ss-editor-row__toggle",
                  "aria-expanded": h,
                  "aria-controls": c,
                  title: h ? "Hide details" : "Show details",
                  onClick: () => f((l) => !l),
                  children: n.jsx("i", {
                    className: `bi ${h ? "bi-chevron-up" : "bi-chevron-down"}`,
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
                  onClick: (l) => {
                    (l.preventDefault(), l.stopPropagation(), r(e.svgId));
                  },
                  children: n.jsx("i", {
                    className: "bi bi-trash",
                    "aria-hidden": "true",
                  }),
                })
              : null,
          ],
        }),
        h
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
                  onClick: () => void ge(e.topic),
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
function Ce(e) {
  if (typeof e != "string" || !e) return !1;
  try {
    return !!e.match(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  } catch {
    return !1;
  }
}
function Me(e) {
  return Array.isArray(e) ? e : e && Array.isArray(e.results) ? e.results : [];
}
function se(e) {
  if (!e || typeof e != "object") return null;
  const s = e.uid;
  return typeof s == "string" && s ? s : null;
}
function ne(e) {
  const s = document.getElementById(e);
  if (!(s != null && s.value)) return [];
  try {
    const t = JSON.parse(s.value);
    return Array.isArray(t) ? t : [];
  } catch {
    return [];
  }
}
function Gt(e, s) {
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
function Wt(e, s) {
  return {
    name: (s.title || "").trim() || `tripwire_${s.uuid || "new"}`,
    scene: e,
    points: s.points || [],
    ...(typeof s.height == "number" ? { height: s.height } : {}),
  };
}
async function Jt(e, s, t) {
  var T, D, v, M, b, g;
  let i, r;
  if (t != null && t.preferHidden)
    ((i = ne("id_rois")),
      (r = ne("tripwires")),
      (D = (T = window.ssMap) == null ? void 0 : T.syncFromLegacyStringify) ==
        null || D.call(T));
  else {
    const m =
        (M = (v = window.ssMap) == null ? void 0 : v.getRois) == null
          ? void 0
          : M.call(v),
      _ =
        (g = (b = window.ssMap) == null ? void 0 : b.getTripwires) == null
          ? void 0
          : g.call(b);
    ((i = m
      ? m.map((E) => ({
          uuid: E.uuid,
          title: E.title,
          points: E.points,
          volumetric: E.volumetric,
          height: E.height,
          buffer_size: E.buffer_size,
          range_max: E.range_max,
          sectors: E.sectors,
        }))
      : ne("id_rois")),
      (r = _
        ? _.map((E) => ({ uuid: E.uuid, title: E.title, points: E.points }))
        : ne("tripwires")));
  }
  const [o, h] = await Promise.all([
      O.getRegions(e, s).then(Me),
      O.getTripwires(e, s).then(Me),
    ]),
    f = new Set(o.map(se).filter((m) => !!m)),
    c = new Set(),
    l = {};
  for (const m of i) {
    const _ = Gt(s, m);
    if (Ce(m.uuid) && f.has(m.uuid))
      (await O.updateRegion(e, m.uuid, _), c.add(m.uuid), (l[m.uuid] = m.uuid));
    else {
      const E = await O.createRegion(e, _),
        A = se(E);
      A && (c.add(A), m.uuid && (l[m.uuid] = A));
    }
  }
  for (const m of f) c.has(m) || (await O.deleteRegion(e, m));
  const y = new Set(h.map(se).filter((m) => !!m)),
    N = new Set(),
    w = {};
  for (const m of r) {
    const _ = Wt(s, m);
    if (Ce(m.uuid) && y.has(m.uuid))
      (await O.updateTripwire(e, m.uuid, _),
        N.add(m.uuid),
        (w[m.uuid] = m.uuid));
    else {
      const E = await O.createTripwire(e, _),
        A = se(E);
      A && (N.add(A), m.uuid && (w[m.uuid] = A));
    }
  }
  for (const m of y) N.has(m) || (await O.deleteTripwire(e, m));
  let x = !1;
  for (const [m, _] of Object.entries(l)) wt(m, _) && (x = !0);
  for (const [m, _] of Object.entries(w)) gt(m, _) && (x = !0);
  return (x && bt(), { roiIds: l, tripIds: w });
}
function K(e) {
  const s = window[e];
  typeof s == "function" && s();
}
function Yt() {
  const e = {
    fit: () => K("fitSceneMapDisplay"),
    numberRois: () => K("numberRois"),
    numberTripwires: () => K("numberTripwires"),
    stringifyRois: () => {
      (K("stringifyRois"), e.syncFromLegacyStringify());
    },
    stringifyTripwires: () => {
      (K("stringifyTripwires"), e.syncFromLegacyStringify());
    },
    syncFromLegacyStringify: () => {
      const s = document.getElementById("id_rois"),
        t = document.getElementById("tripwires");
      try {
        (s != null && s.value && xt(JSON.parse(s.value)),
          t != null && t.value && jt(JSON.parse(t.value)));
      } catch {}
    },
    getRois: () => X(),
    getTripwires: () => Z(),
    flushHidden: () => U(),
  };
  return ((window.ssMap = e), e);
}
function ue(e, s, t) {
  const i = e == null ? void 0 : e.find((o) => o.color === s);
  if (!i) return t;
  const r = Number(i.color_min);
  return Number.isFinite(r) ? r : t;
}
function Re(e, s) {
  var r, o;
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
    greenMin: ue(i, "green", 0),
    yellowMin: ue(i, "yellow", 2),
    redMin: ue(i, "red", 5),
    rangeMax: Number(((o = e.sectors) == null ? void 0 : o.range_max) ?? 10),
    topic: `scenescape/event/region/${s}/${t}/count`,
  };
}
function Vt(e, s) {
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
function Ie(e, s, t) {
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
function ie(e, s) {
  if (e === "roi") {
    ((window.ssRoiDirty = s),
      window.dispatchEvent(new CustomEvent("ss-roi-dirty", { detail: s })));
    return;
  }
  ((window.ssTripDirty = s),
    window.dispatchEvent(new CustomEvent("ss-trip-dirty", { detail: s })));
}
function Te(e, s) {
  we(e.uuid, {
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
function Kt({
  sceneId: e,
  isSuperuser: s,
  authToken: t,
  initialRegions: i,
  initialTripwires: r,
}) {
  const o = De(),
    [h, f] = a.useState(() => i.map((d) => Re(d, e)).filter((d) => !!d)),
    [c, l] = a.useState(() => r.map((d) => Vt(d, e)).filter((d) => !!d)),
    [y, N] = a.useState(!1),
    [w, x] = a.useState(!1),
    T = a.useRef(h),
    D = a.useRef(c),
    v = a.useRef(!1),
    M = a.useRef(o),
    b = a.useRef(""),
    g = a.useRef(""),
    m = a.useRef(() => {});
  ((M.current = o),
    (T.current = h),
    (D.current = c),
    a.useEffect(() => {
      (Yt(),
        i.forEach((d) => {
          if (!String(d.uuid || "").trim()) return;
          const j = Re(d, e);
          j && Te(j, d.points);
        }),
        r.forEach((d) => {
          const S = String(d.uuid || "").trim();
          S &&
            re(S, {
              title: (d.title || "").trim(),
              points: (d.points || []).map((j) => [Number(j[0]), Number(j[1])]),
            });
        }));
    }, [i, r, e]),
    a.useEffect(() => {
      m.current = async (d) => {
        var j, k, u, p, L, $, R;
        if (v.current) return;
        v.current = !0;
        const S = d && !Array.isArray(d) ? d : void 0;
        S != null && S.preferHidden
          ? (k =
              (j = window.ssMap) == null
                ? void 0
                : j.syncFromLegacyStringify) == null || k.call(j)
          : window.ssUseReactMap
            ? (L = window.ssMap) == null || L.flushHidden()
            : ((u = window.ssMap) == null || u.stringifyRois(),
              (p = window.ssMap) == null || p.stringifyTripwires());
        try {
          const C = await Jt(t, e, S);
          (f((B) => Ie(B, C.roiIds, "roi")),
            l((B) => Ie(B, C.tripIds, "tripwire")),
            (b.current =
              (($ = document.getElementById("id_rois")) == null
                ? void 0
                : $.value) ?? b.current),
            (g.current =
              ((R = document.getElementById("tripwires")) == null
                ? void 0
                : R.value) ?? g.current),
            ie("roi", !1),
            ie("trip", !1),
            N(!1),
            x(!1),
            M.current.show("Regions saved", "ok"));
        } catch (C) {
          const B =
            C && typeof C == "object" && "message" in C
              ? String(C.message || "Save failed")
              : "Save failed";
          throw (M.current.show(B, "bad"), C);
        } finally {
          v.current = !1;
        }
      };
    }, [t, e]),
    a.useEffect(() => {
      const d = (S) => m.current(S);
      return (
        (window.ssPersistGeometry = d),
        () => {
          window.ssPersistGeometry === d && delete window.ssPersistGeometry;
        }
      );
    }, []),
    a.useEffect(() => {
      ie("roi", y);
    }, [y]),
    a.useEffect(() => {
      ie("trip", w);
    }, [w]),
    a.useEffect(() => {
      const d = document.getElementById("id_rois"),
        S = document.getElementById("tripwires");
      ((b.current = (d == null ? void 0 : d.value) ?? ""),
        (g.current = (S == null ? void 0 : S.value) ?? ""));
      const j = window.setTimeout(() => {
          var p;
          ((b.current = (d == null ? void 0 : d.value) ?? ""),
            (g.current = (S == null ? void 0 : S.value) ?? ""),
            (p = window.ssMap) == null || p.syncFromLegacyStringify());
        }, 1200),
        k = (p) => {
          var $;
          const L = ($ = p.detail) == null ? void 0 : $.kind;
          if (L === "trips") {
            x(!0);
            return;
          }
          if (L === "rois") {
            N(!0);
            return;
          }
          (N(!0), x(!0));
        };
      window.addEventListener("ss-geometry-stringified", k);
      const u = window.setInterval(() => {
        (d && d.value !== b.current && N(!0),
          S && S.value !== g.current && x(!0));
      }, 600);
      return () => {
        (window.clearTimeout(j),
          window.clearInterval(u),
          window.removeEventListener("ss-geometry-stringified", k));
      };
    }, []),
    a.useEffect(() => {
      const d = (u) => {
          (f((p) =>
            p.some((L) => L.svgId === u.svgId)
              ? p
              : [
                  ...p,
                  {
                    svgId: u.svgId,
                    uuid: u.uuid,
                    title: u.title || "",
                    volumetric: u.volumetric ?? !1,
                    height: u.height ?? 1,
                    buffer_size: u.buffer_size ?? 0,
                    greenMin: u.greenMin ?? 0,
                    yellowMin: u.yellowMin ?? 2,
                    redMin: u.redMin ?? 5,
                    rangeMax: u.rangeMax ?? 10,
                    topic:
                      u.topic || `scenescape/event/region/${e}/${u.uuid}/count`,
                  },
                ],
          ),
            N(!0),
            window.requestAnimationFrame(() => {
              var p;
              (p = window.numberRois) == null || p.call(window);
            }));
        },
        S = (u) => {
          (l((p) =>
            p.some((L) => L.svgId === u.svgId)
              ? p
              : [
                  ...p,
                  {
                    svgId: u.svgId,
                    uuid: u.uuid,
                    title: u.title || "",
                    topic:
                      u.topic ||
                      `scenescape/event/tripwire/${e}/${u.uuid}/objects`,
                  },
                ],
          ),
            x(!0),
            window.requestAnimationFrame(() => {
              var p;
              (p = window.numberTripwires) == null || p.call(window);
            }));
        };
      window.ssRoiEditors = {
        addRoi: d,
        addTripwire: S,
        hasRoi: (u) => T.current.some((p) => p.svgId === u),
        hasTripwire: (u) => D.current.some((p) => p.svgId === u),
      };
      const j = (u) => {
          const p = u.detail;
          p != null && p.svgId && d(p);
        },
        k = (u) => {
          const p = u.detail;
          p != null && p.svgId && S(p);
        };
      return (
        window.addEventListener("ss-roi-form-add", j),
        window.addEventListener("ss-tripwire-form-add", k),
        () => {
          (window.removeEventListener("ss-roi-form-add", j),
            window.removeEventListener("ss-tripwire-form-add", k),
            delete window.ssRoiEditors);
        }
      );
    }, [e]),
    a.useEffect(() => {
      He({ regions: h.length, tripwires: c.length });
    }, [h.length, c.length]),
    a.useEffect(() => {
      const d = document.getElementById("no-regions");
      d && (d.style.display = h.length ? "none" : "");
    }, [h.length]),
    a.useEffect(() => {
      const d = document.getElementById("no-tripwires");
      d && (d.style.display = c.length ? "none" : "");
    }, [c.length]),
    a.useEffect(() => {
      const d = document.getElementById("no-regions");
      if (d && ((d.hidden = h.length > 0), h.length === 0)) {
        d.innerHTML = "";
        const S = document.createElement("p");
        if (
          ((S.textContent = "No regions of interest defined."),
          d.appendChild(S),
          s)
        ) {
          const j = document.createElement("button");
          ((j.type = "button"),
            (j.className = "btn btn-primary btn-sm"),
            (j.id = "empty-new-roi"),
            (j.textContent = "+ New Region"),
            d.appendChild(j));
        }
      }
    }, [h.length, s]),
    a.useEffect(() => {
      const d = document.getElementById("no-tripwires");
      if (d && ((d.hidden = c.length > 0), c.length === 0)) {
        d.innerHTML = "";
        const S = document.createElement("p");
        if (((S.textContent = "No tripwires defined."), d.appendChild(S), s)) {
          const j = document.createElement("button");
          ((j.type = "button"),
            (j.className = "btn btn-primary btn-sm"),
            (j.id = "empty-new-tripwire"),
            (j.textContent = "+ New Tripwire"),
            d.appendChild(j));
        }
      }
    }, [c.length, s]));
  const _ = async (d) => {
      var k;
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
      const j = d.replace(/^roi_/, "");
      (ht(j),
        f((u) => u.filter((p) => p.svgId !== d)),
        (k = window.ssMap) == null || k.flushHidden());
      try {
        await m.current();
      } catch {
        N(!0);
      }
    },
    E = async (d) => {
      var k;
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
      const j = d.replace(/^tripwire_/, "");
      (pt(j),
        l((u) => u.filter((p) => p.svgId !== d)),
        (k = window.ssMap) == null || k.flushHidden());
      try {
        await m.current();
      } catch {
        x(!0);
      }
    },
    A = document.getElementById("roi-fields"),
    I = document.getElementById("tripwire-fields");
  return n.jsxs(n.Fragment, {
    children: [
      A
        ? J.createPortal(
            n.jsx(n.Fragment, {
              children: h.map((d, S) =>
                n.jsx(
                  qt,
                  {
                    roi: d,
                    index: S,
                    isSuperuser: s,
                    onChange: (j) => {
                      (N(!0),
                        Te(j),
                        f((k) => k.map((u) => (u.svgId === j.svgId ? j : u))));
                    },
                    onRemove: _,
                  },
                  d.svgId,
                ),
              ),
            }),
            A,
          )
        : null,
      I
        ? J.createPortal(
            n.jsx(n.Fragment, {
              children: c.map((d, S) =>
                n.jsx(
                  zt,
                  {
                    tripwire: d,
                    index: S,
                    isSuperuser: s,
                    onChange: (j) => {
                      (x(!0),
                        re(j.uuid, { title: j.title }),
                        l((k) => k.map((u) => (u.svgId === j.svgId ? j : u))));
                    },
                    onRemove: E,
                  },
                  d.svgId,
                ),
              ),
            }),
            I,
          )
        : null,
    ],
  });
}
function H(e, s = "") {
  return e == null || e === "" ? s : String(e);
}
function qe(e) {
  if (e == null || e === "") return null;
  const s = String(e);
  return /^\d+$/.test(s) ? s : null;
}
function Qt(e) {
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
function me(e, s) {
  return H(e[s]);
}
function Xt(e) {
  const s = qe(e.id),
    t = H(e.sensor_id || e.uid),
    i = H(e.name, t);
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
function Zt(e, s) {
  const t = qe(e.id),
    i = H(e.sensor_id || e.uid),
    r = H(e.name, i);
  if (!t && !i) return null;
  const o = t || i;
  return {
    id: o,
    sensorId: i || o,
    name: r || i || o,
    iconUrl: (s == null ? void 0 : s.iconUrl) ?? null,
    areaJson: Qt(e) || (s == null ? void 0 : s.areaJson) || "{}",
    calibrateHref: `?ss=calibrate-sensor&id=${o}`,
    editHref: `?ss=sensor-edit&id=${i || o}`,
    deleteUrl: t
      ? `/singleton_sensor/delete/${t}/`
      : ((s == null ? void 0 : s.deleteUrl) ?? null),
  };
}
function es(e, s, t) {
  var y;
  const i = H(e.uid || e.id);
  if (!i) return null;
  const r = H(e.child_type || (t == null ? void 0 : t.childType), "local"),
    o = e.child != null ? H(e.child) : null,
    h =
      e.remote_child_id != null
        ? H(e.remote_child_id)
        : ((t == null ? void 0 : t.remoteChildId) ?? null),
    f = o
      ? (y = s.find((N) => N.id === o)) == null
        ? void 0
        : y.name
      : void 0,
    c = H(
      e.name || e.child_name || f || (t == null ? void 0 : t.name),
      "Child",
    ),
    l = r === "local" && o ? o : h || i;
  return {
    id: i,
    name: c,
    childType: r,
    remoteChildId: h,
    detailUrl: o ? `/${o}/` : ((t == null ? void 0 : t.detailUrl) ?? null),
    thumbnailUrl: (t == null ? void 0 : t.thumbnailUrl) ?? null,
    mapUrl: (t == null ? void 0 : t.mapUrl) ?? null,
    restUid: l,
    editHref: `?ss=child-edit&id=${l}`,
    deleteUrl: /^\d+$/.test(i)
      ? `/child/delete/${i}/`
      : ((t == null ? void 0 : t.deleteUrl) ?? null),
  };
}
function ts(e, s, t) {
  const i = e.findIndex(
    (o) =>
      o.id === s.id || o.sensorId === s.sensorId || !!(t && o.sensorId === t),
  );
  if (i < 0) return [...e, s];
  const r = e.slice();
  return (
    (r[i] = { ...e[i], ...s, deleteUrl: s.deleteUrl || e[i].deleteUrl }),
    r
  );
}
function ss(e, s, t) {
  const i = e.findIndex(
    (o) =>
      o.id === s.id || o.sensorId === s.sensorId || !!(t && o.sensorId === t),
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
function ns(e, s, t) {
  const i = e.findIndex(
    (o) => o.id === s.id || o.restUid === s.restUid || !!(t && o.restUid === t),
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
const is = new Set([
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
function rs(e) {
  return !!(e && is.has(e));
}
function os({
  sceneId: e,
  authToken: s,
  isSuperuser: t,
  isKubernetes: i,
  scenes: r,
  cameras: o,
  sensors: h = [],
  onCamerasChange: f,
  onSensorsChange: c,
  onChildrenChange: l,
  mapUrl: y = null,
  mapScale: N = null,
}) {
  var k;
  const { sheet: w, open: x, close: T } = rt(),
    D = a.useCallback(
      (u, p = null) => {
        const L = ae(u);
        (L && ce(L), x(u, p));
      },
      [x],
    ),
    v = a.useCallback(() => {
      const u = ae(w.action);
      (T(), u && ce(u));
    }, [T, w.action]);
  (a.useEffect(() => {
    const u = (p) => {
      const L = p.target;
      if (!L) return;
      const $ = L.closest("a[href]");
      if (!($ != null && $.href)) return;
      let R;
      try {
        R = new URL($.href, window.location.origin);
      } catch {
        return;
      }
      if (R.origin !== window.location.origin) return;
      const C = R.searchParams.get("ss");
      !C ||
        !rs(C) ||
        ((R.pathname === window.location.pathname ||
          R.pathname === `/${e}/` ||
          R.pathname === `/${e}`) &&
          (p.preventDefault(),
          p.stopPropagation(),
          D(C, R.searchParams.get("id"))));
    };
    return (
      document.addEventListener("click", u, !0),
      () => document.removeEventListener("click", u, !0)
    );
  }, [D, e]),
    a.useEffect(() => {
      const u = ae(w.action);
      u && ce(u);
    }, [w.action]));
  const M = a.useCallback(() => {
      window.location.reload();
    }, []),
    b = a.useCallback(
      (u) => {
        if (!u) return;
        const p = Xt(u);
        if (!p) return;
        const L = me(u, "scene"),
          $ = w.action === "cam-edit" && w.id ? String(w.id) : null;
        f((R) =>
          L && L !== e
            ? R.filter(
                (C) =>
                  C.id !== p.id &&
                  C.sensorId !== p.sensorId &&
                  C.sensorId !== $,
              )
            : ts(R, p, $),
        );
      },
      [f, e, w.action, w.id],
    ),
    g = a.useCallback(
      (u) => {
        if (!u) return;
        const p = me(u, "scene"),
          L = w.action === "sensor-edit" && w.id ? String(w.id) : null;
        c(($) => {
          const R = $.find(
              (B) =>
                B.sensorId === L ||
                B.sensorId === String(u.uid || "") ||
                B.id === String(u.id || ""),
            ),
            C = Zt(u, R);
          return C
            ? p && p !== e
              ? $.filter(
                  (B) =>
                    B.id !== C.id &&
                    B.sensorId !== C.sensorId &&
                    B.sensorId !== L,
                )
              : ss($, C, L)
            : $;
        });
      },
      [c, e, w.action, w.id],
    ),
    m = a.useCallback(
      (u) => {
        if (!u) return;
        const p = me(u, "parent"),
          L = w.action === "child-edit" && w.id ? String(w.id) : null;
        l(($) => {
          const R = $.find(
              (B) => B.id === String(u.uid || u.id || "") || B.restUid === L,
            ),
            C = es(u, r, R);
          return C
            ? p && p !== e
              ? $.filter(
                  (B) =>
                    B.id !== C.id && B.restUid !== C.restUid && B.restUid !== L,
                )
              : ns($, C, L)
            : $;
        });
      },
      [l, e, r, w.action, w.id],
    ),
    _ = a.useMemo(() => {
      const u = new Map();
      return (o.forEach((p) => u.set(String(p.id), p)), u);
    }, [o]),
    E = a.useMemo(() => {
      const u = new Map();
      return (o.forEach((p) => u.set(String(p.sensorId), p)), u);
    }, [o]),
    A = a.useMemo(() => {
      const u = new Map();
      return (h.forEach((p) => u.set(String(p.id), p)), u);
    }, [h]);
  if (!t) return null;
  const I = w.action,
    d = I === "calibrate-cam" && w.id ? _.get(String(w.id)) : null,
    S = I === "calibrate-sensor" && w.id ? A.get(String(w.id)) : null,
    j =
      I === "cam-edit" && w.id
        ? ((k = E.get(String(w.id))) == null ? void 0 : k.sensorId) ||
          String(w.id)
        : null;
  return n.jsxs(n.Fragment, {
    children: [
      n.jsx(Ze, {
        open: I === "cam-create" || I === "cam-edit",
        mode: I === "cam-edit" ? "edit" : "create",
        sceneId: e,
        scenes: r,
        sensorUid: I === "cam-edit" ? j : null,
        authToken: s,
        onClose: v,
        onSaved: b,
      }),
      n.jsx(et, {
        open: I === "sensor-create" || I === "sensor-edit",
        mode: I === "sensor-edit" ? "edit" : "create",
        sceneId: e,
        scenes: r,
        sensorUid: I === "sensor-edit" ? w.id : null,
        authToken: s,
        onClose: v,
        onSaved: g,
      }),
      n.jsx(ot, {
        open: I === "child-create" || I === "child-edit",
        mode: I === "child-edit" ? "edit" : "create",
        parentSceneId: e,
        childUid: I === "child-edit" ? w.id : null,
        scenes: r,
        authToken: s,
        onClose: v,
        onSaved: m,
      }),
      n.jsx(at, {
        open: I === "scene-manage",
        sceneId: e,
        authToken: s,
        onClose: v,
        onSaved: M,
      }),
      n.jsx(tt, {
        open: !!d,
        cameraPk: (d == null ? void 0 : d.id) || "",
        sensorId: (d == null ? void 0 : d.sensorId) || "",
        cameraName: (d == null ? void 0 : d.name) || "",
        sceneId: e,
        authToken: s,
        isKubernetes: i,
        onClose: v,
        onSaved: M,
      }),
      n.jsx(st, {
        open: !!S || I === "calibrate-sensor",
        sensorPk: (S == null ? void 0 : S.id) || w.id || "",
        sensorId: (S == null ? void 0 : S.sensorId) || "",
        sceneId: e,
        authToken: s,
        mapUrlHint: y,
        mapScale: N,
        onClose: v,
        onSaved: M,
      }),
    ],
  });
}
const ze = "ss-workspace-layout-mode",
  as = 224,
  cs = 256,
  oe = 120;
function $e() {
  return {
    w: Math.max(window.innerWidth || 0, 320),
    h: Math.max(window.innerHeight || 0, 320),
  };
}
function ls() {
  try {
    const e = window.localStorage.getItem(ze);
    if (e === "auto" || e === "stack" || e === "row") return e;
  } catch {}
  return "auto";
}
function ds(e) {
  try {
    window.localStorage.setItem(ze, e);
  } catch {}
}
function us() {
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
function Le(e, s, t) {
  const i = Math.max(s, oe),
    r = Math.max(t, oe),
    o = Math.min(i / e.w, r / e.h);
  return !Number.isFinite(o) || o <= 0 ? 0 : e.w * o * (e.h * o);
}
function ke(e, s, t) {
  const i = Math.max(e.w - 32, oe),
    r = Math.max(e.h - t, oe);
  if (i < 720 || r / i > 1.25) return "stack";
  if (!s) return i / r >= 1.35 ? "stack" : "row";
  const o = s.w / s.h,
    h = Le(s, i, r - as),
    f = Le(s, i - cs, r);
  return o >= 1.35
    ? h >= f * 0.92
      ? "stack"
      : "row"
    : o <= 1.05
      ? f >= h * 0.92
        ? "row"
        : "stack"
      : f > h
        ? "row"
        : "stack";
}
function ms(e = {}) {
  const s = e.chromeHeightPx ?? 112,
    [t, i] = a.useState(() => (typeof window < "u" ? ls() : "auto")),
    [r, o] = a.useState(() => ke($e(), null, s)),
    h = a.useCallback((c) => {
      (i(c), ds(c));
    }, []);
  return (
    a.useEffect(() => {
      let c = 0,
        l = null;
      const y = () => {
        (cancelAnimationFrame(c),
          (c = requestAnimationFrame(() => {
            const v = ke($e(), us(), s);
            l !== v && ((l = v), o((M) => (M === v ? M : v)));
          })));
      };
      (y(),
        window.addEventListener("resize", y),
        window.addEventListener("ss-map-host-ready", y));
      const N = document.querySelector("#ss-map-host #map img");
      N && !N.complete && N.addEventListener("load", y);
      const w = document.getElementById("ss-map-host");
      let x = null;
      w &&
        typeof ResizeObserver < "u" &&
        ((x = new ResizeObserver(() => y())), x.observe(w));
      const T = window.setInterval(y, 500),
        D = window.setTimeout(() => window.clearInterval(T), 8e3);
      return () => {
        (cancelAnimationFrame(c),
          window.removeEventListener("resize", y),
          window.removeEventListener("ss-map-host-ready", y),
          N == null || N.removeEventListener("load", y),
          x == null || x.disconnect(),
          window.clearInterval(T),
          window.clearTimeout(D));
      };
    }, [s, t]),
    { layout: t === "auto" ? r : t, mode: t, setMode: h, autoLayout: r }
  );
}
function fs() {
  const [e, s] = a.useState(!1);
  return (
    a.useEffect(() => {
      const t = () => {
        const h = document.getElementById("mqtt_status"),
          f = !!(h != null && h.classList.contains("connected"));
        s((c) => (c === f ? c : f));
      };
      t();
      const i = document.getElementById("mqtt_status");
      let r = null;
      i &&
        ((r = new MutationObserver(t)),
        r.observe(i, { attributes: !0, attributeFilter: ["class"] }));
      const o = (h) => {
        const f = h.detail;
        typeof (f == null ? void 0 : f.connected) == "boolean"
          ? s((c) => (c === f.connected ? c : !!f.connected))
          : t();
      };
      return (
        window.addEventListener("ss-mqtt-status", o),
        () => {
          (r == null || r.disconnect(),
            window.removeEventListener("ss-mqtt-status", o));
        }
      );
    }, []),
    e
  );
}
function hs() {
  const [e, s] = a.useState({});
  return (
    a.useEffect(() => {
      const t = (f, c) => {
          s((l) => (l[f] === c ? l : { ...l, [f]: c }));
        },
        i = (f, c) => {
          t(f, c);
        },
        r = () => s({});
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setCameraRate: i,
        clearRates: r,
      };
      const o = (f) => {
          const c = f.detail;
          c != null && c.sensorId && t(c.sensorId, c.text || c.hz || "--");
        },
        h = () => r();
      return (
        window.addEventListener("ss-camera-rate", o),
        window.addEventListener("ss-telemetry-clear", h),
        () => {
          (window.removeEventListener("ss-camera-rate", o),
            window.removeEventListener("ss-telemetry-clear", h));
        }
      );
    }, []),
    e
  );
}
function Q(e) {
  return String(e);
}
function ps(e) {
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
const ws = [
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
function gs({ bootstrap: e }) {
  const { scene: s, urls: t, isSuperuser: i } = e,
    { layout: r, mode: o, setMode: h, autoLayout: f } = ms(),
    {
      panelSizePx: c,
      setPanelSizePx: l,
      mapFocus: y,
      toggleMapFocus: N,
    } = nt(r),
    [w, x] = a.useState("--"),
    [T, D] = a.useState(!1),
    [v, M] = a.useState(!1),
    [b, g] = a.useState(null),
    m = fs(),
    _ = hs(),
    [E, A] = a.useState(e.cameras),
    [I, d] = a.useState(e.sensors || []),
    [S, j] = a.useState(e.children || []),
    [k, u] = a.useState({
      cameras: e.cameras.length,
      sensors: e.counts.sensors,
      regions: e.counts.regions,
      tripwires: e.counts.tripwires,
      children: e.counts.children,
    });
  ((window.ssUseReactMap = !!s.mapUrl),
    a.useEffect(() => {
      const C = (Y) => x(Y || "--");
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setSceneRate: C,
      };
      const B = (Y) => {
          const G = Y.detail;
          (G == null ? void 0 : G.hz) !== void 0 && C(G.hz);
        },
        z = () => x("--");
      return (
        window.addEventListener("ss-scene-rate", B),
        window.addEventListener("ss-telemetry-clear", z),
        () => {
          (window.removeEventListener("ss-scene-rate", B),
            window.removeEventListener("ss-telemetry-clear", z));
        }
      );
    }, []),
    a.useEffect(() => {
      const C = (B) => {
        const z = B.detail;
        !z ||
          typeof z != "object" ||
          u((Y) => {
            const G = { ...Y };
            return (
              [
                "cameras",
                "sensors",
                "regions",
                "tripwires",
                "children",
              ].forEach((be) => {
                const ee = z[be];
                typeof ee == "number" &&
                  Number.isFinite(ee) &&
                  ee >= 0 &&
                  (G[be] = ee);
              }),
              G
            );
          });
      };
      return (
        window.addEventListener(he, C),
        () => window.removeEventListener(he, C)
      );
    }, []),
    a.useEffect(() => {
      const C = window.requestAnimationFrame(() => {
        typeof window.fitSceneMapDisplay == "function" &&
          window.fitSceneMapDisplay();
      });
      return () => window.cancelAnimationFrame(C);
    }, [y, c, r]));
  const p = a.useCallback(async () => {
      if (t.sceneDelete) {
        (M(!0), g(null));
        try {
          await ct(t.sceneDelete, t.scenesHome || "/");
        } catch (C) {
          (M(!1), g(C instanceof Error ? C.message : "Delete failed"));
        }
      }
    }, [t.sceneDelete, t.scenesHome]),
    L = [
      { id: "cameras", label: "Cameras", count: Q(k.cameras) },
      { id: "sensors", label: "Sensors", count: Q(k.sensors) },
      { id: "regions", label: "Regions", count: Q(k.regions) },
      { id: "tripwires", label: "Tripwires", count: Q(k.tripwires) },
      { id: "children", label: "Children", count: Q(k.children) },
      {
        id: "mqtt",
        label: "MQTT",
        extra: n.jsxs("span", {
          id: "mqtt_status",
          className: `scene-detail-mqtt-pill${m ? " connected" : ""}`,
          title: m ? "MQTT connected" : "MQTT disconnected",
          "data-ss-mqtt": m ? "connected" : "disconnected",
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
    $ = n.jsxs(n.Fragment, {
      children: [
        n.jsxs("div", {
          className: "scene-rate ss-scene-rate",
          children: [
            "Rate: ",
            n.jsx("span", { id: "scene-rate", children: w }),
            " Hz",
          ],
        }),
        n.jsx("div", {
          className: "ss-layout-toggle",
          role: "group",
          "aria-label": "Control panel layout",
          children: ws.map((C) => {
            const B = o === C.mode,
              z = C.mode === "auto" ? ` (now ${f})` : "";
            return n.jsxs(
              "button",
              {
                type: "button",
                className: `ss-layout-toggle-btn${B ? " is-active" : ""}`,
                title: `${C.title}${z}`,
                "aria-pressed": B,
                onClick: () => h(C.mode),
                children: [
                  n.jsx("i", {
                    className: `bi ${C.icon}`,
                    "aria-hidden": "true",
                  }),
                  n.jsx("span", {
                    className: "ss-layout-toggle-label",
                    children: C.label,
                  }),
                ],
              },
              C.mode,
            );
          }),
        }),
        n.jsxs("button", {
          type: "button",
          className: `ss-layout-toggle-btn ss-map-focus-btn${y ? " is-active" : ""}`,
          title: y ? "Show control panel (Esc)" : "Map only focus",
          "aria-pressed": y,
          onClick: N,
          children: [
            n.jsx("i", {
              className: `bi ${y ? "bi-layout-sidebar" : "bi-arrows-fullscreen"}`,
              "aria-hidden": "true",
            }),
            n.jsx("span", {
              className: "ss-layout-toggle-label",
              children: y ? "Panel" : "Map",
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
                (g(null), D(!0));
              },
              children: n.jsx("i", {
                className: "bi bi-trash",
                "aria-hidden": "true",
              }),
            })
          : null,
      ],
    }),
    R = e.deleteImpact;
  return n.jsxs("div", {
    className: `ss-scene-detail ss-scene-detail--workspace ss-workspace--${r}${y ? " ss-workspace--map-focus" : ""}`,
    "data-workspace-layout": r,
    "data-workspace-mode": o,
    "data-map-focus": y ? "1" : "0",
    style: { "--ss-panel-size": `${c}px` },
    children: [
      n.jsx(We, { title: s.name, back: ps(t), actions: $ }),
      n.jsxs("div", {
        className: "ss-workspace-body",
        children: [
          n.jsx("div", {
            className: "ss-workspace-main",
            children: n.jsx(Mt, { mapUrl: s.mapUrl }),
          }),
          n.jsx(it, { layout: r, panelSizePx: c, onResize: l, disabled: y }),
          n.jsx(Ot, {
            tabs: L,
            cameraRates: _,
            cameras: E,
            sensors: I,
            childrenLinks: S,
            isSuperuser: i,
            sceneId: s.id,
            wssConnection: e.scene.wssConnection || "",
            authToken: e.authToken,
            onSensorsChange: d,
          }),
        ],
      }),
      n.jsx(Kt, {
        sceneId: s.id,
        isSuperuser: i,
        authToken: e.authToken,
        initialRegions: e.regions || [],
        initialTripwires: e.tripwires || [],
      }),
      n.jsx(os, {
        sceneId: s.id,
        authToken: e.authToken,
        isSuperuser: i,
        isKubernetes: !!e.isKubernetes,
        scenes: e.scenes || [],
        cameras: E,
        sensors: I,
        onCamerasChange: A,
        onSensorsChange: d,
        onChildrenChange: j,
        mapUrl: s.mapUrl,
        mapScale: s.scale,
      }),
      n.jsxs(Pe, {
        open: T,
        title: "Delete scene?",
        confirmLabel: "Delete scene",
        danger: !0,
        busy: v,
        onConfirm: p,
        onCancel: () => {
          v || D(!1);
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
              ((R == null ? void 0 : R.sensors) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      R == null ? void 0 : R.sensors,
                      " camera(s) and/or sensor(s) will be orphaned",
                    ],
                  })
                : null,
              ((R == null ? void 0 : R.regions) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      R == null ? void 0 : R.regions,
                      " region(s) will be deleted",
                    ],
                  })
                : null,
              ((R == null ? void 0 : R.tripwires) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      R == null ? void 0 : R.tripwires,
                      " tripwire(s) will be deleted",
                    ],
                  })
                : null,
            ],
          }),
          b ? n.jsx("p", { className: "ss-confirm-error", children: b }) : null,
        ],
      }),
    ],
  });
}
function bs({ bootstrap: e }) {
  return n.jsx(Je, {
    children: n.jsx(Ye, { children: n.jsx(gs, { bootstrap: e }) }),
  });
}
function ys({ bootstrap: e }) {
  return n.jsx(bs, { bootstrap: e });
}
function vs() {
  const e = document.getElementById("ss-scene-detail-bootstrap");
  if (!(e != null && e.textContent)) return null;
  try {
    return JSON.parse(e.textContent);
  } catch {
    return (console.error("Failed to parse scene detail bootstrap JSON"), null);
  }
}
const Ae = vs(),
  Be = document.getElementById("ss-scene-detail-root");
Ae &&
  Be &&
  (document.documentElement.classList.add("ss-scene-workspace"),
  document.body.classList.add("ss-scene-workspace"),
  Ge.createRoot(Be).render(
    n.jsx(a.StrictMode, { children: n.jsx(ys, { bootstrap: Ae }) }),
  ));
