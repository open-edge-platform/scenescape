// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Load the browser modules unchanged apart from resolving their absolute imports.
const staticURL = new URL(
  "../../../manager/src/manager/static/",
  import.meta.url,
);
const moduleURL = (source) =>
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const threeURL = moduleURL(
  await readFile(new URL("assets/three.module.js", staticURL), "utf8"),
);
const THREE = await import(threeURL);
class TestElement {
  constructor() {
    this.style = {};
    this.parentNode = null;
    this.children = [];
  }
  setAttribute() {}
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
  }
  removeChild(child) {
    this.children.splice(this.children.indexOf(child), 1);
    child.parentNode = null;
  }
  remove() {
    this.parentNode?.removeChild(this);
  }
}
globalThis.Element = TestElement;
globalThis.document = {
  createElement: () => new TestElement(),
  getElementById: () => ({ value: "test-token" }),
};
const css2DURL = moduleURL(
  (
    await readFile(
      new URL("examples/jsm/renderers/CSS2DRenderer.js", staticURL),
      "utf8",
    )
  ).replace("/static/assets/three.module.js", threeURL),
);
const rendererSource = await readFile(
  new URL("js/dynamicsources.js", staticURL),
  "utf8",
);
const { default: DynamicSources } = await import(
  moduleURL(
    rendererSource
      .replace("/static/assets/three.module.js", threeURL)
      .replace("/static/examples/jsm/renderers/CSS2DRenderer.js", css2DURL),
  )
);
const constantsURL = moduleURL(
  await readFile(new URL("js/constants.js", staticURL), "utf8"),
);
const sceneCameraURL = moduleURL(
  `import { Object3D } from "${threeURL}";
  export default class SceneCamera extends Object3D {
    onClick() {}
    unselect() {}
  }`,
);
const interactionsURL = moduleURL(
  (await readFile(new URL("js/interactions.js", staticURL), "utf8"))
    .replace("/static/assets/three.module.js", threeURL)
    .replace("/static/js/constants.js", constantsURL)
    .replace("/static/js/thing/scenecamera.js", sceneCameraURL),
);
const { SetupInteractions } = await import(interactionsURL);
const { default: SceneCamera } = await import(sceneCameraURL);
const restURL = moduleURL(`
  export default class RESTClient {
    getAssets() { return Promise.resolve({statusCode: 200, content: {results: []}}); }
  }
`);
const drawURL = moduleURL(`
  import * as THREE from "${threeURL}";
  export function createLabelRenderer() { return {render() {}, setSize() {}}; }
  export function updateLabelFields() {}
  export function createMarkObject(object, cache) {
    const mark = new THREE.Object3D();
    const model = new THREE.Object3D();
    model.name = "model";
    model.add(cache.unknown.clone());
    mark.add(model);
    return mark;
  }
`);
const hoverURL = moduleURL(`
  export function SetupMarkHover() { return {getLabelMode: () => "hover"}; }
`);
const { default: AssetManager } = await import(
  moduleURL(
    (await readFile(new URL("js/assetmanager.js", staticURL), "utf8"))
      .replace("/static/assets/three.module.js", threeURL)
      .replace("/static/js/restclient.js", restURL)
      .replace("/static/js/constants.js", constantsURL)
      .replace("/static/js/draw.js", drawURL)
      .replace("/static/js/interactions.js", hoverURL),
  )
);
const NOW = Date.parse("2026-10-26T12:00:00Z");

function state(overrides = {}) {
  return {
    scene_id: "scene-1",
    source_id: "drone-1",
    timestamp: new Date(NOW).toISOString(),
    expires_at: new Date(NOW + 10000).toISOString(),
    translation: [10, 20, 5],
    rotation: new THREE.Quaternion()
      .setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2)
      .toArray(),
    cameras: [
      {
        id: "front",
        mount: {
          translation: [1, 2, 3],
          rotation: [-0.5, 0.5, -0.5, 0.5],
        },
        intrinsics: { fx: 800, fy: 810, cx: 600, cy: 350 },
      },
    ],
    ...overrides,
  };
}

