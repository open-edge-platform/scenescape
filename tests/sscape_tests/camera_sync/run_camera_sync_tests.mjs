// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";

const STATIC = new URL(
  "../../../manager/src/manager/static/js/",
  import.meta.url,
);
const sources = {
  "/static/js/thing/managers/cameramanager.js": await readFile(
    new URL("thing/managers/cameramanager.js", STATIC),
    "utf8",
  ),
  "/static/js/thing/managers/thingmanager.js": await readFile(
    new URL("thing/managers/thingmanager.js", STATIC),
    "utf8",
  ),
};

async function harness(dbCameras) {
  const calls = [];
  const context = vm.createContext({
    console,
    document: { getElementById: () => ({ value: "token" }) },
  });
  class FakeCamera {
    constructor(thing) {
      Object.assign(this, thing);
      this.cameraUID = thing.uid;
      calls.push(["construct", thing.uid]);
    }
    addObject(params) {
      calls.push(["addObject", this.uid, params.currentThings]);
    }
    setMQTTClient(client, appName) {
      calls.push(["mqtt", this.uid, appName]);
    }
    setVARunning(running) {
      calls.push(["va", this.uid, running]);
    }
    detach(folder) {
      calls.push(["detach", this.uid, folder]);
    }
  }
  class FakeREST {
    async getCameras() {
      return { statusCode: 200, content: { results: dbCameras() } };
    }
  }
  const modules = new Map();
  const linker = async (specifier) => {
    if (modules.has(specifier)) return modules.get(specifier);
    let module;
    if (specifier in sources) {
      module = new vm.SourceTextModule(sources[specifier], { context });
    } else {
      const exports = specifier.includes("restclient")
        ? { default: FakeREST }
        : specifier.includes("scenecamera")
          ? { default: FakeCamera }
          : specifier.includes("constants")
            ? { REST_URL: "", SUCCESS: 200 }
            : { default: class {} };
      module = new vm.SyntheticModule(
        Object.keys(exports),
        function () {
          for (const [name, value] of Object.entries(exports))
            this.setExport(name, value);
        },
        { context },
      );
    }
    modules.set(specifier, module);
    return module;
  };
  const entry = await linker("/static/js/thing/managers/cameramanager.js");
  await entry.link(linker);
  await entry.evaluate();
  const manager = new entry.namespace.default("scene-1");
  manager.setPrivilege(true);
  return { manager, calls };
}

const params = { camerasFolder: { name: "folder" }, toast: {} };
// Values built inside the vm realm carry foreign prototypes.
const plain = (value) => JSON.parse(JSON.stringify(value));

test("new database cameras are built and wired to MQTT", async () => {
  let cameras = [{ uid: "a", name: "A" }];
  const { manager, calls } = await harness(() => cameras);
  await manager.load(params);
  calls.length = 0;

  cameras = [...cameras, { uid: "b", name: "B" }];
  const result = await manager.syncWithDatabase(params, {}, "app", true);

  assert.deepEqual(plain(result), { added: ["b"], removed: [] });
  assert.ok("b" in manager.sceneCameras);
  assert.equal(manager.sceneCameras.b.isStoredInDB, true);
  assert.deepEqual(
    calls.map((c) => c.slice(0, 2)),
    [
      ["construct", "b"],
      ["addObject", "b"],
      ["mqtt", "b"],
      ["va", "b"],
    ],
  );
  assert.equal(calls[1][2], manager.sceneCameras);
  assert.equal(calls[3][2], true);
});

test("cameras deleted elsewhere are detached from the scene", async () => {
  let cameras = [
    { uid: "a", name: "A" },
    { uid: "b", name: "B" },
  ];
  const { manager, calls } = await harness(() => cameras);
  await manager.load(params);
  calls.length = 0;

  cameras = [{ uid: "a", name: "A" }];
  const result = await manager.syncWithDatabase(params, {}, "app", false);

  assert.deepEqual(plain(result), { added: [], removed: ["b"] });
  assert.ok(!("b" in manager.sceneCameras));
  assert.ok("a" in manager.sceneCameras);
  assert.deepEqual(calls, [["detach", "b", params.camerasFolder]]);
});

test("existing and unsaved cameras are left untouched", async () => {
  const cameras = [{ uid: "a", name: "A" }];
  const { manager, calls } = await harness(() => cameras);
  await manager.load(params);
  const unsaved = manager.add({ uid: undefined, name: "draft" });
  calls.length = 0;

  const result = await manager.syncWithDatabase(params, {}, "app", false);

  assert.deepEqual(plain(result), { added: [], removed: [] });
  assert.deepEqual(calls, []);
  assert.equal(manager.sceneCameras[undefined].length, 1);
  assert.equal(manager.sceneCameras[undefined][0], unsaved);
});

test("a failed camera listing changes nothing", async () => {
  const cameras = [{ uid: "a", name: "A" }];
  const { manager, calls } = await harness(() => cameras);
  await manager.load(params);
  manager.restclient.getCameras = async () => ({ statusCode: 500 });
  calls.length = 0;

  const result = await manager.syncWithDatabase(params, {}, "app", false);

  assert.deepEqual(plain(result), { added: [], removed: [] });
  assert.deepEqual(calls, []);
  assert.ok("a" in manager.sceneCameras);
});
