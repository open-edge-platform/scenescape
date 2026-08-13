// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Euler, Matrix4, Object3D, Quaternion, Vector3 } from "three";
import { IDENTITY_POSE, type SceneEulerPose } from "./placementTypes";

export type { SceneEulerPose };
export { IDENTITY_POSE };

const DEG = 180 / Math.PI;
const RAD = Math.PI / 180;
const EULER_ORDER = "XYZ";

export class PoseConversionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PoseConversionError";
  }
}

function finiteNumber(n: unknown, label: string): number {
  if (typeof n !== "number" || !Number.isFinite(n)) {
    throw new PoseConversionError(`${label} must be a finite number`);
  }
  return n;
}

export function assertFinitePose(pose: SceneEulerPose): SceneEulerPose {
  return {
    translation: [
      finiteNumber(pose.translation[0], "translation.x"),
      finiteNumber(pose.translation[1], "translation.y"),
      finiteNumber(pose.translation[2], "translation.z"),
    ],
    rotation: [
      finiteNumber(pose.rotation[0], "rotation.x"),
      finiteNumber(pose.rotation[1], "rotation.y"),
      finiteNumber(pose.rotation[2], "rotation.z"),
    ],
    scale: [
      finiteNumber(pose.scale[0], "scale.x"),
      finiteNumber(pose.scale[1], "scale.y"),
      finiteNumber(pose.scale[2], "scale.z"),
    ],
  };
}

export function applyScenePoseToObject(
  object: Object3D,
  pose: SceneEulerPose,
): void {
  const safe = assertFinitePose(pose);
  if (safe.scale.some((s) => Math.abs(s) < 1e-12)) {
    throw new PoseConversionError("Pose scale must be non-zero");
  }
  object.position.set(...safe.translation);
  object.rotation.order = EULER_ORDER;
  object.rotation.set(
    safe.rotation[0] * RAD,
    safe.rotation[1] * RAD,
    safe.rotation[2] * RAD,
    EULER_ORDER,
  );
  object.scale.set(...safe.scale);
  object.updateMatrix();
}

export function scenePoseFromObject(object: Object3D): SceneEulerPose {
  object.updateMatrix();
  const position = new Vector3();
  const quaternion = new Quaternion();
  const scale = new Vector3();
  const ok = object.matrix.decompose(position, quaternion, scale);
  if (!ok) {
    throw new PoseConversionError("Object matrix is not invertible");
  }
  if (
    !Number.isFinite(position.x) ||
    !Number.isFinite(quaternion.x) ||
    Math.abs(scale.x) < 1e-12 ||
    Math.abs(scale.y) < 1e-12 ||
    Math.abs(scale.z) < 1e-12
  ) {
    throw new PoseConversionError(
      "Decomposed pose is degenerate or non-finite",
    );
  }
  const euler = new Euler().setFromQuaternion(quaternion, EULER_ORDER);
  return {
    translation: [position.x, position.y, position.z],
    rotation: [euler.x * DEG, euler.y * DEG, euler.z * DEG],
    scale: [scale.x, scale.y, scale.z],
  };
}

export function scenePoseFromMatrix(matrix: Matrix4): SceneEulerPose {
  const object = new Object3D();
  object.matrix.copy(matrix);
  object.matrix.decompose(object.position, object.quaternion, object.scale);
  object.rotation.setFromQuaternion(object.quaternion, EULER_ORDER);
  return scenePoseFromObject(object);
}

export function dropPoseToZ0(pose: SceneEulerPose): SceneEulerPose {
  const safe = assertFinitePose(pose);
  return {
    ...safe,
    translation: [safe.translation[0], safe.translation[1], 0],
  };
}

export function setObjectZUp(object: Object3D): void {
  object.up.set(0, 0, 1);
}