function setup() {
  const scene = new THREE.Scene();
  return { scene, renderer: new DynamicSources(scene, "scene-1") };
}

function send(renderer, snapshot = state(), sourceID = snapshot.source_id) {
  renderer.handleMessage(sourceID, Buffer.from(JSON.stringify(snapshot)), NOW);
}

function close(actual, expected, tolerance = 1e-6) {
  assert.equal(actual.length, expected.length);
  actual.forEach((value, index) =>
    assert.ok(
      Math.abs(value - expected[index]) < tolerance,
      `${actual} != ${expected}`,
    ),
  );
}

test("body and optical frustum compose drone pose and mount exactly once", () => {
  const { scene, renderer } = setup();
  const snapshot = state();
  send(renderer, snapshot);
  const { body, cameras } = renderer.sources.get("drone-1");
  const frustum = cameras.get("front");
  assert.equal(body.userData.source_id, "drone-1");
  close(body.position.toArray(), snapshot.translation);
  close(body.quaternion.toArray(), snapshot.rotation);
  scene.updateMatrixWorld(true);
  close(frustum.getWorldPosition(new THREE.Vector3()).toArray(), [8, 21, 8]);
  const expectedRotation = new THREE.Quaternion()
    .fromArray(snapshot.rotation)
    .multiply(
      new THREE.Quaternion().fromArray(snapshot.cameras[0].mount.rotation),
    );
  close(
    frustum.getWorldQuaternion(new THREE.Quaternion()).toArray(),
    expectedRotation.toArray(),
  );
  const positions = frustum.geometry.getAttribute("position");
  assert.equal(positions.count, 24);
  for (let i = 0; i < positions.count; i++) {
    const point = new THREE.Vector3().fromBufferAttribute(positions, i);
    const u =
      (point.x * snapshot.cameras[0].intrinsics.fx) / point.z +
      snapshot.cameras[0].intrinsics.cx;
    const v =
      (point.y * snapshot.cameras[0].intrinsics.fy) / point.z +
      snapshot.cameras[0].intrinsics.cy;
    assert.ok(Math.min(Math.abs(u), Math.abs(u - 1200)) < 0.001);
    assert.ok(Math.min(Math.abs(v), Math.abs(v - 700)) < 0.001);
    assert.ok(Math.abs(point.z - 0.2) < 1e-6 || point.z === 1);
  }
  // These runtime-only objects do not instantiate stored SceneCamera controls.
  assert.equal(scene.children.length, 1);
  assert.equal(
    body.children.some((child) => child.isCamera),
    false,
  );
});

test("updates reuse marker and geometry; calibration changes update rays", () => {
  const { renderer } = setup();
  send(renderer);
  const entry = renderer.sources.get("drone-1");
  const geometry = entry.cameras.get("front").geometry;
  const firstX = geometry.getAttribute("position").getX(0);
  send(
    renderer,
    state({
      timestamp: new Date(NOW + 1000).toISOString(),
      translation: [30, 40, 50],
      cameras: [
        {
          ...state().cameras[0],
          intrinsics: { fx: 400, fy: 405, cx: 600, cy: 350 },
        },
      ],
    }),
  );
  assert.equal(renderer.sources.get("drone-1"), entry);
  assert.equal(entry.cameras.get("front").geometry, geometry);
  close(entry.body.position.toArray(), [30, 40, 50]);
  assert.equal(geometry.getAttribute("position").getX(0), firstX * 2);
  send(renderer);
  close(entry.body.position.toArray(), [30, 40, 50]);
});

test("visibility controls are independent; hidden sources still expire", () => {
  const { renderer } = setup();
  send(renderer);
  const { body, cameras } = renderer.sources.get("drone-1");
  const frustum = cameras.get("front");
  renderer.setFrustumsVisible(false);
  assert.equal(body.visible, true);
  assert.equal(frustum.visible, false);
  send(renderer);
  assert.equal(frustum.visible, false);
  renderer.setFrustumsVisible(true);
  assert.equal(frustum.visible, true);
  renderer.root.visible = false;
  renderer.expire(NOW + 9999);
  assert.equal(renderer.sources.size, 1);
  renderer.expire(NOW + 10000);
  assert.equal(renderer.sources.size, 0);
  assert.equal(renderer.root.children.length, 0);
  send(renderer);
  assert.equal(renderer.root.visible, false);
});

