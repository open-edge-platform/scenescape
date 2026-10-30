// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export async function addSceneMaps(zip, scene) {
  if (!scene.map) {
    throw new Error(`Missing map for scene ${scene.name}`);
  }
  const response = await globalThis.fetch(scene.map);
  if (!response.ok) {
    throw new Error(`Failed to fetch map for scene ${scene.name}`);
  }
  const extension = new globalThis.URL(
    scene.map,
    globalThis.window.location.origin,
  ).pathname
    .split(".")
    .pop();
  scene.map_file = `${scene.uid}.${extension}`;
  zip.file(scene.map_file, await response.blob());
  for (const child of scene.children || []) {
    await addSceneMaps(zip, child);
  }
}
