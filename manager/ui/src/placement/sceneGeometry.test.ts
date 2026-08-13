// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import {
  isGlbUrl,
  sceneGeometryFromRest,
  sceneHasPlaceableGeometry,
} from "./sceneGeometry";

describe("sceneGeometry", () => {
  it("parses a map image and pixels-per-meter scale", () => {
    const spec = sceneGeometryFromRest({
      uid: "abc",
      name: "Hall",
      map: "/media/maps/hall.png",
      scale: 100,
    });
    expect(spec.mapUrl).toBe("/media/maps/hall.png");
    expect(spec.scale).toBe(100);
    expect(spec.isGlb).toBe(false);
    expect(sceneHasPlaceableGeometry(spec)).toBe(true);
  });

  it("detects GLB maps", () => {
    expect(isGlbUrl("/media/maps/campus.glb")).toBe(true);
    expect(isGlbUrl("/media/maps/campus.glb?v=2")).toBe(true);
    expect(isGlbUrl("/media/maps/floor.png")).toBe(false);
    const spec = sceneGeometryFromRest({
      id: "1",
      map: "/media/maps/campus.glb",
      scale: 1,
    });
    expect(spec.isGlb).toBe(true);
  });

  it("treats a missing map as not placeable", () => {
    const spec = sceneGeometryFromRest({ uid: "x", name: "Empty" });
    expect(sceneHasPlaceableGeometry(spec)).toBe(false);
  });
});