test("tombstones and reconnect cleanup dispose resources once and preserve static objects", () => {
  const { scene, renderer } = setup();
  const staticObject = new THREE.Object3D();
  scene.add(staticObject);
  send(renderer);
  send(renderer, state({ source_id: "drone-2" }));
  const resources = new Set();
  const entry = renderer.sources.get("drone-1");
  const labelContainer = new TestElement();
  labelContainer.appendChild(entry.label.element);
  entry.body.traverse((object) => {
    if (object.geometry) resources.add(object.geometry);
    if (object.material) resources.add(object.material);
  });
  const disposed = new Map();
  resources.forEach((resource) =>
    resource.addEventListener("dispose", () => {
      disposed.set(resource, (disposed.get(resource) || 0) + 1);
    }),
  );
  renderer.handleMessage("drone-1", Buffer.alloc(0), NOW);
  renderer.handleMessage("drone-1", Buffer.alloc(0), NOW);
  assert.equal(renderer.sources.size, 1);
  assert.equal(labelContainer.children.length, 0);
  assert.equal(disposed.size, resources.size);
  assert.ok([...disposed.values()].every((count) => count === 1));
  renderer.clear();
  renderer.clear();
  assert.equal(renderer.sources.size, 0);
  assert.equal(staticObject.parent, scene);
  send(renderer);
  assert.equal(renderer.sources.size, 1);
});

test("live drones keep distinct colors and selection restores each source color", () => {
  const { renderer } = setup();
  send(renderer);
  send(renderer, state({ source_id: "drone-2" }));
  const first = renderer.sources.get("drone-1");
  const second = renderer.sources.get("drone-2");
  const firstColor = first.body.children[0].material.color.getHex();
  const secondColor = second.body.children[0].material.color.getHex();

  assert.notEqual(firstColor, secondColor);
  assert.equal(first.cameras.get("front").material.color.getHex(), firstColor);
  assert.equal(
    second.cameras.get("front").material.color.getHex(),
    secondColor,
  );

  send(renderer, state({ timestamp: new Date(NOW + 1000).toISOString() }));
  assert.equal(first.body.children[0].material.color.getHex(), firstColor);

  renderer.select("drone-1");
  assert.equal(first.body.children[0].material.color.getHex(), 0xffff00);
  assert.equal(first.cameras.get("front").material.color.getHex(), 0xffff00);
  renderer.select(null);
  assert.equal(first.body.children[0].material.color.getHex(), firstColor);
  assert.equal(first.cameras.get("front").material.color.getHex(), firstColor);
  assert.equal(second.body.children[0].material.color.getHex(), secondColor);
});

test("sources without camera state render without an invented camera", () => {
  const { renderer } = setup();
  send(renderer);
  const snapshot = state();
  delete snapshot.cameras;
  send(renderer, snapshot);
  assert.equal(renderer.sources.get("drone-1").cameras.size, 0);
  renderer.setFrustumsVisible(true);
  assert.equal(
    renderer.sources.get("drone-1").label.element.textContent,
    "drone-1 - FOV unavailable",
  );
});

test("expired retained state never creates a marker", () => {
  const { renderer } = setup();
  send(renderer, state({ expires_at: new Date(NOW).toISOString() }));
  assert.equal(renderer.sources.size, 0);
});

