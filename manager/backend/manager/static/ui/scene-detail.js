// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { r as c, j as n, c as We } from "./chunks/tokens-C2Ju3rc_.js";
import { P as Ge } from "./chunks/PageHeader-Dke5XNFH.js";
import {
  r as fe,
  u as Be,
  C as Pe,
  T as Ve,
} from "./chunks/ConfirmDialog-DanZpjzY.js";
import { L as Je } from "./chunks/LegacyConfirmHost-VsPlnSjJ.js";
import {
  r as Ye,
  c as Ke,
  m as Qe,
  p as xe,
  O as Xe,
  C as Ze,
  S as et,
  a as tt,
  b as st,
  u as nt,
  W as it,
} from "./chunks/SensorCalibratePanel-DUJoj046.js";
import { A as V } from "./chunks/actionIcons-BIxtFbWH.js";
import { a as z, u as rt } from "./chunks/rest-DXX9fmms.js";
import { C as ot, S as at } from "./chunks/SceneManagePanel-BM8p1vX0.js";
import { p as ct } from "./chunks/djangoDelete-BfD_c0xv.js";
import "./chunks/Button-CDF7QSMd.js";
const Fe = "ss-scene-tab:",
  he = "ss-scene-tab",
  pe = "ss-tab-counts";
function He(e) {
  typeof window > "u" ||
    window.dispatchEvent(new CustomEvent(pe, { detail: e }));
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
    window.dispatchEvent(new CustomEvent(he, { detail: { tabId: e } }));
}
const le = { host: "ss-map-host" };
function mt() {
  (window.dispatchEvent(new CustomEvent("ss-map-host-ready")),
    typeof window.fitSceneMapDisplay == "function" &&
      window.fitSceneMapDisplay());
}
let F = new Map(),
  H = new Map();
