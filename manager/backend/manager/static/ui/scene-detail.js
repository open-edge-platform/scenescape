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
  W as rt,
} from "./chunks/SensorCalibratePanel-DUJoj046.js";
import { A as W } from "./chunks/actionIcons-BIxtFbWH.js";
import { a as O, u as it } from "./chunks/rest-DXX9fmms.js";
import { C as ot, S as at } from "./chunks/SceneManagePanel-BM8p1vX0.js";
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
    r = {
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
  (P.set(e, r), U(), q());
}
function ie(e, s) {
  const t = F.get(e),
    r = {
      uuid: e,
      title: s.title ?? (t == null ? void 0 : t.title) ?? "",
      points: s.points ?? (t == null ? void 0 : t.points) ?? [],
    };
  (F.set(e, r), U(), q());
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
    const r = String(t.uuid || "").trim();
    if (!r) continue;
    s.add(r);
    const i = (t.points || []).map((c) => [Number(c[0]), Number(c[1])]),
      o = t.sectors && !Array.isArray(t.sectors) ? t.sectors : null,
      h = Array.isArray(t.sectors)
        ? t.sectors
        : o == null
          ? void 0
          : o.thresholds,
      m =
        (o == null ? void 0 : o.range_max) != null
          ? Number(o.range_max)
          : t.range_max != null
            ? Number(t.range_max)
            : void 0;
    we(r, {
      title: t.title,
      points: i,
      volumetric: t.volumetric,
      height: t.height,
      buffer_size: t.buffer_size,
      range_max: m,
      sectors: h,
    });
  }
  for (const t of Array.from(P.keys())) s.has(t) || P.delete(t);
  (U(), q());
}
function jt(e) {
  const s = new Set();
  for (const t of e) {
    const r = String(t.uuid || "").trim();
    if (!r) continue;
    s.add(r);
    const i = (t.points || []).map((o) => [Number(o[0]), Number(o[1])]);
    ie(r, { title: t.title, points: i });
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
      sectors: { thresholds: t.sectors, range_max: t.range_max },
    })),
    s = Z().map((t) => ({ title: t.title, uuid: t.uuid, points: t.points }));
  (ve("id_rois", JSON.stringify(e)), ve("tripwires", JSON.stringify(s)));
}
const te = { top: 32, right: 72, bottom: 12, left: 72 };
function St(e, s) {
  const t = e + te.left + te.right,
    r = s + te.top + te.bottom;
  return `-72 -32 ${t} ${r}`;
}
const Nt = a.memo(function ({ href: s, width: t, height: r }) {
  return n.jsx("image", {
    href: s,
    x: 0,
    y: 0,
    width: t,
    height: r,
    preserveAspectRatio: "none",
  });
});
function xe() {
  return `tmp${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
function Et(e, s, t = 22) {
  const r = s[0] - e[0],
    i = s[1] - e[1],
    o = Math.hypot(r, i);
  if (o < 1) return null;
  const h = (-t * i) / o,
    m = (t * r) / o,
    c = (e[0] + s[0]) / 2,
    d = (e[1] + s[1]) / 2,
    b = c + h,
    E = d + m,
    g = h / t,
    v = m / t,
    I = -v,
    B = g,
    R = [
      `${b},${E}`,
      `${b - g * 8 + I * 4},${E - v * 8 + B * 4}`,
      `${b - g * 8 - I * 4},${E - v * 8 - B * 4}`,
    ].join(" ");
  return { arrow: { x1: c, y1: d, x2: b, y2: E }, head: R };
}
function _t(e) {
  if (!e.length) return null;
  let s = 0,
    t = 0;
  return (
    e.forEach((r) => {
      ((s += r[0]), (t += r[1]));
    }),
    [s / e.length, t / e.length]
  );
}
const Ct = a.memo(function ({ mapHref: s, mapWidth: t, mapHeight: r }) {
  const [i, o] = a.useState(() => X()),
    [h, m] = a.useState(() => Z()),
    [c, d] = a.useState("idle"),
    [b, E] = a.useState([]),
    g = Ve(),
    v = r || Ke(r);
  (a.useEffect(
    () =>
      ft(() => {
        (o(X()), m(Z()));
      }),
    [],
  ),
    a.useEffect(() => {
      var y;
      (y = window.ssReapplyRoiColors) == null || y.call(window);
    }, [i]),
    a.useEffect(() => {
      const y = () => {
          (d("add-roi"), E([]));
        },
        u = () => {
          (d("add-trip"), E([]));
        };
      window.ssMapReact = { startAddRoi: y, startAddTripwire: u };
      const l = (x) => {
        const j = x.target;
        if (!j) return;
        const k = j.closest(
          "#new-roi, #empty-new-roi, #new-tripwire, #empty-new-tripwire",
        );
        k && (x.preventDefault(), k.id.includes("trip") ? u() : y());
      };
      return (
        document.addEventListener("click", l, !0),
        () => {
          (document.removeEventListener("click", l, !0),
            delete window.ssMapReact);
        }
      );
    }, []));
  const I = a.useCallback((y) => Qe(y[0], y[1], g, v), [g, v]),
    B = (y) => {
      if (c === "idle") return;
      const u = y.currentTarget,
        l = u.createSVGPoint();
      ((l.x = y.clientX), (l.y = y.clientY));
      const x = u.getScreenCTM();
      if (!x) return;
      const j = l.matrixTransform(x.inverse()),
        k = ye(j.x, j.y, g, v);
      if (c === "add-roi") {
        if (b.length >= 3) {
          const M = I(b[0]),
            f = j.x - M[0],
            N = j.y - M[1];
          if (Math.hypot(f, N) < 12) {
            const S = xe();
            (we(S, {
              title: "",
              points: b,
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
                  detail: { svgId: `roi_${S}`, uuid: S, title: "" },
                }),
              ),
              E([]),
              d("idle"));
            return;
          }
        }
        E((M) => [...M, k]);
        return;
      }
      if (c === "add-trip") {
        const M = [...b, k];
        if (M.length >= 2) {
          const f = xe();
          (ie(f, { title: "", points: M.slice(0, 2) }),
            window.dispatchEvent(
              new CustomEvent("ss-tripwire-form-add", {
                detail: { svgId: `tripwire_${f}`, uuid: f, title: "" },
              }),
            ),
            E([]),
            d("idle"));
        } else E(M);
      }
    },
    R = (y, u, l, x) => {
      (x.stopPropagation(), x.preventDefault());
      const j = x.target.ownerSVGElement;
      if (!j) return;
      const k = (f) => {
          const N = j.createSVGPoint();
          ((N.x = f.clientX), (N.y = f.clientY));
          const S = j.getScreenCTM();
          if (!S) return;
          const A = N.matrixTransform(S.inverse()),
            p = ye(A.x, A.y, g, v);
          if (y === "roi") {
            const w = X().find(($) => $.uuid === u);
            if (!w) return;
            const L = w.points.map(($, C) => (C === l ? p : $));
            yt(u, L);
          } else {
            const w = Z().find(($) => $.uuid === u);
            if (!w) return;
            const L = w.points.map(($, C) => (C === l ? p : $));
            vt(u, L);
          }
        },
        M = () => {
          (window.removeEventListener("mousemove", k),
            window.removeEventListener("mouseup", M));
        };
      (window.addEventListener("mousemove", k),
        window.addEventListener("mouseup", M));
    },
    T = a.useMemo(() => b.map(I), [b, I]);
  return n.jsxs("svg", {
    id: "svgout",
    className: `ss-react-scene-map${c !== "idle" ? ` is-${c}` : ""}`,
    viewBox: St(t, r),
    preserveAspectRatio: "xMidYMid meet",
    width: "100%",
    height: "100%",
    onClick: B,
    children: [
      n.jsx(Nt, { href: s, width: t, height: r }),
      i.map((y) => {
        const u = y.points.map(I),
          l = u.map((j) => j.join(",")).join(" "),
          x = _t(u);
        return n.jsxs(
          "g",
          {
            id: `roi_${y.uuid}`,
            className: "roi",
            children: [
              n.jsx("polygon", { points: l, className: "ss-react-roi-poly" }),
              y.title && x
                ? n.jsx("text", {
                    className: "ss-react-roi-title",
                    x: x[0],
                    y: x[1],
                    pointerEvents: "none",
                    children: y.title,
                  })
                : null,
              u.map((j, k) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: j[0],
                    cy: j[1],
                    r: 6,
                    onMouseDown: (M) => R("roi", y.uuid, k, M),
                  },
                  k,
                ),
              ),
            ],
          },
          y.uuid,
        );
      }),
      h.map((y) => {
        const u = y.points.map(I);
        if (u.length < 2) return null;
        const l = Et(u[0], u[1]);
        return n.jsxs(
          "g",
          {
            id: `tripwire_${y.uuid}`,
            className: "tripwire",
            children: [
              n.jsx("line", {
                className: "tripline ss-react-trip-line",
                x1: u[0][0],
                y1: u[0][1],
                x2: u[1][0],
                y2: u[1][1],
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
              y.title
                ? n.jsx("text", {
                    className: "ss-react-trip-title",
                    x: (u[0][0] + u[1][0]) / 2,
                    y: (u[0][1] + u[1][1]) / 2 - 14,
                    pointerEvents: "none",
                    children: y.title,
                  })
                : null,
              u.map((x, j) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: x[0],
                    cy: x[1],
                    r: 6,
                    onMouseDown: (k) => R("trip", y.uuid, j, k),
                  },
                  j,
                ),
              ),
            ],
          },
          y.uuid,
        );
      }),
      T.length > 0
        ? n.jsxs("g", {
            className: "ss-react-draft",
            children: [
              c === "add-roi" && T.length >= 3
                ? n.jsx("polygon", {
                    points: T.map((y) => y.join(",")).join(" "),
                    className: "ss-react-draft-poly",
                  })
                : null,
              c === "add-roi" && T.length === 2
                ? n.jsx("polyline", {
                    points: T.map((y) => y.join(",")).join(" "),
                    className: "ss-react-draft-line",
                  })
                : null,
              T.map((y, u) =>
                n.jsx(
                  "circle",
                  { cx: y[0], cy: y[1], r: 5, className: "ss-react-draft-pt" },
                  u,
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
  const r = s.getAttribute("viewBox"),
    i = s.getAttribute("preserveAspectRatio") || "xMidYMid meet";
  (r && t.setAttribute("viewBox", r),
    t.setAttribute("preserveAspectRatio", i),
    t.removeAttribute("width"),
    t.removeAttribute("height"),
    (t.style.width = "100%"),
    (t.style.height = "100%"));
}
const Mt = a.memo(function ({
  mapUrl: s = null,
  mapWidth: t = 1280,
  mapHeight: r = 720,
}) {
  const i = a.useRef(null),
    [o, h] = a.useState(!1),
    [m, c] = a.useState(null),
    d = !!window.ssUseReactMap && !!s;
  (a.useEffect(() => {
    if (!d || !s) {
      c(null);
      return;
    }
    let g = !1;
    const v = new Image();
    return (
      (v.onload = () => {
        !g &&
          v.naturalWidth > 0 &&
          v.naturalHeight > 0 &&
          c({ width: v.naturalWidth, height: v.naturalHeight });
      }),
      (v.src = s),
      () => {
        g = !0;
      }
    );
  }, [d, s]),
    a.useEffect(() => {
      const g = i.current,
        v = document.getElementById(le.host);
      if (!g || !v) return;
      if ((g.appendChild(v), (v.hidden = !1), d)) {
        document.body.classList.add("ss-use-react-map");
        const u = v.querySelector(
          "svg#svgout, svg.ss-snap-legacy, svg#svgout-snap",
        );
        u &&
          (u.classList.add("ss-snap-legacy"),
          u.id === "svgout" && (u.id = "svgout-snap"));
      }
      (mt(), h(!0));
      let I = 0,
        B = -1,
        R = -1;
      const T = () => {
        I ||
          (I = window.requestAnimationFrame(() => {
            I = 0;
            const u = Math.round(g.clientWidth),
              l = Math.round(g.clientHeight);
            if (!(u === B && l === R && B >= 0))
              if (((B = u), (R = l), !d)) je();
              else {
                const x = v.querySelector(".scene-map-stage");
                (x && Se(x), je());
              }
          }));
      };
      window.addEventListener("resize", T);
      let y = null;
      return (
        typeof ResizeObserver < "u" &&
          ((y = new ResizeObserver(() => T())), y.observe(g)),
        T(),
        () => {
          (I && window.cancelAnimationFrame(I),
            window.removeEventListener("resize", T),
            y == null || y.disconnect(),
            document.body.classList.remove("ss-use-react-map"));
          const u = v.querySelector("svg#svgout-snap, svg.ss-snap-legacy");
          if (u && u.id === "svgout-snap") {
            const x = v.querySelector("svg.ss-react-scene-map");
            (!x || x.id !== "svgout") && (u.id = "svgout");
          }
          const l = document.getElementById("ss-legacy-map-parking");
          l && v.parentElement === g && (l.appendChild(v), (v.hidden = !0));
        }
      );
    }, [d]),
    a.useEffect(() => {
      if (!d || !o) return;
      const g = document.getElementById(le.host),
        v = g == null ? void 0 : g.querySelector(".scene-map-stage");
      v && Se(v);
    }, [d, o, m]));
  const b = o ? document.getElementById(le.host) : null,
    E = (b == null ? void 0 : b.querySelector(".scene-map-stage")) ?? null;
  return n.jsxs("div", {
    className: "ss-scene-map-pane",
    children: [
      n.jsx("div", { ref: i, className: "ss-scene-map-slot" }),
      d && E && s && m
        ? J.createPortal(
            n.jsx("div", {
              className: "ss-react-map-layer",
              children: n.jsx(Ct, {
                mapHref: s,
                mapWidth: m.width || t,
                mapHeight: m.height || r,
              }),
            }),
            E,
          )
        : null,
    ],
  });
});
function Rt(e, s, t) {
  if (t < 1) return null;
  switch (e) {
    case "ArrowRight":
      return (s + 1) % t;
    case "ArrowLeft":
      return (s - 1 + t) % t;
    case "Home":
      return 0;
    case "End":
      return t - 1;
    default:
      return null;
  }
}
function It({ count: e, onSelectIndex: s }) {
  const t = a.useRef([]),
    r = a.useCallback((h, m) => {
      t.current[h] = m;
    }, []),
    i = a.useCallback(
      (h) => {
        var m;
        (s(h), (m = t.current[h]) == null || m.focus());
      },
      [s],
    ),
    o = a.useCallback(
      (h, m) => {
        const c = Rt(h.key, m, e);
        c !== null && (h.preventDefault(), i(c));
      },
      [i, e],
    );
  return { setTabRef: r, onTabKeyDown: o };
}
const Ue = "ss-camera-strip-fit";
function Tt() {
  try {
    const e = window.localStorage.getItem(Ue);
    if (e === "cover" || e === "contain") return e;
  } catch {}
  return "contain";
}
function $t(e) {
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
    r = e.querySelector(".rate"),
    i = Oe(s);
  !i &&
    r &&
    ((r.textContent || "").trim() !== "--" && (r.textContent = "--"),
    r.classList.add("telemetry-hide"));
  const o = ((r == null ? void 0 : r.textContent) || "").trim(),
    h = i ? "1" : "0";
  (e.dataset.ssOnline !== h &&
    ((e.dataset.ssOnline = h),
    e.classList.toggle("is-online", i),
    e.classList.toggle("is-offline", !i)),
    e.dataset.ssRate !== (o || "--") && (e.dataset.ssRate = o || "--"));
  let m = e.querySelector(".ss-camera-strip-badge");
  m ||
    ((m = document.createElement("span")),
    (m.className = "ss-camera-strip-badge"),
    m.setAttribute("aria-hidden", "true"),
    (e.querySelector(".card-header") || e).appendChild(m));
  const c = i ? "Live" : "Offline";
  (m.textContent !== c && (m.textContent = c),
    m.classList.toggle("is-online", i),
    m.classList.toggle("is-offline", !i),
    t && t.hidden !== i && (t.hidden = i));
}
function kt({ rates: e = {} }) {
  const [s, t] = a.useState(() => (typeof window < "u" ? Tt() : "contain"));
  return (
    a.useEffect(() => {
      const r = document.documentElement;
      ((r.dataset.ssCameraFit = s), $t(s));
      const i = document.getElementById("cameras");
      i && ((i.dataset.ssCameraFit = s), i.classList.add("ss-camera-strip"));
    }, [s]),
    a.useEffect(() => {
      Object.entries(e).forEach(([r, i]) => {
        var c;
        const o =
            (c = document.querySelector(
              `[data-ss-card-sensor="${CSS.escape(r)}"]`,
            )) == null
              ? void 0
              : c.closest(".camera-card"),
          h =
            o == null
              ? void 0
              : o.querySelector(
                  "img[data-ss-card-sensor], img[id^='card-preview-']",
                ),
          m = document.getElementById(`rate-${r}`);
        if (!Oe(h)) {
          (m &&
            ((m.textContent || "").trim() !== "--" && (m.textContent = "--"),
            m.classList.add("telemetry-hide")),
            o && de(o));
          return;
        }
        (m &&
          m.textContent !== i &&
          ((m.textContent = i), m.classList.remove("telemetry-hide")),
          o && de(o));
      });
    }, [e]),
    a.useEffect(() => {
      const r = document.getElementById("cameras");
      if (!r) return;
      r.classList.add("ss-camera-strip");
      let i = 0,
        o = !1;
      const h = () => {
          if (!o) {
            o = !0;
            try {
              r.querySelectorAll(".camera-card").forEach(de);
            } finally {
              o = !1;
            }
          }
        },
        m = () => {
          i ||
            (i = window.requestAnimationFrame(() => {
              ((i = 0), h());
            }));
        };
      h();
      const c = new MutationObserver(m);
      c.observe(r, {
        subtree: !0,
        childList: !0,
        attributes: !0,
        attributeFilter: ["class", "src"],
      });
      const d = window.setInterval(h, 2e3);
      return () => {
        (c.disconnect(),
          window.clearInterval(d),
          i && window.cancelAnimationFrame(i));
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
  var t, r;
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
      (r = window.ssToast) == null ||
        r.show("Could not copy to clipboard", "bad"),
      !1
    );
  }
}
function Lt({ cameras: e, isSuperuser: s }) {
  return (
    a.useEffect(() => {
      const t = () => {
        var o;
        return (o = window.ssRefreshCameraSnapshots) == null
          ? void 0
          : o.call(window);
      };
      t();
      const r = window.setTimeout(t, 400),
        i = window.setTimeout(t, 1200);
      return () => {
        (window.clearTimeout(r), window.clearTimeout(i));
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
function At({ sensors: e, isSuperuser: s, onDelete: t }) {
  return (
    a.useEffect(() => {
      var r;
      (r = window.ssDrawSingletonSensors) == null || r.call(window);
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
          children: e.map((r) =>
            n.jsxs(
              "div",
              {
                className: "ss-tab-row singleton count-item",
                "data-sensor-name": r.name,
                children: [
                  r.iconUrl
                    ? n.jsx("img", {
                        className: "sensor-icon ss-tab-row__icon",
                        width: 20,
                        height: 20,
                        src: r.iconUrl,
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
                        children: r.name,
                      }),
                      n.jsx("button", {
                        type: "button",
                        className:
                          "ss-tab-row__meta sensor-id ss-tab-row__copy-id",
                        title: "Click to copy ID",
                        onClick: () => void ge(r.sensorId),
                        children: r.sensorId,
                      }),
                    ],
                  }),
                  n.jsx("input", {
                    type: "hidden",
                    className: "area-json",
                    value: r.areaJson,
                    readOnly: !0,
                  }),
                  s
                    ? n.jsxs("div", {
                        className: "ss-tab-row__actions ss-entity-actions",
                        children: [
                          n.jsx("a", {
                            className: "ss-icon-btn sensor_calibrate",
                            href: r.calibrateHref,
                            id: `sensor_calibrate_${r.id}`,
                            title: `Configure ${r.name}`,
                            "aria-label": `Configure ${r.name}`,
                            children: n.jsx("i", {
                              className: `bi ${W.configure}`,
                              "aria-hidden": "true",
                            }),
                          }),
                          t
                            ? n.jsx("button", {
                                type: "button",
                                className: "ss-icon-btn ss-icon-btn--danger",
                                title: `Delete ${r.name}`,
                                "aria-label": `Delete ${r.name}`,
                                onClick: () => t(r),
                                children: n.jsx("i", {
                                  className: `bi ${W.delete}`,
                                  "aria-hidden": "true",
                                }),
                              })
                            : r.deleteUrl
                              ? n.jsx("a", {
                                  className: "ss-icon-btn ss-icon-btn--danger",
                                  href: r.deleteUrl,
                                  title: `Delete ${r.name}`,
                                  "aria-label": `Delete ${r.name}`,
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
              r.id,
            ),
          ),
        })
  );
}
function Bt({ childrenLinks: e, isSuperuser: s }) {
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
          const r = t.thumbnailUrl || t.mapUrl,
            i = r
              ? n.jsx("img", { src: r, alt: `${t.name} map` })
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
                        children: i,
                      })
                    : i,
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
function Dt({
  cameras: e,
  sensors: s,
  childrenLinks: t,
  isSuperuser: r,
  panelsReady: i,
  authToken: o = "",
  onSensorsChange: h,
}) {
  const m = De(),
    [c, d] = a.useState(null),
    [b, E] = a.useState(!1),
    [g, v] = a.useState(null);
  a.useEffect(() => {
    var l;
    i &&
      (He({ cameras: e.length, sensors: s.length, children: t.length }),
      (l = window.numberTabs) == null || l.call(window));
  }, [i, e, s, t]);
  const I = a.useCallback(async () => {
      var l;
      if (!(!c || !o || !h)) {
        (E(!0), v(null));
        try {
          (await O.deleteSensor(o, c.sensorId),
            (l = window.ssRemoveSingletonSensor) == null ||
              l.call(window, c.sensorId),
            h((x) =>
              x.filter((j) => j.id !== c.id && j.sensorId !== c.sensorId),
            ),
            m.show("Sensor deleted", "ok"),
            d(null));
        } catch (x) {
          v(x.message || "Delete failed");
        } finally {
          E(!1);
        }
      }
    }, [o, h, c, m]),
    B = a.useCallback((l) => {
      (v(null), d(l));
    }, []);
  if (!i) return null;
  const R = document.getElementById("ss-cameras-mount"),
    T = document.getElementById("ss-sensors-mount"),
    y = document.getElementById("ss-children-mount"),
    u = !!(o && h);
  return n.jsxs(n.Fragment, {
    children: [
      R ? J.createPortal(n.jsx(Lt, { cameras: e, isSuperuser: r }), R) : null,
      T
        ? J.createPortal(
            n.jsx(At, { sensors: s, isSuperuser: r, onDelete: u ? B : void 0 }),
            T,
          )
        : null,
      y
        ? J.createPortal(n.jsx(Bt, { childrenLinks: t, isSuperuser: r }), y)
        : null,
      n.jsxs(Pe, {
        open: !!c,
        title: "Delete sensor?",
        confirmLabel: "Delete",
        danger: !0,
        busy: b,
        onConfirm: I,
        onCancel: () => {
          b || (d(null), v(null));
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
          g ? n.jsx("p", { className: "ss-confirm-error", children: g }) : null,
        ],
      }),
    ],
  });
}
function Pt({ wssConnection: e, sceneId: s, panelsReady: t }) {
  return (
    a.useEffect(() => {
      var o;
      if (!t) return;
      const r = document.getElementById("broker"),
        i = document.getElementById("topic");
      (r && e && !r.value && (r.value = e),
        i && s && !i.value && (i.value = `scenescape/regulated/scene/${s}`),
        (o = window.ssEnsureMqttScene) == null || o.call(window));
    }, [t, e, s]),
    null
  );
}
function Ft({ id: e, title: s, children: t, footer: r, onClose: i }) {
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
                onClick: i,
                children: n.jsx("span", {
                  "aria-hidden": "true",
                  children: "×",
                }),
              }),
            ],
          }),
          n.jsx("div", { className: "modal-body", children: t }),
          r ? n.jsx("div", { className: "modal-footer", children: r }) : null,
        ],
      }),
    }),
  });
}
const Ht = [
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
function Ut() {
  return n.jsx(n.Fragment, {
    children: Ht.map((e) =>
      n.jsx(
        Ft,
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
function Ee({ id: e, labelId: s, label: t, title: r }) {
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
        title: r,
        id: s,
        children: t,
      }),
    ],
  });
}
function Ot({ activeTab: e, isSuperuser: s }) {
  const [t, r] = a.useState(() => !!window.ssRoiDirty),
    [i, o] = a.useState(() => !!window.ssTripDirty);
  return (
    a.useEffect(() => {
      const h = (c) => {
          r(!!c.detail);
        },
        m = (c) => {
          o(!!c.detail);
        };
      return (
        window.addEventListener("ss-roi-dirty", h),
        window.addEventListener("ss-trip-dirty", m),
        r(!!window.ssRoiDirty),
        o(!!window.ssTripDirty),
        () => {
          (window.removeEventListener("ss-roi-dirty", h),
            window.removeEventListener("ss-trip-dirty", m));
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
                          className: `btn btn-sm btn-primary${i ? " ss-save-dirty" : " ss-save-clean"}`,
                          id: "save-trips",
                          title: i
                            ? "Save unsaved changes"
                            : "No unsaved changes",
                          disabled: !i,
                          "aria-disabled": i ? "false" : "true",
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
  qt = {
    cameras: "cameras-tab",
    sensors: "sensors-tab",
    regions: "regions-tab",
    tripwires: "tripwires-tab",
    children: "children-tab",
    mqtt: "settings-tab",
  };
function zt({
  tabs: e,
  cameraRates: s = {},
  cameras: t = [],
  sensors: r = [],
  childrenLinks: i = [],
  isSuperuser: o = !1,
  sceneId: h = "",
  wssConnection: m = "",
  authToken: c = "",
  onSensorsChange: d,
}) {
  const [b, E] = a.useState(() => dt(h)),
    [g, v] = a.useState(!1),
    I = a.useRef(null);
  (a.useEffect(() => {
    const u = I.current,
      l = document.getElementById("scene-detail-panels");
    if (!(!u || !l))
      return (
        u.appendChild(l),
        (l.hidden = !1),
        l.classList.add("ss-legacy-panels-adopted"),
        v(!0),
        () => {
          v(!1);
          const x = document.getElementById("ss-legacy-panels-parking");
          x && l.parentElement === u && (x.appendChild(l), (l.hidden = !0));
        }
      );
  }, []),
    a.useEffect(() => {
      Object.entries(_e).forEach(([u, l]) => {
        const x = document.getElementById(l);
        if (!x) return;
        const j = u === b;
        (x.classList.toggle("show", j), x.classList.toggle("active", j));
      });
    }, [b]),
    a.useEffect(() => {
      ut(h, b);
    }, [h, b]),
    a.useEffect(() => {
      const u = (l) => {
        const x = l.detail,
          j = x == null ? void 0 : x.tabId;
        (j === "cameras" ||
          j === "sensors" ||
          j === "regions" ||
          j === "tripwires" ||
          j === "children" ||
          j === "mqtt") &&
          E(j);
      };
      return (
        window.addEventListener(fe, u),
        () => window.removeEventListener(fe, u)
      );
    }, []));
  const B = a.useCallback((u) => {
      (u === "cameras" ||
        u === "sensors" ||
        u === "regions" ||
        u === "tripwires" ||
        u === "children" ||
        u === "mqtt") &&
        E(u);
    }, []),
    R = a.useCallback(
      (u) => {
        const l = e[u];
        l && B(l.id);
      },
      [B, e],
    ),
    { setTabRef: T, onTabKeyDown: y } = It({
      count: e.length,
      onSelectIndex: R,
    });
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
                children: e.map((u, l) => {
                  const x = u.id === b,
                    j = qt[u.id] || `ss-tab-${u.id}`;
                  return n.jsxs(
                    "button",
                    {
                      ref: (k) => T(l, k),
                      type: "button",
                      role: "tab",
                      id: j,
                      "aria-selected": x,
                      "aria-controls": _e[u.id] || u.id,
                      tabIndex: x ? 0 : -1,
                      className: `ss-tabs-tab${x ? " is-active" : ""}`,
                      onClick: () => B(u.id),
                      onKeyDown: (k) => y(k, l),
                      children: [
                        n.jsx("span", {
                          className: "ss-tabs-label",
                          children: u.label,
                        }),
                        u.count !== void 0 && u.count !== null
                          ? n.jsx("span", {
                              className: "ss-tabs-count",
                              children: u.count,
                            })
                          : null,
                        u.extra,
                      ],
                    },
                    u.id,
                  );
                }),
              }),
              n.jsx("div", {
                className: "ss-tabs-toolbar",
                "data-active-tab": b,
                children: n.jsx(Ot, { activeTab: b, isSuperuser: o }),
              }),
              b === "cameras" ? n.jsx(kt, { rates: s }) : null,
            ],
          }),
          n.jsx("div", {
            className: "ss-tabs-panels",
            children: n.jsx("div", {
              ref: I,
              className: "ss-legacy-panels-slot",
            }),
          }),
        ],
      }),
      n.jsx(Dt, {
        cameras: t,
        sensors: r,
        childrenLinks: i,
        isSuperuser: o,
        panelsReady: g,
        authToken: c,
        onSensorsChange: d,
      }),
      n.jsx(Pt, { wssConnection: m, sceneId: h, panelsReady: g }),
      n.jsx(Ut, {}),
    ],
  });
}
function Gt({ roi: e, index: s, isSuperuser: t, onChange: r, onRemove: i }) {
  const o = !t || e.readOnly,
    [h, m] = a.useState(!1),
    c = `roi-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-roi",
    id: `form-${e.svgId}`,
    ref: (d) => (d == null ? void 0 : d.setAttribute("for", e.svgId)),
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
                  onChange: (d) => r({ ...e, title: d.target.value }),
                  onBlur: () => {
                    var d, b;
                    if (window.ssUseReactMap) {
                      (b =
                        (d = window.ssMap) == null ? void 0 : d.numberRois) ==
                        null || b.call(d);
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
                  onClick: () => m((d) => !d),
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
                  onClick: (d) => {
                    (d.preventDefault(), d.stopPropagation(), i(e.svgId));
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
                                onChange: (d) =>
                                  r({ ...e, volumetric: d.target.checked }),
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
                                  r({
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
                                  r({
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
                    onChange: (d) =>
                      r({
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
function Wt({
  tripwire: e,
  index: s,
  isSuperuser: t,
  onChange: r,
  onRemove: i,
}) {
  const o = !!t && !e.readOnly,
    [h, m] = a.useState(!1),
    c = `trip-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-tripwire",
    id: `form-${e.svgId}`,
    ref: (d) => (d == null ? void 0 : d.setAttribute("for", e.svgId)),
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
                  onChange: (d) => {
                    o && r({ ...e, title: d.target.value });
                  },
                  onBlur: () => {
                    var d, b, E;
                    if (window.ssUseReactMap) {
                      (b =
                        (d = window.ssMap) == null
                          ? void 0
                          : d.numberTripwires) == null || b.call(d);
                      return;
                    }
                    (E = window.numberTripwires) == null || E.call(window);
                  },
                }),
                n.jsx("button", {
                  type: "button",
                  className: "ss-editor-row__toggle",
                  "aria-expanded": h,
                  "aria-controls": c,
                  title: h ? "Hide details" : "Show details",
                  onClick: () => m((d) => !d),
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
                  onClick: (d) => {
                    (d.preventDefault(), d.stopPropagation(), i(e.svgId));
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
function Jt(e) {
  const s = e.sectors;
  if (Array.isArray(s))
    return typeof e.range_max != "number"
      ? null
      : { sectors: s, range_max: e.range_max };
  if (s && Array.isArray(s.thresholds)) {
    const t =
      typeof s.range_max == "number"
        ? s.range_max
        : typeof e.range_max == "number"
          ? e.range_max
          : 10;
    return { sectors: s.thresholds, range_max: t };
  }
  return null;
}
function Yt(e, s) {
  const r = {
      name: (s.title || "").trim() || `roi_${s.uuid || "new"}`,
      scene: e,
      points: s.points || [],
      volumetric: !!s.volumetric,
      height: typeof s.height == "number" ? s.height : 1,
      buffer_size: typeof s.buffer_size == "number" ? s.buffer_size : 0,
    },
    i = Jt(s);
  return (
    i && (r.color_ranges = { sectors: i.sectors, range_max: i.range_max }),
    r
  );
}
function Vt(e, s) {
  return {
    name: (s.title || "").trim() || `tripwire_${s.uuid || "new"}`,
    scene: e,
    points: s.points || [],
    ...(typeof s.height == "number" ? { height: s.height } : {}),
  };
}
async function Kt(e, s, t) {
  var I, B, R, T, y, u;
  let r, i;
  if (t != null && t.preferHidden)
    ((r = ne("id_rois")),
      (i = ne("tripwires")),
      (B = (I = window.ssMap) == null ? void 0 : I.syncFromLegacyStringify) ==
        null || B.call(I));
  else {
    const l =
        (T = (R = window.ssMap) == null ? void 0 : R.getRois) == null
          ? void 0
          : T.call(R),
      x =
        (u = (y = window.ssMap) == null ? void 0 : y.getTripwires) == null
          ? void 0
          : u.call(y);
    ((r = l
      ? l.map((j) => ({
          uuid: j.uuid,
          title: j.title,
          points: j.points,
          volumetric: j.volumetric,
          height: j.height,
          buffer_size: j.buffer_size,
          range_max: j.range_max,
          sectors: j.sectors,
        }))
      : ne("id_rois")),
      (i = x
        ? x.map((j) => ({ uuid: j.uuid, title: j.title, points: j.points }))
        : ne("tripwires")));
  }
  const [o, h] = await Promise.all([
      O.getRegions(e, s).then(Me),
      O.getTripwires(e, s).then(Me),
    ]),
    m = new Set(o.map(se).filter((l) => !!l)),
    c = new Set(),
    d = {};
  for (const l of r) {
    const x = Yt(s, l);
    if (Ce(l.uuid) && m.has(l.uuid))
      (await O.updateRegion(e, l.uuid, x), c.add(l.uuid), (d[l.uuid] = l.uuid));
    else {
      const j = await O.createRegion(e, x),
        k = se(j);
      k && (c.add(k), l.uuid && (d[l.uuid] = k));
    }
  }
  for (const l of m) c.has(l) || (await O.deleteRegion(e, l));
  const b = new Set(h.map(se).filter((l) => !!l)),
    E = new Set(),
    g = {};
  for (const l of i) {
    const x = Vt(s, l);
    if (Ce(l.uuid) && b.has(l.uuid))
      (await O.updateTripwire(e, l.uuid, x),
        E.add(l.uuid),
        (g[l.uuid] = l.uuid));
    else {
      const j = await O.createTripwire(e, x),
        k = se(j);
      k && (E.add(k), l.uuid && (g[l.uuid] = k));
    }
  }
  for (const l of b) E.has(l) || (await O.deleteTripwire(e, l));
  let v = !1;
  for (const [l, x] of Object.entries(d)) wt(l, x) && (v = !0);
  for (const [l, x] of Object.entries(g)) gt(l, x) && (v = !0);
  return (v && bt(), { roiIds: d, tripIds: g });
}
function K(e) {
  const s = window[e];
  typeof s == "function" && s();
}
function Qt() {
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
  const r = e == null ? void 0 : e.find((o) => o.color === s);
  if (!r) return t;
  const i = Number(r.color_min);
  return Number.isFinite(i) ? i : t;
}
function Re(e, s) {
  var i, o;
  const t = String(e.uuid || "").trim();
  if (!t) return null;
  const r = ((i = e.sectors) == null ? void 0 : i.thresholds) || [];
  return {
    svgId: `roi_${t}`,
    uuid: t,
    title: (e.title || "").trim(),
    volumetric: !!e.volumetric,
    height: Number(e.height ?? 1),
    buffer_size: Number(e.buffer_size ?? 0),
    greenMin: ue(r, "green", 0),
    yellowMin: ue(r, "yellow", 2),
    redMin: ue(r, "red", 5),
    rangeMax: Number(((o = e.sectors) == null ? void 0 : o.range_max) ?? 10),
    topic: `scenescape/event/region/${s}/${t}/count`,
  };
}
function Xt(e, s) {
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
  return e.map((r) => {
    const i = s[r.uuid];
    return !i || i === r.uuid
      ? r
      : {
          ...r,
          uuid: i,
          svgId: `${t}_${i}`,
          topic: r.topic.split(r.uuid).join(i),
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
function Te(e, s) {
  var r;
  const t = [
    { color: "green", color_min: e.greenMin },
    { color: "yellow", color_min: e.yellowMin },
    { color: "red", color_min: e.redMin },
  ];
  (we(e.uuid, {
    title: e.title,
    volumetric: e.volumetric,
    height: e.height,
    buffer_size: e.buffer_size,
    range_max: e.rangeMax,
    sectors: t,
    ...(s ? { points: s.map((i) => [Number(i[0]), Number(i[1])]) } : {}),
  }),
    (r = window.ssSyncRoiColorSectors) == null ||
      r.call(window, e.uuid, { thresholds: t, range_max: e.rangeMax }));
}
function Zt({
  sceneId: e,
  isSuperuser: s,
  authToken: t,
  initialRegions: r,
  initialTripwires: i,
}) {
  const o = De(),
    [h, m] = a.useState(() => r.map((f) => Re(f, e)).filter((f) => !!f)),
    [c, d] = a.useState(() => i.map((f) => Xt(f, e)).filter((f) => !!f)),
    [b, E] = a.useState(!1),
    [g, v] = a.useState(!1),
    I = a.useRef(h),
    B = a.useRef(c),
    R = a.useRef(!1),
    T = a.useRef(o),
    y = a.useRef(""),
    u = a.useRef(""),
    l = a.useRef(() => {});
  ((T.current = o),
    (I.current = h),
    (B.current = c),
    a.useEffect(() => {
      (Qt(),
        r.forEach((f) => {
          if (!String(f.uuid || "").trim()) return;
          const S = Re(f, e);
          S && Te(S, f.points);
        }),
        i.forEach((f) => {
          const N = String(f.uuid || "").trim();
          N &&
            ie(N, {
              title: (f.title || "").trim(),
              points: (f.points || []).map((S) => [Number(S[0]), Number(S[1])]),
            });
        }));
    }, [r, i, e]),
    a.useEffect(() => {
      l.current = async (f) => {
        var S, A, p, w, L, $, C;
        if (R.current) return;
        R.current = !0;
        const N = f && !Array.isArray(f) ? f : void 0;
        N != null && N.preferHidden
          ? (A =
              (S = window.ssMap) == null
                ? void 0
                : S.syncFromLegacyStringify) == null || A.call(S)
          : window.ssUseReactMap
            ? (L = window.ssMap) == null || L.flushHidden()
            : ((p = window.ssMap) == null || p.stringifyRois(),
              (w = window.ssMap) == null || w.stringifyTripwires());
        try {
          const _ = await Kt(t, e, N);
          (m((D) => Ie(D, _.roiIds, "roi")),
            d((D) => Ie(D, _.tripIds, "tripwire")),
            (y.current =
              (($ = document.getElementById("id_rois")) == null
                ? void 0
                : $.value) ?? y.current),
            (u.current =
              ((C = document.getElementById("tripwires")) == null
                ? void 0
                : C.value) ?? u.current),
            re("roi", !1),
            re("trip", !1),
            E(!1),
            v(!1),
            T.current.show("Regions saved", "ok"));
        } catch (_) {
          const D =
            _ && typeof _ == "object" && "message" in _
              ? String(_.message || "Save failed")
              : "Save failed";
          throw (T.current.show(D, "bad"), _);
        } finally {
          R.current = !1;
        }
      };
    }, [t, e]),
    a.useEffect(() => {
      const f = (N) => l.current(N);
      return (
        (window.ssPersistGeometry = f),
        () => {
          window.ssPersistGeometry === f && delete window.ssPersistGeometry;
        }
      );
    }, []),
    a.useEffect(() => {
      re("roi", b);
    }, [b]),
    a.useEffect(() => {
      re("trip", g);
    }, [g]),
    a.useEffect(() => {
      const f = document.getElementById("id_rois"),
        N = document.getElementById("tripwires");
      ((y.current = (f == null ? void 0 : f.value) ?? ""),
        (u.current = (N == null ? void 0 : N.value) ?? ""));
      const S = window.setTimeout(() => {
          var w;
          ((y.current = (f == null ? void 0 : f.value) ?? ""),
            (u.current = (N == null ? void 0 : N.value) ?? ""),
            (w = window.ssMap) == null || w.syncFromLegacyStringify());
        }, 1200),
        A = (w) => {
          var $;
          const L = ($ = w.detail) == null ? void 0 : $.kind;
          if (L === "trips") {
            v(!0);
            return;
          }
          if (L === "rois") {
            E(!0);
            return;
          }
          (E(!0), v(!0));
        };
      window.addEventListener("ss-geometry-stringified", A);
      const p = window.setInterval(() => {
        (f && f.value !== y.current && E(!0),
          N && N.value !== u.current && v(!0));
      }, 600);
      return () => {
        (window.clearTimeout(S),
          window.clearInterval(p),
          window.removeEventListener("ss-geometry-stringified", A));
      };
    }, []),
    a.useEffect(() => {
      const f = (p) => {
          (m((w) =>
            w.some((L) => L.svgId === p.svgId)
              ? w
              : [
                  ...w,
                  {
                    svgId: p.svgId,
                    uuid: p.uuid,
                    title: p.title || "",
                    volumetric: p.volumetric ?? !1,
                    height: p.height ?? 1,
                    buffer_size: p.buffer_size ?? 0,
                    greenMin: p.greenMin ?? 0,
                    yellowMin: p.yellowMin ?? 2,
                    redMin: p.redMin ?? 5,
                    rangeMax: p.rangeMax ?? 10,
                    topic:
                      p.topic || `scenescape/event/region/${e}/${p.uuid}/count`,
                  },
                ],
          ),
            E(!0),
            window.requestAnimationFrame(() => {
              var w;
              (w = window.numberRois) == null || w.call(window);
            }));
        },
        N = (p) => {
          (d((w) =>
            w.some((L) => L.svgId === p.svgId)
              ? w
              : [
                  ...w,
                  {
                    svgId: p.svgId,
                    uuid: p.uuid,
                    title: p.title || "",
                    topic:
                      p.topic ||
                      `scenescape/event/tripwire/${e}/${p.uuid}/objects`,
                  },
                ],
          ),
            v(!0),
            window.requestAnimationFrame(() => {
              var w;
              (w = window.numberTripwires) == null || w.call(window);
            }));
        };
      window.ssRoiEditors = {
        addRoi: f,
        addTripwire: N,
        hasRoi: (p) => I.current.some((w) => w.svgId === p),
        hasTripwire: (p) => B.current.some((w) => w.svgId === p),
      };
      const S = (p) => {
          const w = p.detail;
          w != null && w.svgId && f(w);
        },
        A = (p) => {
          const w = p.detail;
          w != null && w.svgId && N(w);
        };
      return (
        window.addEventListener("ss-roi-form-add", S),
        window.addEventListener("ss-tripwire-form-add", A),
        () => {
          (window.removeEventListener("ss-roi-form-add", S),
            window.removeEventListener("ss-tripwire-form-add", A),
            delete window.ssRoiEditors);
        }
      );
    }, [e]),
    a.useEffect(() => {
      He({ regions: h.length, tripwires: c.length });
    }, [h.length, c.length]),
    a.useEffect(() => {
      const f = document.getElementById("no-regions");
      f && (f.style.display = h.length ? "none" : "");
    }, [h.length]),
    a.useEffect(() => {
      const f = document.getElementById("no-tripwires");
      f && (f.style.display = c.length ? "none" : "");
    }, [c.length]),
    a.useEffect(() => {
      const f = document.getElementById("no-regions");
      if (f && ((f.hidden = h.length > 0), h.length === 0)) {
        f.innerHTML = "";
        const N = document.createElement("p");
        if (
          ((N.textContent = "No regions of interest defined."),
          f.appendChild(N),
          s)
        ) {
          const S = document.createElement("button");
          ((S.type = "button"),
            (S.className = "btn btn-primary btn-sm"),
            (S.id = "empty-new-roi"),
            (S.textContent = "+ New Region"),
            f.appendChild(S));
        }
      }
    }, [h.length, s]),
    a.useEffect(() => {
      const f = document.getElementById("no-tripwires");
      if (f && ((f.hidden = c.length > 0), c.length === 0)) {
        f.innerHTML = "";
        const N = document.createElement("p");
        if (((N.textContent = "No tripwires defined."), f.appendChild(N), s)) {
          const S = document.createElement("button");
          ((S.type = "button"),
            (S.className = "btn btn-primary btn-sm"),
            (S.id = "empty-new-tripwire"),
            (S.textContent = "+ New Tripwire"),
            f.appendChild(S));
        }
      }
    }, [c.length, s]));
  const x = async (f) => {
      var A;
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
      const S = f.replace(/^roi_/, "");
      (ht(S),
        m((p) => p.filter((w) => w.svgId !== f)),
        (A = window.ssMap) == null || A.flushHidden());
      try {
        await l.current();
      } catch {
        E(!0);
      }
    },
    j = async (f) => {
      var A;
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
      const S = f.replace(/^tripwire_/, "");
      (pt(S),
        d((p) => p.filter((w) => w.svgId !== f)),
        (A = window.ssMap) == null || A.flushHidden());
      try {
        await l.current();
      } catch {
        v(!0);
      }
    },
    k = document.getElementById("roi-fields"),
    M = document.getElementById("tripwire-fields");
  return n.jsxs(n.Fragment, {
    children: [
      k
        ? J.createPortal(
            n.jsx(n.Fragment, {
              children: h.map((f, N) =>
                n.jsx(
                  Gt,
                  {
                    roi: f,
                    index: N,
                    isSuperuser: s,
                    onChange: (S) => {
                      (E(!0),
                        Te(S),
                        m((A) => A.map((p) => (p.svgId === S.svgId ? S : p))));
                    },
                    onRemove: x,
                  },
                  f.svgId,
                ),
              ),
            }),
            k,
          )
        : null,
      M
        ? J.createPortal(
            n.jsx(n.Fragment, {
              children: c.map((f, N) =>
                n.jsx(
                  Wt,
                  {
                    tripwire: f,
                    index: N,
                    isSuperuser: s,
                    onChange: (S) => {
                      (v(!0),
                        ie(S.uuid, { title: S.title }),
                        d((A) => A.map((p) => (p.svgId === S.svgId ? S : p))));
                    },
                    onRemove: j,
                  },
                  f.svgId,
                ),
              ),
            }),
            M,
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
function es(e) {
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
function ts(e) {
  const s = qe(e.id),
    t = H(e.sensor_id || e.uid),
    r = H(e.name, t);
  if (!s && !t) return null;
  const i = s || t;
  return {
    id: i,
    sensorId: t || i,
    name: r || t || i,
    calibrateHref: `?ss=calibrate-cam&id=${i}`,
    cmdTopic: `scenescape/cmd/camera/${t || i}`,
    deleteUrl: s ? `/cam/delete/${s}/` : null,
  };
}
function ss(e, s) {
  const t = qe(e.id),
    r = H(e.sensor_id || e.uid),
    i = H(e.name, r);
  if (!t && !r) return null;
  const o = t || r;
  return {
    id: o,
    sensorId: r || o,
    name: i || r || o,
    iconUrl: (s == null ? void 0 : s.iconUrl) ?? null,
    areaJson: es(e) || (s == null ? void 0 : s.areaJson) || "{}",
    calibrateHref: `?ss=calibrate-sensor&id=${o}`,
    editHref: `?ss=sensor-edit&id=${r || o}`,
    deleteUrl: t
      ? `/singleton_sensor/delete/${t}/`
      : ((s == null ? void 0 : s.deleteUrl) ?? null),
  };
}
function ns(e, s, t) {
  var b;
  const r = H(e.uid || e.id);
  if (!r) return null;
  const i = H(e.child_type || (t == null ? void 0 : t.childType), "local"),
    o = e.child != null ? H(e.child) : null,
    h =
      e.remote_child_id != null
        ? H(e.remote_child_id)
        : ((t == null ? void 0 : t.remoteChildId) ?? null),
    m = o
      ? (b = s.find((E) => E.id === o)) == null
        ? void 0
        : b.name
      : void 0,
    c = H(
      e.name || e.child_name || m || (t == null ? void 0 : t.name),
      "Child",
    ),
    d = i === "local" && o ? o : h || r;
  return {
    id: r,
    name: c,
    childType: i,
    remoteChildId: h,
    detailUrl: o ? `/${o}/` : ((t == null ? void 0 : t.detailUrl) ?? null),
    thumbnailUrl: (t == null ? void 0 : t.thumbnailUrl) ?? null,
    mapUrl: (t == null ? void 0 : t.mapUrl) ?? null,
    restUid: d,
    editHref: `?ss=child-edit&id=${d}`,
    deleteUrl: /^\d+$/.test(r)
      ? `/child/delete/${r}/`
      : ((t == null ? void 0 : t.deleteUrl) ?? null),
  };
}
function rs(e, s, t) {
  const r = e.findIndex(
    (o) =>
      o.id === s.id || o.sensorId === s.sensorId || !!(t && o.sensorId === t),
  );
  if (r < 0) return [...e, s];
  const i = e.slice();
  return (
    (i[r] = { ...e[r], ...s, deleteUrl: s.deleteUrl || e[r].deleteUrl }),
    i
  );
}
function is(e, s, t) {
  const r = e.findIndex(
    (o) =>
      o.id === s.id || o.sensorId === s.sensorId || !!(t && o.sensorId === t),
  );
  if (r < 0) return [...e, s];
  const i = e.slice();
  return (
    (i[r] = {
      ...e[r],
      ...s,
      iconUrl: s.iconUrl ?? e[r].iconUrl,
      areaJson: s.areaJson || e[r].areaJson,
      deleteUrl: s.deleteUrl || e[r].deleteUrl,
    }),
    i
  );
}
function os(e, s, t) {
  const r = e.findIndex(
    (o) => o.id === s.id || o.restUid === s.restUid || !!(t && o.restUid === t),
  );
  if (r < 0) return [...e, s];
  const i = e.slice();
  return (
    (i[r] = {
      ...e[r],
      ...s,
      thumbnailUrl: s.thumbnailUrl ?? e[r].thumbnailUrl,
      mapUrl: s.mapUrl ?? e[r].mapUrl,
      detailUrl: s.detailUrl ?? e[r].detailUrl,
      deleteUrl: s.deleteUrl || e[r].deleteUrl,
    }),
    i
  );
}
const as = new Set([
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
function cs(e) {
  return !!(e && as.has(e));
}
function ls({
  sceneId: e,
  authToken: s,
  isSuperuser: t,
  isKubernetes: r,
  scenes: i,
  cameras: o,
  sensors: h = [],
  onCamerasChange: m,
  onSensorsChange: c,
  onChildrenChange: d,
  mapUrl: b = null,
  mapScale: E = null,
}) {
  var A;
  const { sheet: g, open: v, close: I } = it(),
    B = a.useCallback(
      (p, w = null) => {
        const L = ae(p);
        (L && ce(L), v(p, w));
      },
      [v],
    ),
    R = a.useCallback(() => {
      const p = ae(g.action);
      (I(), p && ce(p));
    }, [I, g.action]);
  (a.useEffect(() => {
    const p = (w) => {
      const L = w.target;
      if (!L) return;
      const $ = L.closest("a[href]");
      if (!($ != null && $.href)) return;
      let C;
      try {
        C = new URL($.href, window.location.origin);
      } catch {
        return;
      }
      if (C.origin !== window.location.origin) return;
      const _ = C.searchParams.get("ss");
      !_ ||
        !cs(_) ||
        ((C.pathname === window.location.pathname ||
          C.pathname === `/${e}/` ||
          C.pathname === `/${e}`) &&
          (w.preventDefault(),
          w.stopPropagation(),
          B(_, C.searchParams.get("id"))));
    };
    return (
      document.addEventListener("click", p, !0),
      () => document.removeEventListener("click", p, !0)
    );
  }, [B, e]),
    a.useEffect(() => {
      const p = ae(g.action);
      p && ce(p);
    }, [g.action]));
  const T = a.useCallback(() => {
      window.location.reload();
    }, []),
    y = a.useCallback(
      (p) => {
        if (!p) return;
        const w = ts(p);
        if (!w) return;
        const L = me(p, "scene"),
          $ = g.action === "cam-edit" && g.id ? String(g.id) : null;
        m((C) =>
          L && L !== e
            ? C.filter(
                (_) =>
                  _.id !== w.id &&
                  _.sensorId !== w.sensorId &&
                  _.sensorId !== $,
              )
            : rs(C, w, $),
        );
      },
      [m, e, g.action, g.id],
    ),
    u = a.useCallback(
      (p) => {
        if (!p) return;
        const w = me(p, "scene"),
          L = g.action === "sensor-edit" && g.id ? String(g.id) : null;
        c(($) => {
          const C = $.find(
              (D) =>
                D.sensorId === L ||
                D.sensorId === String(p.uid || "") ||
                D.id === String(p.id || ""),
            ),
            _ = ss(p, C);
          return _
            ? w && w !== e
              ? $.filter(
                  (D) =>
                    D.id !== _.id &&
                    D.sensorId !== _.sensorId &&
                    D.sensorId !== L,
                )
              : is($, _, L)
            : $;
        });
      },
      [c, e, g.action, g.id],
    ),
    l = a.useCallback(
      (p) => {
        if (!p) return;
        const w = me(p, "parent"),
          L = g.action === "child-edit" && g.id ? String(g.id) : null;
        d(($) => {
          const C = $.find(
              (D) => D.id === String(p.uid || p.id || "") || D.restUid === L,
            ),
            _ = ns(p, i, C);
          return _
            ? w && w !== e
              ? $.filter(
                  (D) =>
                    D.id !== _.id && D.restUid !== _.restUid && D.restUid !== L,
                )
              : os($, _, L)
            : $;
        });
      },
      [d, e, i, g.action, g.id],
    ),
    x = a.useMemo(() => {
      const p = new Map();
      return (o.forEach((w) => p.set(String(w.id), w)), p);
    }, [o]),
    j = a.useMemo(() => {
      const p = new Map();
      return (o.forEach((w) => p.set(String(w.sensorId), w)), p);
    }, [o]),
    k = a.useMemo(() => {
      const p = new Map();
      return (h.forEach((w) => p.set(String(w.id), w)), p);
    }, [h]);
  if (!t) return null;
  const M = g.action,
    f = M === "calibrate-cam" && g.id ? x.get(String(g.id)) : null,
    N = M === "calibrate-sensor" && g.id ? k.get(String(g.id)) : null,
    S =
      M === "cam-edit" && g.id
        ? ((A = j.get(String(g.id))) == null ? void 0 : A.sensorId) ||
          String(g.id)
        : null;
  return n.jsxs(n.Fragment, {
    children: [
      n.jsx(Ze, {
        open: M === "cam-create" || M === "cam-edit",
        mode: M === "cam-edit" ? "edit" : "create",
        sceneId: e,
        scenes: i,
        sensorUid: M === "cam-edit" ? S : null,
        authToken: s,
        onClose: R,
        onSaved: y,
      }),
      n.jsx(et, {
        open: M === "sensor-create" || M === "sensor-edit",
        mode: M === "sensor-edit" ? "edit" : "create",
        sceneId: e,
        scenes: i,
        sensorUid: M === "sensor-edit" ? g.id : null,
        authToken: s,
        onClose: R,
        onSaved: u,
      }),
      n.jsx(ot, {
        open: M === "child-create" || M === "child-edit",
        mode: M === "child-edit" ? "edit" : "create",
        parentSceneId: e,
        childUid: M === "child-edit" ? g.id : null,
        scenes: i,
        authToken: s,
        onClose: R,
        onSaved: l,
      }),
      n.jsx(at, {
        open: M === "scene-manage",
        sceneId: e,
        authToken: s,
        onClose: R,
        onSaved: T,
      }),
      n.jsx(tt, {
        open: !!f,
        cameraPk: (f == null ? void 0 : f.id) || "",
        sensorId: (f == null ? void 0 : f.sensorId) || "",
        cameraName: (f == null ? void 0 : f.name) || "",
        sceneId: e,
        authToken: s,
        isKubernetes: r,
        onClose: R,
        onSaved: T,
      }),
      n.jsx(st, {
        open: !!N || M === "calibrate-sensor",
        sensorPk: (N == null ? void 0 : N.id) || g.id || "",
        sensorId: (N == null ? void 0 : N.sensorId) || "",
        sceneId: e,
        authToken: s,
        mapUrlHint: b,
        mapScale: E,
        onClose: R,
        onSaved: T,
      }),
    ],
  });
}
const ze = "ss-workspace-layout-mode",
  ds = 224,
  us = 256,
  oe = 120;
function $e() {
  return {
    w: Math.max(window.innerWidth || 0, 320),
    h: Math.max(window.innerHeight || 0, 320),
  };
}
function ms() {
  try {
    const e = window.localStorage.getItem(ze);
    if (e === "auto" || e === "stack" || e === "row") return e;
  } catch {}
  return "auto";
}
function fs(e) {
  try {
    window.localStorage.setItem(ze, e);
  } catch {}
}
function hs() {
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
    const r = s.getAttribute("viewBox");
    if (r) {
      const i = r
        .trim()
        .split(/[\s,]+/)
        .map(Number);
      if (
        i.length === 4 &&
        Number.isFinite(i[2]) &&
        Number.isFinite(i[3]) &&
        i[2] > 0 &&
        i[3] > 0
      )
        return { w: i[2], h: i[3] };
    }
  }
  const t = document.querySelector("#ss-map-host #map img");
  return t && t.naturalWidth > 0 && t.naturalHeight > 0
    ? { w: t.naturalWidth, h: t.naturalHeight }
    : null;
}
function ke(e, s, t) {
  const r = Math.max(s, oe),
    i = Math.max(t, oe),
    o = Math.min(r / e.w, i / e.h);
  return !Number.isFinite(o) || o <= 0 ? 0 : e.w * o * (e.h * o);
}
function Le(e, s, t) {
  const r = Math.max(e.w - 32, oe),
    i = Math.max(e.h - t, oe);
  if (r < 720 || i / r > 1.25) return "stack";
  if (!s) return r / i >= 1.35 ? "stack" : "row";
  const o = s.w / s.h,
    h = ke(s, r, i - ds),
    m = ke(s, r - us, i);
  return o >= 1.35
    ? h >= m * 0.92
      ? "stack"
      : "row"
    : o <= 1.05
      ? m >= h * 0.92
        ? "row"
        : "stack"
      : m > h
        ? "row"
        : "stack";
}
function ps(e = {}) {
  const s = e.chromeHeightPx ?? 112,
    [t, r] = a.useState(() => (typeof window < "u" ? ms() : "auto")),
    [i, o] = a.useState(() => Le($e(), null, s)),
    h = a.useCallback((c) => {
      (r(c), fs(c));
    }, []);
  return (
    a.useEffect(() => {
      let c = 0,
        d = null;
      const b = () => {
        (cancelAnimationFrame(c),
          (c = requestAnimationFrame(() => {
            const R = Le($e(), hs(), s);
            d !== R && ((d = R), o((T) => (T === R ? T : R)));
          })));
      };
      (b(),
        window.addEventListener("resize", b),
        window.addEventListener("ss-map-host-ready", b));
      const E = document.querySelector("#ss-map-host #map img");
      E && !E.complete && E.addEventListener("load", b);
      const g = document.getElementById("ss-map-host");
      let v = null;
      g &&
        typeof ResizeObserver < "u" &&
        ((v = new ResizeObserver(() => b())), v.observe(g));
      const I = window.setInterval(b, 500),
        B = window.setTimeout(() => window.clearInterval(I), 8e3);
      return () => {
        (cancelAnimationFrame(c),
          window.removeEventListener("resize", b),
          window.removeEventListener("ss-map-host-ready", b),
          E == null || E.removeEventListener("load", b),
          v == null || v.disconnect(),
          window.clearInterval(I),
          window.clearTimeout(B));
      };
    }, [s, t]),
    { layout: t === "auto" ? i : t, mode: t, setMode: h, autoLayout: i }
  );
}
function ws() {
  const [e, s] = a.useState(!1);
  return (
    a.useEffect(() => {
      const t = () => {
        const h = document.getElementById("mqtt_status"),
          m = !!(h != null && h.classList.contains("connected"));
        s((c) => (c === m ? c : m));
      };
      t();
      const r = document.getElementById("mqtt_status");
      let i = null;
      r &&
        ((i = new MutationObserver(t)),
        i.observe(r, { attributes: !0, attributeFilter: ["class"] }));
      const o = (h) => {
        const m = h.detail;
        typeof (m == null ? void 0 : m.connected) == "boolean"
          ? s((c) => (c === m.connected ? c : !!m.connected))
          : t();
      };
      return (
        window.addEventListener("ss-mqtt-status", o),
        () => {
          (i == null || i.disconnect(),
            window.removeEventListener("ss-mqtt-status", o));
        }
      );
    }, []),
    e
  );
}
function gs() {
  const [e, s] = a.useState({});
  return (
    a.useEffect(() => {
      const t = (m, c) => {
          s((d) => (d[m] === c ? d : { ...d, [m]: c }));
        },
        r = (m, c) => {
          t(m, c);
        },
        i = () => s({});
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setCameraRate: r,
        clearRates: i,
      };
      const o = (m) => {
          const c = m.detail;
          c != null && c.sensorId && t(c.sensorId, c.text || c.hz || "--");
        },
        h = () => i();
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
function bs(e) {
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
const ys = [
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
function vs({ bootstrap: e }) {
  const { scene: s, urls: t, isSuperuser: r } = e,
    { layout: i, mode: o, setMode: h, autoLayout: m } = ps(),
    {
      panelSizePx: c,
      setPanelSizePx: d,
      mapFocus: b,
      toggleMapFocus: E,
    } = nt(i),
    [g, v] = a.useState("--"),
    [I, B] = a.useState(!1),
    [R, T] = a.useState(!1),
    [y, u] = a.useState(null),
    l = ws(),
    x = gs(),
    [j, k] = a.useState(e.cameras),
    [M, f] = a.useState(e.sensors || []),
    [N, S] = a.useState(e.children || []),
    [A, p] = a.useState({
      cameras: e.cameras.length,
      sensors: e.counts.sensors,
      regions: e.counts.regions,
      tripwires: e.counts.tripwires,
      children: e.counts.children,
    });
  ((window.ssUseReactMap = !!s.mapUrl),
    a.useEffect(() => {
      const _ = (Y) => v(Y || "--");
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setSceneRate: _,
      };
      const D = (Y) => {
          const G = Y.detail;
          (G == null ? void 0 : G.hz) !== void 0 && _(G.hz);
        },
        z = () => v("--");
      return (
        window.addEventListener("ss-scene-rate", D),
        window.addEventListener("ss-telemetry-clear", z),
        () => {
          (window.removeEventListener("ss-scene-rate", D),
            window.removeEventListener("ss-telemetry-clear", z));
        }
      );
    }, []),
    a.useEffect(() => {
      const _ = (D) => {
        const z = D.detail;
        !z ||
          typeof z != "object" ||
          p((Y) => {
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
        window.addEventListener(he, _),
        () => window.removeEventListener(he, _)
      );
    }, []),
    a.useEffect(() => {
      const _ = window.requestAnimationFrame(() => {
        typeof window.fitSceneMapDisplay == "function" &&
          window.fitSceneMapDisplay();
      });
      return () => window.cancelAnimationFrame(_);
    }, [b, c, i]));
  const w = a.useCallback(async () => {
      if (t.sceneDelete) {
        (T(!0), u(null));
        try {
          await ct(t.sceneDelete, t.scenesHome || "/");
        } catch (_) {
          (T(!1), u(_ instanceof Error ? _.message : "Delete failed"));
        }
      }
    }, [t.sceneDelete, t.scenesHome]),
    L = [
      { id: "cameras", label: "Cameras", count: Q(A.cameras) },
      { id: "sensors", label: "Sensors", count: Q(A.sensors) },
      { id: "regions", label: "Regions", count: Q(A.regions) },
      { id: "tripwires", label: "Tripwires", count: Q(A.tripwires) },
      { id: "children", label: "Children", count: Q(A.children) },
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
    $ = n.jsxs(n.Fragment, {
      children: [
        n.jsxs("div", {
          className: "scene-rate ss-scene-rate",
          children: [
            "Rate: ",
            n.jsx("span", { id: "scene-rate", children: g }),
            " Hz",
          ],
        }),
        n.jsx("div", {
          className: "ss-layout-toggle",
          role: "group",
          "aria-label": "Control panel layout",
          children: ys.map((_) => {
            const D = o === _.mode,
              z = _.mode === "auto" ? ` (now ${m})` : "";
            return n.jsxs(
              "button",
              {
                type: "button",
                className: `ss-layout-toggle-btn${D ? " is-active" : ""}`,
                title: `${_.title}${z}`,
                "aria-pressed": D,
                onClick: () => h(_.mode),
                children: [
                  n.jsx("i", {
                    className: `bi ${_.icon}`,
                    "aria-hidden": "true",
                  }),
                  n.jsx("span", {
                    className: "ss-layout-toggle-label",
                    children: _.label,
                  }),
                ],
              },
              _.mode,
            );
          }),
        }),
        n.jsxs("button", {
          type: "button",
          className: `ss-layout-toggle-btn ss-map-focus-btn${b ? " is-active" : ""}`,
          title: b ? "Show control panel (Esc)" : "Map only focus",
          "aria-pressed": b,
          onClick: E,
          children: [
            n.jsx("i", {
              className: `bi ${b ? "bi-layout-sidebar" : "bi-arrows-fullscreen"}`,
              "aria-hidden": "true",
            }),
            n.jsx("span", {
              className: "ss-layout-toggle-label",
              children: b ? "Panel" : "Map",
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
        r
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
        r && t.sceneDelete
          ? n.jsx("button", {
              type: "button",
              className: "btn btn-secondary btn-sm ss-icon-btn--danger",
              id: "scene-delete",
              title: `Delete ${s.name}`,
              "aria-label": `Delete ${s.name}`,
              onClick: () => {
                (u(null), B(!0));
              },
              children: n.jsx("i", {
                className: "bi bi-trash",
                "aria-hidden": "true",
              }),
            })
          : null,
      ],
    }),
    C = e.deleteImpact;
  return n.jsxs("div", {
    className: `ss-scene-detail ss-scene-detail--workspace ss-workspace--${i}${b ? " ss-workspace--map-focus" : ""}`,
    "data-workspace-layout": i,
    "data-workspace-mode": o,
    "data-map-focus": b ? "1" : "0",
    style: { "--ss-panel-size": `${c}px` },
    children: [
      n.jsx(We, { title: s.name, back: bs(t), actions: $ }),
      n.jsxs("div", {
        className: "ss-workspace-body",
        children: [
          n.jsx("div", {
            className: "ss-workspace-main",
            children: n.jsx(Mt, { mapUrl: s.mapUrl }),
          }),
          n.jsx(rt, { layout: i, panelSizePx: c, onResize: d, disabled: b }),
          n.jsx(zt, {
            tabs: L,
            cameraRates: x,
            cameras: j,
            sensors: M,
            childrenLinks: N,
            isSuperuser: r,
            sceneId: s.id,
            wssConnection: e.scene.wssConnection || "",
            authToken: e.authToken,
            onSensorsChange: f,
          }),
        ],
      }),
      n.jsx(Zt, {
        sceneId: s.id,
        isSuperuser: r,
        authToken: e.authToken,
        initialRegions: e.regions || [],
        initialTripwires: e.tripwires || [],
      }),
      n.jsx(ls, {
        sceneId: s.id,
        authToken: e.authToken,
        isSuperuser: r,
        isKubernetes: !!e.isKubernetes,
        scenes: e.scenes || [],
        cameras: j,
        sensors: M,
        onCamerasChange: k,
        onSensorsChange: f,
        onChildrenChange: S,
        mapUrl: s.mapUrl,
        mapScale: s.scale,
      }),
      n.jsxs(Pe, {
        open: I,
        title: "Delete scene?",
        confirmLabel: "Delete scene",
        danger: !0,
        busy: R,
        onConfirm: w,
        onCancel: () => {
          R || B(!1);
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
              ((C == null ? void 0 : C.sensors) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      C == null ? void 0 : C.sensors,
                      " camera(s) and/or sensor(s) will be orphaned",
                    ],
                  })
                : null,
              ((C == null ? void 0 : C.regions) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      C == null ? void 0 : C.regions,
                      " region(s) will be deleted",
                    ],
                  })
                : null,
              ((C == null ? void 0 : C.tripwires) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      C == null ? void 0 : C.tripwires,
                      " tripwire(s) will be deleted",
                    ],
                  })
                : null,
            ],
          }),
          y ? n.jsx("p", { className: "ss-confirm-error", children: y }) : null,
        ],
      }),
    ],
  });
}
function xs({ bootstrap: e }) {
  return n.jsx(Je, {
    children: n.jsx(Ye, { children: n.jsx(vs, { bootstrap: e }) }),
  });
}
function js({ bootstrap: e }) {
  return n.jsx(xs, { bootstrap: e });
}
function Ss() {
  const e = document.getElementById("ss-scene-detail-bootstrap");
  if (!(e != null && e.textContent)) return null;
  try {
    return JSON.parse(e.textContent);
  } catch {
    return (console.error("Failed to parse scene detail bootstrap JSON"), null);
  }
}
const Ae = Ss(),
  Be = document.getElementById("ss-scene-detail-root");
Ae &&
  Be &&
  (document.documentElement.classList.add("ss-scene-workspace"),
  document.body.classList.add("ss-scene-workspace"),
  Ge.createRoot(Be).render(
    n.jsx(a.StrictMode, { children: n.jsx(js, { bootstrap: Ae }) }),
  ));