test("invalid payloads and mismatched scenes or source IDs are logged and rejected", (context) => {
  const warning = context.mock.method(console, "warn", () => {});
  const { renderer } = setup();
  const invalid = [
    null,
    state({ scene_id: "other-scene" }),
    state({ source_id: "spoofed" }),
    state({ translation: [1, 2] }),
    state({ rotation: [0, 0, 0, 0] }),
    state({ expires_at: "not a timestamp" }),
    state({ timestamp: 100 }),
    state({ expires_at: new Date(NOW - 1).toISOString() }),
    state({
      cameras: [
        {
          ...state().cameras[0],
          mount: {},
        },
      ],
    }),
    state({ intrinsics: { fx: 0, fy: 810, cx: 600, cy: 350 } }),
  ];
  for (const snapshot of invalid) send(renderer, snapshot, "drone-1");
  renderer.handleMessage("drone-1", Buffer.from("{"), NOW);
  renderer.handleMessage("drone-1/extra", Buffer.from("{}"), NOW);
  assert.equal(renderer.sources.size, 0);
  assert.equal(warning.mock.callCount(), invalid.length + 2);
});

test("multiple cameras render independent mounted frustums", () => {
  const { scene, renderer } = setup();
  const snapshot = state({
    cameras: [
      ...state().cameras,
      {
        id: "rear",
        mount: {
          translation: [-1, 0, 0],
          rotation: [0, 0, 0, 1],
        },
        intrinsics: { fx: 400, fy: 405, cx: 320, cy: 240 },
      },
    ],
  });
  send(renderer, snapshot);
  const entry = renderer.sources.get("drone-1");
  assert.deepEqual([...entry.cameras.keys()], ["front", "rear"]);
  scene.updateMatrixWorld(true);
  close(
    entry.cameras.get("rear").getWorldPosition(new THREE.Vector3()).toArray(),
    [10, 19, 5],
  );
  assert.equal(
    entry.cameras.get("rear").geometry.getAttribute("position").count,
    24,
  );
});

test("pose-only snapshots move the existing drone and mounted frustum without objects", () => {
  const { scene, renderer } = setup();
  send(renderer);
  const entry = renderer.sources.get("drone-1");
  send(
    renderer,
    state({
      timestamp: new Date(NOW + 1000).toISOString(),
      translation: [30, 40, 50],
      rotation: [0, 0, 0, 1],
      objects: [],
    }),
  );
  assert.equal(renderer.sources.get("drone-1"), entry);
  scene.updateMatrixWorld(true);
  close(
    entry.cameras.get("front").getWorldPosition(new THREE.Vector3()).toArray(),
    [31, 42, 53],
  );
});

test("selection toggles, switches publishers, and clears on expiry, hide, or reconnect", () => {
  const { renderer } = setup();
  const selected = [];
  renderer.onSelect = (id) => selected.push(id);
  send(renderer);
  send(renderer, state({ source_id: "drone-2" }));
  const entry = renderer.sources.get("drone-1");
  const secondEntry = renderer.sources.get("drone-2");
  assert.equal(entry.label.visible, false);
  assert.equal(secondEntry.label.visible, false);
  close(entry.label.position.toArray(), [0, 0, 0]);
  close(entry.label.center.toArray(), [0.5, 1]);
  assert.equal(entry.label.element.style.marginTop, "-32px");
  const hit = [{ object: entry.body.children[0] }];
  assert.equal(renderer.selectFromIntersections(hit), true);
  assert.equal(renderer.selectedSource, "drone-1");
  assert.equal(entry.label.visible, true);
  assert.equal(secondEntry.label.visible, false);
  send(renderer, state({ translation: [11, 22, 6] }));
  assert.equal(entry.label.visible, true);
  assert.equal(secondEntry.label.visible, false);
  assert.equal(entry.body.children[0].material.color.getHex(), 0xffff00);
  renderer.selectFromIntersections(hit);
  assert.equal(renderer.selectedSource, null);
  assert.equal(entry.label.visible, false);
  send(renderer);
  assert.equal(entry.label.visible, false);
  assert.equal(entry.body.children[0].material.color.getHex(), entry.color);
  renderer.selectFromIntersections(hit);
  renderer.selectFromIntersections([
    { object: renderer.sources.get("drone-2").body.children[0] },
  ]);
  assert.equal(renderer.selectedSource, "drone-2");
  assert.equal(entry.label.visible, false);
  assert.equal(secondEntry.label.visible, true);
  assert.equal(entry.body.children[0].material.color.getHex(), entry.color);
  renderer.selectFromIntersections([]);
  assert.equal(renderer.selectedSource, null);
  assert.equal(secondEntry.label.visible, false);
  renderer.select("drone-1");
  renderer.setVisible(false);
  assert.equal(renderer.selectedSource, null);
  assert.equal(entry.label.visible, false);
  assert.equal(renderer.selectFromIntersections(hit), false);
  renderer.setVisible(true);
  assert.equal(entry.label.visible, false);
  // A camera's wireframe is not the drone body and cannot steal selection.
  assert.equal(
    renderer.selectFromIntersections([{ object: entry.cameras.get("front") }]),
    false,
  );
  renderer.select("drone-1");
  renderer.expire(NOW + 10000);
  assert.equal(renderer.selectedSource, null);
  send(renderer);
  renderer.select("drone-1");
  renderer.clear();
  assert.equal(renderer.selectedSource, null);
  assert.equal(selected.at(-1), null);
});

