// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { AxesHelper, Box3, Group, Object3D, Vector3 } from "three";

const MIN_AXES_M = 1.5;
const MAX_AXES_M = 20;
const AXES_SPAN_FRACTION = 0.2;

/** Visible RGB axis length in meters from an object bounding-span. */
export function axesLengthFromSpan(span: number): number {
  if (!Number.isFinite(span) || span <= 0) {
    return MIN_AXES_M;
  }
  return Math.min(MAX_AXES_M, Math.max(MIN_AXES_M, span * AXES_SPAN_FRACTION));
}

export function spanOfObject(object: Object3D): number {
  const box = new Box3().setFromObject(object);
  const size = new Vector3();
  box.getSize(size);
  return Math.max(size.x, size.y, size.z, 0);
}

/** RGB = XYZ axes that draw on top of translucent maps. */
export function makePlacementAxes(size: number, name: string): AxesHelper {
  const axes = new AxesHelper(size);
  axes.name = name;
  axes.renderOrder = 20;
  const material = axes.material;
  if (!Array.isArray(material)) {
    material.depthTest = false;
    material.depthWrite = false;
  }
  return axes;
}

/**
 * Child axes live in a sibling group so they follow pose but not uniform
 * scale (keeps the triad readable when the child is scaled down).
 */
export function syncChildAxes(target: Group, child: Object3D): void {
  target.position.copy(child.position);
  target.quaternion.copy(child.quaternion);
}
