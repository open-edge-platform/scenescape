// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { r as l, j as e, c as re } from "./chunks/tokens-C2Ju3rc_.js";
import { u as B, C as le, T as ie } from "./chunks/ConfirmDialog-DanZpjzY.js";
import { L as ce } from "./chunks/LegacyConfirmHost-VsPlnSjJ.js";
import { P as oe } from "./chunks/PageHeader-Dke5XNFH.js";
import { A } from "./chunks/actionIcons-BIxtFbWH.js";
import {
  a as k,
  D as de,
  F as C,
  T as v,
  S as Q,
  u as pe,
} from "./chunks/rest-CiiNoWNe.js";
import { B as V } from "./chunks/Button-CDF7QSMd.js";
import {
  c as me,
  G as ue,
  a as he,
  f as fe,
  S as ge,
  C as xe,
} from "./chunks/SceneManagePanel-wsgpQWOS.js";
const je =
  "Mapping is not running. Upload a map, use geospatial, or start mapping with: docker compose --profile mapping up -d";
function Se({
  open: t,
  mode: r,
  sceneUid: o,
  authToken: a,
  onClose: f,
  onSaved: S,
}) {
  const b = B(),
    [g, m] = l.useState(""),
    [c, u] = l.useState("100"),
    [d, h] = l.useState(null),
    [i, w] = l.useState("upload"),
    [y, K] = l.useState(!1),
    [F, T] = l.useState(!1),
    [p, N] = l.useState(!1),
    [O, x] = l.useState(null),
    [X, L] = l.useState("false"),
    [ee, E] = l.useState(""),
    [_, I] = l.useState("google"),
    [H, D] = l.useState("15"),
    [U, G] = l.useState(""),
    [R, P] = l.useState(""),
    [z, $] = l.useState("0"),
    [M, q] = l.useState(null),
    [J, Z] = l.useState(null),
    [se, W] = l.useState(!1);
  l.useEffect(() => {
    if (!t) return;
    if (
      (x(null),
      h(null),
      q(null),
      Z(null),
      L("false"),
      E(""),
      I("google"),
      D("15"),
      G(""),
      P(""),
      $("0"),
      r === "create")
    ) {
      (m(""), u("100"), T(!1));
      let n = !1;
      return (
        me(a).then((j) => {
          n || (K(j), T(!0), w(j ? "reconstruct" : "upload"));
        }),
        () => {
          n = !0;
        }
      );
    }
    if (!o) return;
    let s = !1;
    return (
      N(!0),
      k
        .getScene(a, o)
        .then((n) => {
          s ||
            (m(String(n.name || "")),
            u(n.scale != null ? String(n.scale) : "100"));
        })
        .catch((n) => {
          s || x(n.message || "Failed to load scene");
        })
        .finally(() => {
          s || N(!1);
        }),
      () => {
        s = !0;
      }
    );
  }, [t, r, o, a]);
  const ae = async (s) => {
      (N(!0), x(null));
      try {
        const n = await fe(s);
        (q(s),
          h(n),
          u(s.scale || c),
          E(s.mapCornersLla),
          L(s.outputLla),
          I(s.geospatialProvider),
          D(s.mapZoom),
          G(s.mapCenterLat),
          P(s.mapCenterLng),
          $(s.mapBearing),
          Z(s.mapFilename),
          b.show("Basemap positioned — create the scene to save", "ok"));
      } catch (n) {
        const j =
          n instanceof Error ? n.message : "Failed to apply geospatial map";
        throw (x(j), new Error(j));
      } finally {
        N(!1);
      }
    },
    te =
      p ||
      (r === "create" &&
        ((i === "upload" && !d) ||
          (i === "geospatial" && !M) ||
          (i === "reconstruct" && (!F || !y)))),
    ne = async (s) => {
      (s.preventDefault(), N(!0), x(null));
      try {
        if (r === "create") {
          if (i === "upload" && !d) {
            x("Choose a map file to upload");
            return;
          }
          if (i === "geospatial" && (!M || !d)) {
            x("Position a geospatial basemap before creating the scene");
            return;
          }
          if (i === "reconstruct" && !y) {
            x(
              "Mapping service is not available. Upload a map or use geospatial instead.",
            );
            return;
          }
          const n = new FormData();
          (n.append("name", g.trim()),
            i === "geospatial" && M && d
              ? he(n, M, { mapFile: d })
              : (n.append("map_type", "map_upload"),
                c.trim() && n.append("scale", c.trim()),
                i === "upload" && d && n.append("map", d)));
          const j = await k.createScene(a, n);
          (b.show("Scene created", "ok"),
            S(
              j == null ? void 0 : j.uid,
              i === "reconstruct" ? { setup: "reconstruct" } : void 0,
            ));
        } else if (o) {
          const n = new FormData();
          (n.append("name", g.trim()),
            c.trim() && n.append("scale", c.trim()),
            d && n.append("map", d),
            await k.updateScene(a, o, n),
            b.show("Scene updated", "ok"),
            S(o));
        }
        f();
      } catch (n) {
        x(n.message || "Save failed");
      } finally {
        N(!1);
      }
    };
  return e.jsxs(e.Fragment, {
    children: [
      e.jsx(de, {
        open: t,
        title: r === "create" ? "New scene" : "Edit scene",
        onClose: f,
        wide: !0,
        actions: e.jsx(V, {
          variant: "primary",
          disabled: te,
          form: "ss-scene-sheet-form",
          type: "submit",
          children: p ? "Saving…" : r === "create" ? "Create scene" : "Save",
        }),
        children: e.jsxs("form", {
          id: "ss-scene-sheet-form",
          className: "ss-drawer-form",
          onSubmit: ne,
          children: [
            O
              ? e.jsx("p", { className: "ss-drawer-error", children: O })
              : null,
            e.jsx(C, {
              id: "ss-scene-identity",
              title: "Identity",
              description: "How this scene appears in the gallery.",
              children: e.jsx(v, {
                id: "ss-scene-name",
                label: "Name",
                value: g,
                onChange: (s) => m(s.target.value),
                required: !0,
                disabled: p,
              }),
            }),
            r === "create"
              ? e.jsxs(C, {
                  id: "ss-scene-map-source",
                  title: "Map source",
                  description:
                    "Choose how this scene gets its floor plan. Tracking needs a map and calibrated cameras.",
                  children: [
                    e.jsxs("fieldset", {
                      className: "ss-map-source-fieldset",
                      children: [
                        e.jsx("legend", {
                          className: "ss-text-field-label",
                          children: "How will you provide the map?",
                        }),
                        e.jsxs("label", {
                          className: "ss-map-source-option",
                          children: [
                            e.jsx("input", {
                              type: "radio",
                              name: "ss-map-source",
                              value: "reconstruct",
                              checked: i === "reconstruct",
                              disabled: p || (F && !y),
                              onChange: () => w("reconstruct"),
                            }),
                            e.jsxs("span", {
                              children: [
                                "Reconstruct from cameras",
                                F && !y ? " (mapping unavailable)" : "",
                              ],
                            }),
                          ],
                        }),
                        e.jsxs("label", {
                          className: "ss-map-source-option",
                          children: [
                            e.jsx("input", {
                              type: "radio",
                              name: "ss-map-source",
                              value: "upload",
                              checked: i === "upload",
                              disabled: p,
                              onChange: () => w("upload"),
                            }),
                            e.jsx("span", {
                              children: "Upload map (image / GLB)",
                            }),
                          ],
                        }),
                        e.jsxs("label", {
                          className: "ss-map-source-option",
                          children: [
                            e.jsx("input", {
                              type: "radio",
                              name: "ss-map-source",
                              value: "geospatial",
                              checked: i === "geospatial",
                              disabled: p,
                              onChange: () => w("geospatial"),
                            }),
                            e.jsx("span", { children: "Geospatial map" }),
                          ],
                        }),
                      ],
                    }),
                    F && !y
                      ? e.jsx("p", {
                          className: "ss-drawer-hint",
                          children: je,
                        })
                      : null,
                  ],
                })
              : null,
            r === "edit" || i === "upload"
              ? e.jsxs(C, {
                  id: "ss-scene-map",
                  title: "Map",
                  description:
                    r === "create"
                      ? "Floor plan image or 3D mesh for this scene."
                      : "Floor plan and scale.",
                  children: [
                    e.jsx(v, {
                      id: "ss-scene-scale",
                      label: "Scale (px per meter)",
                      value: c,
                      onChange: (s) => u(s.target.value),
                      disabled: p,
                    }),
                    e.jsxs("div", {
                      className: "ss-text-field",
                      children: [
                        e.jsx("label", {
                          className: "ss-text-field-label",
                          htmlFor: "ss-scene-map",
                          children: "Map file",
                        }),
                        e.jsx("div", {
                          className: "ss-text-field-control",
                          children: e.jsx("input", {
                            id: "ss-scene-map",
                            type: "file",
                            accept: "image/*,.pdf,.svg,.glb,.gltf",
                            disabled: p,
                            onChange: (s) => {
                              var n;
                              return h(
                                ((n = s.target.files) == null
                                  ? void 0
                                  : n[0]) || null,
                              );
                            },
                            required: r === "create" && i === "upload",
                          }),
                        }),
                      ],
                    }),
                  ],
                })
              : null,
            r === "create" && i === "reconstruct"
              ? e.jsx(C, {
                  id: "ss-scene-reconstruct",
                  title: "Reconstruction",
                  description:
                    "Create an empty scene, add cameras, then generate a mesh on the scene page.",
                  children: e.jsx("p", {
                    className: "ss-drawer-hint",
                    children:
                      "No map file is needed now. After create, add cameras that cover the space, then use Generate Mesh on the scene map. Scale is set from the reconstruction.",
                  }),
                })
              : null,
            r === "create" && i === "geospatial"
              ? e.jsxs(e.Fragment, {
                  children: [
                    e.jsx(C, {
                      id: "ss-scene-geo-map",
                      title: "Geospatial basemap",
                      description:
                        "Frame the scene on the map, then create. Advanced fields stay under settings.",
                      children: e.jsxs("div", {
                        className: "ss-text-field ss-form-section--span-2",
                        children: [
                          e.jsx("span", {
                            className: "ss-text-field-label",
                            children: "Basemap",
                          }),
                          e.jsxs("div", {
                            className: "ss-text-field-control",
                            style: {
                              display: "flex",
                              flexWrap: "wrap",
                              gap: "0.5rem",
                              alignItems: "center",
                            },
                            children: [
                              e.jsx(V, {
                                type: "button",
                                variant: "primary",
                                disabled: p,
                                onClick: () => W(!0),
                                children: "Position map",
                              }),
                              e.jsx("span", {
                                className: "ss-workspace-panel-hint",
                                style: { margin: 0 },
                                children: J
                                  ? `Positioned: ${J}`
                                  : "Open a floating map view to frame the scene",
                              }),
                            ],
                          }),
                        ],
                      }),
                    }),
                    e.jsxs(C, {
                      id: "ss-scene-geo-settings",
                      title: "Geospatial settings",
                      description:
                        "Provider, scale, and WGS84 corners (filled when you position the map).",
                      collapsible: !0,
                      defaultOpen: !1,
                      className: "ss-form-section--columns",
                      children: [
                        e.jsx(v, {
                          id: "ss-scene-geo-scale",
                          label: "Scale (px per meter)",
                          value: c,
                          onChange: (s) => u(s.target.value),
                          disabled: p,
                        }),
                        e.jsxs(Q, {
                          id: "ss-scene-output-lla",
                          label: "Output geospatial coordinates",
                          value: X,
                          onChange: (s) =>
                            L(s.target.value === "true" ? "true" : "false"),
                          disabled: p,
                          children: [
                            e.jsx("option", { value: "true", children: "Yes" }),
                            e.jsx("option", { value: "false", children: "No" }),
                          ],
                        }),
                        e.jsxs(Q, {
                          id: "ss-scene-geo-provider",
                          label: "Geospatial provider",
                          value: _,
                          onChange: (s) => I(s.target.value),
                          disabled: p,
                          children: [
                            e.jsx("option", {
                              value: "google",
                              children: "Google Maps",
                            }),
                            e.jsx("option", {
                              value: "mapbox",
                              children: "Mapbox",
                            }),
                          ],
                        }),
                        e.jsx(v, {
                          id: "ss-scene-map-zoom",
                          label: "Map zoom",
                          value: H,
                          onChange: (s) => D(s.target.value),
                          disabled: p,
                        }),
                        e.jsx(v, {
                          id: "ss-scene-map-lat",
                          label: "Map center latitude",
                          value: U,
                          onChange: (s) => G(s.target.value),
                          disabled: p,
                        }),
                        e.jsx(v, {
                          id: "ss-scene-map-lng",
                          label: "Map center longitude",
                          value: R,
                          onChange: (s) => P(s.target.value),
                          disabled: p,
                        }),
                        e.jsx(v, {
                          id: "ss-scene-map-bearing",
                          label: "Map bearing (degrees)",
                          value: z,
                          onChange: (s) => $(s.target.value),
                          disabled: p,
                        }),
                        e.jsxs("div", {
                          className: "ss-text-field ss-form-section--span-2",
                          children: [
                            e.jsx("label", {
                              className: "ss-text-field-label",
                              htmlFor: "ss-scene-corners",
                              children: "Map corners LLA (JSON)",
                            }),
                            e.jsx("div", {
                              className: "ss-text-field-control",
                              children: e.jsx("textarea", {
                                id: "ss-scene-corners",
                                className: "form-control ss-text-field-input",
                                rows: 4,
                                value: ee,
                                disabled: p,
                                onChange: (s) => E(s.target.value),
                              }),
                            }),
                          ],
                        }),
                      ],
                    }),
                  ],
                })
              : null,
          ],
        }),
      }),
      r === "create"
        ? e.jsx(ue, {
            open: se,
            provider: _,
            mapZoom: H,
            mapCenterLat: U,
            mapCenterLng: R,
            mapBearing: z,
            onClose: () => W(!1),
            onApply: ae,
          })
        : null,
    ],
  });
}
function be({ open: t, authToken: r, onClose: o, onImported: a }) {
  const f = B(),
    [S, b] = l.useState(null),
    [g, m] = l.useState(!1),
    [c, u] = l.useState(null),
    d = async () => {
      if (!S) {
        u("Choose a scene zip file");
        return;
      }
      (m(!0), u(null));
      const h = new FormData();
      h.append("zipFile", S);
      try {
        (await k.importScene(r, h), f.show("Scene imported", "ok"), a(), o());
      } catch (i) {
        u(i.message || "Import failed");
      } finally {
        m(!1);
      }
    };
  return e.jsxs(le, {
    open: t,
    title: "Import scene",
    confirmLabel: g ? "Importing…" : "Import",
    cancelLabel: "Cancel",
    danger: !1,
    busy: g,
    onConfirm: d,
    onCancel: () => {
      g || o();
    },
    children: [
      e.jsx("p", { children: "Upload a SceneScape scene export (.zip)." }),
      e.jsx("input", {
        type: "file",
        accept: ".zip,application/zip",
        disabled: g,
        onChange: (h) => {
          var i;
          return b(((i = h.target.files) == null ? void 0 : i[0]) || null);
        },
      }),
      c ? e.jsx("p", { className: "ss-confirm-error", children: c }) : null,
    ],
  });
}
const ve = new Set([
  "scene-create",
  "scene-import",
  "scene-manage",
  "child-create",
]);
function Ne(t) {
  return !!(t && ve.has(t));
}
function Ce({ scene: t }) {
  const r = t.thumbnailUrl || t.mapUrl;
  return r
    ? e.jsx("img", { className: "cover", src: r, alt: t.name })
    : e.jsx("div", {
        className: "blank-container border",
        "aria-hidden": "true",
      });
}
function ye({ scenes: t, isSuperuser: r, onCreate: o }) {
  return t.length === 0
    ? e.jsxs("p", {
        className: "scene-gallery-empty ss-scene-gallery-empty",
        children: [
          "No scenes are available.",
          r
            ? e.jsxs(e.Fragment, {
                children: [
                  " ",
                  e.jsx("button", {
                    type: "button",
                    className: "ss-text-link",
                    onClick: o,
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
        children: t.map((a) =>
          e.jsxs(
            "div",
            {
              className: "card scene-card ss-scene-card",
              "data-scene-id": a.id,
              ref: (f) => {
                f && f.setAttribute("name", a.name);
              },
              children: [
                e.jsx("h5", { className: "card-header", children: a.name }),
                e.jsx("div", {
                  className: "card-image",
                  children: e.jsx("a", {
                    id: `scene_id_${a.id}`,
                    href: a.detailUrl,
                    children: e.jsx(Ce, { scene: a }),
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
                                children: a.counts.sensors,
                              }),
                            ],
                          }),
                          e.jsxs("tr", {
                            children: [
                              e.jsx("td", { children: "Regions" }),
                              e.jsx("td", {
                                className: "region-count",
                                children: a.counts.regions,
                              }),
                            ],
                          }),
                          e.jsxs("tr", {
                            children: [
                              e.jsx("td", { children: "Tripwires" }),
                              e.jsx("td", {
                                className: "tripwire-count",
                                children: a.counts.tripwires,
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
                          id: `scene-manage-${a.name}`,
                          href: a.detailUrl,
                          title: `Configure ${a.name} Scene`,
                          "aria-label": `Configure ${a.name} Scene`,
                          children: e.jsx("i", {
                            className: `bi ${A.configure}`,
                            "aria-hidden": "true",
                          }),
                        }),
                        e.jsx("a", {
                          className: "ss-btn ss-btn--secondary ss-btn--sm",
                          id: `scene-3d-${a.id}`,
                          href: a.detail3dUrl,
                          title: `View ${a.name} Scene in 3D`,
                          children: "3D",
                        }),
                        r
                          ? e.jsxs(e.Fragment, {
                              children: [
                                e.jsx("a", {
                                  className: "ss-icon-btn",
                                  id: `scene-edit-${a.id}`,
                                  href: a.manageUrl,
                                  title: `Edit ${a.name} Scene Details`,
                                  "aria-label": `Edit ${a.name} Scene Details`,
                                  children: e.jsx("i", {
                                    className: `bi ${A.edit}`,
                                    "aria-hidden": "true",
                                  }),
                                }),
                                a.deleteUrl
                                  ? e.jsx("a", {
                                      className:
                                        "ss-icon-btn ss-icon-btn--danger",
                                      id: `scene-delete-${a.id}`,
                                      href: a.deleteUrl,
                                      title: `Delete ${a.name} Scene`,
                                      "aria-label": `Delete ${a.name} Scene`,
                                      children: e.jsx("i", {
                                        className: `bi ${A.delete}`,
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
            a.id,
          ),
        ),
      });
}
function we({ bootstrap: t }) {
  const { sheet: r, open: o, close: a } = pe();
  (B(),
    l.useEffect(() => {
      const m = (c) => {
        const u = c.target,
          d = u == null ? void 0 : u.closest("a[href]");
        if (!(d != null && d.href)) return;
        let h;
        try {
          h = new URL(d.href, window.location.origin);
        } catch {
          return;
        }
        const i = h.searchParams.get("ss");
        if (!i || !Ne(i)) {
          if (d.id === "new_scene") {
            (c.preventDefault(), o("scene-create"));
            return;
          }
          if (d.id === "import-scene") {
            (c.preventDefault(), o("scene-import"));
            return;
          }
          return;
        }
        (h.pathname === "/" || h.pathname === "") &&
          (c.preventDefault(), o(i, h.searchParams.get("id")));
      };
      return (
        document.addEventListener("click", m, !0),
        () => document.removeEventListener("click", m, !0)
      );
    }, [o]));
  const f = l.useCallback(() => {
      window.location.reload();
    }, []),
    S = l.useCallback(() => o("scene-create"), [o]),
    b = l.useMemo(
      () => (t.scenes || []).map((m) => ({ id: m.id, name: m.name })),
      [t.scenes],
    ),
    g = r.action === "scene-manage" && r.id ? r.id : "";
  return e.jsxs(e.Fragment, {
    children: [
      e.jsx(oe, {
        title: "Scenes",
        actions: t.isSuperuser
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
      e.jsx(ye, {
        scenes: t.scenes || [],
        isSuperuser: t.isSuperuser,
        onCreate: S,
      }),
      t.isSuperuser
        ? e.jsxs(e.Fragment, {
            children: [
              e.jsx(Se, {
                open: r.action === "scene-create",
                mode: "create",
                sceneUid: null,
                authToken: t.authToken,
                onClose: a,
                onSaved: (m, c) => {
                  if (m) {
                    const u =
                      (c == null ? void 0 : c.setup) === "reconstruct"
                        ? "?setup=reconstruct"
                        : "";
                    window.location.href = `/${m}/${u}`;
                    return;
                  }
                  f();
                },
              }),
              e.jsx(be, {
                open: r.action === "scene-import",
                authToken: t.authToken,
                onClose: a,
                onImported: f,
              }),
              e.jsx(ge, {
                open: !!g,
                sceneId: g,
                authToken: t.authToken,
                onClose: a,
                onSaved: f,
              }),
              e.jsx(xe, {
                open: r.action === "child-create",
                mode: "create",
                parentSceneId: "",
                scenes: b,
                authToken: t.authToken,
                onClose: a,
                onSaved: f,
              }),
            ],
          })
        : null,
    ],
  });
}
function Fe({ bootstrap: t }) {
  return e.jsx(ie, {
    children: e.jsx(ce, {
      children: e.jsx("div", {
        className: "ss-scenes-home",
        children: e.jsx(we, { bootstrap: t }),
      }),
    }),
  });
}
function Me() {
  const t = document.getElementById("ss-scenes-home-bootstrap");
  if (!(t != null && t.textContent)) return null;
  try {
    return JSON.parse(t.textContent);
  } catch {
    return (console.error("Failed to parse scenes home bootstrap JSON"), null);
  }
}
const Y = Me(),
  ke =
    document.getElementById("ss-scenes-home-app") ||
    (() => {
      const t = document.createElement("div");
      return (
        (t.id = "ss-scenes-home-app"),
        (
          document.querySelector("main") ||
          document.querySelector(".container") ||
          document.body
        ).appendChild(t),
        t
      );
    })();
Y &&
  re
    .createRoot(ke)
    .render(e.jsx(l.StrictMode, { children: e.jsx(Fe, { bootstrap: Y }) }));
