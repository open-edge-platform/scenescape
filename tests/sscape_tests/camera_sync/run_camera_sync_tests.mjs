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

test("camera loading and reconciliation include all pages beyond 100 cameras", async () => {
  const { manager, calls } = await harness(() => []);
  const cameras = Array.from({ length: 101 }, (_, index) => ({
    uid: `camera-${index}`,
    name: `Camera ${index}`,
  }));
  const pages = [];
  manager.restclient.getCameras = async ({ scene, page }) => {
    assert.equal(scene, "scene-1");
    pages.push(page);
    return {
      statusCode: 200,
      content: {
        results: cameras.slice((page - 1) * 100, page * 100),
        next: page === 1 ? "/api/v1/cameras?page=2" : null,
      },
    };
  };
  await manager.load(params);
  assert.deepEqual(pages, [1, 2]);
  const last = manager.sceneCameras["camera-100"];
  calls.length = 0;
  await manager.syncWithDatabase(params, {}, "app", true);
  assert.equal(manager.sceneCameras["camera-100"], last);
  assert.deepEqual(calls, []);
  const published = [];
  await manager.refresh(
    { publish: (...args) => published.push(args) },
    "image/",
  );
  // refresh returns after scheduling its callback.
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(published.length, 101);
});

test("failure of a later camera page leaves membership and optics untouched", async () => {
  const { manager, calls } = await harness(() => [{ uid: "a", name: "A" }]);
  await manager.load(params);
  const original = manager.sceneCameras.a;
  calls.length = 0;
  manager.restclient.getCameras = async ({ page }) =>
    page === 1
      ? {
          statusCode: 200,
          content: { results: [{ uid: "new" }], next: "page2" },
        }
      : { statusCode: 503 };
  assert.deepEqual(
    plain(await manager.syncWithDatabase(params, {}, "app", true)),
    { added: [], removed: [] },
  );
  assert.equal(manager.sceneCameras.a, original);
  assert.equal(original.optics, undefined);
  assert.deepEqual(calls, []);
});

test("reconciliation normalizes legacy name keys without recreating saved cameras", async () => {
  const { manager, calls } = await harness(() => [
    { uid: "Front_Camera", name: "Front Camera" },
  ]);
  await manager.load(params);
  const camera = manager.sceneCameras.Front_Camera;
  manager.sceneCameras["Front Camera"] = camera;
  delete manager.sceneCameras.Front_Camera;
  camera.localEdit = [7, 8, 9];
  calls.length = 0;
  await manager.syncWithDatabase(params, {}, "app", true);
  assert.equal(manager.sceneCameras.Front_Camera, camera);
  assert.ok(!("Front Camera" in manager.sceneCameras));
  assert.deepEqual(camera.localEdit, [7, 8, 9]);
  assert.deepEqual(calls, []);
});

test("legacy camera names colliding with other UIDs are rekeyed without losing objects", async () => {
  const { manager } = await harness(() => [{ uid: "a" }, { uid: "b" }]);
  await manager.load(params);
  const first = manager.sceneCameras.a;
  const second = manager.sceneCameras.b;
  delete manager.sceneCameras.a;
  manager.sceneCameras.b = first;
  manager.sceneCameras.legacy = second;
  await manager.syncWithDatabase(params, {}, "app", true);
  assert.equal(manager.sceneCameras.a, first);
  assert.equal(manager.sceneCameras.b, second);
  assert.ok(!manager.sceneCameras.legacy);
});

test("superseded camera responses cannot resurrect or remove cameras", async () => {
  const { manager, calls } = await harness(() => [{ uid: "old", name: "Old" }]);
  await manager.load(params);
  const pending = [];
  manager.restclient.getCameras = () =>
    new Promise((resolve) => pending.push(resolve));
  calls.length = 0;
  const oldRequest = manager.syncWithDatabase(params, {}, "app", true);
  const newRequest = manager.syncWithDatabase(params, {}, "app", true);
  pending[1]({
    statusCode: 200,
    content: { results: [{ uid: "new", name: "New" }] },
  });

  await newRequest;
  const appliedCalls = calls.length;
  pending[0]({
    statusCode: 200,
    content: { results: [{ uid: "old", name: "Old" }] },
  });
  assert.deepEqual(plain(await oldRequest), { added: [], removed: [] });
  assert.deepEqual(
    Object.keys(manager.sceneCameras).filter((uid) => uid !== "undefined"),
    ["new"],
  );
  assert.equal(calls.length, appliedCalls);
});

