// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import { Group, Vector3 } from "three";
import {
  axesLengthFromSpan,
  makePlacementAxes,
  syncChildAxes,
} from "./placementAxes";

describe("placementAxes", () => {
  it("clamps tiny and huge spans to a readable triad", () => {
    expect(axesLengthFromSpan(0)).toBe(1.5);
    expect(axesLengthFromSpan(-4)).toBe(1.5);
    expect(axesLengthFromSpan(4)).toBe(1.5);
    expect(axesLengthFromSpan(20)).toBe(4);
    expect(axesLengthFromSpan(200)).toBe(20);
  });

  it("builds an RGB helper that ignores depth", () => {
    const axes = makePlacementAxes(3, "parent-axes");
    expect(axes.name).toBe("parent-axes");
    const material = axes.material;
    expect(Array.isArray(material)).toBe(false);
    if (!Array.isArray(material)) {
      expect(material.depthTest).toBe(false);
    }
  });

  it("copies child pose without inheriting scale", () => {
    const child = new Group();
    child.position.set(2, 3, 0.5);
    child.scale.set(0.25, 0.25, 0.25);
    const axesRoot = new Group();
    syncChildAxes(axesRoot, child);
    expect(axesRoot.position).toEqual(new Vector3(2, 3, 0.5));
    expect(axesRoot.scale).toEqual(new Vector3(1, 1, 1));
  });
});
