// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * URL for the 2D scene map bitmap.
 * GLB/PLY maps use the generated ortho thumbnail; image maps use the file itself.
 */
export function sceneMapBitmapUrl(scene: {
  thumbnailUrl?: string | null;
  mapUrl?: string | null;
  thumbnail?: string | null;
  map?: string | null;
}): string | null {
  return (
    scene.thumbnailUrl ||
    scene.thumbnail ||
    scene.mapUrl ||
    scene.map ||
    null
  );
}
