// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef } from "react";
import {
  AmbientLight,
  AxesHelper,
  Box3,
  Color,
  DirectionalLight,
  GridHelper,
  Group,
  PerspectiveCamera,
  Scene,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import {
  applyScenePoseToObject,
  scenePoseFromObject,
  setObjectZUp,
  type SceneEulerPose,
} from "./poseThree";
import { loadSceneObject } from "./loadSceneObject";
import type { SceneGeometrySpec } from "./sceneGeometry";
import type { PlacementGizmoMode } from "./placementTypes";

type Props = {
  parentSpec: SceneGeometrySpec;
  childSpec: SceneGeometrySpec;
  pose: SceneEulerPose;
  /** Increment to push `pose` onto the child Object3D (reset / drop). */
  poseTick: number;
  mode: PlacementGizmoMode;
  onPoseChange: (pose: SceneEulerPose) => void;
};

function fitCamera(
  camera: PerspectiveCamera,
  controls: OrbitControls,
  objects: Group[],
): void {
  const box = new Box3();
  objects.forEach((obj) => box.expandByObject(obj));
  const size = new Vector3();
  const center = new Vector3();
  box.getSize(size);
  box.getCenter(center);
  const span = Math.max(size.x, size.y, size.z, 4);
  camera.position.set(center.x, center.y - span * 1.4, center.z + span * 1.1);
  camera.lookAt(center);
  controls.target.copy(center);
  controls.update();
}

/**
 * Z-up placement canvas: parent geometry is world, child is a posed Object3D
 * with TransformControls. Framework-light so the future 3D viewport can remount it.
 */
export function ChildPlacementCanvas({
  parentSpec,
  childSpec,
  pose,
  poseTick,
  mode,
  onPoseChange,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const poseRef = useRef(pose);
  poseRef.current = pose;
  const onPoseChangeRef = useRef(onPoseChange);
  onPoseChangeRef.current = onPoseChange;
  const childRef = useRef<Group | null>(null);
  const controlsRef = useRef<TransformControls | null>(null);
  const applyingRef = useRef(false);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) {
      return;
    }
    let disposed = false;
    let renderer: WebGLRenderer | null = null;
    let orbit: OrbitControls | null = null;
    let gizmo: TransformControls | null = null;
    let frame = 0;

    const scene = new Scene();
    scene.background = new Color(0x1b1f23);
    const camera = new PerspectiveCamera(
      50,
      Math.max(host.clientWidth, 1) / Math.max(host.clientHeight, 1),
      0.1,
      5000,
    );
    setObjectZUp(camera);

    try {
      renderer = new WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      host.replaceChildren();
      const note = document.createElement("p");
      note.className = "ss-placement-error";
      note.textContent = "WebGL is not available in this browser.";
      host.appendChild(note);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(host.clientWidth, host.clientHeight, false);
    host.replaceChildren(renderer.domElement);

    scene.add(new AmbientLight(0xffffff, 0.7));
    const key = new DirectionalLight(0xffffff, 0.8);
    key.position.set(4, -6, 10);
    scene.add(key);

    const parentGroup = new Group();
    parentGroup.name = "parent-world";
    const childGroup = new Group();
    childGroup.name = "child-pose";
    childRef.current = childGroup;
    scene.add(parentGroup);
    scene.add(childGroup);

    orbit = new OrbitControls(camera, renderer.domElement);
    orbit.enableDamping = true;
    gizmo = new TransformControls(camera, renderer.domElement);
    gizmo.setMode(modeRef.current);
    gizmo.addEventListener("dragging-changed", (event) => {
      if (orbit) {
        orbit.enabled = !(event as { value?: unknown }).value;
      }
    });
    gizmo.addEventListener("objectChange", () => {
      if (!childRef.current || applyingRef.current) {
        return;
      }
      if (gizmo?.mode === "scale") {
        const s =
          (childGroup.scale.x + childGroup.scale.y + childGroup.scale.z) / 3;
        childGroup.scale.set(s, s, s);
      }
      onPoseChangeRef.current(scenePoseFromObject(childGroup));
    });
    scene.add(gizmo.getHelper());
    controlsRef.current = gizmo;

    const grid = new GridHelper(40, 40, 0x4b5563, 0x2d333b);
    grid.rotation.x = Math.PI / 2;
    scene.add(grid);
    scene.add(new AxesHelper(2));

    const resize = () => {
      if (!renderer || disposed) {
        return;
      }
      const w = Math.max(host.clientWidth, 1);
      const h = Math.max(host.clientHeight, 1);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    };
    const ro = new ResizeObserver(resize);

    const tick = () => {
      if (disposed || !renderer) {
        return;
      }
      orbit?.update();
      renderer.render(scene, camera);
      frame = window.requestAnimationFrame(tick);
    };

    void (async () => {
      try {
        const [parentObj, childObj] = await Promise.all([
          loadSceneObject(parentSpec, 0xffffff),
          loadSceneObject(childSpec, 0x7eb6ff),
        ]);
        if (disposed) {
          return;
        }
        parentGroup.add(parentObj);
        childGroup.add(childObj);
        applyingRef.current = true;
        applyScenePoseToObject(childGroup, poseRef.current);
        applyingRef.current = false;
        gizmo?.attach(childGroup);
        fitCamera(camera, orbit as OrbitControls, [parentGroup, childGroup]);
        ro.observe(host);
        tick();
      } catch (err) {
        if (!disposed) {
          const note = document.createElement("p");
          note.className = "ss-placement-error";
          note.textContent =
            err instanceof Error ? err.message : "Failed to load scene maps";
          host.appendChild(note);
        }
      }
    })();

    return () => {
      disposed = true;
      window.cancelAnimationFrame(frame);
      ro.disconnect();
      gizmo?.detach();
      gizmo?.dispose();
      orbit?.dispose();
      renderer?.dispose();
      renderer?.domElement.remove();
      childRef.current = null;
      controlsRef.current = null;
    };
  }, [parentSpec, childSpec]);

  useEffect(() => {
    controlsRef.current?.setMode(mode);
  }, [mode]);

  useEffect(() => {
    if (!childRef.current) {
      return;
    }
    applyingRef.current = true;
    applyScenePoseToObject(childRef.current, poseRef.current);
    applyingRef.current = false;
  }, [poseTick]);

  return <div className="ss-placement-canvas" ref={hostRef} />;
}
