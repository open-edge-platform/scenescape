// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import { Object3D, Vector3 } from "three";
import {
  IDENTITY_POSE,
  PoseConversionError,
  applyScenePoseToObject,
  dropPoseToZ0,
  scenePoseFromObject,
  setObjectZUp,
  type SceneEulerPose,
} from "./poseThree";

function almostEqual(a: number, b: number, eps = 1e-6): void {
  expect(Math.abs(a - b)).toBeLessThan(eps);
}

function expectPose(
  actual: SceneEulerPose,
  expected: SceneEulerPose,
  eps = 1e-5,
): void {
  for (let i = 0; i < 3; i += 1) {
    almostEqual(actual.translation[i], expected.translation[i], eps);
    almostEqual(actual.rotation[i], expected.rotation[i], eps);
    almostEqual(actual.scale[i], expected.scale[i], eps);
  }
}

describe("poseThree", () => {
  it("roundtrips the identity pose", () => {
    const object = new Object3D();
    applyScenePoseToObject(object, IDENTITY_POSE);
    expectPose(scenePoseFromObject(object), IDENTITY_POSE);
  });

  it("roundtrips a +Z translation", () => {
    const object = new Object3D();
    const pose: SceneEulerPose = {
      translation: [0, 0, 2.5],
      rotation: [0, 0, 0],
      scale: [1, 1, 1],
    };
    applyScenePoseToObject(object, pose);
    expectPose(scenePoseFromObject(object), pose);
    const origin = new Vector3(0, 0, 0);
    origin.applyMatrix4(object.matrix);
    almostEqual(origin.z, 2.5);
  });

  it("roundtrips a yaw about Z", () => {
    const object = new Object3D();
    const pose: SceneEulerPose = {
      translation: [1, 2, 0],
      rotation: [0, 0, 90],
      scale: [1, 1, 1],
    };
    applyScenePoseToObject(object, pose);
    const recovered = scenePoseFromObject(object);
    almostEqual(recovered.translation[0], 1);
    almostEqual(recovered.translation[1], 2);
    almostEqual(recovered.rotation[2], 90, 1e-4);
    const xAxis = new Vector3(1, 0, 0);
    xAxis.applyMatrix4(object.matrix);
    almostEqual(xAxis.x, 1, 1e-5);
    almostEqual(xAxis.y, 3, 1e-5);
  });

  it("roundtrips combined translate rotate scale", () => {
    const object = new Object3D();
    const pose: SceneEulerPose = {
      translation: [3, -1, 0.5],
      rotation: [10, -20, 35],
      scale: [2, 2, 2],
    };
    applyScenePoseToObject(object, pose);
    const recovered = scenePoseFromObject(object);
    expectPose(recovered, pose, 1e-4);
  });

  it("rejects non-finite pose values", () => {
    const object = new Object3D();
    expect(() =>
      applyScenePoseToObject(object, {
        translation: [Number.NaN, 0, 0],
        rotation: [0, 0, 0],
        scale: [1, 1, 1],
      }),
    ).toThrow(PoseConversionError);
  });

  it("rejects zero scale", () => {
    const object = new Object3D();
    expect(() =>
      applyScenePoseToObject(object, {
        translation: [0, 0, 0],
        rotation: [0, 0, 0],
        scale: [0, 1, 1],
      }),
    ).toThrow(PoseConversionError);
  });

  it("drops translation z to zero", () => {
    const dropped = dropPoseToZ0({
      translation: [4, 5, 9],
      rotation: [1, 2, 3],
      scale: [1, 1, 1],
    });
    expect(dropped.translation[2]).toBe(0);
    expect(dropped.translation[0]).toBe(4);
  });

  it("sets object up to +Z", () => {
    const object = new Object3D();
    setObjectZUp(object);
    expect(object.up.z).toBe(1);
    expect(object.up.y).toBe(0);
  });
});