test("source selections highlight only attributed objects and follow live changes", async () => {
  const scene = new THREE.Scene();
  const manager = AssetManager(
    scene,
    () => {},
    new THREE.PerspectiveCamera(),
    {},
  );
  manager.loadAssets();
  await new Promise((resolve) => setImmediate(resolve));
  const renderer = new DynamicSources(scene, "scene-1", manager.selectSource);
  send(renderer);
  const object = (id, sourceID, translation = [1, 2, 3]) => ({
    id,
    source_id: sourceID,
    category: "unknown",
    translation,
    size: [2, 2, 2],
    rotation: [0, 0, 0, 1],
  });
  const highlights = () =>
    scene.children.filter((obj) => obj.name === "source-object-highlight");
  manager.plot({
    objects: [object("a", "drone-1"), object("b", "drone-2"), object("c")],
  });
  renderer.select("drone-1");
  assert.equal(highlights().length, 1);
  const highlight = highlights()[0];
  const originalMaterial = highlight.object.children[0].material;
  const originalColor = originalMaterial.color.getHex();
  const bounds = [...highlight.geometry.attributes.position.array];
  manager.plot({
    objects: [
      object("a", "drone-1", [5, 6, 7]),
      object("b", "drone-1"),
      object("c"),
    ],
  });
  assert.equal(highlights().length, 2);
  assert.notDeepEqual(
    [...highlight.geometry.attributes.position.array],
    bounds,
  );
  assert.equal(highlight.object.children[0].material, originalMaterial);
  assert.equal(originalMaterial.color.getHex(), originalColor);
  manager.setMarksVisibility(false);
  assert.ok(highlights().every((obj) => !obj.visible));
  manager.setMarksVisibility(true);
  assert.ok(highlights().every((obj) => obj.visible));
  let disposed = 0;
  highlight.geometry.addEventListener("dispose", () => disposed++);
  highlight.material.addEventListener("dispose", () => disposed++);
  manager.plot({
    objects: [object("a", "drone-2"), object("b", "drone-1"), object("c")],
  });
  assert.equal(disposed, 2);
  assert.equal(highlights().length, 1);
  // Removing provenance removes the previous attribution and its highlight.
  manager.plot({ objects: [object("a", "drone-2"), object("b"), object("c")] });
  assert.equal(highlights().length, 0);
  manager.plot({ objects: [object("a", "drone-1")] });
  const last = highlights()[0];
  let expiredResources = 0;
  last.geometry.addEventListener("dispose", () => expiredResources++);
  last.material.addEventListener("dispose", () => expiredResources++);
  renderer.expire(NOW + 10000);
  assert.equal(highlights().length, 0);
  assert.equal(expiredResources, 2);
  // Source removal does not remove observations managed by Analytics.
  assert.equal(last.object.parent.parent, scene);
});

