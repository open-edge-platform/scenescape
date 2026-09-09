// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { j as e, c, r as h } from "./chunks/tokens-C2Ju3rc_.js";
import { P as m } from "./chunks/PageHeader-Dke5XNFH.js";
function o({ cell: s }) {
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
function x({ bootstrap: s }) {
  const r = !!s.isSuperuser && s.rows.some((n) => (n.actions || []).length > 0),
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
      e.jsx(m, {
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
                        s.columns.map((n) => e.jsx("th", { children: n }, n)),
                        r ? e.jsx("th", { children: "Actions" }) : null,
                      ],
                    }),
                  }),
                  e.jsx("tbody", {
                    children: s.rows.map((n) =>
                      e.jsxs(
                        "tr",
                        {
                          children: [
                            n.cells.map((t, d) =>
                              e.jsx(
                                "td",
                                { children: e.jsx(o, { cell: t }) },
                                `${n.id}-${d}`,
                              ),
                            ),
                            r
                              ? e.jsx("td", {
                                  children: e.jsx("div", {
                                    className: "ss-table-actions",
                                    children: (n.actions || []).map((t) =>
                                      e.jsx(
                                        "a",
                                        {
                                          className: `ss-table-action${t.tone === "danger" ? " is-danger" : ""}`,
                                          href: t.href,
                                          id: t.id,
                                          title: t.label,
                                          children: e.jsx("span", {
                                            children: t.label,
                                          }),
                                        },
                                        `${n.id}-${t.label}-${t.href}`,
                                      ),
                                    ),
                                  }),
                                })
                              : null,
                          ],
                        },
                        n.id,
                      ),
                    ),
                  }),
                ],
              }),
      }),
    ],
  });
}
function j() {
  const s = document.getElementById("ss-admin-list-bootstrap");
  if (!(s != null && s.textContent)) return null;
  try {
    return JSON.parse(s.textContent);
  } catch {
    return (console.error("Failed to parse admin list bootstrap JSON"), null);
  }
}
const i = j(),
  l = document.getElementById("ss-admin-list-root");
i &&
  l &&
  c
    .createRoot(l)
    .render(e.jsx(h.StrictMode, { children: e.jsx(x, { bootstrap: i }) }));
