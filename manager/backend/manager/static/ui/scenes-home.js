// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { r as l, j as e, c as D } from "./chunks/tokens-C2Ju3rc_.js";
import { u as C, C as E, T as $ } from "./chunks/ConfirmDialog-DanZpjzY.js";
import { L as T } from "./chunks/LegacyConfirmHost-VsPlnSjJ.js";
import { P as B } from "./chunks/PageHeader-Dke5XNFH.js";
import { A as y } from "./chunks/actionIcons-BIxtFbWH.js";
import {
  a as N,
  D as A,
  F as w,
  T as F,
  u as M,
} from "./chunks/rest-CiiNoWNe.js";
import { B as H } from "./chunks/Button-CDF7QSMd.js";
import { S as L, C as O } from "./chunks/SceneManagePanel-C7ukm3Qu.js";
function P({
  open: n,
  mode: a,
  sceneUid: t,
  authToken: s,
  onClose: d,
  onSaved: x,
}) {
  const j = C(),
    [f, r] = l.useState(""),
    [u, h] = l.useState("100"),
    [p, o] = l.useState(null),
    [i, g] = l.useState(!1),
    [v, b] = l.useState(null);
  l.useEffect(() => {
    if (!n) return;
    if ((b(null), o(null), a === "create")) {
      (r(""), h("100"));
      return;
    }
    if (!t) return;
    let m = !1;
    return (
      g(!0),
      N.getScene(s, t)
        .then((c) => {
          m ||
            (r(String(c.name || "")),
            h(c.scale != null ? String(c.scale) : "100"));
        })
        .catch((c) => {
          m || b(c.message || "Failed to load scene");
        })
        .finally(() => {
          m || g(!1);
        }),
      () => {
        m = !0;
      }
    );
  }, [n, a, t, s]);
  const I = async (m) => {
    (m.preventDefault(), g(!0), b(null));
    const c = new FormData();
    (c.append("name", f.trim()),
      u.trim() && c.append("scale", u.trim()),
      p && c.append("map", p));
    try {
      if (a === "create") {
        const S = await N.createScene(s, c);
        (j.show("Scene created", "ok"), x(S == null ? void 0 : S.uid));
      } else
        t &&
          (await N.updateScene(s, t, c), j.show("Scene updated", "ok"), x(t));
      d();
    } catch (S) {
      b(S.message || "Save failed");
    } finally {
      g(!1);
    }
  };
  return e.jsx(A, {
    open: n,
    title: a === "create" ? "New scene" : "Edit scene",
    onClose: d,
    wide: !0,
    actions: e.jsx(H, {
      variant: "primary",
      disabled: i,
      form: "ss-scene-sheet-form",
      type: "submit",
      children: i ? "Saving…" : a === "create" ? "Create scene" : "Save",
    }),
    children: e.jsxs("form", {
      id: "ss-scene-sheet-form",
      className: "ss-drawer-form",
      onSubmit: I,
      children: [
        v ? e.jsx("p", { className: "ss-drawer-error", children: v }) : null,
        e.jsx(w, {
          id: "ss-scene-identity",
          title: "Identity",
          description: "How this scene appears in the gallery.",
          children: e.jsx(F, {
            id: "ss-scene-name",
            label: "Name",
            value: f,
            onChange: (m) => r(m.target.value),
            required: !0,
            disabled: i,
          }),
        }),
        e.jsxs(w, {
          id: "ss-scene-map",
          title: "Map",
          description: "Floor plan and scale for the common create path.",
          children: [
            e.jsx(F, {
              id: "ss-scene-scale",
              label: "Scale (px per meter)",
              value: u,
              onChange: (m) => h(m.target.value),
              disabled: i,
            }),
            e.jsxs("div", {
              className: "ss-text-field",
              children: [
                e.jsx("label", {
                  className: "ss-text-field-label",
                  htmlFor: "ss-scene-map",
                  children: "Map image",
                }),
                e.jsx("div", {
                  className: "ss-text-field-control",
                  children: e.jsx("input", {
                    id: "ss-scene-map",
                    type: "file",
                    accept: "image/*,.pdf,.svg,.glb,.gltf",
                    disabled: i,
                    onChange: (m) => {
                      var c;
                      return o(
                        ((c = m.target.files) == null ? void 0 : c[0]) || null,
                      );
                    },
                  }),
                }),
              ],
            }),
            e.jsx("p", {
              className: "ss-drawer-hint",
              children:
                "Geospatial providers and advanced calibration live under Manage Scene after create.",
            }),
          ],
        }),
      ],
    }),
  });
}
function U({ open: n, authToken: a, onClose: t, onImported: s }) {
  const d = C(),
    [x, j] = l.useState(null),
    [f, r] = l.useState(!1),
    [u, h] = l.useState(null),
    p = async () => {
      if (!x) {
        h("Choose a scene zip file");
        return;
      }
      (r(!0), h(null));
      const o = new FormData();
      o.append("zipFile", x);
      try {
        (await N.importScene(a, o), d.show("Scene imported", "ok"), s(), t());
      } catch (i) {
        h(i.message || "Import failed");
      } finally {
        r(!1);
      }
    };
  return e.jsxs(E, {
    open: n,
    title: "Import scene",
    confirmLabel: f ? "Importing…" : "Import",
    cancelLabel: "Cancel",
    danger: !1,
    busy: f,
    onConfirm: p,
    onCancel: () => {
      f || t();
    },
    children: [
      e.jsx("p", { children: "Upload a SceneScape scene export (.zip)." }),
      e.jsx("input", {
        type: "file",
        accept: ".zip,application/zip",
        disabled: f,
        onChange: (o) => {
          var i;
          return j(((i = o.target.files) == null ? void 0 : i[0]) || null);
        },
      }),
      u ? e.jsx("p", { className: "ss-confirm-error", children: u }) : null,
    ],
  });
}
const _ = new Set([
  "scene-create",
  "scene-import",
  "scene-manage",
  "child-create",
]);
function z(n) {
  return !!(n && _.has(n));
}
function R({ scene: n }) {
  const a = n.thumbnailUrl || n.mapUrl;
  return a
    ? e.jsx("img", { className: "cover", src: a, alt: n.name })
    : e.jsx("div", {
        className: "blank-container border",
        "aria-hidden": "true",
      });
}
function q({ scenes: n, isSuperuser: a, onCreate: t }) {
  return n.length === 0
    ? e.jsxs("p", {
        className: "scene-gallery-empty ss-scene-gallery-empty",
        children: [
          "No scenes are available.",
          a
            ? e.jsxs(e.Fragment, {
                children: [
                  " ",
                  e.jsx("button", {
                    type: "button",
                    className: "ss-text-link",
                    onClick: t,
                    children: "Click here",
                  }),
                  " ",
                  "to add one.",
                ],
              })
            : " Ask an administrator to add one.",
        ],
      })
    : e.jsx("div", {
        className: "scene-gallery ss-scene-gallery",
        children: n.map((s) =>
          e.jsxs(
            "div",
            {
              className: "card scene-card ss-scene-card",
              "data-scene-id": s.id,
              ref: (d) => {
                d && d.setAttribute("name", s.name);
              },
              children: [
                e.jsx("h5", { className: "card-header", children: s.name }),
                e.jsx("div", {
                  className: "card-image",
                  children: e.jsx("a", {
                    id: `scene_id_${s.id}`,
                    href: s.detailUrl,
                    children: e.jsx(R, { scene: s }),
                  }),
                }),
                e.jsxs("div", {
                  className: "card-body",
                  children: [
                    e.jsx("table", {
                      className: "table table-sm scene-card-meta",
                      children: e.jsxs("tbody", {
                        children: [
                          e.jsxs("tr", {
                            children: [
                              e.jsx("td", { children: "Cameras & Sensors" }),
                              e.jsx("td", {
                                className: "sensor-count",
                                children: s.counts.sensors,
                              }),
                            ],
                          }),
                          e.jsxs("tr", {
                            children: [
                              e.jsx("td", { children: "Regions" }),
                              e.jsx("td", {
                                className: "region-count",
                                children: s.counts.regions,
                              }),
                            ],
                          }),
                          e.jsxs("tr", {
                            children: [
                              e.jsx("td", { children: "Tripwires" }),
                              e.jsx("td", {
                                className: "tripwire-count",
                                children: s.counts.tripwires,
                              }),
                            ],
                          }),
                        ],
                      }),
                    }),
                    e.jsxs("div", {
                      className: "scene-card-actions ss-scene-card-actions",
                      children: [
                        e.jsx("a", {
                          className: "ss-icon-btn",
                          id: `scene-manage-${s.name}`,
                          href: s.detailUrl,
                          title: `Configure ${s.name} Scene`,
                          "aria-label": `Configure ${s.name} Scene`,
                          children: e.jsx("i", {
                            className: `bi ${y.configure}`,
                            "aria-hidden": "true",
                          }),
                        }),
                        e.jsx("a", {
                          className: "ss-btn ss-btn--secondary ss-btn--sm",
                          id: `scene-3d-${s.id}`,
                          href: s.detail3dUrl,
                          title: `View ${s.name} Scene in 3D`,
                          children: "3D",
                        }),
                        a
                          ? e.jsxs(e.Fragment, {
                              children: [
                                e.jsx("a", {
                                  className: "ss-icon-btn",
                                  id: `scene-edit-${s.id}`,
                                  href: s.manageUrl,
                                  title: `Edit ${s.name} Scene Details`,
                                  "aria-label": `Edit ${s.name} Scene Details`,
                                  children: e.jsx("i", {
                                    className: `bi ${y.edit}`,
                                    "aria-hidden": "true",
                                  }),
                                }),
                                s.deleteUrl
                                  ? e.jsx("a", {
                                      className:
                                        "ss-icon-btn ss-icon-btn--danger",
                                      id: `scene-delete-${s.id}`,
                                      href: s.deleteUrl,
                                      title: `Delete ${s.name} Scene`,
                                      "aria-label": `Delete ${s.name} Scene`,
                                      children: e.jsx("i", {
                                        className: `bi ${y.delete}`,
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
                }),
              ],
            },
            s.id,
          ),
        ),
      });
}
function G({ bootstrap: n }) {
  const { sheet: a, open: t, close: s } = M();
  (C(),
    l.useEffect(() => {
      const r = (u) => {
        const h = u.target,
          p = h == null ? void 0 : h.closest("a[href]");
        if (!(p != null && p.href)) return;
        let o;
        try {
          o = new URL(p.href, window.location.origin);
        } catch {
          return;
        }
        const i = o.searchParams.get("ss");
        if (!i || !z(i)) {
          if (p.id === "new_scene") {
            (u.preventDefault(), t("scene-create"));
            return;
          }
          if (p.id === "import-scene") {
            (u.preventDefault(), t("scene-import"));
            return;
          }
          return;
        }
        (o.pathname === "/" || o.pathname === "") &&
          (u.preventDefault(), t(i, o.searchParams.get("id")));
      };
      return (
        document.addEventListener("click", r, !0),
        () => document.removeEventListener("click", r, !0)
      );
    }, [t]));
  const d = l.useCallback(() => {
      window.location.reload();
    }, []),
    x = l.useCallback(() => t("scene-create"), [t]),
    j = l.useMemo(
      () => (n.scenes || []).map((r) => ({ id: r.id, name: r.name })),
      [n.scenes],
    ),
    f = a.action === "scene-manage" && a.id ? a.id : "";
  return e.jsxs(e.Fragment, {
    children: [
      e.jsx(B, {
        title: "Scenes",
        actions: n.isSuperuser
          ? e.jsxs(e.Fragment, {
              children: [
                e.jsx("a", {
                  id: "import-scene",
                  className: "ss-btn ss-btn--secondary",
                  href: "?ss=scene-import",
                  children: "Import Scene",
                }),
                e.jsx("a", {
                  id: "new_scene",
                  className: "ss-btn ss-btn--primary",
                  href: "?ss=scene-create",
                  children: "+ New Scene",
                }),
              ],
            })
          : null,
      }),
      e.jsx(q, {
        scenes: n.scenes || [],
        isSuperuser: n.isSuperuser,
        onCreate: x,
      }),
      n.isSuperuser
        ? e.jsxs(e.Fragment, {
            children: [
              e.jsx(P, {
                open: a.action === "scene-create",
                mode: "create",
                sceneUid: null,
                authToken: n.authToken,
                onClose: s,
                onSaved: (r) => {
                  if (r) {
                    window.location.href = `/${r}/`;
                    return;
                  }
                  d();
                },
              }),
              e.jsx(U, {
                open: a.action === "scene-import",
                authToken: n.authToken,
                onClose: s,
                onImported: d,
              }),
              e.jsx(L, {
                open: !!f,
                sceneId: f,
                authToken: n.authToken,
                onClose: s,
                onSaved: d,
              }),
              e.jsx(O, {
                open: a.action === "child-create",
                mode: "create",
                parentSceneId: "",
                scenes: j,
                authToken: n.authToken,
                onClose: s,
                onSaved: d,
              }),
            ],
          })
        : null,
    ],
  });
}
function J({ bootstrap: n }) {
  return e.jsx($, {
    children: e.jsx(T, {
      children: e.jsx("div", {
        className: "ss-scenes-home",
        children: e.jsx(G, { bootstrap: n }),
      }),
    }),
  });
}
function Q() {
  const n = document.getElementById("ss-scenes-home-bootstrap");
  if (!(n != null && n.textContent)) return null;
  try {
    return JSON.parse(n.textContent);
  } catch {
    return (console.error("Failed to parse scenes home bootstrap JSON"), null);
  }
}
const k = Q(),
  V =
    document.getElementById("ss-scenes-home-app") ||
    (() => {
      const n = document.createElement("div");
      return (
        (n.id = "ss-scenes-home-app"),
        (
          document.querySelector("main") ||
          document.querySelector(".container") ||
          document.body
        ).appendChild(n),
        n
      );
    })();
k &&
  D.createRoot(V).render(
    e.jsx(l.StrictMode, { children: e.jsx(J, { bootstrap: k }) }),
  );