const we = new Set();
function W() {
  we.forEach((e) => {
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
    we.add(e),
    () => {
      we.delete(e);
    }
  );
}
function X() {
  return Array.from(F.values());
}
function Z() {
  return Array.from(H.values());
}
function ge(e, s) {
  const t = F.get(e),
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
  (F.set(e, i), O(), W());
}
function re(e, s) {
  const t = H.get(e),
    i = {
      uuid: e,
      title: s.title ?? (t == null ? void 0 : t.title) ?? "",
      points: s.points ?? (t == null ? void 0 : t.points) ?? [],
    };
  (H.set(e, i), O(), W());
}
function ht(e) {
  (F.delete(e), O(), W());
}
function pt(e) {
  (H.delete(e), O(), W());
}
function wt(e, s) {
  if (!e || !s || e === s) return !1;
  const t = F.get(e);
  return t ? (F.delete(e), F.set(s, { ...t, uuid: s }), !0) : !1;
}
function gt(e, s) {
  if (!e || !s || e === s) return !1;
  const t = H.get(e);
  return t ? (H.delete(e), H.set(s, { ...t, uuid: s }), !0) : !1;
}
function bt() {
  (O(), W());
}
function yt(e, s) {
  const t = F.get(e);
  (t
    ? F.set(e, { ...t, points: s })
    : F.set(e, {
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
    O(),
    W());
}
function xt(e, s) {
  const t = H.get(e);
  (t
    ? H.set(e, { ...t, points: s })
    : H.set(e, { uuid: e, title: "", points: s }),
    O(),
    W());
}
function vt(e) {
  const s = new Set();
  for (const t of e) {
    const i = String(t.uuid || "").trim();
    if (!i) continue;
    s.add(i);
    const r = (t.points || []).map((l) => [Number(l[0]), Number(l[1])]),
      o = t.sectors && !Array.isArray(t.sectors) ? t.sectors : null,
      m = Array.isArray(t.sectors)
        ? t.sectors
        : o == null
          ? void 0
          : o.thresholds,
      u =
        (o == null ? void 0 : o.range_max) != null
          ? Number(o.range_max)
          : t.range_max != null
            ? Number(t.range_max)
            : void 0;
    ge(i, {
      title: t.title,
      points: r,
      volumetric: t.volumetric,
      height: t.height,
      buffer_size: t.buffer_size,
      range_max: u,
      sectors: m,
    });
  }
  for (const t of Array.from(F.keys())) s.has(t) || F.delete(t);
  (O(), W());
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
  for (const t of Array.from(H.keys())) s.has(t) || H.delete(t);
  (O(), W());
}
function O() {
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
    i = s + te.top + te.bottom;
  return `-72 -32 ${t} ${i}`;
}
const St = c.memo(function ({ href: s, width: t, height: i }) {
  return n.jsx("image", {
    href: s,
    x: 0,
    y: 0,
    width: t,
    height: i,
    preserveAspectRatio: "none",
  });
});
function je() {
  return `tmp${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
function Et(e, s, t = 22) {
  const i = s[0] - e[0],
    r = s[1] - e[1],
    o = Math.hypot(i, r);
  if (o < 1) return null;
  const m = (-t * r) / o,
    u = (t * i) / o,
    l = (e[0] + s[0]) / 2,
    a = (e[1] + s[1]) / 2,
    h = l + m,
    x = a + u,
    w = m / t,
    d = u / t,
    R = -d,
    $ = w,
    I = [
      `${h},${x}`,
      `${h - w * 8 + R * 4},${x - d * 8 + $ * 4}`,
      `${h - w * 8 - R * 4},${x - d * 8 - $ * 4}`,
    ].join(" ");
  return { arrow: { x1: l, y1: a, x2: h, y2: x }, head: I };
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
const Ct = c.memo(function ({ mapHref: s, mapWidth: t, mapHeight: i }) {
  const [r, o] = c.useState(() => X()),
    [m, u] = c.useState(() => Z()),
    [l, a] = c.useState("idle"),
    [h, x] = c.useState([]),
    w = Ye(),
    d = i || Ke(i);
  (c.useEffect(
    () =>
      ft(() => {
        (o(X()), u(Z()));
      }),
    [],
  ),
    c.useEffect(() => {
      var v;
      (v = window.ssReapplyRoiColors) == null || v.call(window);
    }, [r]),
    c.useEffect(() => {
      const v = () => {
          (a("add-roi"), x([]));
        },
        j = () => {
          (a("add-trip"), x([]));
        };
      window.ssMapReact = { startAddRoi: v, startAddTripwire: j };
      const g = (M) => {
        const _ = M.target;
        if (!_) return;
        const A = _.closest(
          "#new-roi, #empty-new-roi, #new-tripwire, #empty-new-tripwire",
        );
        A && (M.preventDefault(), A.id.includes("trip") ? j() : v());
      };
      return (
        document.addEventListener("click", g, !0),
        () => {
          (document.removeEventListener("click", g, !0),
            delete window.ssMapReact);
        }
      );
    }, []));
  const R = c.useCallback((v) => Qe(v[0], v[1], w, d), [w, d]),
    $ = (v) => {
      if (l === "idle") return;
      const j = v.currentTarget,
        g = j.createSVGPoint();
      ((g.x = v.clientX), (g.y = v.clientY));
      const M = j.getScreenCTM();
      if (!M) return;
      const _ = g.matrixTransform(M.inverse()),
        A = xe(_.x, _.y, w, d);
      if (l === "add-roi") {
        if (h.length >= 3) {
          const T = R(h[0]),
            L = _.x - T[0],
            B = _.y - T[1];
          if (Math.hypot(L, B) < 12) {
            const p = je();
            (ge(p, {
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
                  detail: { svgId: `roi_${p}`, uuid: p, title: "" },
                }),
              ),
              x([]),
              a("idle"));
            return;
          }
        }
        x((T) => [...T, A]);
        return;
      }
      if (l === "add-trip") {
        const T = [...h, A];
        if (T.length >= 2) {
          const L = je();
          (re(L, { title: "", points: T.slice(0, 2) }),
            window.dispatchEvent(
              new CustomEvent("ss-tripwire-form-add", {
                detail: { svgId: `tripwire_${L}`, uuid: L, title: "" },
              }),
            ),
            x([]),
            a("idle"));
        } else x(T);
      }
    },
    I = (v, j, g, M) => {
      (M.stopPropagation(), M.preventDefault());
      const _ = M.target.ownerSVGElement;
      if (!_) return;
      const A = (L) => {
          const B = _.createSVGPoint();
          ((B.x = L.clientX), (B.y = L.clientY));
          const p = _.getScreenCTM();
          if (!p) return;
          const S = B.matrixTransform(p.inverse()),
            f = xe(S.x, S.y, w, d);
          if (v === "roi") {
            const N = X().find((b) => b.uuid === j);
            if (!N) return;
            const y = N.points.map((b, E) => (E === g ? f : b));
            yt(j, y);
          } else {
            const N = Z().find((b) => b.uuid === j);
            if (!N) return;
            const y = N.points.map((b, E) => (E === g ? f : b));
            xt(j, y);
          }
        },
        T = () => {
          (window.removeEventListener("mousemove", A),
            window.removeEventListener("mouseup", T));
        };
      (window.addEventListener("mousemove", A),
        window.addEventListener("mouseup", T));
    },
    k = c.useMemo(() => h.map(R), [h, R]);
  return n.jsxs("svg", {
    id: "svgout",
    className: `ss-react-scene-map${l !== "idle" ? ` is-${l}` : ""}`,
    viewBox: Nt(t, i),
    preserveAspectRatio: "xMidYMid meet",
    width: "100%",
    height: "100%",
    onClick: $,
    children: [
      n.jsx(St, { href: s, width: t, height: i }),
      r.map((v) => {
        const j = v.points.map(R),
          g = j.map((_) => _.join(",")).join(" "),
          M = _t(j);
        return n.jsxs(
          "g",
          {
            id: `roi_${v.uuid}`,
            className: "roi",
            children: [
              n.jsx("polygon", { points: g, className: "ss-react-roi-poly" }),
              v.title && M
                ? n.jsx("text", {
                    className: "ss-react-roi-title",
                    x: M[0],
                    y: M[1],
                    pointerEvents: "none",
                    children: v.title,
                  })
                : null,
              j.map((_, A) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: _[0],
                    cy: _[1],
                    r: 6,
                    onMouseDown: (T) => I("roi", v.uuid, A, T),
                  },
                  A,
                ),
              ),
            ],
          },
          v.uuid,
        );
      }),
      m.map((v) => {
        const j = v.points.map(R);
        if (j.length < 2) return null;
        const g = Et(j[0], j[1]);
        return n.jsxs(
          "g",
          {
            id: `tripwire_${v.uuid}`,
            className: "tripwire",
            children: [
              n.jsx("line", {
                className: "tripline ss-react-trip-line",
                x1: j[0][0],
                y1: j[0][1],
                x2: j[1][0],
                y2: j[1][1],
              }),
              g
                ? n.jsxs("g", {
                    className: "ss-react-trip-dir",
                    pointerEvents: "none",
                    children: [
                      n.jsx("line", {
                        className: "ss-react-trip-arrow",
                        x1: g.arrow.x1,
                        y1: g.arrow.y1,
                        x2: g.arrow.x2,
                        y2: g.arrow.y2,
                      }),
                      n.jsx("polygon", {
                        className: "ss-react-trip-arrowhead",
                        points: g.head,
                      }),
                    ],
                  })
                : null,
              v.title
                ? n.jsx("text", {
                    className: "ss-react-trip-title",
                    x: (j[0][0] + j[1][0]) / 2,
                    y: (j[0][1] + j[1][1]) / 2 - 14,
                    pointerEvents: "none",
                    children: v.title,
                  })
                : null,
              j.map((M, _) =>
                n.jsx(
                  "circle",
                  {
                    className: "ss-react-vertex",
                    cx: M[0],
                    cy: M[1],
                    r: 6,
                    onMouseDown: (A) => I("trip", v.uuid, _, A),
                  },
                  _,
                ),
              ),
            ],
          },
          v.uuid,
        );
      }),
      k.length > 0
        ? n.jsxs("g", {
            className: "ss-react-draft",
            children: [
              l === "add-roi" && k.length >= 3
                ? n.jsx("polygon", {
                    points: k.map((v) => v.join(",")).join(" "),
                    className: "ss-react-draft-poly",
                  })
                : null,
              l === "add-roi" && k.length === 2
                ? n.jsx("polyline", {
                    points: k.map((v) => v.join(",")).join(" "),
                    className: "ss-react-draft-line",
                  })
                : null,
              k.map((v, j) =>
                n.jsx(
                  "circle",
                  { cx: v[0], cy: v[1], r: 5, className: "ss-react-draft-pt" },
                  j,
                ),
              ),
            ],
          })
        : null,
    ],
  });
});
function Ne() {
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
const Mt = c.memo(function ({
  mapUrl: s = null,
  mapWidth: t = 1280,
  mapHeight: i = 720,
}) {
  const r = c.useRef(null),
    [o, m] = c.useState(!1),
    [u, l] = c.useState(null),
    a = !!window.ssUseReactMap && !!s;
  (c.useEffect(() => {
    if (!a || !s) {
      l(null);
      return;
    }
    let w = !1;
    const d = new Image();
    return (
      (d.onload = () => {
        !w &&
          d.naturalWidth > 0 &&
          d.naturalHeight > 0 &&
          l({ width: d.naturalWidth, height: d.naturalHeight });
      }),
      (d.src = s),
      () => {
        w = !0;
      }
    );
  }, [a, s]),
    c.useEffect(() => {
      const w = r.current,
        d = document.getElementById(le.host);
      if (!w || !d) return;
      if ((w.appendChild(d), (d.hidden = !1), a)) {
        document.body.classList.add("ss-use-react-map");
        const j = d.querySelector(
          "svg#svgout, svg.ss-snap-legacy, svg#svgout-snap",
        );
        j &&
          (j.classList.add("ss-snap-legacy"),
          j.id === "svgout" && (j.id = "svgout-snap"));
      }
      (mt(), m(!0));
      let R = 0,
        $ = -1,
        I = -1;
      const k = () => {
        R ||
          (R = window.requestAnimationFrame(() => {
            R = 0;
            const j = Math.round(w.clientWidth),
              g = Math.round(w.clientHeight);
            if (!(j === $ && g === I && $ >= 0))
              if ((($ = j), (I = g), !a)) Ne();
              else {
                const M = d.querySelector(".scene-map-stage");
                (M && Se(M), Ne());
              }
          }));
      };
      window.addEventListener("resize", k);
      let v = null;
      return (
        typeof ResizeObserver < "u" &&
          ((v = new ResizeObserver(() => k())), v.observe(w)),
        k(),
        () => {
          (R && window.cancelAnimationFrame(R),
            window.removeEventListener("resize", k),
            v == null || v.disconnect(),
            document.body.classList.remove("ss-use-react-map"));
          const j = d.querySelector("svg#svgout-snap, svg.ss-snap-legacy");
          if (j && j.id === "svgout-snap") {
            const M = d.querySelector("svg.ss-react-scene-map");
            (!M || M.id !== "svgout") && (j.id = "svgout");
          }
          const g = document.getElementById("ss-legacy-map-parking");
          g && d.parentElement === w && (g.appendChild(d), (d.hidden = !0));
        }
      );
    }, [a]),
    c.useEffect(() => {
      if (!a || !o) return;
      const w = document.getElementById(le.host),
        d = w == null ? void 0 : w.querySelector(".scene-map-stage");
      d && Se(d);
    }, [a, o, u]));
  const h = o ? document.getElementById(le.host) : null,
    x = (h == null ? void 0 : h.querySelector(".scene-map-stage")) ?? null;
  return n.jsxs("div", {
    className: "ss-scene-map-pane",
    children: [
      n.jsx("div", { ref: r, className: "ss-scene-map-slot" }),
      a && x && s && u
        ? fe.createPortal(
            n.jsx("div", {
              className: "ss-react-map-layer",
              children: n.jsx(Ct, {
                mapHref: s,
                mapWidth: u.width || t,
                mapHeight: u.height || i,
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
  const i = c.useRef([]),
    r = c.useRef(null),
    o = c.useCallback((l, a) => {
      i.current[l] = a;
    }, []);
  c.useEffect(() => {
    if (s < 0) return;
    const l = r.current;
    if (!l) return;
    const a = document.activeElement;
    if (!(a instanceof Node) || !l.contains(a)) return;
    const h = i.current[s];
    h && a !== h && h.focus();
  }, [s]);
  const m = c.useCallback(
      (l) => {
        var a;
        (t(l), (a = i.current[l]) == null || a.focus());
      },
      [t],
    ),
    u = c.useCallback(
      (l, a) => {
        const h = Rt(l.key, a, e);
        h !== null && (l.preventDefault(), m(h));
      },
      [m, e],
    );
  return { listRef: r, setTabRef: o, onTabKeyDown: u };
}
function kt(e) {
  return `ss-tab-${e.id}`;
}
function At(e) {
  return `ss-tab-panel-${e.id}`;
}
function Lt({
  tabs: e,
  activeId: s,
  onChange: t,
  id: i,
  tabDomId: r = kt,
  tabPanelId: o = At,
}) {
  const m = Tt(e, s),
    u = c.useCallback(
      (x) => {
        const w = e[x];
        w && t(w.id);
      },
      [t, e],
    ),
    {
      listRef: l,
      setTabRef: a,
      onTabKeyDown: h,
    } = $t({ count: e.length, focusIndex: m, onSelectIndex: u });
  return n.jsx("div", {
    ref: l,
    className: "ss-tabs-list",
    role: "tablist",
    id: i,
    children: e.map((x, w) => {
      const d = x.id === s;
      return n.jsxs(
        "button",
        {
          ref: (R) => a(w, R),
          type: "button",
          role: "tab",
          id: r(x),
          "aria-selected": d,
          "aria-controls": o(x),
          tabIndex: w === m ? 0 : -1,
          className: `ss-tabs-tab${d ? " is-active" : ""}`,
          onClick: () => t(x.id),
          onKeyDown: (R) => h(R, w),
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
const qe = "ss-camera-strip-fit";
function Dt() {
  try {
    const e = window.localStorage.getItem(qe);
    if (e === "cover" || e === "contain") return e;
  } catch {}
  return "contain";
}
function Bt(e) {
  try {
    window.localStorage.setItem(qe, e);
  } catch {}
}
function Ue(e) {
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
    r = Ue(s);
  !r &&
    i &&
    ((i.textContent || "").trim() !== "--" && (i.textContent = "--"),
    i.classList.add("telemetry-hide"));
  const o = ((i == null ? void 0 : i.textContent) || "").trim(),
    m = r ? "1" : "0";
  (e.dataset.ssOnline !== m &&
    ((e.dataset.ssOnline = m),
    e.classList.toggle("is-online", r),
    e.classList.toggle("is-offline", !r)),
    e.dataset.ssRate !== (o || "--") && (e.dataset.ssRate = o || "--"));
  let u = e.querySelector(".ss-camera-strip-badge");
  u ||
    ((u = document.createElement("span")),
    (u.className = "ss-camera-strip-badge"),
    u.setAttribute("aria-hidden", "true"),
    (e.querySelector(".card-header") || e).appendChild(u));
  const l = r ? "Live" : "Offline";
  (u.textContent !== l && (u.textContent = l),
    u.classList.toggle("is-online", r),
    u.classList.toggle("is-offline", !r),
    t && t.hidden !== r && (t.hidden = r));
}
function Pt({ rates: e = {} }) {
  const [s, t] = c.useState(() => (typeof window < "u" ? Dt() : "contain"));
  return (
    c.useEffect(() => {
      const i = document.documentElement;
      ((i.dataset.ssCameraFit = s), Bt(s));
      const r = document.getElementById("cameras");
      r && ((r.dataset.ssCameraFit = s), r.classList.add("ss-camera-strip"));
    }, [s]),
    c.useEffect(() => {
      Object.entries(e).forEach(([i, r]) => {
        var l;
        const o =
            (l = document.querySelector(
              `[data-ss-card-sensor="${CSS.escape(i)}"]`,
            )) == null
              ? void 0
              : l.closest(".camera-card"),
          m =
            o == null
              ? void 0
              : o.querySelector(
                  "img[data-ss-card-sensor], img[id^='card-preview-']",
                ),
          u = document.getElementById(`rate-${i}`);
        if (!Ue(m)) {
          (u &&
            ((u.textContent || "").trim() !== "--" && (u.textContent = "--"),
            u.classList.add("telemetry-hide")),
            o && de(o));
          return;
        }
        (u &&
          u.textContent !== r &&
          ((u.textContent = r), u.classList.remove("telemetry-hide")),
          o && de(o));
      });
    }, [e]),
    c.useEffect(() => {
      const i = document.getElementById("cameras");
      if (!i) return;
      i.classList.add("ss-camera-strip");
      let r = 0,
        o = !1;
      const m = () => {
          if (!o) {
            o = !0;
            try {
              i.querySelectorAll(".camera-card").forEach(de);
            } finally {
              o = !1;
            }
          }
        },
        u = () => {
          r ||
            (r = window.requestAnimationFrame(() => {
              ((r = 0), m());
            }));
        };
      m();
      const l = new MutationObserver(u);
      l.observe(i, {
        subtree: !0,
        childList: !0,
        attributes: !0,
        attributeFilter: ["class", "src"],
      });
      const a = window.setInterval(m, 2e3);
      return () => {
        (l.disconnect(),
          window.clearInterval(a),
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
async function be(e) {
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
    c.useEffect(() => {
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
                                className: `bi ${V.configure}`,
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
                                    className: `bi ${V.delete}`,
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
function Ht({
  sensors: e,
  isSuperuser: s,
  authToken: t = "",
  onSensorsChange: i,
}) {
  const r = Be(),
    [o, m] = c.useState(null),
    [u, l] = c.useState(!1),
    [a, h] = c.useState(null),
    x = !!(t && i);
  c.useEffect(() => {
    var d;
    (d = window.ssDrawSingletonSensors) == null || d.call(window);
  }, [e]);
  const w = c.useCallback(async () => {
    var d;
    if (!(!o || !t || !i)) {
      (l(!0), h(null));
      try {
        (await z.deleteSensor(t, o.sensorId),
          (d = window.ssRemoveSingletonSensor) == null ||
            d.call(window, o.sensorId),
          i((R) => R.filter(($) => $.id !== o.id && $.sensorId !== o.sensorId)),
          r.show("Sensor deleted", "ok"),
          m(null));
      } catch (R) {
        h(R.message || "Delete failed");
      } finally {
        l(!1);
      }
    }
  }, [t, i, o, r]);
  return n.jsxs(n.Fragment, {
    children: [
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
            children: e.map((d) =>
              n.jsxs(
                "div",
                {
                  className: "ss-tab-row singleton count-item",
                  "data-sensor-name": d.name,
                  children: [
                    d.iconUrl
                      ? n.jsx("img", {
                          className: "sensor-icon ss-tab-row__icon",
                          width: 20,
                          height: 20,
                          src: d.iconUrl,
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
                          children: d.name,
                        }),
                        n.jsx("button", {
                          type: "button",
                          className:
                            "ss-tab-row__meta sensor-id ss-tab-row__copy-id",
                          title: "Click to copy ID",
                          onClick: () => void be(d.sensorId),
                          children: d.sensorId,
                        }),
                      ],
                    }),
                    n.jsx("input", {
                      type: "hidden",
                      className: "area-json",
                      value: d.areaJson,
                      readOnly: !0,
                    }),
                    s
                      ? n.jsxs("div", {
                          className: "ss-tab-row__actions ss-entity-actions",
                          children: [
                            n.jsx("a", {
                              className: "ss-icon-btn sensor_calibrate",
                              href: d.calibrateHref,
                              id: `sensor_calibrate_${d.id}`,
                              title: `Configure ${d.name}`,
                              "aria-label": `Configure ${d.name}`,
                              children: n.jsx("i", {
                                className: `bi ${V.configure}`,
                                "aria-hidden": "true",
                              }),
                            }),
                            x
                              ? n.jsx("button", {
                                  type: "button",
                                  className: "ss-icon-btn ss-icon-btn--danger",
                                  title: `Delete ${d.name}`,
                                  "aria-label": `Delete ${d.name}`,
                                  onClick: () => {
                                    (h(null), m(d));
                                  },
                                  children: n.jsx("i", {
                                    className: `bi ${V.delete}`,
                                    "aria-hidden": "true",
                                  }),
                                })
                              : d.deleteUrl
                                ? n.jsx("a", {
                                    className:
                                      "ss-icon-btn ss-icon-btn--danger",
                                    href: d.deleteUrl,
                                    title: `Delete ${d.name}`,
                                    "aria-label": `Delete ${d.name}`,
                                    children: n.jsx("i", {
                                      className: `bi ${V.delete}`,
                                      "aria-hidden": "true",
                                    }),
                                  })
                                : null,
                          ],
                        })
                      : null,
                  ],
                },
                d.id,
              ),
            ),
          }),
      n.jsxs(Pe, {
        open: !!o,
        title: "Delete sensor?",
        confirmLabel: "Delete",
        danger: !0,
        busy: u,
        onConfirm: w,
        onCancel: () => {
          u || (m(null), h(null));
        },
        children: [
          n.jsxs("p", {
            children: [
              "Are you sure you want to delete",
              " ",
              n.jsx("strong", {
                children: (o == null ? void 0 : o.name) || "this sensor",
              }),
              "?",
            ],
          }),
          n.jsx("p", { children: "This action cannot be undone." }),
          a ? n.jsx("p", { className: "ss-confirm-error", children: a }) : null,
        ],
      }),
    ],
  });
}
function qt({ childrenLinks: e, isSuperuser: s }) {
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
                              className: `bi ${V.configure}`,
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
                                  className: `bi ${V.delete}`,
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
function Ut(e, s, t) {
  c.useEffect(() => {
    He({ cameras: e.length, sensors: s.length, children: t.length });
  }, [e, s, t]);
}
function Ot({ wssConnection: e, sceneId: s }) {
  c.useEffect(() => {
    var i;
    (i = window.ssEnsureMqttScene) == null || i.call(window);
  }, [e, s]);
  const t = s
    ? `scenescape/regulated/scene/${s}`
    : "scenescape/regulated/scene/";
  return n.jsx("div", {
    className: "ss-mqtt-settings",
    id: "ss-mqtt-mount",
    children: n.jsxs("div", {
      className: "ss-mqtt-settings-grid",
      children: [
        n.jsxs("div", {
          className: "ss-mqtt-settings-controls",
          children: [
            n.jsxs("div", {
              className: "ss-mqtt-field",
              children: [
                n.jsx("label", {
                  className: "ss-mqtt-label",
                  htmlFor: "broker",
                  id: "label-broker",
                  children: "WSS Connection",
                }),
                n.jsx("input", {
                  type: "text",
                  className: "form-control",
                  id: "broker",
                  "aria-labelledby": "label-broker",
                  defaultValue: e,
                }),
              ],
            }),
            n.jsxs("div", {
              className: "ss-mqtt-field",
              children: [
                n.jsx("label", {
                  className: "ss-mqtt-label",
                  htmlFor: "topic",
                  id: "label-topic",
                  children: "Scene Data Topic",
                }),
                n.jsx("input", {
                  type: "text",
                  className: "form-control",
                  id: "topic",
                  "aria-labelledby": "label-topic",
                  defaultValue: t,
                }),
              ],
            }),
            n.jsxs("div", {
              className: "ss-mqtt-actions",
              children: [
                n.jsx("button", {
                  type: "button",
                  className: "ss-btn ss-btn--primary",
                  id: "connect",
                  children: "Connect",
                }),
                n.jsx("button", {
                  type: "button",
                  className: "ss-btn ss-btn--secondary",
                  id: "disconnect",
                  children: "Disconnect",
                }),
              ],
            }),
          ],
        }),
        n.jsxs("table", {
          className: "table table-bordered table-sm ss-mqtt-client-table",
          children: [
            n.jsx("thead", {
              children: n.jsx("tr", {
                children: n.jsx("th", {
                  colSpan: 2,
                  children: "Client Settings",
                }),
              }),
            }),
            n.jsxs("tbody", {
              children: [
                n.jsxs("tr", {
                  children: [
                    n.jsx("th", { scope: "row", children: "Broker" }),
                    n.jsx("td", { id: "broker-address" }),
                  ],
                }),
                n.jsxs("tr", {
                  children: [
                    n.jsx("th", {
                      scope: "row",
                      children: "Validate Certificate",
                    }),
                    n.jsx("td", { children: "Off" }),
                  ],
                }),
                n.jsxs("tr", {
                  children: [
                    n.jsx("th", { scope: "row", children: "Encryption (TLS)" }),
                    n.jsx("td", { children: "On" }),
                  ],
                }),
                n.jsxs("tr", {
                  children: [
                    n.jsx("th", { scope: "row", children: "Protocol" }),
                    n.jsx("td", { children: "mqtt://" }),
                  ],
                }),
                n.jsxs("tr", {
                  children: [
                    n.jsx("th", { scope: "row", children: "Port" }),
                    n.jsx("td", { children: "1883" }),
                  ],
                }),
              ],
            }),
          ],
        }),
      ],
    }),
  });
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
const Wt = [
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
function Gt() {
  return n.jsx(n.Fragment, {
    children: Wt.map((e) =>
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
function Ee(e) {
  var s;
  (e.preventDefault(),
    e.stopPropagation(),
    (s = window.ssPersistGeometry) == null || s.call(window));
}
function Y({ id: e, modalId: s, title: t }) {
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
function _e({ id: e, labelId: s, label: t, title: i }) {
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
function Vt({ activeTab: e, isSuperuser: s }) {
  const [t, i] = c.useState(() => !!window.ssRoiDirty),
    [r, o] = c.useState(() => !!window.ssTripDirty);
  return (
    c.useEffect(() => {
      const m = (l) => {
          i(!!l.detail);
        },
        u = (l) => {
          o(!!l.detail);
        };
      return (
        window.addEventListener("ss-roi-dirty", m),
        window.addEventListener("ss-trip-dirty", u),
        i(!!window.ssRoiDirty),
        o(!!window.ssTripDirty),
        () => {
          (window.removeEventListener("ss-roi-dirty", m),
            window.removeEventListener("ss-trip-dirty", u));
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
                n.jsx(Y, {
                  id: "camera-help",
                  modalId: "cameraHelpModal",
                  title: "How cameras work in this scene",
                }),
                n.jsx(_e, {
                  id: "live-view",
                  labelId: "live-view-label",
                  label: "Live View",
                  title: "Toggle Live View",
                }),
                n.jsx(_e, {
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
                n.jsx(Y, {
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
                n.jsx(Y, {
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
                          onClick: Ee,
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
                n.jsx(Y, {
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
                          onClick: Ee,
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
                n.jsx(Y, {
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
const Jt = {
  cameras: "cameras",
  sensors: "sensors",
  regions: "regions",
  tripwires: "trips",
  children: "children",
  mqtt: "mqtt",
};
function J({ paneId: e, tabId: s, activeId: t, children: i }) {
  const r = s === t;
  return n.jsx("div", {
    role: "tabpanel",
    id: e,
    "aria-labelledby": `ss-tab-${s}`,
    hidden: !r,
    className: `ss-tabs-panel scene-detail-panel-wrap${r ? " is-active" : ""}`,
    children: n.jsx("div", {
      className: "card scene-detail-panel",
      children: n.jsx("div", { className: "card-body", children: i }),
    }),
  });
}
function Yt({
  tabs: e,
  cameraRates: s = {},
  cameras: t = [],
  sensors: i = [],
  childrenLinks: r = [],
  isSuperuser: o = !1,
  sceneId: m = "",
  wssConnection: u = "",
  authToken: l = "",
  onSensorsChange: a,
}) {
  const [h, x] = c.useState(() => dt(m));
  (Ut(t, i, r),
    c.useEffect(() => {
      ut(m, h);
    }, [m, h]),
    c.useEffect(() => {
      const d = (R) => {
        const $ = R.detail,
          I = $ == null ? void 0 : $.tabId;
        (I === "cameras" ||
          I === "sensors" ||
          I === "regions" ||
          I === "tripwires" ||
          I === "children" ||
          I === "mqtt") &&
          x(I);
      };
      return (
        window.addEventListener(he, d),
        () => window.removeEventListener(he, d)
      );
    }, []));
  const w = c.useCallback((d) => {
    (d === "cameras" ||
      d === "sensors" ||
      d === "regions" ||
      d === "tripwires" ||
      d === "children" ||
      d === "mqtt") &&
      x(d);
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
              n.jsx(Lt, {
                id: "ss-scene-tablist",
                tabs: e,
                activeId: h,
                onChange: w,
                tabPanelId: (d) => Jt[d.id] || d.id,
              }),
              n.jsx("div", {
                className: "ss-tabs-toolbar",
                "data-active-tab": h,
                children: n.jsx(Vt, { activeTab: h, isSuperuser: o }),
              }),
              h === "cameras" ? n.jsx(Pt, { rates: s }) : null,
            ],
          }),
          n.jsxs("div", {
            className: "ss-tabs-panels",
            id: "ss-scene-tab-panels",
            children: [
              n.jsx(J, {
                paneId: "cameras",
                tabId: "cameras",
                activeId: h,
                children: n.jsx("div", {
                  id: "ss-cameras-mount",
                  children: n.jsx(Ft, { cameras: t, isSuperuser: o }),
                }),
              }),
              n.jsx(J, {
                paneId: "sensors",
                tabId: "sensors",
                activeId: h,
                children: n.jsx("div", {
                  id: "ss-sensors-mount",
                  children: n.jsx(Ht, {
                    sensors: i,
                    isSuperuser: o,
                    authToken: l,
                    onSensorsChange: a,
                  }),
                }),
              }),
              n.jsxs(J, {
                paneId: "regions",
                tabId: "regions",
                activeId: h,
                children: [
                  n.jsx("div", { id: "roi-fields", className: "top-buffer" }),
                  n.jsx("div", {
                    id: "no-regions",
                    className: "ss-empty-state",
                    hidden: !0,
                  }),
                ],
              }),
              n.jsxs(J, {
                paneId: "trips",
                tabId: "tripwires",
                activeId: h,
                children: [
                  n.jsx("div", {
                    id: "tripwire-fields",
                    className: "top-buffer",
                  }),
                  n.jsx("div", {
                    id: "no-tripwires",
                    className: "ss-empty-state",
                    hidden: !0,
                  }),
                ],
              }),
              n.jsx(J, {
                paneId: "children",
                tabId: "children",
                activeId: h,
                children: n.jsxs("div", {
                  id: "childrenlist",
                  children: [
                    n.jsx("input", {
                      type: "hidden",
                      name: "children",
                      id: "scene_children",
                      value: String(r.length),
                      readOnly: !0,
                    }),
                    n.jsx("div", {
                      id: "ss-children-mount",
                      children: n.jsx(qt, { childrenLinks: r, isSuperuser: o }),
                    }),
                  ],
                }),
              }),
              n.jsx(J, {
                paneId: "mqtt",
                tabId: "mqtt",
                activeId: h,
                children: n.jsx(Ot, { wssConnection: u, sceneId: m }),
              }),
            ],
          }),
        ],
      }),
      n.jsx(Gt, {}),
    ],
  });
}
function Kt({ roi: e, index: s, isSuperuser: t, onChange: i, onRemove: r }) {
  const o = !t || e.readOnly,
    [m, u] = c.useState(!1),
    l = `roi-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-roi",
    id: `form-${e.svgId}`,
    ref: (a) => (a == null ? void 0 : a.setAttribute("for", e.svgId)),
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
                  onChange: (a) => i({ ...e, title: a.target.value }),
                  onBlur: () => {
                    var a, h;
                    if (window.ssUseReactMap) {
                      (h =
                        (a = window.ssMap) == null ? void 0 : a.numberRois) ==
                        null || h.call(a);
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
                  "aria-controls": l,
                  title: m ? "Hide details" : "Show details",
                  onClick: () => u((a) => !a),
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
                  onClick: (a) => {
                    (a.preventDefault(), a.stopPropagation(), r(e.svgId));
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
              id: l,
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
                                onChange: (a) =>
                                  i({ ...e, volumetric: a.target.checked }),
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
                                onChange: (a) =>
                                  i({
                                    ...e,
                                    height: Number(a.target.value) || 1,
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
                                onChange: (a) =>
                                  i({
                                    ...e,
                                    buffer_size: Number(a.target.value) || 0,
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
                    onChange: (a) =>
                      i({
                        ...e,
                        greenMin: a.greenMin,
                        yellowMin: a.yellowMin,
                        redMin: a.redMin,
                        rangeMax: a.rangeMax,
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
                    onClick: () => void be(e.topic),
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
  const o = !!t && !e.readOnly,
    [m, u] = c.useState(!1),
    l = `trip-details-${e.svgId}`;
  return n.jsx("div", {
    className: "form-tripwire",
    id: `form-${e.svgId}`,
    ref: (a) => (a == null ? void 0 : a.setAttribute("for", e.svgId)),
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
                  onChange: (a) => {
                    o && i({ ...e, title: a.target.value });
                  },
                  onBlur: () => {
                    var a, h, x;
                    if (window.ssUseReactMap) {
                      (h =
                        (a = window.ssMap) == null
                          ? void 0
                          : a.numberTripwires) == null || h.call(a);
                      return;
                    }
                    (x = window.numberTripwires) == null || x.call(window);
                  },
                }),
                n.jsx("button", {
                  type: "button",
                  className: "ss-editor-row__toggle",
                  "aria-expanded": m,
                  "aria-controls": l,
                  title: m ? "Hide details" : "Show details",
                  onClick: () => u((a) => !a),
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
                  onClick: (a) => {
                    (a.preventDefault(), a.stopPropagation(), r(e.svgId));
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
              id: l,
              children: n.jsx("div", {
                className: "ss-editor-row__meta form-text text-muted topic",
                id: `label-${e.svgId}`,
                children: n.jsx("button", {
                  type: "button",
                  className: "ss-editor-copy-id topic-text",
                  title: "Click to copy the topic",
                  onClick: () => void be(e.topic),
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
  const i = {
      name: (s.title || "").trim() || `roi_${s.uuid || "new"}`,
      scene: e,
      points: s.points || [],
      volumetric: !!s.volumetric,
      height: typeof s.height == "number" ? s.height : 1,
      buffer_size: typeof s.buffer_size == "number" ? s.buffer_size : 0,
    },
    r = Xt(s);
  return (
    r && (i.color_ranges = { sectors: r.sectors, range_max: r.range_max }),
    i
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
  var R, $, I, k, v, j;
  let i, r;
  if (t != null && t.preferHidden)
    ((i = ne("id_rois")),
      (r = ne("tripwires")),
      ($ = (R = window.ssMap) == null ? void 0 : R.syncFromLegacyStringify) ==
        null || $.call(R));
  else {
    const g =
        (k = (I = window.ssMap) == null ? void 0 : I.getRois) == null
          ? void 0
          : k.call(I),
      M =
        (j = (v = window.ssMap) == null ? void 0 : v.getTripwires) == null
          ? void 0
          : j.call(v);
    ((i = g
      ? g.map((_) => ({
          uuid: _.uuid,
          title: _.title,
          points: _.points,
          volumetric: _.volumetric,
          height: _.height,
          buffer_size: _.buffer_size,
          range_max: _.range_max,
          sectors: _.sectors,
        }))
      : ne("id_rois")),
      (r = M
        ? M.map((_) => ({ uuid: _.uuid, title: _.title, points: _.points }))
        : ne("tripwires")));
  }
  const [o, m] = await Promise.all([
      z.getRegions(e, s).then(Me),
      z.getTripwires(e, s).then(Me),
    ]),
    u = new Set(o.map(se).filter((g) => !!g)),
    l = new Set(),
    a = {};
  for (const g of i) {
    const M = Zt(s, g);
    if (Ce(g.uuid) && u.has(g.uuid))
      (await z.updateRegion(e, g.uuid, M), l.add(g.uuid), (a[g.uuid] = g.uuid));
    else {
      const _ = await z.createRegion(e, M),
        A = se(_);
      A && (l.add(A), g.uuid && (a[g.uuid] = A));
    }
  }
  for (const g of u) l.has(g) || (await z.deleteRegion(e, g));
  const h = new Set(m.map(se).filter((g) => !!g)),
    x = new Set(),
    w = {};
  for (const g of r) {
    const M = es(s, g);
    if (Ce(g.uuid) && h.has(g.uuid))
      (await z.updateTripwire(e, g.uuid, M),
        x.add(g.uuid),
        (w[g.uuid] = g.uuid));
    else {
      const _ = await z.createTripwire(e, M),
        A = se(_);
      A && (x.add(A), g.uuid && (w[g.uuid] = A));
    }
  }
  for (const g of h) x.has(g) || (await z.deleteTripwire(e, g));
  let d = !1;
  for (const [g, M] of Object.entries(a)) wt(g, M) && (d = !0);
  for (const [g, M] of Object.entries(w)) gt(g, M) && (d = !0);
  return (d && bt(), { roiIds: a, tripIds: w });
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
        (s != null && s.value && vt(JSON.parse(s.value)),
          t != null && t.value && jt(JSON.parse(t.value)));
      } catch {}
    },
    getRois: () => X(),
    getTripwires: () => Z(),
    flushHidden: () => O(),
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
  var i;
  const t = [
    { color: "green", color_min: e.greenMin },
    { color: "yellow", color_min: e.yellowMin },
    { color: "red", color_min: e.redMin },
  ];
  (ge(e.uuid, {
    title: e.title,
    volumetric: e.volumetric,
    height: e.height,
    buffer_size: e.buffer_size,
    range_max: e.rangeMax,
    sectors: t,
    ...(s ? { points: s.map((r) => [Number(r[0]), Number(r[1])]) } : {}),
  }),
    (i = window.ssSyncRoiColorSectors) == null ||
      i.call(window, e.uuid, { thresholds: t, range_max: e.rangeMax }));
}
function is({
  sceneId: e,
  isSuperuser: s,
  authToken: t,
  initialRegions: i,
  initialTripwires: r,
}) {
  const o = Be(),
    [m, u] = c.useState(() => i.map((p) => Re(p, e)).filter((p) => !!p)),
    [l, a] = c.useState(() => r.map((p) => ns(p, e)).filter((p) => !!p)),
    [h, x] = c.useState(!1),
    [w, d] = c.useState(!1),
    R = c.useRef(m),
    $ = c.useRef(l),
    I = c.useRef(!1),
    k = c.useRef(o),
    v = c.useRef(""),
    j = c.useRef(""),
    g = c.useRef(() => {});
  ((k.current = o),
    (R.current = m),
    ($.current = l),
    c.useEffect(() => {
      (ss(),
        i.forEach((p) => {
          if (!String(p.uuid || "").trim()) return;
          const f = Re(p, e);
          f && Te(f, p.points);
        }),
        r.forEach((p) => {
          const S = String(p.uuid || "").trim();
          S &&
            re(S, {
              title: (p.title || "").trim(),
              points: (p.points || []).map((f) => [Number(f[0]), Number(f[1])]),
            });
        }));
    }, [i, r, e]),
    c.useEffect(() => {
      g.current = async (p) => {
        var f, N, y, b, E, C, D;
        if (I.current) return;
        I.current = !0;
        const S = p && !Array.isArray(p) ? p : void 0;
        S != null && S.preferHidden
          ? (N =
              (f = window.ssMap) == null
                ? void 0
                : f.syncFromLegacyStringify) == null || N.call(f)
          : window.ssUseReactMap
            ? (E = window.ssMap) == null || E.flushHidden()
            : ((y = window.ssMap) == null || y.stringifyRois(),
              (b = window.ssMap) == null || b.stringifyTripwires());
        try {
          const P = await ts(t, e, S);
          (u((q) => Ie(q, P.roiIds, "roi")),
            a((q) => Ie(q, P.tripIds, "tripwire")),
            (v.current =
              ((C = document.getElementById("id_rois")) == null
                ? void 0
                : C.value) ?? v.current),
            (j.current =
              ((D = document.getElementById("tripwires")) == null
                ? void 0
                : D.value) ?? j.current),
            ie("roi", !1),
            ie("trip", !1),
            x(!1),
            d(!1),
            k.current.show("Regions saved", "ok"));
        } catch (P) {
          const q =
            P && typeof P == "object" && "message" in P
              ? String(P.message || "Save failed")
              : "Save failed";
          throw (k.current.show(q, "bad"), P);
        } finally {
          I.current = !1;
        }
      };
    }, [t, e]),
    c.useEffect(() => {
      const p = (S) => g.current(S);
      return (
        (window.ssPersistGeometry = p),
        () => {
          window.ssPersistGeometry === p && delete window.ssPersistGeometry;
        }
      );
    }, []),
    c.useEffect(() => {
      ie("roi", h);
    }, [h]),
    c.useEffect(() => {
      ie("trip", w);
    }, [w]),
    c.useEffect(() => {
      const p = document.getElementById("id_rois"),
        S = document.getElementById("tripwires");
      ((v.current = (p == null ? void 0 : p.value) ?? ""),
        (j.current = (S == null ? void 0 : S.value) ?? ""));
      const f = window.setTimeout(() => {
          var b;
          ((v.current = (p == null ? void 0 : p.value) ?? ""),
            (j.current = (S == null ? void 0 : S.value) ?? ""),
            (b = window.ssMap) == null || b.syncFromLegacyStringify());
        }, 1200),
        N = (b) => {
          var C;
          const E = (C = b.detail) == null ? void 0 : C.kind;
          if (E === "trips") {
            d(!0);
            return;
          }
          if (E === "rois") {
            x(!0);
            return;
          }
          (x(!0), d(!0));
        };
      window.addEventListener("ss-geometry-stringified", N);
      const y = window.setInterval(() => {
        (p && p.value !== v.current && x(!0),
          S && S.value !== j.current && d(!0));
      }, 600);
      return () => {
        (window.clearTimeout(f),
          window.clearInterval(y),
          window.removeEventListener("ss-geometry-stringified", N));
      };
    }, []),
    c.useEffect(() => {
      const p = (y) => {
          (u((b) =>
            b.some((E) => E.svgId === y.svgId)
              ? b
              : [
                  ...b,
                  {
                    svgId: y.svgId,
                    uuid: y.uuid,
                    title: y.title || "",
                    volumetric: y.volumetric ?? !1,
                    height: y.height ?? 1,
                    buffer_size: y.buffer_size ?? 0,
                    greenMin: y.greenMin ?? 0,
                    yellowMin: y.yellowMin ?? 2,
                    redMin: y.redMin ?? 5,
                    rangeMax: y.rangeMax ?? 10,
                    topic:
                      y.topic || `scenescape/event/region/${e}/${y.uuid}/count`,
                  },
                ],
          ),
            x(!0),
            window.requestAnimationFrame(() => {
              var b;
              (b = window.numberRois) == null || b.call(window);
            }));
        },
        S = (y) => {
          (a((b) =>
            b.some((E) => E.svgId === y.svgId)
              ? b
              : [
                  ...b,
                  {
                    svgId: y.svgId,
                    uuid: y.uuid,
                    title: y.title || "",
                    topic:
                      y.topic ||
                      `scenescape/event/tripwire/${e}/${y.uuid}/objects`,
                  },
                ],
          ),
            d(!0),
            window.requestAnimationFrame(() => {
              var b;
              (b = window.numberTripwires) == null || b.call(window);
            }));
        };
      window.ssRoiEditors = {
        addRoi: p,
        addTripwire: S,
        hasRoi: (y) => R.current.some((b) => b.svgId === y),
        hasTripwire: (y) => $.current.some((b) => b.svgId === y),
      };
      const f = (y) => {
          const b = y.detail;
          b != null && b.svgId && p(b);
        },
        N = (y) => {
          const b = y.detail;
          b != null && b.svgId && S(b);
        };
      return (
        window.addEventListener("ss-roi-form-add", f),
        window.addEventListener("ss-tripwire-form-add", N),
        () => {
          (window.removeEventListener("ss-roi-form-add", f),
            window.removeEventListener("ss-tripwire-form-add", N),
            delete window.ssRoiEditors);
        }
      );
    }, [e]),
    c.useEffect(() => {
      He({ regions: m.length, tripwires: l.length });
    }, [m.length, l.length]),
    c.useEffect(() => {
      const p = document.getElementById("no-regions");
      p && (p.style.display = m.length ? "none" : "");
    }, [m.length]),
    c.useEffect(() => {
      const p = document.getElementById("no-tripwires");
      p && (p.style.display = l.length ? "none" : "");
    }, [l.length]),
    c.useEffect(() => {
      const p = document.getElementById("no-regions");
      if (p && ((p.hidden = m.length > 0), m.length === 0)) {
        p.innerHTML = "";
        const S = document.createElement("p");
        if (
          ((S.textContent = "No regions of interest defined."),
          p.appendChild(S),
          s)
        ) {
          const f = document.createElement("button");
          ((f.type = "button"),
            (f.className = "btn btn-primary btn-sm"),
            (f.id = "empty-new-roi"),
            (f.textContent = "+ New Region"),
            p.appendChild(f));
        }
      }
    }, [m.length, s]),
    c.useEffect(() => {
      const p = document.getElementById("no-tripwires");
      if (p && ((p.hidden = l.length > 0), l.length === 0)) {
        p.innerHTML = "";
        const S = document.createElement("p");
        if (((S.textContent = "No tripwires defined."), p.appendChild(S), s)) {
          const f = document.createElement("button");
          ((f.type = "button"),
            (f.className = "btn btn-primary btn-sm"),
            (f.id = "empty-new-tripwire"),
            (f.textContent = "+ New Tripwire"),
            p.appendChild(f));
        }
      }
    }, [l.length, s]));
  const M = async (p) => {
      var N;
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
      const f = p.replace(/^roi_/, "");
      (ht(f),
        u((y) => y.filter((b) => b.svgId !== p)),
        (N = window.ssMap) == null || N.flushHidden());
      try {
        await g.current();
      } catch {
        x(!0);
      }
    },
    _ = async (p) => {
      var N;
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
      const f = p.replace(/^tripwire_/, "");
      (pt(f),
        a((y) => y.filter((b) => b.svgId !== p)),
        (N = window.ssMap) == null || N.flushHidden());
      try {
        await g.current();
      } catch {
        d(!0);
      }
    },
    [A, T] = c.useState(null),
    [L, B] = c.useState(null);
  return (
    c.useLayoutEffect(() => {
      const p = () => {
        (T(document.getElementById("roi-fields")),
          B(document.getElementById("tripwire-fields")));
      };
      p();
      const S = window.requestAnimationFrame(p);
      return () => window.cancelAnimationFrame(S);
    }, []),
    n.jsxs(n.Fragment, {
      children: [
        A
          ? fe.createPortal(
              n.jsx(n.Fragment, {
                children: m.map((p, S) =>
                  n.jsx(
                    Kt,
                    {
                      roi: p,
                      index: S,
                      isSuperuser: s,
                      onChange: (f) => {
                        (x(!0),
                          Te(f),
                          u((N) =>
                            N.map((y) => (y.svgId === f.svgId ? f : y)),
                          ));
                      },
                      onRemove: M,
                    },
                    p.svgId,
                  ),
                ),
              }),
              A,
            )
          : null,
        L
          ? fe.createPortal(
              n.jsx(n.Fragment, {
                children: l.map((p, S) =>
                  n.jsx(
                    Qt,
                    {
                      tripwire: p,
                      index: S,
                      isSuperuser: s,
                      onChange: (f) => {
                        (d(!0),
                          re(f.uuid, { title: f.title }),
                          a((N) =>
                            N.map((y) => (y.svgId === f.svgId ? f : y)),
                          ));
                      },
                      onRemove: _,
                    },
                    p.svgId,
                  ),
                ),
              }),
              L,
            )
          : null,
      ],
    })
  );
}
function U(e, s = "") {
  return e == null || e === "" ? s : String(e);
}
function Oe(e) {
  if (e == null || e === "") return null;
  const s = String(e);
  return /^\d+$/.test(s) ? s : null;
}
function rs(e) {
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
  return U(e[s]);
}
function os(e) {
  const s = Oe(e.id),
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
  const t = Oe(e.id),
    i = U(e.sensor_id || e.uid),
    r = U(e.name, i);
  if (!t && !i) return null;
  const o = t || i;
  return {
    id: o,
    sensorId: i || o,
    name: r || i || o,
    iconUrl: (s == null ? void 0 : s.iconUrl) ?? null,
    areaJson: rs(e) || (s == null ? void 0 : s.areaJson) || "{}",
    calibrateHref: `?ss=calibrate-sensor&id=${o}`,
    editHref: `?ss=sensor-edit&id=${i || o}`,
    deleteUrl: t
      ? `/singleton_sensor/delete/${t}/`
      : ((s == null ? void 0 : s.deleteUrl) ?? null),
  };
}
function cs(e, s, t) {
  var h;
  const i = U(e.uid || e.id);
  if (!i) return null;
  const r = U(e.child_type || (t == null ? void 0 : t.childType), "local"),
    o = e.child != null ? U(e.child) : null,
    m =
      e.remote_child_id != null
        ? U(e.remote_child_id)
        : ((t == null ? void 0 : t.remoteChildId) ?? null),
    u = o
      ? (h = s.find((x) => x.id === o)) == null
        ? void 0
        : h.name
      : void 0,
    l = U(
      e.name || e.child_name || u || (t == null ? void 0 : t.name),
      "Child",
    ),
    a = r === "local" && o ? o : m || i;
  return {
    id: i,
    name: l,
    childType: r,
    remoteChildId: m,
    detailUrl: o ? `/${o}/` : ((t == null ? void 0 : t.detailUrl) ?? null),
    thumbnailUrl: (t == null ? void 0 : t.thumbnailUrl) ?? null,
    mapUrl: (t == null ? void 0 : t.mapUrl) ?? null,
    restUid: a,
    editHref: `?ss=child-edit&id=${a}`,
    deleteUrl: /^\d+$/.test(i)
      ? `/child/delete/${i}/`
      : ((t == null ? void 0 : t.deleteUrl) ?? null),
  };
}
function ls(e, s, t) {
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
function ds(e, s, t) {
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
function us(e, s, t) {
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
  isKubernetes: i,
  scenes: r,
  cameras: o,
  sensors: m = [],
  onCamerasChange: u,
  onSensorsChange: l,
  onChildrenChange: a,
  mapUrl: h = null,
  mapScale: x = null,
}) {
  var S;
  const { sheet: w, open: d, close: R } = rt(),
    $ = c.useCallback(
      (f, N = null) => {
        const y = ae(f);
        (y && ce(y), d(f, N));
      },
      [d],
    ),
    I = c.useCallback(() => {
      const f = ae(w.action);
      (R(), f && ce(f));
    }, [R, w.action]);
  (c.useEffect(() => {
    const f = (N) => {
      const y = N.target;
      if (!y) return;
      const b = y.closest("a[href]");
      if (!(b != null && b.href)) return;
      let E;
      try {
        E = new URL(b.href, window.location.origin);
      } catch {
        return;
      }
      if (E.origin !== window.location.origin) return;
      const C = E.searchParams.get("ss");
      !C ||
        !fs(C) ||
        ((E.pathname === window.location.pathname ||
          E.pathname === `/${e}/` ||
          E.pathname === `/${e}`) &&
          (N.preventDefault(),
          N.stopPropagation(),
          $(C, E.searchParams.get("id"))));
    };
    return (
      document.addEventListener("click", f, !0),
      () => document.removeEventListener("click", f, !0)
    );
  }, [$, e]),
    c.useEffect(() => {
      const f = ae(w.action);
      f && ce(f);
    }, [w.action]));
  const k = c.useCallback(() => {
      window.location.reload();
    }, []),
    v = c.useCallback(
      (f) => {
        if (!f) return;
        const N = os(f);
        if (!N) return;
        const y = me(f, "scene"),
          b = w.action === "cam-edit" && w.id ? String(w.id) : null;
        u((E) =>
          y && y !== e
            ? E.filter(
                (C) =>
                  C.id !== N.id &&
                  C.sensorId !== N.sensorId &&
                  C.sensorId !== b,
              )
            : ls(E, N, b),
        );
      },
      [u, e, w.action, w.id],
    ),
    j = c.useCallback(
      (f) => {
        if (!f) return;
        const N = me(f, "scene"),
          y = w.action === "sensor-edit" && w.id ? String(w.id) : null;
        l((b) => {
          const E = b.find(
              (D) =>
                D.sensorId === y ||
                D.sensorId === String(f.uid || "") ||
                D.id === String(f.id || ""),
            ),
            C = as(f, E);
          return C
            ? N && N !== e
              ? b.filter(
                  (D) =>
                    D.id !== C.id &&
                    D.sensorId !== C.sensorId &&
                    D.sensorId !== y,
                )
              : ds(b, C, y)
            : b;
        });
      },
      [l, e, w.action, w.id],
    ),
    g = c.useCallback(
      (f) => {
        if (!f) return;
        const N = me(f, "parent"),
          y = w.action === "child-edit" && w.id ? String(w.id) : null;
        a((b) => {
          const E = b.find(
              (D) => D.id === String(f.uid || f.id || "") || D.restUid === y,
            ),
            C = cs(f, r, E);
          return C
            ? N && N !== e
              ? b.filter(
                  (D) =>
                    D.id !== C.id && D.restUid !== C.restUid && D.restUid !== y,
                )
              : us(b, C, y)
            : b;
        });
      },
      [a, e, r, w.action, w.id],
    ),
    M = c.useMemo(() => {
      const f = new Map();
      return (o.forEach((N) => f.set(String(N.id), N)), f);
    }, [o]),
    _ = c.useMemo(() => {
      const f = new Map();
      return (o.forEach((N) => f.set(String(N.sensorId), N)), f);
    }, [o]),
    A = c.useMemo(() => {
      const f = new Map();
      return (m.forEach((N) => f.set(String(N.id), N)), f);
    }, [m]);
  if (!t) return null;
  const T = w.action,
    L = T === "calibrate-cam" && w.id ? M.get(String(w.id)) : null,
    B = T === "calibrate-sensor" && w.id ? A.get(String(w.id)) : null,
    p =
      T === "cam-edit" && w.id
        ? ((S = _.get(String(w.id))) == null ? void 0 : S.sensorId) ||
          String(w.id)
        : null;
  return n.jsxs(n.Fragment, {
    children: [
      n.jsx(Ze, {
        open: T === "cam-create" || T === "cam-edit",
        mode: T === "cam-edit" ? "edit" : "create",
        sceneId: e,
        scenes: r,
        sensorUid: T === "cam-edit" ? p : null,
        authToken: s,
        onClose: I,
        onSaved: v,
      }),
      n.jsx(et, {
        open: T === "sensor-create" || T === "sensor-edit",
        mode: T === "sensor-edit" ? "edit" : "create",
        sceneId: e,
        scenes: r,
        sensorUid: T === "sensor-edit" ? w.id : null,
        authToken: s,
        onClose: I,
        onSaved: j,
      }),
      n.jsx(ot, {
        open: T === "child-create" || T === "child-edit",
        mode: T === "child-edit" ? "edit" : "create",
        parentSceneId: e,
        childUid: T === "child-edit" ? w.id : null,
        scenes: r,
        authToken: s,
        onClose: I,
        onSaved: g,
      }),
      n.jsx(at, {
        open: T === "scene-manage",
        sceneId: e,
        authToken: s,
        onClose: I,
        onSaved: k,
      }),
      n.jsx(tt, {
        open: !!L,
        cameraPk: (L == null ? void 0 : L.id) || "",
        sensorId: (L == null ? void 0 : L.sensorId) || "",
        cameraName: (L == null ? void 0 : L.name) || "",
        sceneId: e,
        authToken: s,
        isKubernetes: i,
        onClose: I,
        onSaved: k,
      }),
      n.jsx(st, {
        open: !!B || T === "calibrate-sensor",
        sensorPk: (B == null ? void 0 : B.id) || w.id || "",
        sensorId: (B == null ? void 0 : B.sensorId) || "",
        sceneId: e,
        authToken: s,
        mapUrlHint: h,
        mapScale: x,
        onClose: I,
        onSaved: k,
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
function ke(e, s, t) {
  const i = Math.max(s, oe),
    r = Math.max(t, oe),
    o = Math.min(i / e.w, r / e.h);
  return !Number.isFinite(o) || o <= 0 ? 0 : e.w * o * (e.h * o);
}
function Ae(e, s, t) {
  const i = Math.max(e.w - 32, oe),
    r = Math.max(e.h - t, oe);
  if (i < 720 || r / i > 1.25) return "stack";
  if (!s) return i / r >= 1.35 ? "stack" : "row";
  const o = s.w / s.h,
    m = ke(s, i, r - ps),
    u = ke(s, i - ws, r);
  return o >= 1.35
    ? m >= u * 0.92
      ? "stack"
      : "row"
    : o <= 1.05
      ? u >= m * 0.92
        ? "row"
        : "stack"
      : u > m
        ? "row"
        : "stack";
}
function xs(e = {}) {
  const s = e.chromeHeightPx ?? 112,
    [t, i] = c.useState(() => (typeof window < "u" ? gs() : "auto")),
    [r, o] = c.useState(() => Ae($e(), null, s)),
    m = c.useCallback((l) => {
      (i(l), bs(l));
    }, []);
  return (
    c.useEffect(() => {
      let l = 0,
        a = null;
      const h = () => {
        (cancelAnimationFrame(l),
          (l = requestAnimationFrame(() => {
            const I = Ae($e(), ys(), s);
            a !== I && ((a = I), o((k) => (k === I ? k : I)));
          })));
      };
      (h(),
        window.addEventListener("resize", h),
        window.addEventListener("ss-map-host-ready", h));
      const x = document.querySelector("#ss-map-host #map img");
      x && !x.complete && x.addEventListener("load", h);
      const w = document.getElementById("ss-map-host");
      let d = null;
      w &&
        typeof ResizeObserver < "u" &&
        ((d = new ResizeObserver(() => h())), d.observe(w));
      const R = window.setInterval(h, 500),
        $ = window.setTimeout(() => window.clearInterval(R), 8e3);
      return () => {
        (cancelAnimationFrame(l),
          window.removeEventListener("resize", h),
          window.removeEventListener("ss-map-host-ready", h),
          x == null || x.removeEventListener("load", h),
          d == null || d.disconnect(),
          window.clearInterval(R),
          window.clearTimeout($));
      };
    }, [s, t]),
    { layout: t === "auto" ? r : t, mode: t, setMode: m, autoLayout: r }
  );
}
function vs() {
  const [e, s] = c.useState(!1);
  return (
    c.useEffect(() => {
      const t = () => {
        const m = document.getElementById("mqtt_status"),
          u = !!(m != null && m.classList.contains("connected"));
        s((l) => (l === u ? l : u));
      };
      t();
      const i = document.getElementById("mqtt_status");
      let r = null;
      i &&
        ((r = new MutationObserver(t)),
        r.observe(i, { attributes: !0, attributeFilter: ["class"] }));
      const o = (m) => {
        const u = m.detail;
        typeof (u == null ? void 0 : u.connected) == "boolean"
          ? s((l) => (l === u.connected ? l : !!u.connected))
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
function js() {
  const [e, s] = c.useState({});
  return (
    c.useEffect(() => {
      const t = (u, l) => {
          s((a) => (a[u] === l ? a : { ...a, [u]: l }));
        },
        i = (u, l) => {
          t(u, l);
        },
        r = () => s({});
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setCameraRate: i,
        clearRates: r,
      };
      const o = (u) => {
          const l = u.detail;
          l != null && l.sensorId && t(l.sensorId, l.text || l.hz || "--");
        },
        m = () => r();
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
  const { scene: s, urls: t, isSuperuser: i } = e,
    { layout: r, mode: o, setMode: m, autoLayout: u } = xs(),
    {
      panelSizePx: l,
      setPanelSizePx: a,
      mapFocus: h,
      toggleMapFocus: x,
    } = nt(r),
    [w, d] = c.useState("--"),
    [R, $] = c.useState(!1),
    [I, k] = c.useState(!1),
    [v, j] = c.useState(null),
    g = vs(),
    M = js(),
    [_, A] = c.useState(e.cameras),
    [T, L] = c.useState(e.sensors || []),
    [B, p] = c.useState(e.children || []),
    [S, f] = c.useState({
      cameras: e.cameras.length,
      sensors: e.counts.sensors,
      regions: e.counts.regions,
      tripwires: e.counts.tripwires,
      children: e.counts.children,
    });
  ((window.ssUseReactMap = !!s.mapUrl),
    c.useEffect(() => {
      const C = (q) => d(q || "--");
      window.ssSceneTelemetry = {
        ...(window.ssSceneTelemetry || {}),
        setSceneRate: C,
      };
      const D = (q) => {
          const G = q.detail;
          (G == null ? void 0 : G.hz) !== void 0 && C(G.hz);
        },
        P = () => d("--");
      return (
        window.addEventListener("ss-scene-rate", D),
        window.addEventListener("ss-telemetry-clear", P),
        () => {
          (window.removeEventListener("ss-scene-rate", D),
            window.removeEventListener("ss-telemetry-clear", P));
        }
      );
    }, []),
    c.useEffect(() => {
      const C = (D) => {
        const P = D.detail;
        !P ||
          typeof P != "object" ||
          f((q) => {
            const G = { ...q };
            return (
              [
                "cameras",
                "sensors",
                "regions",
                "tripwires",
                "children",
              ].forEach((ye) => {
                const ee = P[ye];
                typeof ee == "number" &&
                  Number.isFinite(ee) &&
                  ee >= 0 &&
                  (G[ye] = ee);
              }),
              G
            );
          });
      };
      return (
        window.addEventListener(pe, C),
        () => window.removeEventListener(pe, C)
      );
    }, []),
    c.useEffect(() => {
      const C = window.requestAnimationFrame(() => {
        typeof window.fitSceneMapDisplay == "function" &&
          window.fitSceneMapDisplay();
      });
      return () => window.cancelAnimationFrame(C);
    }, [h, l, r]));
  const N = c.useCallback(async () => {
      if (t.sceneDelete) {
        (k(!0), j(null));
        try {
          await ct(t.sceneDelete, t.scenesHome || "/");
        } catch (C) {
          (k(!1), j(C instanceof Error ? C.message : "Delete failed"));
        }
      }
    }, [t.sceneDelete, t.scenesHome]),
    y = [
      { id: "cameras", label: "Cameras", count: Q(S.cameras) },
      { id: "sensors", label: "Sensors", count: Q(S.sensors) },
      { id: "regions", label: "Regions", count: Q(S.regions) },
      { id: "tripwires", label: "Tripwires", count: Q(S.tripwires) },
      { id: "children", label: "Children", count: Q(S.children) },
      {
        id: "mqtt",
        label: "MQTT",
        extra: n.jsxs("span", {
          id: "mqtt_status",
          className: `scene-detail-mqtt-pill${g ? " connected" : ""}`,
          title: g ? "MQTT connected" : "MQTT disconnected",
          "data-ss-mqtt": g ? "connected" : "disconnected",
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
    b = n.jsxs(n.Fragment, {
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
          children: Ss.map((C) => {
            const D = o === C.mode,
              P = C.mode === "auto" ? ` (now ${u})` : "";
            return n.jsxs(
              "button",
              {
                type: "button",
                className: `ss-layout-toggle-btn${D ? " is-active" : ""}`,
                title: `${C.title}${P}`,
                "aria-pressed": D,
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
          className: `ss-layout-toggle-btn ss-map-focus-btn${h ? " is-active" : ""}`,
          title: h ? "Show control panel (Esc)" : "Map only focus",
          "aria-pressed": h,
          onClick: x,
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
                (j(null), $(!0));
              },
              children: n.jsx("i", {
                className: "bi bi-trash",
                "aria-hidden": "true",
              }),
            })
          : null,
      ],
    }),
    E = e.deleteImpact;
  return n.jsxs("div", {
    className: `ss-scene-detail ss-scene-detail--workspace ss-workspace--${r}${h ? " ss-workspace--map-focus" : ""}`,
    "data-workspace-layout": r,
    "data-workspace-mode": o,
    "data-map-focus": h ? "1" : "0",
    style: { "--ss-panel-size": `${l}px` },
    children: [
      n.jsx(Ge, { title: s.name, back: Ns(t), actions: b }),
      n.jsxs("div", {
        className: "ss-workspace-body",
        children: [
          n.jsx("div", {
            className: "ss-workspace-main",
            children: n.jsx(Mt, { mapUrl: s.mapUrl }),
          }),
          n.jsx(it, { layout: r, panelSizePx: l, onResize: a, disabled: h }),
          n.jsx(Yt, {
            tabs: y,
            cameraRates: M,
            cameras: _,
            sensors: T,
            childrenLinks: B,
            isSuperuser: i,
            sceneId: s.id,
            wssConnection: e.scene.wssConnection || "",
            authToken: e.authToken,
            onSensorsChange: L,
          }),
        ],
      }),
      n.jsx(is, {
        sceneId: s.id,
        isSuperuser: i,
        authToken: e.authToken,
        initialRegions: e.regions || [],
        initialTripwires: e.tripwires || [],
      }),
      n.jsx(hs, {
        sceneId: s.id,
        authToken: e.authToken,
        isSuperuser: i,
        isKubernetes: !!e.isKubernetes,
        scenes: e.scenes || [],
        cameras: _,
        sensors: T,
        onCamerasChange: A,
        onSensorsChange: L,
        onChildrenChange: p,
        mapUrl: s.mapUrl,
        mapScale: s.scale,
      }),
      n.jsxs(Pe, {
        open: R,
        title: "Delete scene?",
        confirmLabel: "Delete scene",
        danger: !0,
        busy: I,
        onConfirm: N,
        onCancel: () => {
          I || $(!1);
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
              ((E == null ? void 0 : E.sensors) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      E == null ? void 0 : E.sensors,
                      " camera(s) and/or sensor(s) will be orphaned",
                    ],
                  })
                : null,
              ((E == null ? void 0 : E.regions) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      E == null ? void 0 : E.regions,
                      " region(s) will be deleted",
                    ],
                  })
                : null,
              ((E == null ? void 0 : E.tripwires) ?? 0) > 0
                ? n.jsxs("li", {
                    children: [
                      E == null ? void 0 : E.tripwires,
                      " tripwire(s) will be deleted",
                    ],
                  })
                : null,
            ],
          }),
          v ? n.jsx("p", { className: "ss-confirm-error", children: v }) : null,
        ],
      }),
    ],
  });
}
function _s({ bootstrap: e }) {
  return n.jsx(Ve, {
    children: n.jsx(Je, { children: n.jsx(Es, { bootstrap: e }) }),
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
const Le = Ms(),
  De = document.getElementById("ss-scene-detail-root");
Le &&
  De &&
  (document.documentElement.classList.add("ss-scene-workspace"),
  document.body.classList.add("ss-scene-workspace"),
  We.createRoot(De).render(
    n.jsx(c.StrictMode, { children: n.jsx(Cs, { bootstrap: Le }) }),
  ));
