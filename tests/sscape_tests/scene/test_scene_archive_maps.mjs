// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL(
    "../../../manager/src/manager/static/js/scene-archive.js",
    import.meta.url,
  ),
  "utf8",
);
const { addSceneMaps } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);
globalThis.window = { location: { origin: "https://localhost" } };

test("packs all local descendants without fetching remote maps", async () => {
  const requested = [];
  globalThis.fetch = async (url) => {
    requested.push(url);
    return { ok: true, blob: async () => new Blob(["map"]) };
  };
  const scene = {
    uid: "parent",
    name: "Parent",
    map: "/parent.png",
    remote_children: [{ remote_child_id: "remote" }],
    children: [
      {
        uid: "local",
        name: "Local",
        map: "/local.png",
        children: [{ uid: "nested", name: "Nested", map: "/nested.glb" }],
      },
    ],
  };
  const files = [];
  await addSceneMaps({ file: (name) => files.push(name) }, scene);
  assert.deepEqual(requested, ["/parent.png", "/local.png", "/nested.glb"]);
  assert.deepEqual(files, ["parent.png", "local.png", "nested.glb"]);
  assert.equal(scene.children[0].children[0].map_file, "nested.glb");
});

test("fails rather than generating an incomplete archive", async () => {
  globalThis.fetch = async () => ({ ok: false });
  await assert.rejects(
    addSceneMaps({ file() {} }, { name: "Missing", map: "/missing.png" }),
    /Failed to fetch map/,
  );
  await assert.rejects(
    addSceneMaps({ file() {} }, { name: "Missing" }),
    /Missing map/,
  );
});
