// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import {
  SNAPSHOT_SIZE_PX,
  scaleFromView,
  snapshotCornersLla,
} from "./geospatialSnapshot";

describe("geospatialSnapshot", () => {
  it("emits SW, SE, NE, NW for a north-up snapshot", () => {
    const [sw, se, ne, nw] = snapshotCornersLla(37.4, -121.96, 17, 0);
    expect(sw[0]).toBeLessThan(ne[0]);
    expect(sw[1]).toBeLessThan(ne[1]);
    expect(se[0]).toBeCloseTo(sw[0], 8);
    expect(se[1]).toBeCloseTo(ne[1], 8);
    expect(nw[0]).toBeCloseTo(ne[0], 8);
    expect(nw[1]).toBeCloseTo(sw[1], 8);
  });

  it("covers a mercator square matching the 1280 snapshot", () => {
    const lat = 37.4;
    const zoom = 17;
    const [sw, se, ne] = snapshotCornersLla(lat, -121.96, zoom, 0);
    const ppm = scaleFromView(lat, zoom);
    const widthM =
      ((se[1] - sw[1]) * 40075016.686) /
      360 *
      Math.cos((lat * Math.PI) / 180);
    const heightPx = SNAPSHOT_SIZE_PX;
    expect(widthM * ppm).toBeCloseTo(heightPx, 0);
    expect(ne[0]).toBeGreaterThan(sw[0]);
  });
});
