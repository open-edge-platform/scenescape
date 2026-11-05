// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

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
const frustumSource = await readFile(
  new URL("js/platformfrustums.js", staticURL),
  "utf8",
);
const {
  clearPlatformFrustums,
  frustumPoints,
  setPlatformFrustumsVisible,
  syncPlatformFrustums,
  validPlatformCamera,
} = await import(
  moduleURL(frustumSource.replace("/static/assets/three.module.js", threeURL))
);

function close(actual, expected, tolerance = 1e-6) {
  assert.equal(actual.length, expected.length);
  actual.forEach((value, index) =>
    assert.ok(
      Math.abs(value - expected[index]) < tolerance,
      `${actual} != ${expected}`,
    ),
  );
}

function camera(overrides = {}) {
  return {
    id: "front",
    mount: {
      translation: [1, 2, 3],
      rotation: [-0.5, 0.5, -0.5, 0.5],
    },
    intrinsics: { fx: 800, fy: 810, cx: 600, cy: 350 },
    ...overrides,
  };
}

test("frustumPoints uses optical axes with centered principal point", () => {
  const points = frustumPoints({
    intrinsics: { fx: 800, fy: 810, cx: 600, cy: 350 },
  });
  assert.equal(points.length, 24);
  for (const point of points) {
    const u = (point.x * 800) / point.z + 600;
    const v = (point.y * 810) / point.z + 350;
    assert.ok(Math.min(Math.abs(u), Math.abs(u - 1200)) < 0.001);
    assert.ok(Math.min(Math.abs(v), Math.abs(v - 700)) < 0.001);
    assert.ok(Math.abs(point.z - 0.2) < 1e-6 || point.z === 1);
  }
});

test("syncPlatformFrustums parents optical frustum under body mount", () => {
  const body = new THREE.Object3D();
  body.position.set(10, 20, 5);
  body.quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2);
  const cam = camera();
  assert.equal(syncPlatformFrustums(body, [cam]), 1);
  const frustum = body.children[0];
  assert.equal(frustum.name, "platform-camera-frustum");
  assert.equal(frustum.userData.camera_id, "front");
  close(frustum.position.toArray(), cam.mount.translation);
  close(frustum.quaternion.toArray(), cam.mount.rotation);
  body.updateMatrixWorld(true);
  close(frustum.getWorldPosition(new THREE.Vector3()).toArray(), [8, 21, 8]);
  const expectedRotation = new THREE.Quaternion()
    .copy(body.quaternion)
    .multiply(new THREE.Quaternion().fromArray(cam.mount.rotation));
  close(
    frustum.getWorldQuaternion(new THREE.Quaternion()).toArray(),
    expectedRotation.toArray(),
  );
});

test("sync updates reuse geometry and drop removed cameras", () => {
  const body = new THREE.Object3D();
  syncPlatformFrustums(body, [camera()]);
  const frustum = body.children[0];
  const geometry = frustum.geometry;
  const firstX = geometry.getAttribute("position").getX(0);
  syncPlatformFrustums(body, [
    camera({
      intrinsics: { fx: 400, fy: 405, cx: 600, cy: 350 },
    }),
  ]);
  assert.equal(body.children[0], frustum);
  assert.equal(frustum.geometry, geometry);
  assert.equal(geometry.getAttribute("position").getX(0), firstX * 2);
  syncPlatformFrustums(body, [camera({ id: "rear" })]);
  assert.equal(body.children.length, 1);
  assert.equal(body.children[0].userData.camera_id, "rear");
});

test("visibility toggle and clear dispose child frustums", () => {
  const body = new THREE.Object3D();
  syncPlatformFrustums(body, [camera(), camera({ id: "rear" })]);
  assert.equal(body.children.length, 2);
  setPlatformFrustumsVisible(body, false);
  assert.ok(body.children.every((child) => child.visible === false));
  const resources = new Set();
  body.traverse((object) => {
    if (object.geometry) resources.add(object.geometry);
    if (object.material) resources.add(object.material);
  });
  const disposed = new Map();
  resources.forEach((resource) =>
    resource.addEventListener("dispose", () => {
      disposed.set(resource, (disposed.get(resource) || 0) + 1);
    }),
  );
  clearPlatformFrustums(body);
  assert.equal(body.children.length, 0);
  assert.equal(disposed.size, resources.size);
  assert.ok([...disposed.values()].every((count) => count === 1));
});

test("invalid cameras are ignored without inventing mounts", () => {
  assert.equal(validPlatformCamera({ id: "bad" }), false);
  const body = new THREE.Object3D();
  assert.equal(
    syncPlatformFrustums(body, [
      { id: "bad", mount: { translation: [0, 0, 0], rotation: [0, 0, 0, 0] } },
      camera(),
    ]),
    1,
  );
  assert.equal(body.children.length, 1);
  assert.equal(body.children[0].userData.camera_id, "front");
});
