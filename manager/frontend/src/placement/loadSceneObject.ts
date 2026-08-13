// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  DoubleSide,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Object3D,
  PlaneGeometry,
  SRGBColorSpace,
  TextureLoader,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import type { SceneGeometrySpec } from "./sceneGeometry";

function loadImageSize(
  url: string,
): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      resolve({ width: image.naturalWidth, height: image.naturalHeight });
    };
    image.onerror = () => {
      reject(new Error(`Failed to load scene map image: ${url}`));
    };
    image.src = url;
  });
}

function loadTexture(url: string) {
  const loader = new TextureLoader();
  loader.setCrossOrigin("anonymous");
  return loader.loadAsync(url);
}

async function loadMapPlane(
  spec: SceneGeometrySpec,
  color: number,
): Promise<Object3D> {
  if (!spec.mapUrl) {
    throw new Error("Scene has no map image");
  }
  const pixels = await loadImageSize(spec.mapUrl);
  const ppm = spec.scale && spec.scale > 0 ? spec.scale : 100;
  const widthM = pixels.width / ppm;
  const heightM = pixels.height / ppm;
  const texture = await loadTexture(spec.mapUrl);
  texture.colorSpace = SRGBColorSpace;
  const material = new MeshBasicMaterial({
    map: texture,
    side: DoubleSide,
    transparent: true,
    opacity: 0.92,
    color,
  });
  const mesh = new Mesh(new PlaneGeometry(widthM, heightM), material);
  mesh.position.set(widthM / 2, heightM / 2, 0);
  mesh.name = spec.name || "scene-map";
  const root = new Group();
  root.name = spec.id || spec.name || "scene";
  root.add(mesh);
  return root;
}

async function loadGlb(spec: SceneGeometrySpec): Promise<Object3D> {
  if (!spec.mapUrl) {
    throw new Error("Scene has no GLB map");
  }
  const loader = new GLTFLoader();
  const gltf = await loader.loadAsync(spec.mapUrl);
  const root = gltf.scene;
  root.name = spec.id || spec.name || "scene-glb";
  root.traverse((child) => {
    const mesh = child as Mesh;
    if (mesh.isMesh && mesh.material instanceof MeshStandardMaterial) {
      mesh.material.transparent = true;
      mesh.material.opacity = Math.min(mesh.material.opacity, 0.95);
    }
  });
  return root;
}

/** Load a scene map as a textured XY plane (Z-up floor) or a GLB mesh. */
export async function loadSceneObject(
  spec: SceneGeometrySpec,
  tint = 0xffffff,
): Promise<Object3D> {
  if (!spec.mapUrl) {
    throw new Error(`Scene ${spec.name || spec.id} has no map or mesh`);
  }
  if (spec.isGlb) {
    return loadGlb(spec);
  }
  return loadMapPlane(spec, tint);
}