test("removing a highlighted object disposes its highlight", async () => {
  const scene = new THREE.Scene();
  const manager = AssetManager(
    scene,
    () => {},
    new THREE.PerspectiveCamera(),
    {},
  );
  manager.loadAssets();
  await new Promise((resolve) => setImmediate(resolve));
  manager.selectSource("drone-1");
  manager.plot({
    objects: [
      {
        id: "a",
        source_id: "drone-1",
        category: "unknown",
        translation: [0, 0, 0],
        size: [1, 1, 1],
      },
    ],
  });
  const highlight = scene.getObjectByName("source-object-highlight");
  let disposed = 0;
  highlight.geometry.addEventListener("dispose", () => disposed++);
  highlight.material.addEventListener("dispose", () => disposed++);
  manager.plot({ objects: [] });
  assert.equal(disposed, 2);
  assert.equal(scene.getObjectByName("source-object-highlight"), undefined);
});

test("canvas clicks select a drone using the active view without camera calibration actions", async () => {
  const { scene, renderer } = setup();
  send(renderer);
  const listeners = new Map();
  const domElement = {
    clientWidth: 800,
    clientHeight: 600,
    getBoundingClientRect: () => ({
      left: 100,
      top: 50,
      width: 800,
      height: 600,
    }),
    addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: (name) => listeners.delete(name),
  };
  let activeCamera = new THREE.PerspectiveCamera();
  const orthographic = new THREE.OrthographicCamera();
  const entry = renderer.sources.get("drone-1");
  let hits = [{ object: entry.body.children[0] }];
  const raycaster = {
    setFromCamera: (mouse, camera) => {
      close([mouse.x, mouse.y], [0, 0]);
      assert.equal(camera, activeCamera);
    },
    intersectObjects: () => hits,
  };
  const interactions = SetupInteractions(
    scene,
    { domElement },
    raycaster,
    {},
    () => activeCamera,
    renderer,
  );
  const storedCamera = new SceneCamera();
  let unselected = 0;
  storedCamera.unselect = () => unselected++;
  interactions.setSelectedCamera(storedCamera);
  activeCamera = orthographic;
  const click = async () => {
    listeners.get("click")({ detail: 1, clientX: 500, clientY: 350 });
    await new Promise((resolve) => setTimeout(resolve, 230));
  };
  await click();
  assert.equal(renderer.selectedSource, "drone-1");
  assert.equal(unselected, 1);
  hits = [];
  await click();
  assert.equal(renderer.selectedSource, null);
  let staticClicks = 0;
  storedCamera.onClick = () => staticClicks++;
  const helper = new THREE.Object3D();
  helper.type = "CameraHelper";
  storedCamera.add(helper);
  hits = [{ object: helper }];
  await click();
  assert.equal(staticClicks, 1);
  assert.equal(renderer.selectedSource, null);
});

test("the same source in another scene has independent selection and lifetime", () => {
  const first = setup();
  const otherScene = new THREE.Scene();
  const other = new DynamicSources(otherScene, "scene-2");
  send(first.renderer);
  send(other, state({ scene_id: "scene-2" }));
  first.renderer.select("drone-1");
  assert.equal(other.selectedSource, null);
  first.renderer.expire(NOW + 10000);
  assert.equal(first.renderer.sources.size, 0);
  assert.equal(other.sources.size, 1);
  assert.equal(
    other.sources.get("drone-1").label.element.textContent,
    "drone-1",
  );
});

test("expiry removes labels and disposes every source GPU resource exactly once", () => {
  const { renderer } = setup();
  send(renderer);
  const entry = renderer.sources.get("drone-1");
  const parent = new TestElement();
  parent.appendChild(entry.label.element);
  const resources = new Set();
  entry.body.traverse((object) => {
    if (object.geometry) resources.add(object.geometry);
    if (object.material) resources.add(object.material);
  });
  const disposed = new Map();
  for (const resource of resources) {
    resource.addEventListener("dispose", () => {
      disposed.set(resource, (disposed.get(resource) || 0) + 1);
    });
  }
  renderer.expire(NOW + 10000);
  renderer.clear();
  assert.equal(parent.children.length, 0);
  assert.equal(renderer.root.children.length, 0);
  assert.equal(disposed.size, resources.size);
  assert.ok([...disposed.values()].every((count) => count === 1));
});