test("a superseded multi-page response cannot overwrite a newer complete snapshot", async () => {
  const { manager } = await harness(() => []);
  let releaseOldPage;
  const oldPage = new Promise((resolve) => {
    releaseOldPage = resolve;
  });
  let requests = 0;
  manager.restclient.getCameras = async ({ page }) => {
    requests += 1;
    if (requests === 1)
      return {
        statusCode: 200,
        content: { results: [{ uid: "old" }], next: "page2" },
      };
    if (page === 2) return oldPage;
    return {
      statusCode: 200,
      content: { results: [{ uid: "new" }], next: null },
    };
  };
  const older = manager.syncWithDatabase(params, {}, "app", true);
  await new Promise((resolve) => setImmediate(resolve));
  await manager.syncWithDatabase(params, {}, "app", true);
  releaseOldPage({
    statusCode: 200,
    content: { results: [{ uid: "old2" }], next: null },
  });
  assert.deepEqual(plain(await older), { added: [], removed: [] });
  assert.equal(manager.sceneCameras.new.cameraUID, "new");
  assert.ok(!manager.sceneCameras.old);
  assert.ok(!manager.sceneCameras.old2);
});

test("a failed latest listing does not allow an older snapshot to apply", async () => {
  const { manager, calls } = await harness(() => [{ uid: "a", name: "A" }]);
  await manager.load(params);
  const pending = [];
  manager.restclient.getCameras = () =>
    new Promise((resolve) => pending.push(resolve));
  calls.length = 0;
  const first = manager.syncWithDatabase(params, {}, "app", false);
  const latest = manager.syncWithDatabase(params, {}, "app", false);
  pending[1]({ statusCode: 500 });
  await latest;
  pending[0]({ statusCode: 200, content: { results: [] } });
  await first;
  assert.ok("a" in manager.sceneCameras);
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
  const pendingTextures = [];
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
      matFromArray: (rows, cols, type, data64F) => ({ data64F, delete() {} }),
    },
  });
  const entry = new vm.SourceTextModule(source, { context });
  await entry.link(async (specifier) => {
    let exports;
    if (specifier.includes("three.module")) {
      exports = {
        Object3D: class {},
        TextureLoader: class {
          load(url, callback) {
            pendingTextures.push(callback);
          }
        },
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
        DEFAULT_CAMERA_UID: undefined,
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
    pendingTextures,
    cameraUID: "mobile",
    name: "mobile",
    resolution: { w: 640, h: 480 },
    hasAuthoritativeResolution: false,
    databaseOptics: {},
    intrinsics: { fx: 900, fy: 1000, cx: 800, cy: 500 },
    cameraMatrix: {
      data64F: [900, 0, 800, 0, 1000, 500, 0, 0, 1],
      delete() {},
    },
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

test("FOV calibration rebuilds pixel intrinsics for resolution-only and same-FOV updates", async () => {
  for (const includeIntrinsics of [false, true]) {
    const camera = await sceneCameraHarness();
    camera.updateOptics({ intrinsics: { fov: 70 }, resolution: [640, 480] });
    const focalLength = camera.cameraMatrix.data64F[0];
    const verticalFov = camera.sceneCamera.fov;
    camera.updateOptics({
      resolution: [1280, 960],
      ...(includeIntrinsics ? { intrinsics: { fov: 70 } } : {}),
    });
    assert.ok(
      Math.abs(camera.cameraMatrix.data64F[0] - 2 * focalLength) < 1e-10,
    );
    assert.equal(camera.cameraMatrix.data64F[2], 640);
    assert.equal(camera.cameraMatrix.data64F[5], 480);
    assert.ok(Math.abs(camera.sceneCamera.fov - verticalFov) < 1e-10);
    camera.updateOptics({ resolution: [0, 960] });
    assert.equal(camera.cameraMatrix.data64F[2], 640);
  }
});

test("resolution-only updates retain explicit pixel intrinsics", async () => {
  const camera = await sceneCameraHarness();
  const matrix = camera.cameraMatrix;
  camera.updateOptics({ resolution: [1920, 1080] });
  assert.equal(camera.cameraMatrix, matrix);
  assert.deepEqual(plain(camera.sceneCamera.offset), { x: 160, y: 40 });
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
  let disposed = 0;
  camera.socket = {
    removeAllListeners() {
      removed += 1;
    },
    disconnect() {
      disconnected += 1;
    },
  };
  camera.scene = { remove() {} };
  camera.transformControl = {
    detach() {},
    dispose() {
      disposed += 1;
    },
  };
  camera.getTransformControlObject3D = () => ({});
  camera.currentCameras = { mobile: camera, undefined: [] };
  camera.controlsFolder = { destroy() {} };
  camera.detach();
  camera.detach();
  assert.equal(client.listenerCount("message"), 1);
  assert.equal(client.listeners("message")[0], unrelated);
  assert.equal(disconnected, 1);
  assert.equal(removed, 1);
  assert.equal(camera.controlsFolder, null);
  assert.equal(camera.transformControl, null);
  assert.equal(disposed, 1);
  assert.ok(!("mobile" in camera.currentCameras));
});

test("saving and renaming a camera keeps UID keys and removes only its own draft", async () => {
  const camera = await sceneCameraHarness();
  camera.name = "Front Camera";
  camera.sceneCamera = null;
  camera.toast = { showToast() {} };
  const otherDraft = { name: "Front Camera" };
  camera.currentCameras = { undefined: [otherDraft, camera] };
  camera.restclient = {
    createCamera: async () => ({
      statusCode: 201,
      content: { uid: "Front_Camera" },
    }),
  };
  await camera.createNewCamera({}, null);
  assert.equal(camera.currentCameras.Front_Camera, camera);
  assert.deepEqual(camera.currentCameras.undefined, [otherDraft]);
  assert.ok(!("Front Camera" in camera.currentCameras));
  camera.controlsFolder = { title() {}, $title: { setAttribute() {} } };
  camera.addStatusIndicator = () => {};
  camera.isUpdatedInDB = true;
  camera.name = "Renamed Camera";
  camera.updateCameras("Front Camera", "Renamed Camera", null);
  assert.equal(camera.currentCameras.Front_Camera, camera);
  assert.ok(!("Renamed Camera" in camera.currentCameras));
});

test("a POST response detaches a wrapper created by an earlier database notice", async () => {
  const camera = await sceneCameraHarness();
  camera.sceneCamera = null;
  camera.toast = { showToast() {} };
  camera.currentCameras = { undefined: [camera] };
  let respond;
  camera.restclient = {
    createCamera: () =>
      new Promise((resolve) => {
        respond = resolve;
      }),
  };
  const saving = camera.createNewCamera({}, null);
  let detached = 0;
  const synchronized = {
    detach() {
      detached++;
      delete camera.currentCameras.mobile;
    },
  };
  camera.currentCameras.mobile = synchronized;
  respond({ statusCode: 201, content: { uid: "mobile" } });
  await saving;
  assert.equal(detached, 1);
  assert.equal(camera.currentCameras.mobile, camera);
  assert.deepEqual(camera.currentCameras.undefined, []);
});

test("detach disposes camera-owned GPU and WASM resources exactly once", async () => {
  const camera = await sceneCameraHarness();
  const counts = {};
  const resource = (name) => ({
    dispose() {
      counts[name] = (counts[name] || 0) + 1;
    },
  });
  const texture = { ...resource("texture"), isTexture: true };
  const material = {
    ...resource("material"),
    texture,
    uniforms: { map: { value: texture } },
  };
  const geometry = resource("geometry");
  camera.mesh = {
    traverse(callback) {
      callback({ geometry, material: [material, material] });
    },
  };
  camera.cameraCapture = { texture };
  camera.sceneCameraHelper = resource("helper");
  camera.sceneMesh = { geometry: resource("shared") };
  for (const key of ["cameraMatrix", "distCoeffs", "imagePoints"])
    camera[key] = {
      delete() {
        counts[key] = (counts[key] || 0) + 1;
      },
    };
  camera.scene = { remove() {} };
  camera.currentCameras = { mobile: camera, undefined: [] };
  camera.detach();
  camera.detach();
  assert.deepEqual(counts, {
    texture: 1,
    material: 1,
    geometry: 1,
    helper: 1,
    cameraMatrix: 1,
    distCoeffs: 1,
    imagePoints: 1,
  });
});

test("optics replacement releases superseded OpenCV matrices", async () => {
  const camera = await sceneCameraHarness();
  let deleted = 0;
  camera.cameraMatrix.delete = () => {
    deleted++;
  };
  camera.distCoeffs = {
    delete() {
      deleted++;
    },
  };
  camera.updateIntrinsics({ fx: 1000, fy: 1100, cx: 800, cy: 500 });
  camera.updateDistortion({ k1: 0.1 });
  assert.equal(deleted, 2);
});

test("a late frame texture is released rather than recreating a detached projection", async () => {
  const camera = await sceneCameraHarness();
  camera.projectFrame = true;
  camera.projectCameraCapture("frame", {}, false);
  assert.equal(camera.pendingTextures.length, 1);
  camera.scene = { remove() {} };
  camera.currentCameras = { mobile: camera, undefined: [] };
  camera.detach();
  let disposed = 0;
  camera.pendingTextures[0]({
    dispose() {
      disposed++;
    },
  });
  assert.equal(disposed, 1);
  assert.equal(camera.mesh, null);
});

async function calibrationHarness() {
  const values = {
    "#id_width": 1920,
    "#id_height": 1440,
    "#id_intrinsics_cx": 950,
    "#id_intrinsics_cy": 710,
  };
  const handlers = {};
  const submitted = [];
  const context = vm.createContext({
    console,
    document: { getElementById: () => ({}) },
    $: (selector) => ({
      0: {
        submit() {
          submitted.push({ ...values });
        },
      },
      on(event, handler) {
        handlers[event] = handler;
      },
      val(value) {
        if (value !== undefined) values[selector] = value;
        return values[selector];
      },
    }),
  });
  const source = await readFile(new URL("cameracalibrate.js", STATIC), "utf8");
  const module = new vm.SourceTextModule(source, { context });
  await module.link(async (specifier) => {
    const names = specifier.includes("constants")
      ? [
          "APP_NAME",
          "CALIBRATION_MIN_POINTS_FOR_FIT",
          "CALIBRATION_OUTLIER_THRESHOLD_PX",
          "CMD_CAMERA",
          "INITIAL_PROJECTION_OPACITY",
          "MAX_COPLANAR_DETERMINANT",
          "MAX_INTRINSICS_UPDATE_WAIT_TIME",
          "FX",
          "FY",
          "CX",
          "CY",
          "K1",
          "K2",
          "P1",
          "P2",
          "K3",
          "REST_URL",
        ]
      : specifier.includes("utils")
        ? ["compareIntrinsics", "resizeRendererToDisplaySize", "waitUntil"]
        : specifier.includes("camcanvas")
          ? ["CamCanvas"]
          : specifier.includes("viewport")
            ? ["Viewport"]
            : specifier.includes("GLTFLoader")
              ? ["GLTFLoader"]
              : [];
    return new vm.SyntheticModule(
      names,
      function () {
        for (const name of names) this.setExport(name, class {});
      },
      { context },
    );
  });
  await module.evaluate();
  const calibration = Object.create(
    module.namespace.ConvergedCameraCalibration.prototype,
  );
  calibration.camCanvas = {
    getImageSize: () => [320, 240],
    updateImageSrc(image, onLoad) {
      onLoad();
    },
    getCalibrationPoints: () => ({ p0: [160, 120] }),
  };
  calibration.viewport = { calibrationUpdated: false };
  calibration.calibrationFitState = "idle";
  calibration.projections = [];
  calibration.projectImage = (image, matrix) =>
    calibration.projections.push(plain(matrix));
  calibration.undistortAndProjectImage = calibration.projectImage;
  return { calibration, values, handlers, submitted };
}

test("calibration JPEGs preserve sensor dimensions and off-center intrinsics", async () => {
  const { calibration, values } = await calibrationHarness();
  const matrix = [
    [1200, 0, 950],
    [0, 1200, 710],
    [0, 0, 1],
  ];
  calibration.updateCalibrationViews("jpeg", matrix, [0, 0, 0, 0, 0]);
  assert.equal(values["#id_width"], 1920);
  assert.equal(values["#id_height"], 1440);
  assert.equal(values["#id_intrinsics_cx"], 950);
  assert.equal(values["#id_intrinsics_cy"], 710);
  assert.deepEqual(matrix, [
    [1200, 0, 950],
    [0, 1200, 710],
    [0, 0, 1],
  ]);
  const expected = [
    [200, 0, 950 / 6],
    [0, 200, 710 / 6],
    [0, 0, 1],
  ];
  calibration.projections[0]
    .flat()
    .forEach((value, index) =>
      assert.ok(Math.abs(value - expected.flat()[index]) < 1e-10),
    );
  assert.deepEqual(plain(calibration.getSensorCalibrationPoints()), {
    p0: [960, 720],
  });
  assert.equal(calibration.resolutionNeedsRefit, undefined);
});

test("saving after a JPEG preview preserves the registered sensor fields", async () => {
  const { calibration, handlers, submitted } = await calibrationHarness();
  calibration.camCanvas.getCalibrationPoints = () => ({});
  calibration.viewport.getCalibrationPoints = () => ({});
  calibration.updateCalibrationViews(
    "jpeg",
    [
      [1200, 0, 950],
      [0, 1200, 710],
      [0, 0, 1],
    ],
    [0, 0, 0, 0, 0],
  );
  calibration.setupSaveCameraButton();
  handlers.submit({ preventDefault() {} });
  assert.equal(submitted.length, 1);
  assert.equal(submitted[0]["#id_width"], 1920);
  assert.equal(submitted[0]["#id_height"], 1440);
  assert.equal(submitted[0]["#id_intrinsics_cx"], 950);
});

test("calibration accepts explicit sensor metadata but rejects invalid dimensions", async () => {
  const { calibration, values } = await calibrationHarness();
  calibration.updateSensorResolution({ width: 1280, height: 960 });
  assert.equal(values["#id_width"], 1280);
  assert.equal(values["#id_height"], 960);
  assert.equal(calibration.resolutionNeedsRefit, true);
  calibration.updateSensorResolution([0, 240]);
  assert.equal(values["#id_width"], 1280);
  assert.equal(values["#id_intrinsics_cx"], 950);
  const points = [];
  calibration.camCanvas.addCalibrationPoint = (...point) => points.push(point);
  calibration.addSensorCalibrationPoint(640, 480);
  assert.deepEqual(points, [[160, 120]]);
});

test("calibration canvas rescales existing point coordinates when preview dimensions change", async () => {
  const context = vm.createContext({});
  const module = new vm.SourceTextModule(
    await readFile(new URL("camcanvas.js", STATIC), "utf8"),
    { context },
  );
  await module.link(async () => {
    const names = [
      "CALIBRATION_BACKGROUND_COLOR",
      "CALIBRATION_DIAGNOSTIC_OUTLINE_COLOR",
      "CALIBRATION_DIAGNOSTIC_RING_COLOR",
      "CALIBRATION_POINT_COLORS",
      "CALIBRATION_POINT_SCALE",
      "CAMERA_SCALE_FACTOR",
      "MAX_CALIBRATION_POINTS",
    ];
    return new vm.SyntheticModule(
      names,
      function () {
        for (const name of names) this.setExport(name, 1);
      },
      { context },
    );
  });
  await module.evaluate();
  const canvas = Object.create(module.namespace.CamCanvas.prototype);
  Object.assign(canvas, {
    image: { width: 320, height: 240 },
    canvas: { clientWidth: 320 },
    scale: 1,
    calibrationPoints: [{ x: 160, y: 120 }],
    drawImage() {},
  });
  canvas.handleImageLoad();
  canvas.image.width = 640;
  canvas.image.height = 480;
  canvas.handleImageLoad();
  assert.deepEqual(canvas.calibrationPoints, [{ x: 320, y: 240 }]);
  canvas.handleImageLoad();
  assert.deepEqual(canvas.calibrationPoints, [{ x: 320, y: 240 }]);
  let observed;
  canvas.updateImageSrc("next", () => {
    observed = canvas.getImageSize();
  });
  canvas.image.width = 320;
  canvas.image.height = 240;
  canvas.image.onload();
  assert.deepEqual(plain(observed), [320, 240]);
  assert.deepEqual(canvas.calibrationPoints, [{ x: 160, y: 120 }]);
});

test("calibration projection preserves unequal focal lengths and principal-point offset", async () => {
  const context = vm.createContext({});
  const module = new vm.SourceTextModule(
    await readFile(new URL("viewport.js", STATIC), "utf8"),
    { context },
  );
  await module.link(async (specifier) => {
    const exports = specifier.includes("three.module")
      ? {
          Scene: class {},
          Vector3: class {},
          MathUtils: { radToDeg: (value) => (value * 180) / Math.PI },
        }
      : specifier.includes("constants")
        ? Object.fromEntries(
            [
              "CALIBRATION_POINT_COLORS",
              "CALIBRATION_SCALE_FACTOR",
              "CALIBRATION_TEXT_SIZE",
              "CAMERA_FOV",
              "CAMERA_ASPECT",
              "CAMERA_NEAR",
              "CAMERA_FAR",
              "MAX_CALIBRATION_POINTS",
              "SCENE_MAX_TEXTURE_SIZE",
              "SPHERE_RADIUS",
              "REST_URL",
            ].map((name) => [name, 1]),
          )
        : specifier.includes("OrbitControls")
          ? { OrbitControls: class {} }
          : specifier.includes("draw.js")
            ? { Draw: class {} }
            : specifier.includes("interactions")
              ? { isMeshToProjectOn() {} }
              : { default: class {} };
    return new vm.SyntheticModule(
      Object.keys(exports),
      function () {
        for (const [name, value] of Object.entries(exports))
          this.setExport(name, value);
      },
      { context },
    );
  });
  await module.evaluate();
  const viewport = Object.create(module.namespace.Viewport.prototype);
  const offsets = [];
  viewport.sceneMesh = {};
  viewport.textureLoader = {
    load(image, callback) {
      callback({ image: { width: 320, height: 240 } });
    },
  };
  viewport.projectionCamera = {
    setViewOffset(...args) {
      offsets.push(args);
    },
    updateProjectionMatrix() {},
  };
  viewport.projectedMaterial = { project() {} };
  viewport.setProjectionVisibility = () => {};
  viewport.projectImage("jpeg", [
    [200, 0, 150],
    [0, 220, 110],
    [0, 0, 1],
  ]);
  assert.deepEqual(offsets, [[320, 240, 10, 10, 320, 240]]);
  assert.equal(viewport.projectionCamera.aspect, (320 * 220) / (240 * 200));
});

async function regionHarness() {
  const context = vm.createContext({ console });
  const modules = new Map();
  const linker = async (specifier) => {
    if (modules.has(specifier)) return modules.get(specifier);
    let module;
    if (
      specifier.endsWith("/sceneregion.js") ||
      specifier.endsWith("/thingcontrols.js")
    ) {
      module = new vm.SourceTextModule(
        await readFile(
          new URL(specifier.replace("/static/js/", ""), STATIC),
          "utf8",
        ),
        { context },
      );
    } else {
      const exports = specifier.includes("three.module")
        ? {
            Object3D: class {
              constructor() {
                this.children = [];
              }
              add(child) {
                child.parent = this;
                this.children.push(child);
              }
              remove(child) {
                this.children = this.children.filter(
                  (value) => value !== child,
                );
              }
            },
          }
        : { default: () => ({}) };
      module = new vm.SyntheticModule(
        Object.keys(exports),
        function () {
          for (const [key, value] of Object.entries(exports))
            this.setExport(key, value);
        },
        { context },
      );
    }
    modules.set(specifier, module);
    return module;
  };
  const entry = await linker("/static/js/thing/sceneregion.js");
  await entry.link(linker);
  await entry.evaluate();
  const region = new entry.namespace.default({
    uid: "region",
    name: "Region",
    area: "poly",
  });
  const controls = modules.get("/static/js/thing/controls/thingcontrols.js");
  region.regionControls = new controls.namespace.default(region);
  const disposed = [];
  region.drawObj = {
    createThingLabel(name) {
      return { name: "thingLabel_" + name };
    },
    disposeThingLabel(label) {
      disposed.push(label);
    },
  };
  return { region, disposed };
}

test("region teardown removes labels even after rename and geometry rebuild", async () => {
  const { region, disposed } = await regionHarness();
  const initial = region.drawObj.createThingLabel("Original");
  region.add(initial);
  region.name = "Renamed";
  region.createGeometry = () => {
    region.points = [
      { x: 1, y: 2 },
      { x: 3, y: 4 },
    ];
  };
  region.regionControls.updateGeometry({ area: "poly" });
  assert.equal(disposed[0], initial);
  assert.equal(region.children.length, 1);
  const replacement = region.children[0];
  assert.equal(replacement.name, "thingLabel_Renamed");
  region.disposeResources();
  region.disposeResources();
  assert.deepEqual(disposed, [initial, replacement]);
  assert.equal(region.children.length, 0);
});

test("region teardown releases the initial DOM label and preserves unrelated children", async () => {
  const { region, disposed } = await regionHarness();
  const parent = {
    removeChild(child) {
      assert.equal(child, label.element);
    },
  };
  const label = { name: "thingLabel_Region", element: { parentNode: parent } };
  let removed = 0;
  parent.removeChild = () => {
    removed += 1;
    label.element.parentNode = null;
  };
  region.drawObj.disposeThingLabel = (child) => {
    disposed.push(child);
    child.element.parentNode.removeChild(child.element);
  };
  const unrelated = { name: "marker", geometry: { dispose() {} } };
  region.add(label);
  region.add(unrelated);
  region.disposeResources();
  region.disposeResources();
  assert.equal(removed, 1);
  assert.deepEqual(disposed, [label]);
  assert.deepEqual(region.children, [unrelated]);
});
