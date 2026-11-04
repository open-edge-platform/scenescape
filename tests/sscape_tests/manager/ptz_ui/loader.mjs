// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Node module hooks for unit testing Manager browser modules.
 *
 * "/static/..." specifiers resolve to the Manager static tree. Modules under test
 * load from source; every other module is replaced by a stub that exports the
 * names its importer uses. Stub calls are recorded in globalThis.__ptzStubCalls
 * and can be overridden through globalThis.__ptzStubImpls ("<path>#<name>").
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../..",
);
const STATIC_ROOT = path.join(REPO_ROOT, "manager/src/manager/static");
const STATIC_URL = pathToFileURL(STATIC_ROOT).href;
const STUB_SCHEME = "ptz-ui-stub:";

// Modules without browser side effects at import time that are tested for real.
const REAL_MODULES = new Set([
  "assets/three.module.js",
  "js/camcanvas.js",
  "js/cameracalibrate.js",
  "js/constants.js",
  "js/customcamerahelper.js",
  "js/ptzpose.js",
  "js/thing/controls/thingtransformcontrols.js",
  "js/thing/scene.js",
  "js/thing/scenecamera.js",
  "js/viewport.js",
]);

function importedNames(parentURL, specifier) {
  const names = new Set();
  let hasDefault = false;
  if (!parentURL || !parentURL.startsWith("file:")) {
    return { names, hasDefault };
  }
  const source = readFileSync(fileURLToPath(parentURL), "utf8");
  const pattern = /import\s+([\s\S]*?)\s+from\s+["']([^"']+)["']/g;
  for (const [, clause, from] of source.matchAll(pattern)) {
    if (from !== specifier) continue;
    const named = clause.match(/\{([\s\S]*?)\}/);
    if (named) {
      for (const item of named[1].split(",")) {
        const name = item.trim().split(/\s+as\s+/)[0];
        if (name) names.add(name);
      }
    }
    const beforeBrace = clause.split("{")[0].replace(/,\s*$/, "").trim();
    if (beforeBrace && !beforeBrace.startsWith("*")) hasDefault = true;
  }
  return { names, hasDefault };
}

export async function resolve(specifier, context, nextResolve) {
  if (!specifier.startsWith("/static/")) {
    return nextResolve(specifier, context);
  }
  const relative = specifier.slice("/static/".length);
  if (REAL_MODULES.has(relative)) {
    return {
      url: pathToFileURL(path.join(STATIC_ROOT, relative)).href,
      shortCircuit: true,
    };
  }
  const { names, hasDefault } = importedNames(context.parentURL, specifier);
  const query = new URLSearchParams({
    names: [...names].sort().join(","),
    default: hasDefault ? "1" : "0",
  });
  return { url: `${STUB_SCHEME}${relative}?${query}`, shortCircuit: true };
}

function stubSource(url) {
  const [relative, queryString] = url.slice(STUB_SCHEME.length).split("?");
  const query = new URLSearchParams(queryString);
  const names = (query.get("names") || "").split(",").filter(Boolean);
  const lines = [
    "const calls = (globalThis.__ptzStubCalls ??= {});",
    "const impls = (globalThis.__ptzStubImpls ??= {});",
    "function make(name) {",
    `  const key = ${JSON.stringify(relative)} + "#" + name;`,
    "  return function stub(...args) {",
    "    (calls[key] ??= []).push(args);",
    "    if (impls[key]) return impls[key].apply(this, args);",
    "    return undefined;",
    "  };",
    "}",
    ...names.map(
      (name) => `export const ${name} = make(${JSON.stringify(name)});`,
    ),
  ];
  if (query.get("default") === "1") {
    lines.push('export default make("default");');
  }
  return lines.join("\n");
}

export async function load(url, context, nextLoad) {
  if (url.startsWith(STUB_SCHEME)) {
    return { format: "module", source: stubSource(url), shortCircuit: true };
  }
  if (url.startsWith(STATIC_URL)) {
    // Static files are browser ES modules without a package.json "type" marker.
    return {
      format: "module",
      source: readFileSync(fileURLToPath(url), "utf8"),
      shortCircuit: true,
    };
  }
  return nextLoad(url, context);
}
