// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";
import { EventEmitter } from "node:events";

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
    updatePose(pose) {
      calls.push(["pose", this.uid, pose]);
    }
    syncOptics(data) {
      this.optics = data;
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

test("database notifications refresh existing optics without applying saved poses", async () => {
  let cameras = [{ uid: "a", name: "A", intrinsics: { fx: 500 } }];
  const { manager, calls } = await harness(() => cameras);
  await manager.load(params);
  const camera = manager.sceneCameras.a;
  calls.length = 0;
  cameras = [
    {
      uid: "a",
      name: "A",
      intrinsics: { fx: 1300 },
      resolution: [1920, 1440],
      translation: [0, 0, 0],
    },
  ];
  await manager.syncWithDatabase(params, {}, "app", false);
  assert.equal(manager.sceneCameras.a, camera);
  assert.deepEqual(camera.optics, cameras[0]);
  assert.deepEqual(calls, []);
});

test("only explicitly dynamic poses overwrite camera edits", async () => {
  const { manager, calls } = await harness(() => [{ uid: "a", name: "A" }]);
  await manager.load(params);
  calls.length = 0;
  manager.updatePoses([
    { id: "a", dynamic_pose: false },
    { id: "a" },
    { id: "missing", dynamic_pose: true },
    { id: "a", dynamic_pose: true, translation: [1, 2, 3] },
  ]);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].slice(0, 2), ["pose", "a"]);
  assert.deepEqual(calls[0][2].translation, [1, 2, 3]);
});

async function sceneCameraHarness() {
  const source = await readFile(
    new URL("thing/scenecamera.js", STATIC),
    "utf8",
  );
  const context = vm.createContext({
    console,
    clearInterval,
    window: { confirm: () => true },
    cv: {
      CV_64F: 0,
      matFromArray: (rows, cols, type, data64F) => ({ data64F }),
    },
  });
  const entry = new vm.SourceTextModule(source, { context });
  await entry.link(async (specifier) => {
    let exports;
    if (specifier.includes("three.module")) {
      exports = {
        Object3D: class {},
        MathUtils: {
          radToDeg: (v) => (v * 180) / Math.PI,
          degToRad: (v) => (v * Math.PI) / 180,
        },
      };
    } else if (specifier.includes("constants")) {
      exports = {
        CMD_CAMERA: "cmd/camera/",
        IMAGE_CAMERA: "image/camera/",
        MAX_INTRINSICS_UPDATE_WAIT_TIME: 0,
        FX: 0,
        FY: 4,
        CX: 2,
        CY: 5,
        K1: 0,
        K2: 1,
        P1: 2,
        P2: 3,
        K3: 4,
      };
    } else if (specifier.endsWith("/utils.js")) {
      exports = { compareIntrinsics: () => true };
    } else if (specifier.endsWith("/calibration.js")) {
      exports = { startCameraCalibration: () => {} };
    } else {
      exports = { default: class {} };
    }
    return new vm.SyntheticModule(
      Object.keys(exports),
      function () {
        for (const [name, value] of Object.entries(exports))
          this.setExport(name, value);
      },
      { context },
    );
  });
  await entry.evaluate();
  const camera = Object.create(entry.namespace.default.prototype);
  Object.assign(camera, {
    cameraUID: "mobile",
    name: "mobile",
    resolution: { w: 640, h: 480 },
    hasAuthoritativeResolution: false,
    databaseOptics: {},
    intrinsics: { fx: 900, fy: 1000, cx: 800, cy: 500 },
    cameraMatrix: { data64F: [900, 0, 800, 0, 1000, 500, 0, 0, 1] },
    sceneCamera: {
      setViewOffset(w, h, x, y) {
        this.aspect = w / h;
        this.offset = { x, y };
      },
      updateProjectionMatrix() {},
      getObjectByName() {},
    },
    executeOnControl() {},
    showCameraOnline() {},
  });
  return camera;
}

test("known sensor dimensions and off-center intrinsics define projection", async () => {
  const camera = await sceneCameraHarness();
  camera.updateCameraResolutionUsingInputFrame({
    resolution: { width: 1920, height: 1080 },
  });
  camera.applyOpticalProjection();
  assert.deepEqual(plain(camera.intrinsicsResolution()), { w: 1920, h: 1080 });
  assert.deepEqual(plain(camera.sceneCamera.offset), { x: 160, y: 40 });
  const verticalScale = 1 / Math.tan((camera.sceneCamera.fov * Math.PI) / 360);
  assert.ok(Math.abs(verticalScale - (2 * 1000) / 1080) < 1e-10);
  assert.ok(
    Math.abs(verticalScale / camera.sceneCamera.aspect - (2 * 900) / 1920) <
      1e-10,
  );
  camera.projectCameraCapture("thumbnail.png", { width: 320, height: 180 });
  assert.deepEqual(plain(camera.intrinsicsResolution()), { w: 1920, h: 1080 });
});

test("missing resolution uses intrinsics fallback; invalid metadata is ignored", async () => {
  const camera = await sceneCameraHarness();
  assert.deepEqual(plain(camera.intrinsicsResolution()), { w: 1600, h: 1000 });
  camera.updateCameraResolutionUsingInputFrame({ resolution: [0, -1] });
  assert.equal(camera.hasAuthoritativeResolution, false);
  camera.updateCameraResolutionUsingInputFrame({ resolution: [1920, 1080] });
  assert.deepEqual(plain(camera.intrinsicsResolution()), { w: 1920, h: 1080 });
});

