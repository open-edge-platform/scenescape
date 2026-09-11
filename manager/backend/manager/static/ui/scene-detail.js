// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { r as l, j as n, c as Ge } from "./chunks/tokens-C2Ju3rc_.js";
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
    const i = (t.points || []).map((a) => [Number(a[0]), Number(a[1])]),
      o = t.sectors && !Array.isArray(t.sectors) ? t.sectors : null,
      m = Array.isArray(t.sectors)
        ? t.sectors
        : o == null
          ? void 0
          : o.thresholds,
      f =
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
      range_max: f,
      sectors: m,
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
function Nt(e, s) {
  const t = e + te.left + te.right,
    r = s + te.top + te.bottom;
  return `-72 -32 ${t} ${r}`;
}
const St = l.memo(function ({ href: s, width: t, height: r }) {
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
  const m = (-t * i) / o,
    f = (t * r) / o,
    a = (e[0] + s[0]) / 2,
    c = (e[1] + s[1]) / 2,
    w = a + m,
    x = c + f,
    h = m / t,
    v = f / t,
    I = -v,
    D = h,
    j = [
      `${w},${x}`,
      `${w - h * 8 + I * 4},${x - v * 8 + D * 4}`,
      `${w - h * 8 - I * 4},${x - v * 8 - D * 4}`,
    ].join(" ");
  return { arrow: { x1: a, y1: c, x2: w, y2: x }, head: j };
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
const Ct = l.memo(function ({ mapHref: s, mapWidth: t, mapHeight: r }) {
  const [i, o] = l.useState(() => X()),
    [m, f] = l.useState(() => Z()),
    [a, c] = l.useState("idle"),
    [w, x] = l.useState([]),
    h = Ve(),
    v = r || Ke(r);
  (l.useEffect(
    () =>
      ft(() => {
        (o(X()), f(Z()));
      }),
    [],
  ),
    l.useEffect(() => {
      var b;
      (b = window.ssReapplyRoiColors) == null || b.call(window);
    }, [i]),
    l.useEffect(() => {
      const b = () => {
          (c("add-roi"), x([]));
        },
        y = () => {
          (c("add-trip"), x([]));
        };
      window.ssMapReact = { startAddRoi: b, startAddTripwire: y };
      const p = (_) => {
        const E = _.target;
        if (!E) return;
        const A = E.closest(
          "#new-roi, #empty-new-roi, #new-tripwire, #empty-new-tripwire",
        );
        A && (_.preventDefault(), A.id.includes("trip") ? y() : b());
      };
      return (
        document.addEventListener("click", p, !0),
        () => {
          (document.removeEventListener("click", p, !0),
            delete window.ssMapReact);
        }
      );
    }, []));
  const I = l.useCallback((b) => Qe(b[0], b[1], h, v), [h, v]),
    D = (b) => {
      if (a === "idle") return;
      const y = b.currentTarget,
        p = y.createSVGPoint();
      ((p.x = b.clientX), (p.y = b.clientY));
      const _ = y.getScreenCTM();
      if (!_) return;
      const E = p.matrixTransform(_.inverse()),
        A = ye(E.x, E.y, h, v);
      if (a === "add-roi") {
        if (w.length >= 3) {
          const T = I(w[0]),
            d = E.x - T[0],
            S = E.y - T[1];
          if (Math.hypot(d, S) < 12) {
            const N = xe();
            (we(N, {
              title: "",
              points: w,
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
                  detail: { svgId: `roi_${N}`, uuid: N, title: "" },
                }),
              ),
              x([]),
              c("idle"));
            return;
          }
        }
        x((T) => [...T, A]);
        return;
      }
      if (a === "add-trip") {
        const T = [...w, A];
        if (T.length >= 2) {
          const d = xe();
          (ie(d, { title: "", points: T.slice(0, 2) }),
            window.dispatchEvent(
              new CustomEvent("ss-tripwire-form-add", {
                detail: { svgId: `tripwire_${d}`, uuid: d, title: "" },
              }),
            ),
            x([]),
            c("idle"));
        } else x(T);
      }
    },
    j = (b, y, p, _) => {
      (_.stopPropagation(), _.preventDefault());
      const E = _.target.ownerSVGElement;
      if (!E) return;
      const A = (d) => {
          const S = E.createSVGPoint();
          ((S.x = d.clientX), (S.y = d.clientY));
          const N = E.getScreenCTM();
          if (!N) return;
          const k = S.matrixTransform(N.inverse()),
            u = ye(k.x, k.y, h, v);
          if (b === "roi") {
            const g = X().find(($) => $.uuid === y);
            if (!g) return;
            const L = g.points.map(($, R) => (R === p ? u : $));
            yt(y, L);
          } else {
            const g = Z().find(($) => $.uuid === y);
            if (!g) return;
            const L = g.points.map(($, R) => (R === p ? u : $));
            vt(y, L);
          }
        },
        T = () => {
          (window.removeEventListener("mousemove", A),
            window.removeEventListener("mouseup", T));
        };
      (window.addEventListener("mousemove", A),
        window.addEventListener("mouseup", T));
    },
    M = l.useMemo(() => w.map(I), [w, I]);
  return n.jsxs("svg", {
    id: "svgout",
    className: `ss-react-scene-map${a !== "idle" ? ` is-${a}` : ""}`,
    viewBox: Nt(t, r),
    preserveAspectRatio: "xMidYMid meet",
    width: "100%",
    height: "100%",
    onClick: D,
    children: [
      n.jsx(St, { href: s, width: t, height: r }),
      i.map((b) => {
        const y = b.points.map(I),
          p = y.map((E) => E.join(",")).join(" "),
          _ = _t(y);
        return n.jsxs(
          "g",
          {
            id: `roi_${b.uuid}`,
            className: "roi",
            children: [
              n.jsx("polygon", { points: p, className: "ss-react-roi-poly" }),
              b.title && _
                ? n.jsx("text", {
                    className: "ss-react-roi-title",
                    x: _[0],
                    y: _[1],
                    pointerEvents: "none",
                    children: b.title,
                  })
                : null,
              y.map((E, A) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: E[0],
                    cy: E[1],
                    r: 6,
                    onMouseDown: (T) => j("roi", b.uuid, A, T),
                  },
                  A,
                ),
              ),
            ],
          },
          b.uuid,
        );
      }),
      m.map((b) => {
        const y = b.points.map(I);
        if (y.length < 2) return null;
        const p = Et(y[0], y[1]);
        return n.jsxs(
          "g",
          {
            id: `tripwire_${b.uuid}`,
            className: "tripwire",
            children: [
              n.jsx("line", {
                className: "tripline ss-react-trip-line",
                x1: y[0][0],
                y1: y[0][1],
                x2: y[1][0],
                y2: y[1][1],
              }),
              p
                ? n.jsxs("g", {
                    className: "ss-react-trip-dir",
                    pointerEvents: "none",
                    children: [
                      n.jsx("line", {
                        className: "ss-react-trip-arrow",
                        x1: p.arrow.x1,
                        y1: p.arrow.y1,
                        x2: p.arrow.x2,
                        y2: p.arrow.y2,
                      }),
                      n.jsx("polygon", {
                        className: "ss-react-trip-arrowhead",
                        points: p.head,
                      }),
                    ],
                  })
                : null,
              b.title
                ? n.jsx("text", {
                    className: "ss-react-trip-title",
                    x: (y[0][0] + y[1][0]) / 2,
                    y: (y[0][1] + y[1][1]) / 2 - 14,
                    pointerEvents: "none",
                    children: b.title,
                  })
                : null,
              y.map((_, E) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: _[0],
                    cy: _[1],
                    r: 6,
                    onMouseDown: (A) => j("trip", b.uuid, E, A),
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
              a === "add-roi" && M.length >= 3
                ? n.jsx("polygon", {
                    points: M.map((b) => b.join(",")).join(" "),
                    className: "ss-react-draft-poly",
                  })
                : null,
              a === "add-roi" && M.length === 2
                ? n.jsx("polyline", {
                    points: M.map((b) => b.join(",")).join(" "),
                    className: "ss-react-draft-line",
                  })
                : null,
              M.map((b, y) =>
                n.jsx(
                  "circle",
                  { cx: b[0], cy: b[1], r: 5, className: "ss-react-draft-pt" },
                  y,
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
function Ne(e) {
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
const Mt = l.memo(function ({
  mapUrl: s = null,
  mapWidth: t = 1280,
  mapHeight: r = 720,
}) {
  const i = l.useRef(null),
    [o, m] = l.useState(!1),
    [f, a] = l.useState(null),
    c = !!window.ssUseReactMap && !!s;
  (l.useEffect(() => {
    if (!c || !s) {
      a(null);
      return;
    }
    let h = !1;
    const v = new Image();
    return (
      (v.onload = () => {
        !h &&
          v.naturalWidth > 0 &&
          v.naturalHeight > 0 &&
          a({ width: v.naturalWidth, height: v.naturalHeight });
      }),
      (v.src = s),
      () => {
        h = !0;
      }
    );
  }, [c, s]),
    l.useEffect(() => {
      const h = i.current,
        v = document.getElementById(le.host);
      if (!h || !v) return;
      if ((h.appendChild(v), (v.hidden = !1), c)) {
        document.body.classList.add("ss-use-react-map");
        const y = v.querySelector(
          "svg#svgout, svg.ss-snap-legacy, svg#svgout-snap",
        );
        y &&
          (y.classList.add("ss-snap-legacy"),
          y.id === "svgout" && (y.id = "svgout-snap"));
      }
      (mt(), m(!0));
      let I = 0,
        D = -1,
        j = -1;
      const M = () => {
        I ||
          (I = window.requestAnimationFrame(() => {
            I = 0;
            const y = Math.round(h.clientWidth),
              p = Math.round(h.clientHeight);
            if (!(y === D && p === j && D >= 0))
              if (((D = y), (j = p), !c)) je();
              else {
                const _ = v.querySelector(".scene-map-stage");
                (_ && Ne(_), je());
              }
          }));
      };
      window.addEventListener("resize", M);
      let b = null;
      return (
        typeof ResizeObserver < "u" &&
          ((b = new ResizeObserver(() => M())), b.observe(h)),
        M(),
        () => {
          (I && window.cancelAnimationFrame(I),
            window.removeEventListener("resize", M),
            b == null || b.disconnect(),
            document.body.classList.remove("ss-use-react-map"));
          const y = v.querySelector("svg#svgout-snap, svg.ss-snap-legacy");
          if (y && y.id === "svgout-snap") {
            const _ = v.querySelector("svg.ss-react-scene-map");
            (!_ || _.id !== "svgout") && (y.id = "svgout");
          }
          const p = document.getElementById("ss-legacy-map-parking");
          p && v.parentElement === h && (p.appendChild(v), (v.hidden = !0));
        }
      );
    }, [c]),
    l.useEffect(() => {
      if (!c || !o) return;
      const h = document.getElementById(le.host),
        v = h == null ? void 0 : h.querySelector(".scene-map-stage");
      v && Ne(v);
    }, [c, o, f]));
  const w = o ? document.getElementById(le.host) : null,
    x = (w == null ? void 0 : w.querySelector(".scene-map-stage")) ?? null;
  return n.jsxs("div", {
    className: "ss-scene-map-pane",
    children: [
      n.jsx("div", { ref: i, className: "ss-scene-map-slot" }),
      c && x && s && f
        ? J.createPortal(
            n.jsx("div", {
              className: "ss-react-map-layer",
              children: n.jsx(Ct, {
                mapHref: s,
                mapWidth: f.width || t,
                mapHeight: f.height || r,
              }),
            }),
            x,
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
function It(e, s) {
  return e.findIndex((t) => t.id === s);
}
function Tt(e, s) {
  if (e.length === 0) return -1;
  const t = It(e, s);
  return t >= 0 ? t : 0;
}
function $t({ count: e, focusIndex: s, onSelectIndex: t }) {
  const r = l.useRef([]),
    i = l.useRef(null),
    o = l.useCallback((a, c) => {
      r.current[a] = c;
    }, []);
  l.useEffect(() => {
    if (s < 0) return;
    const a = i.current;
    if (!a) return;
    const c = document.activeElement;
    if (!(c instanceof Node) || !a.contains(c)) return;
    const w = r.current[s];
    w && c !== w && w.focus();
  }, [s]);
  const m = l.useCallback(
      (a) => {
        var c;
        (t(a), (c = r.current[a]) == null || c.focus());
      },
      [t],
    ),
    f = l.useCallback(
      (a, c) => {
        const w = Rt(a.key, c, e);
        w !== null && (a.preventDefault(), m(w));
      },
      [m, e],
    );
  return { listRef: i, setTabRef: o, onTabKeyDown: f };
}
function Lt(e) {
  return `ss-tab-${e.id}`;
}
function kt(e) {
  return `ss-tab-panel-${e.id}`;
}
function At({
  tabs: e,
  activeId: s,
  onChange: t,
  id: r,
  tabDomId: i = Lt,
  tabPanelId: o = kt,
}) {
  const m = Tt(e, s),
    f = l.useCallback(
      (x) => {
        const h = e[x];
        h && t(h.id);
      },
      [t, e],
    ),
    {
      listRef: a,
      setTabRef: c,
      onTabKeyDown: w,
    } = $t({ count: e.length, focusIndex: m, onSelectIndex: f });
  return n.jsx("div", {
    ref: a,
    className: "ss-tabs-list",
    role: "tablist",
    id: r,
    children: e.map((x, h) => {
      const v = x.id === s;
      return n.jsxs(
        "button",
        {
          ref: (I) => c(h, I),
          type: "button",
          role: "tab",
          id: i(x),
          "aria-selected": v,
          "aria-controls": o(x),
          tabIndex: h === m ? 0 : -1,
          className: `ss-tabs-tab${v ? " is-active" : ""}`,
          onClick: () => t(x.id),
          onKeyDown: (I) => w(I, h),
          children: [
            n.jsx("span", {
              className: "ss-tabs-main",
              children: n.jsx("span", {
                className: "ss-tabs-label",
                children: x.label,
              }),
            }),
            x.count !== void 0 && x.count !== null
              ? n.jsx("span", { className: "ss-tabs-count", children: x.count })
              : null,
            x.extra,
          ],
        },
        x.id,
      );
    }),
  });
}
const Ue = "ss-camera-strip-fit";
function Bt() {
  try {
    const e = window.localStorage.getItem(Ue);
    if (e === "cover" || e === "contain") return e;
  } catch {}
  return "contain";
}
function Dt(e) {
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
    m = i ? "1" : "0";
  (e.dataset.ssOnline !== m &&
    ((e.dataset.ssOnline = m),
    e.classList.toggle("is-online", i),
    e.classList.toggle("is-offline", !i)),
    e.dataset.ssRate !== (o || "--") && (e.dataset.ssRate = o || "--"));
  let f = e.querySelector(".ss-camera-strip-badge");
  f ||
    ((f = document.createElement("span")),
    (f.className = "ss-camera-strip-badge"),
    f.setAttribute("aria-hidden", "true"),
    (e.querySelector(".card-header") || e).appendChild(f));
  const a = i ? "Live" : "Offline";
  (f.textContent !== a && (f.textContent = a),
    f.classList.toggle("is-online", i),
    f.classList.toggle("is-offline", !i),
    t && t.hidden !== i && (t.hidden = i));
}
function Pt({ rates: e = {} }) {
  const [s, t] = l.useState(() => (typeof window < "u" ? Bt() : "contain"));
  return (
    l.useEffect(() => {
      const r = document.documentElement;
      ((r.dataset.ssCameraFit = s), Dt(s));
      const i = document.getElementById("cameras");
      i && ((i.dataset.ssCameraFit = s), i.classList.add("ss-camera-strip"));
    }, [s]),
    l.useEffect(() => {
      Object.entries(e).forEach(([r, i]) => {
        var a;
        const o =
            (a = document.querySelector(
              `[data-ss-card-sensor="${CSS.escape(r)}"]`,
            )) == null
              ? void 0
              : a.closest(".camera-card"),
          m =
            o == null
              ? void 0
              : o.querySelector(
                  "img[data-ss-card-sensor], img[id^='card-preview-']",
                ),
          f = document.getElementById(`rate-${r}`);
        if (!Oe(m)) {
          (f &&
            ((f.textContent || "").trim() !== "--" && (f.textContent = "--"),
            f.classList.add("telemetry-hide")),
            o && de(o));
          return;
        }
        (f &&
          f.textContent !== i &&
          ((f.textContent = i), f.classList.remove("telemetry-hide")),
          o && de(o));
      });
    }, [e]),
    l.useEffect(() => {
      const r = document.getElementById("cameras");
      if (!r) return;
      r.classList.add("ss-camera-strip");
      let i = 0,
        o = !1;
      const m = () => {
          if (!o) {
            o = !0;
            try {
              r.querySelectorAll(".camera-card").forEach(de);
            } finally {
              o = !1;
            }
          }
        },
        f = () => {
          i ||
            (i = window.requestAnimationFrame(() => {
              ((i = 0), m());
            }));
        };
      m();
      const a = new MutationObserver(f);
      a.observe(r, {
        subtree: !0,
        childList: !0,
        attributes: !0,
        attributeFilter: ["class", "src"],
      });
      const c = window.setInterval(m, 2e3);
      return () => {
        (a.disconnect(),
          window.clearInterval(c),
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
function Ft({ cameras: e, isSuperuser: s }) {
  return (
    l.useEffect(() => {
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
function Ht({ sensors: e, isSuperuser: s, onDelete: t }) {
  return (
    l.useEffect(() => {
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
function Ut({ childrenLinks: e, isSuperuser: s }) {
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
function Ot({
  cameras: e,
  sensors: s,
  childrenLinks: t,
  isSuperuser: r,
  panelsReady: i,
  authToken: o = "",
  onSensorsChange: m,
}) {
  const f = De(),
    [a, c] = l.useState(null),
    [w, x] = l.useState(!1),
    [h, v] = l.useState(null);
  l.useEffect(() => {
    i && He({ cameras: e.length, sensors: s.length, children: t.length });
  }, [i, e, s, t]);
  const I = l.useCallback(async () => {
      var p;
      if (!(!a || !o || !m)) {
        (x(!0), v(null));
        try {
          (await O.deleteSensor(o, a.sensorId),
            (p = window.ssRemoveSingletonSensor) == null ||
              p.call(window, a.sensorId),
            m((_) =>
              _.filter((E) => E.id !== a.id && E.sensorId !== a.sensorId),
            ),
            f.show("Sensor deleted", "ok"),
            c(null));
        } catch (_) {
          v(_.message || "Delete failed");
        } finally {
          x(!1);
        }
      }
    }, [o, m, a, f]),
    D = l.useCallback((p) => {
      (v(null), c(p));
    }, []);
  if (!i) return null;
  const j = document.getElementById("ss-cameras-mount"),
    M = document.getElementById("ss-sensors-mount"),
    b = document.getElementById("ss-children-mount"),
    y = !!(o && m);
  return n.jsxs(n.Fragment, {
    children: [
      j ? J.createPortal(n.jsx(Ft, { cameras: e, isSuperuser: r }), j) : null,
      M
        ? J.createPortal(
            n.jsx(Ht, { sensors: s, isSuperuser: r, onDelete: y ? D : void 0 }),
            M,
          )
        : null,
      b
        ? J.createPortal(n.jsx(Ut, { childrenLinks: t, isSuperuser: r }), b)
        : null,
      n.jsxs(Pe, {
        open: !!a,
        title: "Delete sensor?",
        confirmLabel: "Delete",
        danger: !0,
        busy: w,
        onConfirm: I,
        onCancel: () => {
          w || (c(null), v(null));
        },
        children: [
          n.jsxs("p", {
            children: [
              "Are you sure you want to delete",
              " ",
              n.jsx("strong", {
                children: (a == null ? void 0 : a.name) || "this sensor",
              }),
              "?",
            ],
          }),
          n.jsx("p", { children: "This action cannot be undone." }),
          h ? n.jsx("p", { className: "ss-confirm-error", children: h }) : null,
        ],
      }),
    ],
  });
}
function qt({ wssConnection: e, sceneId: s, panelsReady: t }) {
  return (
    l.useEffect(() => {
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
function zt({ id: e, title: s, children: t, footer: r, onClose: i }) {
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
function Se(e) {
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
function Jt({ activeTab: e, isSuperuser: s }) {
  const [t, r] = l.useState(() => !!window.ssRoiDirty),
    [i, o] = l.useState(() => !!window.ssTripDirty);
  return (
    l.useEffect(() => {
      const m = (a) => {
          r(!!a.detail);
        },
        f = (a) => {
          o(!!a.detail);
        };
      return (
        window.addEventListener("ss-roi-dirty", m),
        window.addEventListener("ss-trip-dirty", f),
        r(!!window.ssRoiDirty),
        o(!!window.ssTripDirty),
        () => {
          (window.removeEventListener("ss-roi-dirty", m),
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
                          onClick: Se,
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
                          onClick: Se,
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
  sensors: r = [],
  childrenLinks: i = [],
  isSuperuser: o = !1,
  sceneId: m = "",
  wssConnection: f = "",
  authToken: a = "",
  onSensorsChange: c,
}) {
  const [w, x] = l.useState(() => dt(m)),
    [h, v] = l.useState(!1),
    I = l.useRef(null);
  (l.useEffect(() => {
    const j = I.current,
      M = document.getElementById("scene-detail-panels");
    if (!(!j || !M))
      return (
        j.appendChild(M),
        (M.hidden = !1),
        M.classList.add("ss-legacy-panels-adopted"),
        v(!0),
        () => {
          v(!1);
          const b = document.getElementById("ss-legacy-panels-parking");
          b && M.parentElement === j && (b.appendChild(M), (M.hidden = !0));
        }
      );
  }, []),
    l.useEffect(() => {
      Object.entries(_e).forEach(([j, M]) => {
        const b = document.getElementById(M);
        if (!b) return;
        const y = j === w;
        (b.classList.toggle("show", y), b.classList.toggle("active", y));
      });
    }, [w]),
    l.useEffect(() => {
      ut(m, w);
    }, [m, w]),
    l.useEffect(() => {
      const j = (M) => {
        const b = M.detail,
          y = b == null ? void 0 : b.tabId;
        (y === "cameras" ||
          y === "sensors" ||
          y === "regions" ||
          y === "tripwires" ||
          y === "children" ||
          y === "mqtt") &&
          x(y);
      };
      return (
        window.addEventListener(fe, j),
        () => window.removeEventListener(fe, j)
      );
    }, []));
  const D = l.useCallback((j) => {
    (j === "cameras" ||
      j === "sensors" ||
      j === "regions" ||
      j === "tripwires" ||
      j === "children" ||
      j === "mqtt") &&
      x(j);
  }, []);
  return n.jsxs("aside", {
    className: "ss-scene-side hide-fullscreen",
    children: [
      n.jsxs("div", {
        className: "ss-tabs",
        children: [
          n.jsxs("div", {
            className: "ss-tabs-chrome",
            children: [
              n.jsx(At, {
                id: "ss-scene-tablist",
                tabs: e,
                activeId: w,
                onChange: D,
                tabDomId: (j) => Yt[j.id] || `ss-tab-${j.id}`,
                tabPanelId: (j) => _e[j.id] || j.id,
              }),
              n.jsx("div", {
                className: "ss-tabs-toolbar",
                "data-active-tab": w,
                children: n.jsx(Jt, { activeTab: w, isSuperuser: o }),
              }),
              w === "cameras" ? n.jsx(Pt, { rates: s }) : null,
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
      n.jsx(Ot, {
        cameras: t,
        sensors: r,
        childrenLinks: i,
        isSuperuser: o,
        panelsReady: h,
        authToken: a,
        onSensorsChange: c,
      }),
      n.jsx(qt, { wssConnection: f, sceneId: m, panelsReady: h }),
      n.jsx(Wt, {}),
    ],
  });
}
function Kt({ roi: e, index: s, isSuperuser: t, onChange: r, onRemove: i }) {
  const o = !t || e.readOnly,
    [m, f] = l.useState(!1),
    a = `roi-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-roi",
    id: `form-${e.svgId}`,
    ref: (c) => (c == null ? void 0 : c.setAttribute("for", e.svgId)),
    children: n.jsxs("div", {
      className: `ss-editor-row count-item col ss-editor-card${m ? " is-expanded" : ""}`,
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
                  onChange: (c) => r({ ...e, title: c.target.value }),
                  onBlur: () => {
                    var c, w;
                    if (window.ssUseReactMap) {
                      (w =
                        (c = window.ssMap) == null ? void 0 : c.numberRois) ==
                        null || w.call(c);
                      return;
                    }
                    typeof window.numberRois == "function" &&
                      window.numberRois();
                  },
                }),
                n.jsx("button", {
                  type: "button",
                  className: "ss-editor-row__toggle",
                  "aria-expanded": m,
                  "aria-controls": a,
                  title: m ? "Hide details" : "Show details",
                  onClick: () => f((c) => !c),
                  children: n.jsx("i", {
                    className: `bi ${m ? "bi-chevron-up" : "bi-chevron-down"}`,
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
                  onClick: (c) => {
                    (c.preventDefault(), c.stopPropagation(), i(e.svgId));
                  },
                  children: n.jsx("i", {
                    className: "bi bi-trash",
                    "aria-hidden": "true",
                  }),
                })
              : null,
          ],
        }),
        m
          ? n.jsxs("div", {
              className: "ss-editor-row__details",
              id: a,
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
                                onChange: (c) =>
                                  r({ ...e, volumetric: c.target.checked }),
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
                                onChange: (c) =>
                                  r({
                                    ...e,
                                    height: Number(c.target.value) || 1,
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
                                onChange: (c) =>
                                  r({
                                    ...e,
                                    buffer_size: Number(c.target.value) || 0,
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
                    onChange: (c) =>
                      r({
                        ...e,
                        greenMin: c.greenMin,
                        yellowMin: c.yellowMin,
                        redMin: c.redMin,
                        rangeMax: c.rangeMax,
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
function Qt({
  tripwire: e,
  index: s,
  isSuperuser: t,
  onChange: r,
  onRemove: i,
}) {
  const o = !!t && !e.readOnly,
    [m, f] = l.useState(!1),
    a = `trip-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-tripwire",
    id: `form-${e.svgId}`,
    ref: (c) => (c == null ? void 0 : c.setAttribute("for", e.svgId)),
    children: n.jsxs("div", {
      className: `ss-editor-row count-item col ss-editor-card${m ? " is-expanded" : ""}`,
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
                  onChange: (c) => {
                    o && r({ ...e, title: c.target.value });
                  },
                  onBlur: () => {
                    var c, w, x;
                    if (window.ssUseReactMap) {
                      (w =
                        (c = window.ssMap) == null
                          ? void 0
                          : c.numberTripwires) == null || w.call(c);
                      return;
                    }
                    (x = window.numberTripwires) == null || x.call(window);
                  },
                }),
                n.jsx("button", {
                  type: "button",
                  className: "ss-editor-row__toggle",
                  "aria-expanded": m,
                  "aria-controls": a,
                  title: m ? "Hide details" : "Show details",
                  onClick: () => f((c) => !c),
                  children: n.jsx("i", {
                    className: `bi ${m ? "bi-chevron-up" : "bi-chevron-down"}`,
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
                  onClick: (c) => {
                    (c.preventDefault(), c.stopPropagation(), i(e.svgId));
                  },
                  children: n.jsx("i", {
                    className: "bi bi-trash",
                    "aria-hidden": "true",
                  }),
                })
              : null,
          ],
        }),
        m
          ? n.jsx("div", {
              className: "ss-editor-row__details",
              id: a,
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
function Xt(e) {
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
function Zt(e, s) {
  const r = {
      name: (s.title || "").trim() || `roi_${s.uuid || "new"}`,
      scene: e,
      points: s.points || [],
      volumetric: !!s.volumetric,
      height: typeof s.height == "number" ? s.height : 1,
      buffer_size: typeof s.buffer_size == "number" ? s.buffer_size : 0,
    },
    i = Xt(s);
  return (
    i && (r.color_ranges = { sectors: i.sectors, range_max: i.range_max }),
    r
  );
}
function es(e, s) {
  return {
    name: (s.title || "").trim() || `tripwire_${s.uuid || "new"}`,
    scene: e,
    points: s.points || [],
    ...(typeof s.height == "number" ? { height: s.height } : {}),
  };
}
async function ts(e, s, t) {
  var I, D, j, M, b, y;
  let r, i;
  if (t != null && t.preferHidden)
    ((r = ne("id_rois")),
      (i = ne("tripwires")),
      (D = (I = window.ssMap) == null ? void 0 : I.syncFromLegacyStringify) ==
        null || D.call(I));
  else {
    const p =
        (M = (j = window.ssMap) == null ? void 0 : j.getRois) == null
          ? void 0
          : M.call(j),
      _ =
        (y = (b = window.ssMap) == null ? void 0 : b.getTripwires) == null
          ? void 0
          : y.call(b);
    ((r = p
      ? p.map((E) => ({
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
      (i = _
        ? _.map((E) => ({ uuid: E.uuid, title: E.title, points: E.points }))
        : ne("tripwires")));
  }
  const [o, m] = await Promise.all([
      O.getRegions(e, s).then(Me),
      O.getTripwires(e, s).then(Me),
    ]),
    f = new Set(o.map(se).filter((p) => !!p)),
    a = new Set(),
    c = {};
  for (const p of r) {
    const _ = Zt(s, p);
    if (Ce(p.uuid) && f.has(p.uuid))
      (await O.updateRegion(e, p.uuid, _), a.add(p.uuid), (c[p.uuid] = p.uuid));
    else {
      const E = await O.createRegion(e, _),
        A = se(E);
      A && (a.add(A), p.uuid && (c[p.uuid] = A));
    }
  }
  for (const p of f) a.has(p) || (await O.deleteRegion(e, p));
  const w = new Set(m.map(se).filter((p) => !!p)),
    x = new Set(),
    h = {};
  for (const p of i) {
    const _ = es(s, p);
    if (Ce(p.uuid) && w.has(p.uuid))
      (await O.updateTripwire(e, p.uuid, _),
        x.add(p.uuid),
        (h[p.uuid] = p.uuid));
    else {
      const E = await O.createTripwire(e, _),
        A = se(E);
      A && (x.add(A), p.uuid && (h[p.uuid] = A));
    }
  }
  for (const p of w) x.has(p) || (await O.deleteTripwire(e, p));
  let v = !1;
  for (const [p, _] of Object.entries(c)) wt(p, _) && (v = !0);
  for (const [p, _] of Object.entries(h)) gt(p, _) && (v = !0);
  return (v && bt(), { roiIds: c, tripIds: h });
}
function K(e) {
  const s = window[e];
  typeof s == "function" && s();
}
function ss() {
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
function ns(e, s) {
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
function rs({
  sceneId: e,
  isSuperuser: s,
  authToken: t,
  initialRegions: r,
  initialTripwires: i,
}) {
  const o = De(),
    [m, f] = l.useState(() => r.map((d) => Re(d, e)).filter((d) => !!d)),
    [a, c] = l.useState(() => i.map((d) => ns(d, e)).filter((d) => !!d)),
    [w, x] = l.useState(!1),
    [h, v] = l.useState(!1),
    I = l.useRef(m),
    D = l.useRef(a),
    j = l.useRef(!1),
    M = l.useRef(o),
    b = l.useRef(""),
    y = l.useRef(""),
    p = l.useRef(() => {});
  ((M.current = o),
    (I.current = m),
    (D.current = a),
    l.useEffect(() => {
      (ss(),
        r.forEach((d) => {
          if (!String(d.uuid || "").trim()) return;
          const N = Re(d, e);
          N && Te(N, d.points);
        }),
        i.forEach((d) => {
          const S = String(d.uuid || "").trim();
          S &&
            ie(S, {
              title: (d.title || "").trim(),
              points: (d.points || []).map((N) => [Number(N[0]), Number(N[1])]),
            });
        }));
    }, [r, i, e]),
    l.useEffect(() => {
      p.current = async (d) => {
        var N, k, u, g, L, $, R;
        if (j.current) return;
        j.current = !0;
        const S = d && !Array.isArray(d) ? d : void 0;
        S != null && S.preferHidden
          ? (k =
              (N = window.ssMap) == null
                ? void 0
                : N.syncFromLegacyStringify) == null || k.call(N)
          : window.ssUseReactMap
            ? (L = window.ssMap) == null || L.flushHidden()
            : ((u = window.ssMap) == null || u.stringifyRois(),
              (g = window.ssMap) == null || g.stringifyTripwires());
        try {
          const C = await ts(t, e, S);
          (f((B) => Ie(B, C.roiIds, "roi")),
            c((B) => Ie(B, C.tripIds, "tripwire")),
            (b.current =
              (($ = document.getElementById("id_rois")) == null
                ? void 0
                : $.value) ?? b.current),
            (y.current =
              ((R = document.getElementById("tripwires")) == null
                ? void 0
                : R.value) ?? y.current),
            re("roi", !1),
            re("trip", !1),
            x(!1),
            v(!1),
            M.current.show("Regions saved", "ok"));
        } catch (C) {
          const B =
            C && typeof C == "object" && "message" in C
              ? String(C.message || "Save failed")
              : "Save failed";
          throw (M.current.show(B, "bad"), C);
        } finally {
          j.current = !1;
        }
      };
    }, [t, e]),
    l.useEffect(() => {
      const d = (S) => p.current(S);
      return (
        (window.ssPersistGeometry = d),
        () => {
          window.ssPersistGeometry === d && delete window.ssPersistGeometry;
        }
      );
    }, []),
    l.useEffect(() => {
      re("roi", w);
    }, [w]),
    l.useEffect(() => {
      re("trip", h);
    }, [h]),
    l.useEffect(() => {
      const d = document.getElementById("id_rois"),
        S = document.getElementById("tripwires");
      ((b.current = (d == null ? void 0 : d.value) ?? ""),
        (y.current = (S == null ? void 0 : S.value) ?? ""));
      const N = window.setTimeout(() => {
          var g;
          ((b.current = (d == null ? void 0 : d.value) ?? ""),
            (y.current = (S == null ? void 0 : S.value) ?? ""),
            (g = window.ssMap) == null || g.syncFromLegacyStringify());
        }, 1200),
        k = (g) => {
          var $;
          const L = ($ = g.detail) == null ? void 0 : $.kind;
          if (L === "trips") {
            v(!0);
            return;
          }
          if (L === "rois") {
            x(!0);
            return;
          }
          (x(!0), v(!0));
        };
      window.addEventListener("ss-geometry-stringified", k);
      const u = window.setInterval(() => {
        (d && d.value !== b.current && x(!0),
          S && S.value !== y.current && v(!0));
      }, 600);
      return () => {
        (window.clearTimeout(N),
          window.clearInterval(u),
          window.removeEventListener("ss-geometry-stringified", k));
      };
    }, []),
    l.useEffect(() => {
      const d = (u) => {
          (f((g) =>
            g.some((L) => L.svgId === u.svgId)
              ? g
              : [
                  ...g,
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
            x(!0),
            window.requestAnimationFrame(() => {
              var g;
              (g = window.numberRois) == null || g.call(window);
            }));
        },
        S = (u) => {
          (c((g) =>
            g.some((L) => L.svgId === u.svgId)
              ? g
              : [
                  ...g,
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
            v(!0),
            window.requestAnimationFrame(() => {
              var g;
              (g = window.numberTripwires) == null || g.call(window);
            }));
        };
      window.ssRoiEditors = {
        addRoi: d,
        addTripwire: S,
        hasRoi: (u) => I.current.some((g) => g.svgId === u),
        hasTripwire: (u) => D.current.some((g) => g.svgId === u),
      };
      const N = (u) => {
          const g = u.detail;
          g != null && g.svgId && d(g);
        },
        k = (u) => {
          const g = u.detail;
          g != null && g.svgId && S(g);
        };
      return (
        window.addEventListener("ss-roi-form-add", N),
        window.addEventListener("ss-tripwire-form-add", k),
        () => {
          (window.removeEventListener("ss-roi-form-add", N),
            window.removeEventListener("ss-tripwire-form-add", k),
            delete window.ssRoiEditors);
        }
      );
    }, [e]),
    l.useEffect(() => {
      He({ regions: m.length, tripwires: a.length });
    }, [m.length, a.length]),
    l.useEffect(() => {
      const d = document.getElementById("no-regions");
      d && (d.style.display = m.length ? "none" : "");
    }, [m.length]),
    l.useEffect(() => {
      const d = document.getElementById("no-tripwires");
      d && (d.style.display = a.length ? "none" : "");
    }, [a.length]),
    l.useEffect(() => {
      const d = document.getElementById("no-regions");
      if (d && ((d.hidden = m.length > 0), m.length === 0)) {
        d.innerHTML = "";
        const S = document.createElement("p");
        if (
          ((S.textContent = "No regions of interest defined."),
          d.appendChild(S),
          s)
        ) {
          const N = document.createElement("button");
          ((N.type = "button"),
            (N.className = "btn btn-primary btn-sm"),
            (N.id = "empty-new-roi"),
            (N.textContent = "+ New Region"),
            d.appendChild(N));
        }
      }
    }, [m.length, s]),
    l.useEffect(() => {
      const d = document.getElementById("no-tripwires");
      if (d && ((d.hidden = a.length > 0), a.length === 0)) {
        d.innerHTML = "";
        const S = document.createElement("p");
        if (((S.textContent = "No tripwires defined."), d.appendChild(S), s)) {
          const N = document.createElement("button");
          ((N.type = "button"),
            (N.className = "btn btn-primary btn-sm"),
            (N.id = "empty-new-tripwire"),
            (N.textContent = "+ New Tripwire"),
            d.appendChild(N));
        }
      }
    }, [a.length, s]));
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
      const N = d.replace(/^roi_/, "");
      (ht(N),
        f((u) => u.filter((g) => g.svgId !== d)),
        (k = window.ssMap) == null || k.flushHidden());
      try {
        await p.current();
      } catch {
        x(!0);
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
      const N = d.replace(/^tripwire_/, "");
      (pt(N),
        c((u) => u.filter((g) => g.svgId !== d)),
        (k = window.ssMap) == null || k.flushHidden());
      try {
        await p.current();
      } catch {
        v(!0);
      }
    },
    A = document.getElementById("roi-fields"),
    T = document.getElementById("tripwire-fields");
  return n.jsxs(n.Fragment, {
    children: [
      A
        ? J.createPortal(
            n.jsx(n.Fragment, {
              children: m.map((d, S) =>
                n.jsx(
                  Kt,
                  {
                    roi: d,
                    index: S,
                    isSuperuser: s,
                    onChange: (N) => {
                      (x(!0),
                        Te(N),
                        f((k) => k.map((u) => (u.svgId === N.svgId ? N : u))));
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
      T
        ? J.createPortal(
            n.jsx(n.Fragment, {
              children: a.map((d, S) =>
                n.jsx(
                  Qt,
                  {
                    tripwire: d,
                    index: S,
                    isSuperuser: s,
                    onChange: (N) => {
                      (v(!0),
                        ie(N.uuid, { title: N.title }),
                        c((k) => k.map((u) => (u.svgId === N.svgId ? N : u))));
                    },
                    onRemove: E,
                  },
                  d.svgId,
                ),
              ),
            }),
            T,
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
function me(e, s) {
  return H(e[s]);
}
function os(e) {
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
function as(e, s) {
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
    areaJson: is(e) || (s == null ? void 0 : s.areaJson) || "{}",
    calibrateHref: `?ss=calibrate-sensor&id=${o}`,
    editHref: `?ss=sensor-edit&id=${r || o}`,
    deleteUrl: t
      ? `/singleton_sensor/delete/${t}/`
      : ((s == null ? void 0 : s.deleteUrl) ?? null),
  };
}
function cs(e, s, t) {
  var w;
  const r = H(e.uid || e.id);
  if (!r) return null;
  const i = H(e.child_type || (t == null ? void 0 : t.childType), "local"),
    o = e.child != null ? H(e.child) : null,
    m =
      e.remote_child_id != null
        ? H(e.remote_child_id)
        : ((t == null ? void 0 : t.remoteChildId) ?? null),
    f = o
      ? (w = s.find((x) => x.id === o)) == null
        ? void 0
        : w.name
      : void 0,
    a = H(
      e.name || e.child_name || f || (t == null ? void 0 : t.name),
      "Child",
    ),
    c = i === "local" && o ? o : m || r;
  return {
    id: r,
    name: a,
    childType: i,
    remoteChildId: m,
    detailUrl: o ? `/${o}/` : ((t == null ? void 0 : t.detailUrl) ?? null),
    thumbnailUrl: (t == null ? void 0 : t.thumbnailUrl) ?? null,
    mapUrl: (t == null ? void 0 : t.mapUrl) ?? null,
    restUid: c,
    editHref: `?ss=child-edit&id=${c}`,
    deleteUrl: /^\d+$/.test(r)
      ? `/child/delete/${r}/`
      : ((t == null ? void 0 : t.deleteUrl) ?? null),
  };
}
function ls(e, s, t) {
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
function ds(e, s, t) {
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
function us(e, s, t) {
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
const ms = new Set([
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
function fs(e) {
  return !!(e && ms.has(e));
}
function hs({
  sceneId: e,
  authToken: s,
  isSuperuser: t,
  isKubernetes: r,
  scenes: i,
  cameras: o,
  sensors: m = [],
  onCamerasChange: f,
  onSensorsChange: a,
  onChildrenChange: c,
  mapUrl: w = null,
  mapScale: x = null,
}) {
  var k;
  const { sheet: h, open: v, close: I } = it(),
    D = l.useCallback(
      (u, g = null) => {
        const L = ae(u);
        (L && ce(L), v(u, g));
      },
      [v],
    ),
    j = l.useCallback(() => {
      const u = ae(h.action);
      (I(), u && ce(u));
    }, [I, h.action]);
  (l.useEffect(() => {
    const u = (g) => {
      const L = g.target;
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
        !fs(C) ||
        ((R.pathname === window.location.pathname ||
          R.pathname === `/${e}/` ||
          R.pathname === `/${e}`) &&
          (g.preventDefault(),
          g.stopPropagation(),
          D(C, R.searchParams.get("id"))));
    };
    return (
      document.addEventListener("click", u, !0),
      () => document.removeEventListener("click", u, !0)
    );
  }, [D, e]),
    l.useEffect(() => {
      const u = ae(h.action);
      u && ce(u);
    }, [h.action]));
  const M = l.useCallback(() => {
      window.location.reload();
    }, []),
    b = l.useCallback(
      (u) => {
        if (!u) return;
        const g = os(u);
        if (!g) return;
        const L = me(u, "scene"),
          $ = h.action === "cam-edit" && h.id ? String(h.id) : null;
        f((R) =>
          L && L !== e
            ? R.filter(
                (C) =>
                  C.id !== g.id &&
                  C.sensorId !== g.sensorId &&
                  C.sensorId !== $,
              )
            : ls(R, g, $),
        );
      },
      [f, e, h.action, h.id],
    ),
    y = l.useCallback(
      (u) => {
        if (!u) return;
        const g = me(u, "scene"),
          L = h.action === "sensor-edit" && h.id ? String(h.id) : null;
        a(($) => {
          const R = $.find(
              (B) =>
                B.sensorId === L ||
                B.sensorId === String(u.uid || "") ||
                B.id === String(u.id || ""),
            ),
            C = as(u, R);
          return C
            ? g && g !== e
              ? $.filter(
                  (B) =>
                    B.id !== C.id &&
                    B.sensorId !== C.sensorId &&
                    B.sensorId !== L,
                )
              : ds($, C, L)
            : $;
        });
      },
      [a, e, h.action, h.id],
    ),
    p = l.useCallback(
      (u) => {
        if (!u) return;
        const g = me(u, "parent"),
          L = h.action === "child-edit" && h.id ? String(h.id) : null;
        c(($) => {
          const R = $.find(
              (B) => B.id === String(u.uid || u.id || "") || B.restUid === L,
            ),
            C = cs(u, i, R);
          return C
            ? g && g !== e
              ? $.filter(
                  (B) =>
                    B.id !== C.id && B.restUid !== C.restUid && B.restUid !== L,
                )
              : us($, C, L)
            : $;
        });
      },
      [c, e, i, h.action, h.id],
    ),
    _ = l.useMemo(() => {
      const u = new Map();
      return (o.forEach((g) => u.set(String(g.id), g)), u);
    }, [o]),
    E = l.useMemo(() => {
      const u = new Map();
      return (o.forEach((g) => u.set(String(g.sensorId), g)), u);
    }, [o]),
    A = l.useMemo(() => {
      const u = new Map();
      return (m.forEach((g) => u.set(String(g.id), g)), u);
    }, [m]);
  if (!t) return null;
  const T = h.action,
    d = T === "calibrate-cam" && h.id ? _.get(String(h.id)) : null,
    S = T === "calibrate-sensor" && h.id ? A.get(String(h.id)) : null,
    N =
      T === "cam-edit" && h.id
        ? ((k = E.get(String(h.id))) == null ? void 0 : k.sensorId) ||
          String(h.id)
        : null;
  return n.jsxs(n.Fragment, {
    children: [
      n.jsx(Ze, {
        open: T === "cam-create" || T === "cam-edit",
        mode: T === "cam-edit" ? "edit" : "create",
        sceneId: e,
        scenes: i,
        sensorUid: T === "cam-edit" ? N : null,
        authToken: s,
        onClose: j,
        onSaved: b,
      }),
      n.jsx(et, {
        open: T === "sensor-create" || T === "sensor-edit",
        mode: T === "sensor-edit" ? "edit" : "create",
        sceneId: e,
        scenes: i,
        sensorUid: T === "sensor-edit" ? h.id : null,
        authToken: s,
        onClose: j,
        onSaved: y,
      }),
      n.jsx(ot, {
        open: T === "child-create" || T === "child-edit",
        mode: T === "child-edit" ? "edit" : "create",
        parentSceneId: e,
        childUid: T === "child-edit" ? h.id : null,
        scenes: i,
        authToken: s,
        onClose: j,
        onSaved: p,
      }),
      n.jsx(at, {
        open: T === "scene-manage",
        sceneId: e,
        authToken: s,
        onClose: j,
        onSaved: M,
      }),
      n.jsx(tt, {
        open: !!d,
        cameraPk: (d == null ? void 0 : d.id) || "",
        sensorId: (d == null ? void 0 : d.sensorId) || "",
        cameraName: (d == null ? void 0 : d.name) || "",
        sceneId: e,
        authToken: s,
        isKubernetes: r,
        onClose: j,
        onSaved: M,
      }),
      n.jsx(st, {
        open: !!S || T === "calibrate-sensor",
        sensorPk: (S == null ? void 0 : S.id) || h.id || "",
        sensorId: (S == null ? void 0 : S.sensorId) || "",
        sceneId: e,
        authToken: s,
        mapUrlHint: w,
        mapScale: x,
        onClose: j,
        onSaved: M,
      }),
    ],
  });
}
const ze = "ss-workspace-layout-mode",
  ps = 224,
  ws = 256,
  oe = 120;
function $e() {
  return {
    w: Math.max(window.innerWidth || 0, 320),
    h: Math.max(window.innerHeight || 0, 320),
  };
}
function gs() {
  try {
    const e = window.localStorage.getItem(ze);
    if (e === "auto" || e === "stack" || e === "row") return e;
  } catch {}
  return "auto";
}
function bs(e) {
  try {
    window.localStorage.setItem(ze, e);
  } catch {}
}
function ys() {
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
function Le(e, s, t) {
  const r = Math.max(s, oe),
    i = Math.max(t, oe),
    o = Math.min(r / e.w, i / e.h);
  return !Number.isFinite(o) || o <= 0 ? 0 : e.w * o * (e.h * o);
}
function ke(e, s, t) {
  const r = Math.max(e.w - 32, oe),
    i = Math.max(e.h - t, oe);
  if (r < 720 || i / r > 1.25) return "stack";
  if (!s) return r / i >= 1.35 ? "stack" : "row";
  const o = s.w / s.h,
    m = Le(s, r, i - ps),
    f = Le(s, r - ws, i);
  return o >= 1.35
    ? m >= f * 0.92
      ? "stack"
      : "row"
    : o <= 1.05
      ? f >= m * 0.92
        ? "row"
        : "stack"
      : f > m
        ? "row"
        : "stack";
}
function vs(e = {}) {
  const s = e.chromeHeightPx ?? 112,
    [t, r] = l.useState(() => (typeof window < "u" ? gs() : "auto")),
    [i, o] = l.useState(() => ke($e(), null, s)),
    m = l.useCallback((a) => {
      (r(a), bs(a));
    }, []);
  return (
    l.useEffect(() => {
      let a = 0,
        c = null;
      const w = () => {
        (cancelAnimationFrame(a),
          (a = requestAnimationFrame(() => {
            const j = ke($e(), ys(), s);
            c !== j && ((c = j), o((M) => (M === j ? M : j)));
          })));
      };
      (w(),
        window.addEventListener("resize", w),
        window.addEventListener("ss-map-host-ready", w));
      const x = document.querySelector("#ss-map-host #map img");
      x && !x.complete && x.addEventListener("load", w);
      const h = document.getElementById("ss-map-host");
      let v = null;
      h &&
        typeof ResizeObserver < "u" &&
        ((v = new ResizeObserver(() => w())), v.observe(h));
      const I = window.setInterval(w, 500),
        D = window.setTimeout(() => window.clearInterval(I), 8e3);
      return () => {
        (cancelAnimationFrame(a),
          window.removeEventListener("resize", w),
          window.removeEventListener("ss-map-host-ready", w),
          x == null || x.removeEventListener("load", w),
          v == null || v.disconnect(),
          window.clearInterval(I),
          window.clearTimeout(D));
      };
    }, [s, t]),
    { layout: t === "auto" ? i : t, mode: t, setMode: m, autoLayout: i }
  );
}
function xs() {
  const [e, s] = l.useState(!1);
  return (
    l.useEffect(() => {
      const t = () => {
        const m = document.getElementById("mqtt_status"),
          f = !!(m != null && m.classList.contains("connected"));
        s((a) => (a === f ? a : f));
      };
      t();
      const r = document.getElementById("mqtt_status");
      let i = null;
      r &&
        ((i = new MutationObserver(t)),
        i.observe(r, { attributes: !0, attributeFilter: ["class"] }));
      const o = (m) => {
        const f = m.detail;
        typeof (f == null ? void 0 : f.connected) == "boolean"
          ? s((a) => (a === f.connected ? a : !!f.connected))
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
function js() {
  const [e, s] = l.useState({});
  return (
    l.useEffect(() => {
      const t = (f, a) => {
          s((c) => (c[f] === a ? c : { ...c, [f]: a }));
        },
        r = (f, a) => {
          t(f, a);
        },
        i = () => s({});
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setCameraRate: r,
        clearRates: i,
      };
      const o = (f) => {
          const a = f.detail;
          a != null && a.sensorId && t(a.sensorId, a.text || a.hz || "--");
        },
        m = () => i();
      return (
        window.addEventListener("ss-camera-rate", o),
        window.addEventListener("ss-telemetry-clear", m),
        () => {
          (window.removeEventListener("ss-camera-rate", o),
            window.removeEventListener("ss-telemetry-clear", m));
        }
      );
    }, []),
    e
  );
}
function Q(e) {
  return String(e);
}
function Ns(e) {
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
const Ss = [
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
function Es({ bootstrap: e }) {
  const { scene: s, urls: t, isSuperuser: r } = e,
    { layout: i, mode: o, setMode: m, autoLayout: f } = vs(),
    {
      panelSizePx: a,
      setPanelSizePx: c,
      mapFocus: w,
      toggleMapFocus: x,
    } = nt(i),
    [h, v] = l.useState("--"),
    [I, D] = l.useState(!1),
    [j, M] = l.useState(!1),
    [b, y] = l.useState(null),
    p = xs(),
    _ = js(),
    [E, A] = l.useState(e.cameras),
    [T, d] = l.useState(e.sensors || []),
    [S, N] = l.useState(e.children || []),
    [k, u] = l.useState({
      cameras: e.cameras.length,
      sensors: e.counts.sensors,
      regions: e.counts.regions,
      tripwires: e.counts.tripwires,
      children: e.counts.children,
    });
  ((window.ssUseReactMap = !!s.mapUrl),
    l.useEffect(() => {
      const C = (Y) => v(Y || "--");
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setSceneRate: C,
      };
      const B = (Y) => {
          const G = Y.detail;
          (G == null ? void 0 : G.hz) !== void 0 && C(G.hz);
        },
        z = () => v("--");
      return (
        window.addEventListener("ss-scene-rate", B),
        window.addEventListener("ss-telemetry-clear", z),
        () => {
          (window.removeEventListener("ss-scene-rate", B),
            window.removeEventListener("ss-telemetry-clear", z));
        }
      );
    }, []),
    l.useEffect(() => {
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
    l.useEffect(() => {
      const C = window.requestAnimationFrame(() => {
        typeof window.fitSceneMapDisplay == "function" &&
          window.fitSceneMapDisplay();
      });
      return () => window.cancelAnimationFrame(C);
    }, [w, a, i]));
  const g = l.useCallback(async () => {
      if (t.sceneDelete) {
        (M(!0), y(null));
        try {
          await ct(t.sceneDelete, t.scenesHome || "/");
        } catch (C) {
          (M(!1), y(C instanceof Error ? C.message : "Delete failed"));
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
          className: `scene-detail-mqtt-pill${p ? " connected" : ""}`,
          title: p ? "MQTT connected" : "MQTT disconnected",
          "data-ss-mqtt": p ? "connected" : "disconnected",
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
            n.jsx("span", { id: "scene-rate", children: h }),
            " Hz",
          ],
        }),
        n.jsx("div", {
          className: "ss-layout-toggle",
          role: "group",
          "aria-label": "Control panel layout",
          children: Ss.map((C) => {
            const B = o === C.mode,
              z = C.mode === "auto" ? ` (now ${f})` : "";
            return n.jsxs(
              "button",
              {
                type: "button",
                className: `ss-layout-toggle-btn${B ? " is-active" : ""}`,
                title: `${C.title}${z}`,
                "aria-pressed": B,
                onClick: () => m(C.mode),
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
          className: `ss-layout-toggle-btn ss-map-focus-btn${w ? " is-active" : ""}`,
          title: w ? "Show control panel (Esc)" : "Map only focus",
          "aria-pressed": w,
          onClick: x,
          children: [
            n.jsx("i", {
              className: `bi ${w ? "bi-layout-sidebar" : "bi-arrows-fullscreen"}`,
              "aria-hidden": "true",
            }),
            n.jsx("span", {
              className: "ss-layout-toggle-label",
              children: w ? "Panel" : "Map",
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
                (y(null), D(!0));
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
    className: `ss-scene-detail ss-scene-detail--workspace ss-workspace--${i}${w ? " ss-workspace--map-focus" : ""}`,
    "data-workspace-layout": i,
    "data-workspace-mode": o,
    "data-map-focus": w ? "1" : "0",
    style: { "--ss-panel-size": `${a}px` },
    children: [
      n.jsx(We, { title: s.name, back: Ns(t), actions: $ }),
      n.jsxs("div", {
        className: "ss-workspace-body",
        children: [
          n.jsx("div", {
            className: "ss-workspace-main",
            children: n.jsx(Mt, { mapUrl: s.mapUrl }),
          }),
          n.jsx(rt, { layout: i, panelSizePx: a, onResize: c, disabled: w }),
          n.jsx(Vt, {
            tabs: L,
            cameraRates: _,
            cameras: E,
            sensors: T,
            childrenLinks: S,
            isSuperuser: r,
            sceneId: s.id,
            wssConnection: e.scene.wssConnection || "",
            authToken: e.authToken,
            onSensorsChange: d,
          }),
        ],
      }),
      n.jsx(rs, {
        sceneId: s.id,
        isSuperuser: r,
        authToken: e.authToken,
        initialRegions: e.regions || [],
        initialTripwires: e.tripwires || [],
      }),
      n.jsx(hs, {
        sceneId: s.id,
        authToken: e.authToken,
        isSuperuser: r,
        isKubernetes: !!e.isKubernetes,
        scenes: e.scenes || [],
        cameras: E,
        sensors: T,
        onCamerasChange: A,
        onSensorsChange: d,
        onChildrenChange: N,
        mapUrl: s.mapUrl,
        mapScale: s.scale,
      }),
      n.jsxs(Pe, {
        open: I,
        title: "Delete scene?",
        confirmLabel: "Delete scene",
        danger: !0,
        busy: j,
        onConfirm: g,
        onCancel: () => {
          j || D(!1);
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
function _s({ bootstrap: e }) {
  return n.jsx(Je, {
    children: n.jsx(Ye, { children: n.jsx(Es, { bootstrap: e }) }),
  });
}
function Cs({ bootstrap: e }) {
  return n.jsx(_s, { bootstrap: e });
}
function Ms() {
  const e = document.getElementById("ss-scene-detail-bootstrap");
  if (!(e != null && e.textContent)) return null;
  try {
    return JSON.parse(e.textContent);
  } catch {
    return (console.error("Failed to parse scene detail bootstrap JSON"), null);
  }
}
const Ae = Ms(),
  Be = document.getElementById("ss-scene-detail-root");
Ae &&
  Be &&
  (document.documentElement.classList.add("ss-scene-workspace"),
  document.body.classList.add("ss-scene-workspace"),
  Ge.createRoot(Be).render(
    n.jsx(l.StrictMode, { children: n.jsx(Cs, { bootstrap: Ae }) }),
  ));
