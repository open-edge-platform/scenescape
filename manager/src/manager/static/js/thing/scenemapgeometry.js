// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Pure helpers for the flat base map plane in the 3D scene view. They use
// plain numbers and {min, max} bounds only, so they run without WebGL.

// Size and centre of the base map plane in metres. The SW corner of the plane
// sits at the frame origin (0, 0), so its centre is half of its size.
export function basePlaneLayout(imageWidth, imageHeight, baseScale) {
  const width = imageWidth / baseScale;
  const height = imageHeight / baseScale;
  return { width, height, centerX: width / 2, centerY: height / 2 };
}

// Smallest box containing both boxes. Each box is {min: {x, y, z}, max: {x, y, z}}.
export function unionBounds(a, b) {
  return {
    min: {
      x: Math.min(a.min.x, b.min.x),
      y: Math.min(a.min.y, b.min.y),
      z: Math.min(a.min.z, b.min.z),
    },
    max: {
      x: Math.max(a.max.x, b.max.x),
      y: Math.max(a.max.y, b.max.y),
      z: Math.max(a.max.z, b.max.z),
    },
  };
}

// Ground frame of a hybrid scene covering the GLB and the flat plane. The plane
// lies in the XY plane, so the frame width runs along X and the height along Y.
export function hybridFrameSize(glbBounds, planeBounds) {
  const union = unionBounds(glbBounds, planeBounds);
  const floorWidth = union.max.x - union.min.x;
  const floorHeight = union.max.y - union.min.y;
  return {
    floorWidth,
    floorHeight,
    minX: union.min.x,
    minY: union.min.y,
    centerX: union.min.x + floorWidth / 2,
    centerY: union.min.y + floorHeight / 2,
  };
}