test("latest optics update the existing camera without resetting its live pose", async () => {
  const camera = await sceneCameraHarness();
  const sceneCamera = camera.sceneCamera;
  sceneCamera.position = { x: 4, y: 5, z: 6 };
  camera.updateOptics({
    intrinsics: { fx: 1339, fy: 1340, cx: 956, cy: 726 },
    resolution: [1920, 1440],
  });
  assert.equal(camera.sceneCamera, sceneCamera);
  assert.deepEqual(sceneCamera.position, { x: 4, y: 5, z: 6 });
  assert.deepEqual(plain(sceneCamera.offset), { x: 4, y: -6 });
  assert.ok(
    Math.abs(
      sceneCamera.fov - (2 * Math.atan(1440 / (2 * 1340)) * 180) / Math.PI,
    ) < 1e-10,
  );
  camera.updateOptics({ extrinsics: { translation: [1, 2, 3] } });
  camera.updateIntrinsics(undefined);
  assert.equal(camera.intrinsics.fx, 1339);
});

test("database optics snapshots preserve local edits on unrelated notices", async () => {
  const camera = await sceneCameraHarness();
  const original = {
    intrinsics: { ...camera.intrinsics },
    resolution: [1600, 1000],
  };
  camera.syncOptics(original);
  camera.updateIntrinsics({ ...camera.intrinsics, fx: 950 });
  camera.syncOptics(original);
  assert.equal(camera.intrinsics.fx, 950);
  camera.syncOptics({
    intrinsics: { ...camera.intrinsics, fx: 1100 },
    resolution: [1920, 1080],
  });
  assert.equal(camera.intrinsics.fx, 1100);
  assert.deepEqual(plain(camera.intrinsicsResolution()), { w: 1920, h: 1080 });
});

test("image metadata updates optics but a manual FOV override is retained", async () => {
  const camera = await sceneCameraHarness();
  camera.projectCameraCapture("thumbnail.png", {
    intrinsics: [
      [700, 0, 320],
      [0, 710, 240],
      [0, 0, 1],
    ],
    resolution: [640, 480],
  });
  assert.equal(camera.intrinsics.fx, 700);
  assert.equal(camera.intrinsics.fy, 710);
  camera.fovEnabled = true;
  camera.updateOptics({
    intrinsics: { fx: 1200, fy: 1200, cx: 960, cy: 540 },
    resolution: [1920, 1080],
  });
  assert.equal(camera.intrinsics.fx, 700);
  assert.deepEqual(plain(camera.intrinsicsResolution()), { w: 640, h: 480 });
});

test("database diagonal FOV calibration is accepted as well as pixel intrinsics", async () => {
  const camera = await sceneCameraHarness();
  camera.syncOptics({ intrinsics: { fov: 70 }, resolution: [640, 480] });
  assert.ok(Number.isFinite(camera.sceneCamera.fov));
  assert.deepEqual(plain(camera.intrinsics), { fov: 70 });
});

test("save persists sensor dimensions or inferred fallback, never the default", async () => {
  for (const known of [false, true]) {
    const camera = await sceneCameraHarness();
    if (known)
      camera.updateCameraResolutionUsingInputFrame({
        resolution: [1920, 1080],
      });
    camera.sceneCamera.clone = () => ({
      position: [1, 2, 3],
      rotation: { x: 0, y: 0, z: 0 },
    });
    camera.togglePoseYupYdown = () => {};
    camera.updateCameras = () => {};
    camera.isStoredInDB = true;
    let payload;
    camera.updateExistingCamera = async (data) => {
      payload = data;
    };
    await camera.saveSettings();
    assert.deepEqual(
      plain(payload.resolution),
      known ? { width: 1920, height: 1080 } : { width: 1600, height: 1000 },
    );
  }
});

test("failed DELETE keeps the camera intact, success detaches it", async () => {
  for (const response of [500, "throw", 200]) {
    const camera = await sceneCameraHarness();
    let detached = 0;
    camera.detach = () => {
      detached += 1;
    };
    camera.toast = { showToast() {} };
    camera.isStoredInDB = true;
    camera.restclient = {
      deleteCamera: async () => {
        if (response === "throw") throw new Error("offline");
        return { statusCode: response };
      },
    };
    await camera.removeFromScene({});
    assert.equal(detached, response === 200 ? 1 : 0);
  }
});

test("rebinding and detaching releases only this camera's MQTT listener and socket", async () => {
  const camera = await sceneCameraHarness();
  const client = new EventEmitter();
  const unrelated = () => {};
  client.on("message", unrelated);
  camera.setMQTTClient(client, "app/");
  camera.setMQTTClient(client, "app/");
  assert.equal(client.listenerCount("message"), 2);
  let disconnected = 0;
  let removed = 0;
  camera.socket = {
    removeAllListeners() {
      removed += 1;
    },
    disconnect() {
      disconnected += 1;
    },
  };
  camera.scene = { remove() {} };
  camera.currentCameras = { mobile: camera, undefined: [] };
  camera.controlsFolder = { destroy() {} };
  camera.detach();
  camera.detach();
  assert.equal(client.listenerCount("message"), 1);
  assert.equal(client.listeners("message")[0], unrelated);
  assert.equal(disconnected, 1);
  assert.equal(removed, 1);
  assert.equal(camera.controlsFolder, null);
  assert.ok(!("mobile" in camera.currentCameras));
});
