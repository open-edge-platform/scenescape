// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import { Group, Object3D, Vector3 } from "three";
import { attachSceneMeshPose } from "./loadSceneObject";
import {
  applyScenePoseToObject,
  scenePoseFromObject,
} from "./poseThree";
import type { SceneGeometrySpec } from "./sceneGeometry";
import { IDENTITY_POSE } from "./placementTypes";

function glbSpec(
  meshPose: SceneGeometrySpec["meshPose"],
): SceneGeometrySpec {
  return {
    id: "child",
    name: "Child",
    mapUrl: "/media/maps/child.glb",
    scale: 1,
    isGlb: true,
    meshPose,
  };
}

describe("attachSceneMeshPose", () => {
  it("orients a GLB with the scene mesh pose", () => {
    const raw = new Object3D();
    raw.position.set(0, 1, 0);
    const oriented = attachSceneMeshPose(
      raw,
      glbSpec({
        translation: [0, 0, 0],
        rotation: [90, 0, 0],
        scale: [1, 1, 1],
      }),
    );
    oriented.updateMatrixWorld(true);
    const world = new Vector3();
    raw.getWorldPosition(world);
    expect(Math.abs(world.x)).toBeLessThan(1e-6);
    expect(Math.abs(world.y)).toBeLessThan(1e-6);
    expect(Math.abs(world.z - 1)).toBeLessThan(1e-6);
  });

  it("does not bake mesh pose into the child-link Euler", () => {
    const childLink = new Group();
    childLink.add(
      attachSceneMeshPose(
        new Object3D(),
        glbSpec({
          translation: [4, 5, 1],
          rotation: [90, 0, 0],
          scale: [1, 1, 1],
        }),
      ),
    );
    applyScenePoseToObject(childLink, {
      translation: [10, 2, 0],
      rotation: [0, 0, 45],
      scale: [1, 1, 1],
    });
    const stored = scenePoseFromObject(childLink);
    expect(stored.translation[0]).toBeCloseTo(10, 5);
    expect(stored.translation[1]).toBeCloseTo(2, 5);
    expect(stored.rotation[2]).toBeCloseTo(45, 4);
    expect(stored.translation[2]).toBeCloseTo(0, 5);
  });

  it("leaves 2D map planes untransformed", () => {
    const plane = new Object3D();
    plane.position.set(1, 2, 0);
    const spec: SceneGeometrySpec = {
      id: "hall",
      name: "Hall",
      mapUrl: "/media/maps/hall.png",
      scale: 100,
      isGlb: false,
      meshPose: IDENTITY_POSE,
    };
    expect(attachSceneMeshPose(plane, spec)).toBe(plane);
    expect(plane.position.x).toBe(1);
    expect(plane.position.y).toBe(2);
  });
});
