// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { j as e, c as h, r as o } from "./chunks/tokens-C2Ju3rc_.js";
import { P as x } from "./chunks/PageHeader-Dke5XNFH.js";
import { i as u, A as j } from "./chunks/actionIcons-BIxtFbWH.js";
function b({ cell: s }) {
  const r = s.text || "—",
    a = s.href ? e.jsx("a", { href: s.href, children: r }) : r;
  return s.swatch
    ? e.jsxs("span", {
        className: "ss-admin-swatch-cell",
        children: [
          e.jsx("span", {
            className: "ss-admin-swatch",
            style: { backgroundColor: s.swatch },
            title: s.swatch,
            "aria-hidden": "true",
          }),
          a,
        ],
      })
    : a;
}
function p({ bootstrap: s }) {
  const r = !!s.isSuperuser && s.rows.some((t) => (t.actions || []).length > 0),
    a = s.primaryAction
      ? e.jsx("a", {
          className: "ss-btn ss-btn--primary",
          href: s.primaryAction.href,
          id: s.primaryAction.id,
          children: s.primaryAction.label,
        })
      : null;
  return e.jsxs("div", {
    className: "ss-admin-list hide-fullscreen",
    children: [
      e.jsx(x, {
        title: s.title,
        breadcrumbs: s.breadcrumbs || [],
        actions: a,
      }),
      e.jsx("div", {
        className: "ss-table-card ss-admin-table-card",
        children:
          s.rows.length === 0
            ? e.jsx("p", {
                className: "ss-table-empty",
                children: s.emptyMessage || "Nothing to show.",
              })
            : e.jsxs("table", {
                className: "table ss-admin-table",
                children: [
                  e.jsx("thead", {
                    children: e.jsxs("tr", {
                      children: [
                        s.columns.map((t) => e.jsx("th", { children: t }, t)),
                        r ? e.jsx("th", { children: "Actions" }) : null,
                      ],
                    }),
                  }),
                  e.jsx("tbody", {
                    children: s.rows.map((t) =>
                      e.jsxs(
                        "tr",
                        {
                          children: [
                            t.cells.map((n, i) =>
                              e.jsx(
                                "td",
                                { children: e.jsx(b, { cell: n }) },
                                `${t.id}-${i}`,
                              ),
                            ),
                            r
                              ? e.jsx("td", {
                                  children: e.jsx("div", {
                                    className: "ss-table-actions",
                                    children: (t.actions || []).map((n) => {
                                      const i = u(n.label),
                                        l = i ? j[i] : null,
                                        m = n.tone === "danger";
                                      return e.jsx(
                                        "a",
                                        {
                                          className: `ss-table-action${m ? " is-danger" : ""}${l ? " is-icon" : ""}`,
                                          href: n.href,
                                          id: n.id,
                                          title: n.label,
                                          "aria-label": n.label,
                                          children: l
                                            ? e.jsx("i", {
                                                className: `bi ${l}`,
                                                "aria-hidden": "true",
                                              })
                                            : e.jsx("span", {
                                                children: n.label,
                                              }),
                                        },
                                        `${t.id}-${n.label}-${n.href}`,
                                      );
                                    }),
                                  }),
                                })
                              : null,
                          ],
                        },
                        t.id,
                      ),
                    ),
                  }),
                ],
              }),
      }),
    ],
  });
}
function f() {
  const s = document.getElementById("ss-admin-list-bootstrap");
  if (!(s != null && s.textContent)) return null;
  try {
    return JSON.parse(s.textContent);
  } catch {
    return (console.error("Failed to parse admin list bootstrap JSON"), null);
  }
}
const c = f(),
  d = document.getElementById("ss-admin-list-root");
c &&
  d &&
  h
    .createRoot(d)
    .render(e.jsx(o.StrictMode, { children: e.jsx(p, { bootstrap: c }) }));
