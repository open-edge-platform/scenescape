// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { r as a, j as n, c as ze } from "./chunks/tokens-C2Ju3rc_.js";
import { P as Ge } from "./chunks/PageHeader-Dke5XNFH.js";
import {
  r as J,
  u as Be,
  C as De,
  T as We,
} from "./chunks/ConfirmDialog-DanZpjzY.js";
import { L as Je } from "./chunks/LegacyConfirmHost-VsPlnSjJ.js";
import {
  r as Ye,
  c as Ve,
  m as Ke,
  p as be,
  C as Qe,
  S as Xe,
  a as Ze,
  b as et,
  u as tt,
  W as st,
} from "./chunks/SensorCalibratePanel-BhueTzc0.js";
import { A as W } from "./chunks/actionIcons-BIxtFbWH.js";
import { a as q, u as nt } from "./chunks/rest-CiiNoWNe.js";
import { C as it, S as rt } from "./chunks/SceneManagePanel-C7ukm3Qu.js";
import { p as ot } from "./chunks/djangoDelete-BfD_c0xv.js";
import "./chunks/Button-CDF7QSMd.js";
const Pe = "ss-scene-tab:",
  me = "ss-scene-tab",
  fe = "ss-tab-counts";
function Fe(e) {
  typeof window > "u" ||
    window.dispatchEvent(new CustomEvent(fe, { detail: e }));
}
const at = {
  "cam-create": "cameras",
  "cam-edit": "cameras",
  "calibrate-cam": "cameras",
  "sensor-create": "sensors",
  "sensor-edit": "sensors",
  "calibrate-sensor": "sensors",
  "child-create": "children",
  "child-edit": "children",
};
function oe(e) {
  return (e && at[e]) || null;
}
function lt(e, s = "cameras") {
  if (!e || typeof sessionStorage > "u") return s;
  try {
    const t = sessionStorage.getItem(Pe + e);
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
function ct(e, s) {
  if (!(!e || typeof sessionStorage > "u"))
    try {
      sessionStorage.setItem(Pe + e, s);
    } catch {}
}
function ae(e) {
  typeof window > "u" ||
    window.dispatchEvent(new CustomEvent(me, { detail: { tabId: e } }));
}
const le = { host: "ss-map-host" };
function dt() {
  (window.dispatchEvent(new CustomEvent("ss-map-host-ready")),
    typeof window.fitSceneMapDisplay == "function" &&
      window.fitSceneMapDisplay());
}
let P = new Map(),
  F = new Map();
const he = new Set();
function O() {
  he.forEach((e) => {
    try {
      e();
    } catch {}
  });
}
function ye(e, s) {
  const t = document.getElementById(e);
  t && (t.value = s);
}
function ut(e) {
  return (
    he.add(e),
    () => {
      he.delete(e);
    }
  );
}
function X() {
  return Array.from(P.values());
}
function Z() {
  return Array.from(F.values());
}
function pe(e, s) {
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
  (P.set(e, i), U(), O());
}
function ie(e, s) {
  const t = F.get(e),
    i = {
      uuid: e,
      title: s.title ?? (t == null ? void 0 : t.title) ?? "",
      points: s.points ?? (t == null ? void 0 : t.points) ?? [],
    };
  (F.set(e, i), U(), O());
}
function mt(e) {
  (P.delete(e), U(), O());
}
function ft(e) {
  (F.delete(e), U(), O());
}
function ht(e, s) {
  if (!e || !s || e === s) return !1;
  const t = P.get(e);
  return t ? (P.delete(e), P.set(s, { ...t, uuid: s }), !0) : !1;
}
function pt(e, s) {
  if (!e || !s || e === s) return !1;
  const t = F.get(e);
  return t ? (F.delete(e), F.set(s, { ...t, uuid: s }), !0) : !1;
}
function wt() {
  (U(), O());
}
function gt(e, s) {
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
    O());
}
function bt(e, s) {
  const t = F.get(e);
  (t
    ? F.set(e, { ...t, points: s })
    : F.set(e, { uuid: e, title: "", points: s }),
    U(),
    O());
}
function yt(e) {
  const s = new Set();
  for (const t of e) {
    const i = String(t.uuid || "").trim();
    if (!i) continue;
    s.add(i);
    const r = (t.points || []).map((o) => [Number(o[0]), Number(o[1])]);
    pe(i, {
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
  (U(), O());
}
function vt(e) {
  const s = new Set();
  for (const t of e) {
    const i = String(t.uuid || "").trim();
    if (!i) continue;
    s.add(i);
    const r = (t.points || []).map((o) => [Number(o[0]), Number(o[1])]);
    ie(i, { title: t.title, points: r });
  }
  for (const t of Array.from(F.keys())) s.has(t) || F.delete(t);
  (U(), O());
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
  (ye("id_rois", JSON.stringify(e)), ye("tripwires", JSON.stringify(s)));
}
const xt = a.memo(function ({ href: s, width: t, height: i }) {
  return n.jsx("image", {
    href: s,
    x: 0,
    y: 0,
    width: t,
    height: i,
    preserveAspectRatio: "none",
  });
});
function ve() {
  return `tmp${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
function jt(e, s, t = 22) {
  const i = s[0] - e[0],
    r = s[1] - e[1],
    o = Math.hypot(i, r);
  if (o < 1) return null;
  const h = (-t * r) / o,
    f = (t * i) / o,
    c = (e[0] + s[0]) / 2,
    l = (e[1] + s[1]) / 2,
    y = c + h,
    S = l + f,
    w = h / t,
    x = f / t,
    T = -x,
    D = w,
    v = [
      `${y},${S}`,
      `${y - w * 8 + T * 4},${S - x * 8 + D * 4}`,
      `${y - w * 8 - T * 4},${S - x * 8 - D * 4}`,
    ].join(" ");
  return { arrow: { x1: c, y1: l, x2: y, y2: S }, head: v };
}
function Nt(e) {
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
const St = a.memo(function ({ mapHref: s, mapWidth: t, mapHeight: i }) {
  const [r, o] = a.useState(() => X()),
    [h, f] = a.useState(() => Z()),
    [c, l] = a.useState("idle"),
    [y, S] = a.useState([]),
    w = Ye(),
    x = i || Ve(i);
  (a.useEffect(
    () =>
      ut(() => {
        (o(X()), f(Z()));
      }),
    [],
  ),
    a.useEffect(() => {
      const b = () => {
          (l("add-roi"), S([]));
        },
        g = () => {
          (l("add-trip"), S([]));
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
  const T = a.useCallback((b) => Ke(b[0], b[1], w, x), [w, x]),
    D = (b) => {
      if (c === "idle") return;
      const g = b.currentTarget,
        m = g.createSVGPoint();
      ((m.x = b.clientX), (m.y = b.clientY));
      const _ = g.getScreenCTM();
      if (!_) return;
      const E = m.matrixTransform(_.inverse()),
        A = be(E.x, E.y, w, x);
      if (c === "add-roi") {
        if (y.length >= 3) {
          const I = T(y[0]),
            d = E.x - I[0],
            N = E.y - I[1];
          if (Math.hypot(d, N) < 12) {
            const j = ve();
            (pe(j, {
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
              S([]),
              l("idle"));
            return;
          }
        }
        S((I) => [...I, A]);
        return;
      }
      if (c === "add-trip") {
        const I = [...y, A];
        if (I.length >= 2) {
          const d = ve();
          (ie(d, { title: "", points: I.slice(0, 2) }),
            window.dispatchEvent(
              new CustomEvent("ss-tripwire-form-add", {
                detail: { svgId: `tripwire_${d}`, uuid: d, title: "" },
              }),
            ),
            S([]),
            l("idle"));
        } else S(I);
      }
    },
    v = (b, g, m, _) => {
      (_.stopPropagation(), _.preventDefault());
      const E = _.target.ownerSVGElement;
      if (!E) return;
      const A = (d) => {
          const N = E.createSVGPoint();
          ((N.x = d.clientX), (N.y = d.clientY));
          const j = E.getScreenCTM();
          if (!j) return;
          const k = N.matrixTransform(j.inverse()),
            u = be(k.x, k.y, w, x);
          if (b === "roi") {
            const p = X().find(($) => $.uuid === g);
            if (!p) return;
            const L = p.points.map(($, R) => (R === m ? u : $));
            gt(g, L);
          } else {
            const p = Z().find(($) => $.uuid === g);
            if (!p) return;
            const L = p.points.map(($, R) => (R === m ? u : $));
            bt(g, L);
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
    viewBox: `0 0 ${t} ${i}`,
    preserveAspectRatio: "xMidYMid meet",
    width: "100%",
    height: "100%",
    onClick: D,
    children: [
      n.jsx(xt, { href: s, width: t, height: i }),
      r.map((b) => {
        const g = b.points.map(T),
          m = g.map((E) => E.join(",")).join(" "),
          _ = Nt(g);
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
        const m = jt(g[0], g[1]);
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
function xe() {
  typeof window.fitSceneMapDisplay == "function" && window.fitSceneMapDisplay();
}
function je(e) {
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
const Et = a.memo(function ({
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
        (dt(), h(!0));
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
                if (((D = g), (v = m), !l)) xe();
                else {
                  const _ = x.querySelector(".scene-map-stage");
                  (_ && je(_), xe());
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
        x && je(x);
      }, [l, o, f]));
    const y = o ? document.getElementById(le.host) : null,
      S = (y == null ? void 0 : y.querySelector(".scene-map-stage")) ?? null;
    return n.jsxs("div", {
      className: "ss-scene-map-pane",
      children: [
        n.jsx("div", { ref: r, className: "ss-scene-map-slot" }),
        l && S && s && f
          ? J.createPortal(
              n.jsx("div", {
                className: "ss-react-map-layer",
                children: n.jsx(St, {
                  mapHref: s,
                  mapWidth: f.width || t,
                  mapHeight: f.height || i,
                }),
              }),
              S,
            )
          : null,
      ],
    });
  }),
  He = "ss-camera-strip-fit";
function _t() {
  try {
    const e = window.localStorage.getItem(He);
    if (e === "cover" || e === "contain") return e;
  } catch {}
  return "contain";
}
function Ct(e) {
  try {
    window.localStorage.setItem(He, e);
  } catch {}
}
function Ue(e) {
  if (!e || e.classList.contains("display-none")) return !1;
  const s = e.currentSrc || e.getAttribute("src") || "";
  return !s || s.includes("offline.png")
    ? !1
    : e.naturalWidth > 0 || s.startsWith("data:image");
}
function ce(e) {
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
function Mt({ rates: e = {} }) {
  const [s, t] = a.useState(() => (typeof window < "u" ? _t() : "contain"));
  return (
    a.useEffect(() => {
      const i = document.documentElement;
      ((i.dataset.ssCameraFit = s), Ct(s));
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
        if (!Ue(h)) {
          (f &&
            ((f.textContent || "").trim() !== "--" && (f.textContent = "--"),
            f.classList.add("telemetry-hide")),
            o && ce(o));
          return;
        }
        (f &&
          f.textContent !== r &&
          ((f.textContent = r), f.classList.remove("telemetry-hide")),
          o && ce(o));
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
              i.querySelectorAll(".camera-card").forEach(ce);
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
async function we(e) {
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
function Rt({ cameras: e, isSuperuser: s }) {
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
function It({ sensors: e, isSuperuser: s, onDelete: t }) {
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
                        onClick: () => void we(i.sensorId),
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
function Tt({ childrenLinks: e, isSuperuser: s }) {
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
    : n.jsx("div", {
        className: "ss-tab-list",
        children: e.map((t) => {
          const i = t.thumbnailUrl || t.mapUrl;
          return n.jsxs(
            "div",
            {
              className: "ss-tab-row",
              children: [
                i
                  ? t.detailUrl
                    ? n.jsx("a", {
                        className: "ss-tab-row__thumb",
                        href: t.detailUrl,
                        title: t.name,
                        children: n.jsx("img", { src: i, alt: "" }),
                      })
                    : n.jsx("span", {
                        className: "ss-tab-row__thumb",
                        children: n.jsx("img", { src: i, alt: "" }),
                      })
                  : n.jsx("span", {
                      className: "ss-tab-row__thumb ss-tab-row__thumb--empty",
                      "aria-hidden": "true",
                    }),
                n.jsxs("div", {
                  className: "ss-tab-row__main",
                  children: [
                    n.jsx("span", {
                      className: "ss-tab-row__title",
                      children: t.name,
                    }),
                    t.childType === "remote"
                      ? n.jsx("span", {
                          className: "ss-tab-row__meta",
                          children: "Remote",
                        })
                      : null,
                  ],
                }),
                n.jsxs("div", {
                  className: "ss-tab-row__actions ss-entity-actions",
                  children: [
                    t.childType === "remote" && t.remoteChildId
                      ? n.jsx("span", {
                          id: `mqtt_status_remote_${t.remoteChildId}`,
                          className: "child_mqtt_status btn-sm btn",
                          children: n.jsx("i", {
                            className: "bi bi-arrow-down-up",
                          }),
                        })
                      : null,
                    t.detailUrl
                      ? n.jsx("a", {
                          className: "ss-btn ss-btn--secondary ss-btn--sm",
                          href: t.detailUrl,
                          title: "View Scene",
                          children: "Open",
                        })
                      : null,
                    s
                      ? n.jsxs(n.Fragment, {
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
                  ],
                }),
              ],
            },
            t.id,
          );
        }),
      });
}
function $t({
  cameras: e,
  sensors: s,
  childrenLinks: t,
  isSuperuser: i,
  panelsReady: r,
  authToken: o = "",
  onSensorsChange: h,
}) {
  const f = Be(),
    [c, l] = a.useState(null),
    [y, S] = a.useState(!1),
    [w, x] = a.useState(null);
  a.useEffect(() => {
    var m;
    r &&
      (Fe({ cameras: e.length, sensors: s.length, children: t.length }),
      (m = window.numberTabs) == null || m.call(window));
  }, [r, e, s, t]);
  const T = a.useCallback(async () => {
      var m;
      if (!(!c || !o || !h)) {
        (S(!0), x(null));
        try {
          (await q.deleteSensor(o, c.sensorId),
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
          S(!1);
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
      v ? J.createPortal(n.jsx(Rt, { cameras: e, isSuperuser: i }), v) : null,
      M
        ? J.createPortal(
            n.jsx(It, { sensors: s, isSuperuser: i, onDelete: g ? D : void 0 }),
            M,
          )
        : null,
      b
        ? J.createPortal(n.jsx(Tt, { childrenLinks: t, isSuperuser: i }), b)
        : null,
      n.jsxs(De, {
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
function Lt({ wssConnection: e, sceneId: s, panelsReady: t }) {
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
function kt({ id: e, title: s, children: t, footer: i, onClose: r }) {
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
const At = [
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
function Bt() {
  return n.jsx(n.Fragment, {
    children: At.map((e) =>
      n.jsx(
        kt,
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
function Se({ id: e, labelId: s, label: t, title: i }) {
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
function Dt({ activeTab: e, isSuperuser: s }) {
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
                n.jsx(Se, {
                  id: "live-view",
                  labelId: "live-view-label",
                  label: "Live View",
                  title: "Toggle Live View",
                }),
                n.jsx(Se, {
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
const Ee = {
    cameras: "cameras",
    sensors: "sensors",
    regions: "regions",
    tripwires: "trips",
    children: "children",
    mqtt: "mqtt",
  },
  Pt = {
    cameras: "cameras-tab",
    sensors: "sensors-tab",
    regions: "regions-tab",
    tripwires: "tripwires-tab",
    children: "children-tab",
    mqtt: "settings-tab",
  };
function Ft({
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
  const [y, S] = a.useState(() => lt(h)),
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
      Object.entries(Ee).forEach(([v, M]) => {
        const b = document.getElementById(M);
        if (!b) return;
        const g = v === y;
        (b.classList.toggle("show", g), b.classList.toggle("active", g));
      });
    }, [y]),
    a.useEffect(() => {
      ct(h, y);
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
          S(g);
      };
      return (
        window.addEventListener(me, v),
        () => window.removeEventListener(me, v)
      );
    }, []));
  const D = (v) => {
    (v === "cameras" ||
      v === "sensors" ||
      v === "regions" ||
      v === "tripwires" ||
      v === "children" ||
      v === "mqtt") &&
      S(v);
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
                    b = Pt[v.id] || `ss-tab-${v.id}`;
                  return n.jsxs(
                    "button",
                    {
                      type: "button",
                      role: "tab",
                      id: b,
                      "aria-selected": M,
                      "aria-controls": Ee[v.id] || v.id,
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
                children: n.jsx(Dt, { activeTab: y, isSuperuser: o }),
              }),
              y === "cameras" ? n.jsx(Mt, { rates: s }) : null,
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
      n.jsx($t, {
        cameras: t,
        sensors: i,
        childrenLinks: r,
        isSuperuser: o,
        panelsReady: w,
        authToken: c,
        onSensorsChange: l,
      }),
      n.jsx(Lt, { wssConnection: f, sceneId: h, panelsReady: w }),
      n.jsx(Bt, {}),
    ],
  });
}
function Ht({ roi: e, index: s, isSuperuser: t, onChange: i, onRemove: r }) {
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
                  ? n.jsxs("div", {
                      className: "ss-editor-card-meta",
                      children: [
                        n.jsxs("div", {
                          className: "form-check form-check-inline",
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
                    })
                  : null,
                n.jsx("div", {
                  className: "roi-visualization ss-editor-sectors",
                  children: n.jsxs("div", {
                    className: "sector-container",
                    children: [
                      n.jsx("div", {
                        className: "color-range",
                        children: "Color Range:",
                      }),
                      n.jsxs("div", {
                        className: "sector-config",
                        children: [
                          n.jsx("input", {
                            type: "number",
                            className: "green_min",
                            disabled: o,
                            value: e.greenMin,
                            onChange: (l) =>
                              i({
                                ...e,
                                greenMin: Number(l.target.value) || 0,
                              }),
                          }),
                          n.jsx("div", {
                            className: "green-sec",
                            children: "--",
                          }),
                          n.jsx("input", {
                            type: "number",
                            className: "yellow_min",
                            disabled: o,
                            value: e.yellowMin,
                            onChange: (l) =>
                              i({
                                ...e,
                                yellowMin: Number(l.target.value) || 0,
                              }),
                          }),
                          n.jsx("div", {
                            className: "yellow-sec",
                            children: "--",
                          }),
                          n.jsx("input", {
                            type: "number",
                            className: "red_min",
                            disabled: o,
                            value: e.redMin,
                            onChange: (l) =>
                              i({ ...e, redMin: Number(l.target.value) || 0 }),
                          }),
                          n.jsx("div", {
                            className: "red-sec",
                            children: "--",
                          }),
                          n.jsx("input", {
                            type: "number",
                            className: "range_max",
                            disabled: o,
                            value: e.rangeMax,
                            onChange: (l) =>
                              i({
                                ...e,
                                rangeMax: Number(l.target.value) || 0,
                              }),
                          }),
                        ],
                      }),
                    ],
                  }),
                }),
                n.jsxs("div", {
                  className: "col form-text text-muted roi-topic",
                  children: [
                    n.jsxs("label", {
                      id: `label-${e.svgId}`,
                      htmlFor: `input-${e.svgId}`,
                      children: ["Topic:", " "],
                    }),
                    n.jsx("button", {
                      type: "button",
                      className: "ss-editor-copy-id topic-text",
                      title: "Click to copy the topic",
                      onClick: () => void we(e.topic),
                      children: e.topic,
                    }),
                  ],
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
function Ut({
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
                    var l, y, S;
                    if (window.ssUseReactMap) {
                      (y =
                        (l = window.ssMap) == null
                          ? void 0
                          : l.numberTripwires) == null || y.call(l);
                      return;
                    }
                    (S = window.numberTripwires) == null || S.call(window);
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
                  onClick: () => void we(e.topic),
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
function _e(e) {
  if (typeof e != "string" || !e) return !1;
  try {
    return !!e.match(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  } catch {
    return !1;
  }
}
function Ce(e) {
  return Array.isArray(e) ? e : e && Array.isArray(e.results) ? e.results : [];
}
function te(e) {
  if (!e || typeof e != "object") return null;
  const s = e.uid;
  return typeof s == "string" && s ? s : null;
}
function se(e) {
  const s = document.getElementById(e);
  if (!(s != null && s.value)) return [];
  try {
    const t = JSON.parse(s.value);
    return Array.isArray(t) ? t : [];
  } catch {
    return [];
  }
}
function qt(e, s) {
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
function Ot(e, s) {
  return {
    name: (s.title || "").trim() || `tripwire_${s.uuid || "new"}`,
    scene: e,
    points: s.points || [],
    ...(typeof s.height == "number" ? { height: s.height } : {}),
  };
}
async function zt(e, s, t) {
  var T, D, v, M, b, g;
  let i, r;
  if (t != null && t.preferHidden)
    ((i = se("id_rois")),
      (r = se("tripwires")),
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
      : se("id_rois")),
      (r = _
        ? _.map((E) => ({ uuid: E.uuid, title: E.title, points: E.points }))
        : se("tripwires")));
  }
  const [o, h] = await Promise.all([
      q.getRegions(e, s).then(Ce),
      q.getTripwires(e, s).then(Ce),
    ]),
    f = new Set(o.map(te).filter((m) => !!m)),
    c = new Set(),
    l = {};
  for (const m of i) {
    const _ = qt(s, m);
    if (_e(m.uuid) && f.has(m.uuid))
      (await q.updateRegion(e, m.uuid, _), c.add(m.uuid), (l[m.uuid] = m.uuid));
    else {
      const E = await q.createRegion(e, _),
        A = te(E);
      A && (c.add(A), m.uuid && (l[m.uuid] = A));
    }
  }
  for (const m of f) c.has(m) || (await q.deleteRegion(e, m));
  const y = new Set(h.map(te).filter((m) => !!m)),
    S = new Set(),
    w = {};
  for (const m of r) {
    const _ = Ot(s, m);
    if (_e(m.uuid) && y.has(m.uuid))
      (await q.updateTripwire(e, m.uuid, _),
        S.add(m.uuid),
        (w[m.uuid] = m.uuid));
    else {
      const E = await q.createTripwire(e, _),
        A = te(E);
      A && (S.add(A), m.uuid && (w[m.uuid] = A));
    }
  }
  for (const m of y) S.has(m) || (await q.deleteTripwire(e, m));
  let x = !1;
  for (const [m, _] of Object.entries(l)) ht(m, _) && (x = !0);
  for (const [m, _] of Object.entries(w)) pt(m, _) && (x = !0);
  return (x && wt(), { roiIds: l, tripIds: w });
}
function K(e) {
  const s = window[e];
  typeof s == "function" && s();
}
function Gt() {
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
        (s != null && s.value && yt(JSON.parse(s.value)),
          t != null && t.value && vt(JSON.parse(t.value)));
      } catch {}
    },
    getRois: () => X(),
    getTripwires: () => Z(),
    flushHidden: () => U(),
  };
  return ((window.ssMap = e), e);
}
function de(e, s, t) {
  const i = e == null ? void 0 : e.find((o) => o.color === s);
  if (!i) return t;
  const r = Number(i.color_min);
  return Number.isFinite(r) ? r : t;
}
function Me(e, s) {
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
    greenMin: de(i, "green", 0),
    yellowMin: de(i, "yellow", 2),
    redMin: de(i, "red", 5),
    rangeMax: Number(((o = e.sectors) == null ? void 0 : o.range_max) ?? 10),
    topic: `scenescape/event/region/${s}/${t}/count`,
  };
}
function Wt(e, s) {
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
function Re(e, s, t) {
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
function ne(e, s) {
  if (e === "roi") {
    ((window.ssRoiDirty = s),
      window.dispatchEvent(new CustomEvent("ss-roi-dirty", { detail: s })));
    return;
  }
  ((window.ssTripDirty = s),
    window.dispatchEvent(new CustomEvent("ss-trip-dirty", { detail: s })));
}
function Ie(e, s) {
  pe(e.uuid, {
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
function Jt({
  sceneId: e,
  isSuperuser: s,
  authToken: t,
  initialRegions: i,
  initialTripwires: r,
}) {
  const o = Be(),
    [h, f] = a.useState(() => i.map((d) => Me(d, e)).filter((d) => !!d)),
    [c, l] = a.useState(() => r.map((d) => Wt(d, e)).filter((d) => !!d)),
    [y, S] = a.useState(!1),
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
      (Gt(),
        i.forEach((d) => {
          if (!String(d.uuid || "").trim()) return;
          const j = Me(d, e);
          j && Ie(j, d.points);
        }),
        r.forEach((d) => {
          const N = String(d.uuid || "").trim();
          N &&
            ie(N, {
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
        const N = d && !Array.isArray(d) ? d : void 0;
        N != null && N.preferHidden
          ? (k =
              (j = window.ssMap) == null
                ? void 0
                : j.syncFromLegacyStringify) == null || k.call(j)
          : window.ssUseReactMap
            ? (L = window.ssMap) == null || L.flushHidden()
            : ((u = window.ssMap) == null || u.stringifyRois(),
              (p = window.ssMap) == null || p.stringifyTripwires());
        try {
          const C = await zt(t, e, N);
          (f((B) => Re(B, C.roiIds, "roi")),
            l((B) => Re(B, C.tripIds, "tripwire")),
            (b.current =
              (($ = document.getElementById("id_rois")) == null
                ? void 0
                : $.value) ?? b.current),
            (g.current =
              ((R = document.getElementById("tripwires")) == null
                ? void 0
                : R.value) ?? g.current),
            ne("roi", !1),
            ne("trip", !1),
            S(!1),
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
      const d = (N) => m.current(N);
      return (
        (window.ssPersistGeometry = d),
        () => {
          window.ssPersistGeometry === d && delete window.ssPersistGeometry;
        }
      );
    }, []),
    a.useEffect(() => {
      ne("roi", y);
    }, [y]),
    a.useEffect(() => {
      ne("trip", w);
    }, [w]),
    a.useEffect(() => {
      const d = document.getElementById("id_rois"),
        N = document.getElementById("tripwires");
      ((b.current = (d == null ? void 0 : d.value) ?? ""),
        (g.current = (N == null ? void 0 : N.value) ?? ""));
      const j = window.setTimeout(() => {
          var p;
          ((b.current = (d == null ? void 0 : d.value) ?? ""),
            (g.current = (N == null ? void 0 : N.value) ?? ""),
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
            S(!0);
            return;
          }
          (S(!0), x(!0));
        };
      window.addEventListener("ss-geometry-stringified", k);
      const u = window.setInterval(() => {
        (d && d.value !== b.current && S(!0),
          N && N.value !== g.current && x(!0));
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
            S(!0),
            window.requestAnimationFrame(() => {
              var p;
              (p = window.numberRois) == null || p.call(window);
            }));
        },
        N = (u) => {
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
        addTripwire: N,
        hasRoi: (u) => T.current.some((p) => p.svgId === u),
        hasTripwire: (u) => D.current.some((p) => p.svgId === u),
      };
      const j = (u) => {
          const p = u.detail;
          p != null && p.svgId && d(p);
        },
        k = (u) => {
          const p = u.detail;
          p != null && p.svgId && N(p);
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
      Fe({ regions: h.length, tripwires: c.length });
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
        const N = document.createElement("p");
        if (
          ((N.textContent = "No regions of interest defined."),
          d.appendChild(N),
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
        const N = document.createElement("p");
        if (((N.textContent = "No tripwires defined."), d.appendChild(N), s)) {
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
      (mt(j),
        f((u) => u.filter((p) => p.svgId !== d)),
        (k = window.ssMap) == null || k.flushHidden());
      try {
        await m.current();
      } catch {
        S(!0);
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
      (ft(j),
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
              children: h.map((d, N) =>
                n.jsx(
                  Ht,
                  {
                    roi: d,
                    index: N,
                    isSuperuser: s,
                    onChange: (j) => {
                      (S(!0),
                        Ie(j),
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
              children: c.map((d, N) =>
                n.jsx(
                  Ut,
                  {
                    tripwire: d,
                    index: N,
                    isSuperuser: s,
                    onChange: (j) => {
                      (x(!0),
                        ie(j.uuid, { title: j.title }),
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
function Yt(e) {
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
function ue(e, s) {
  return H(e[s]);
}
function Vt(e) {
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
function Kt(e, s) {
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
    areaJson: Yt(e) || (s == null ? void 0 : s.areaJson) || "{}",
    calibrateHref: `?ss=calibrate-sensor&id=${o}`,
    editHref: `?ss=sensor-edit&id=${i || o}`,
    deleteUrl: t
      ? `/singleton_sensor/delete/${t}/`
      : ((s == null ? void 0 : s.deleteUrl) ?? null),
  };
}
function Qt(e, s, t) {
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
      ? (y = s.find((S) => S.id === o)) == null
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
function Xt(e, s, t) {
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
function Zt(e, s, t) {
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
function es(e, s, t) {
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
const ts = new Set([
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
function ss(e) {
  return !!(e && ts.has(e));
}
function ns({
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
  mapScale: S = null,
}) {
  var k;
  const { sheet: w, open: x, close: T } = nt(),
    D = a.useCallback(
      (u, p = null) => {
        const L = oe(u);
        (L && ae(L), x(u, p));
      },
      [x],
    ),
    v = a.useCallback(() => {
      const u = oe(w.action);
      (T(), u && ae(u));
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
        !ss(C) ||
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
      const u = oe(w.action);
      u && ae(u);
    }, [w.action]));
  const M = a.useCallback(() => {
      window.location.reload();
    }, []),
    b = a.useCallback(
      (u) => {
        if (!u) return;
        const p = Vt(u);
        if (!p) return;
        const L = ue(u, "scene"),
          $ = w.action === "cam-edit" && w.id ? String(w.id) : null;
        f((R) =>
          L && L !== e
            ? R.filter(
                (C) =>
                  C.id !== p.id &&
                  C.sensorId !== p.sensorId &&
                  C.sensorId !== $,
              )
            : Xt(R, p, $),
        );
      },
      [f, e, w.action, w.id],
    ),
    g = a.useCallback(
      (u) => {
        if (!u) return;
        const p = ue(u, "scene"),
          L = w.action === "sensor-edit" && w.id ? String(w.id) : null;
        c(($) => {
          const R = $.find(
              (B) =>
                B.sensorId === L ||
                B.sensorId === String(u.uid || "") ||
                B.id === String(u.id || ""),
            ),
            C = Kt(u, R);
          return C
            ? p && p !== e
              ? $.filter(
                  (B) =>
                    B.id !== C.id &&
                    B.sensorId !== C.sensorId &&
                    B.sensorId !== L,
                )
              : Zt($, C, L)
            : $;
        });
      },
      [c, e, w.action, w.id],
    ),
    m = a.useCallback(
      (u) => {
        if (!u) return;
        const p = ue(u, "parent"),
          L = w.action === "child-edit" && w.id ? String(w.id) : null;
        l(($) => {
          const R = $.find(
              (B) => B.id === String(u.uid || u.id || "") || B.restUid === L,
            ),
            C = Qt(u, r, R);
          return C
            ? p && p !== e
              ? $.filter(
                  (B) =>
                    B.id !== C.id && B.restUid !== C.restUid && B.restUid !== L,
                )
              : es($, C, L)
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
    N = I === "calibrate-sensor" && w.id ? A.get(String(w.id)) : null,
    j =
      I === "cam-edit" && w.id
        ? ((k = E.get(String(w.id))) == null ? void 0 : k.sensorId) ||
          String(w.id)
        : null;
  return n.jsxs(n.Fragment, {
    children: [
      n.jsx(Qe, {
        open: I === "cam-create" || I === "cam-edit",
        mode: I === "cam-edit" ? "edit" : "create",
        sceneId: e,
        scenes: r,
        sensorUid: I === "cam-edit" ? j : null,
        authToken: s,
        onClose: v,
        onSaved: b,
      }),
      n.jsx(Xe, {
        open: I === "sensor-create" || I === "sensor-edit",
        mode: I === "sensor-edit" ? "edit" : "create",
        sceneId: e,
        scenes: r,
        sensorUid: I === "sensor-edit" ? w.id : null,
        authToken: s,
        onClose: v,
        onSaved: g,
      }),
      n.jsx(it, {
        open: I === "child-create" || I === "child-edit",
        mode: I === "child-edit" ? "edit" : "create",
        parentSceneId: e,
        childUid: I === "child-edit" ? w.id : null,
        scenes: r,
        authToken: s,
        onClose: v,
        onSaved: m,
      }),
      n.jsx(rt, {
        open: I === "scene-manage",
        sceneId: e,
        authToken: s,
        onClose: v,
        onSaved: M,
      }),
      n.jsx(Ze, {
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
      n.jsx(et, {
        open: !!N || I === "calibrate-sensor",
        sensorPk: (N == null ? void 0 : N.id) || w.id || "",
        sensorId: (N == null ? void 0 : N.sensorId) || "",
        sceneId: e,
        authToken: s,
        mapUrlHint: y,
        mapScale: S,
        onClose: v,
        onSaved: M,
      }),
    ],
  });
}
const Oe = "ss-workspace-layout-mode",
  is = 224,
  rs = 256,
  re = 120;
function Te() {
  return {
    w: Math.max(window.innerWidth || 0, 320),
    h: Math.max(window.innerHeight || 0, 320),
  };
}
function os() {
  try {
    const e = window.localStorage.getItem(Oe);
    if (e === "auto" || e === "stack" || e === "row") return e;
  } catch {}
  return "auto";
}
function as(e) {
  try {
    window.localStorage.setItem(Oe, e);
  } catch {}
}
function ls() {
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
function $e(e, s, t) {
  const i = Math.max(s, re),
    r = Math.max(t, re),
    o = Math.min(i / e.w, r / e.h);
  return !Number.isFinite(o) || o <= 0 ? 0 : e.w * o * (e.h * o);
}
function Le(e, s, t) {
  const i = Math.max(e.w - 32, re),
    r = Math.max(e.h - t, re);
  if (i < 720 || r / i > 1.25) return "stack";
  if (!s) return i / r >= 1.35 ? "stack" : "row";
  const o = s.w / s.h,
    h = $e(s, i, r - is),
    f = $e(s, i - rs, r);
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
function cs(e = {}) {
  const s = e.chromeHeightPx ?? 112,
    [t, i] = a.useState(() => (typeof window < "u" ? os() : "auto")),
    [r, o] = a.useState(() => Le(Te(), null, s)),
    h = a.useCallback((c) => {
      (i(c), as(c));
    }, []);
  return (
    a.useEffect(() => {
      let c = 0,
        l = null;
      const y = () => {
        (cancelAnimationFrame(c),
          (c = requestAnimationFrame(() => {
            const v = Le(Te(), ls(), s);
            l !== v && ((l = v), o((M) => (M === v ? M : v)));
          })));
      };
      (y(),
        window.addEventListener("resize", y),
        window.addEventListener("ss-map-host-ready", y));
      const S = document.querySelector("#ss-map-host #map img");
      S && !S.complete && S.addEventListener("load", y);
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
          S == null || S.removeEventListener("load", y),
          x == null || x.disconnect(),
          window.clearInterval(T),
          window.clearTimeout(D));
      };
    }, [s, t]),
    { layout: t === "auto" ? r : t, mode: t, setMode: h, autoLayout: r }
  );
}
function ds() {
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
function us() {
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
function ms(e) {
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
const fs = [
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
function hs({ bootstrap: e }) {
  const { scene: s, urls: t, isSuperuser: i } = e,
    { layout: r, mode: o, setMode: h, autoLayout: f } = cs(),
    {
      panelSizePx: c,
      setPanelSizePx: l,
      mapFocus: y,
      toggleMapFocus: S,
    } = tt(r),
    [w, x] = a.useState("--"),
    [T, D] = a.useState(!1),
    [v, M] = a.useState(!1),
    [b, g] = a.useState(null),
    m = ds(),
    _ = us(),
    [E, A] = a.useState(e.cameras),
    [I, d] = a.useState(e.sensors || []),
    [N, j] = a.useState(e.children || []),
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
              ].forEach((ge) => {
                const ee = z[ge];
                typeof ee == "number" &&
                  Number.isFinite(ee) &&
                  ee >= 0 &&
                  (G[ge] = ee);
              }),
              G
            );
          });
      };
      return (
        window.addEventListener(fe, C),
        () => window.removeEventListener(fe, C)
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
          await ot(t.sceneDelete, t.scenesHome || "/");
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
          children: fs.map((C) => {
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
          onClick: S,
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
      n.jsx(Ge, { title: s.name, back: ms(t), actions: $ }),
      n.jsxs("div", {
        className: "ss-workspace-body",
        children: [
          n.jsx("div", {
            className: "ss-workspace-main",
            children: n.jsx(Et, { mapUrl: s.mapUrl }),
          }),
          n.jsx(st, { layout: r, panelSizePx: c, onResize: l, disabled: y }),
          n.jsx(Ft, {
            tabs: L,
            cameraRates: _,
            cameras: E,
            sensors: I,
            childrenLinks: N,
            isSuperuser: i,
            sceneId: s.id,
            wssConnection: e.scene.wssConnection || "",
            authToken: e.authToken,
            onSensorsChange: d,
          }),
        ],
      }),
      n.jsx(Jt, {
        sceneId: s.id,
        isSuperuser: i,
        authToken: e.authToken,
        initialRegions: e.regions || [],
        initialTripwires: e.tripwires || [],
      }),
      n.jsx(ns, {
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
      n.jsxs(De, {
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
function ps({ bootstrap: e }) {
  return n.jsx(We, {
    children: n.jsx(Je, { children: n.jsx(hs, { bootstrap: e }) }),
  });
}
function ws({ bootstrap: e }) {
  return n.jsx(ps, { bootstrap: e });
}
function gs() {
  const e = document.getElementById("ss-scene-detail-bootstrap");
  if (!(e != null && e.textContent)) return null;
  try {
    return JSON.parse(e.textContent);
  } catch {
    return (console.error("Failed to parse scene detail bootstrap JSON"), null);
  }
}
const ke = gs(),
  Ae = document.getElementById("ss-scene-detail-root");
ke &&
  Ae &&
  (document.documentElement.classList.add("ss-scene-workspace"),
  document.body.classList.add("ss-scene-workspace"),
  ze
    .createRoot(Ae)
    .render(n.jsx(a.StrictMode, { children: n.jsx(ws, { bootstrap: ke }) })));
