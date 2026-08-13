// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useMemo, useState } from "react";
import { WorkspacePanel } from "../components/WorkspacePanel";
import { Button } from "../components/Button";
import { api, type RestError } from "../lib/rest";
import { ChildPlacementCanvas } from "./ChildPlacementCanvas";
import { IDENTITY_POSE, dropPoseToZ0, type SceneEulerPose } from "./poseThree";
import {
  sceneGeometryFromRest,
  sceneHasPlaceableGeometry,
  type SceneGeometrySpec,
} from "./sceneGeometry";
import type { PlacementGizmoMode } from "./placementTypes";
import "./ChildPlacementWorkspace.css";

type Props = {
  open: boolean;
  parentSceneId: string;
  childSceneId: string;
  initialPose: SceneEulerPose;
  authToken: string;
  onApply: (pose: SceneEulerPose) => void;
  onClose: () => void;
};

function fmt(n: number, digits = 2): string {
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

/**
 * Full-viewport 3D placement chrome (same WorkspacePanel pattern as calibrate).
 * Parent map/GLB is the world; the child is a movable Object3D.
 */
export function ChildPlacementWorkspace({
  open,
  parentSceneId,
  childSceneId,
  initialPose,
  authToken,
  onApply,
  onClose,
}: Props) {
  const [mode, setMode] = useState<PlacementGizmoMode>("translate");
  const [pose, setPose] = useState<SceneEulerPose>(initialPose);
  const [poseTick, setPoseTick] = useState(0);
  const [parentSpec, setParentSpec] = useState<SceneGeometrySpec | null>(null);
  const [childSpec, setChildSpec] = useState<SceneGeometrySpec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    setMode("translate");
    setPose(initialPose);
    setPoseTick((n) => n + 1);
    setDirty(false);
    setError(null);
    setParentSpec(null);
    setChildSpec(null);
    if (!parentSceneId || !childSceneId) {
      setError("Select a parent and child scene first");
      return;
    }
    let cancelled = false;
    setBusy(true);
    Promise.all([
      api.getScene(authToken, parentSceneId),
      api.getScene(authToken, childSceneId),
    ])
      .then(([parent, child]) => {
        if (cancelled) {
          return;
        }
        const parentGeom = sceneGeometryFromRest(parent);
        const childGeom = sceneGeometryFromRest(child);
        if (
          !sceneHasPlaceableGeometry(parentGeom) ||
          !sceneHasPlaceableGeometry(childGeom)
        ) {
          setError(
            "Both scenes need a map image or GLB to place the child in 3D.",
          );
          return;
        }
        setParentSpec(parentGeom);
        setChildSpec(childGeom);
      })
      .catch((err: RestError) => {
        if (!cancelled) {
          setError(err.message || "Failed to load scenes");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setBusy(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // Snapshot initialPose only when the workspace opens or the pair changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see above
  }, [open, parentSceneId, childSceneId, authToken]);

  const pushPose = useCallback((next: SceneEulerPose) => {
    setPose(next);
    setPoseTick((n) => n + 1);
    setDirty(true);
  }, []);

  const onPoseChange = useCallback((next: SceneEulerPose) => {
    setPose(next);
    setDirty(true);
  }, []);

  const specsReady = useMemo(
    () => Boolean(parentSpec && childSpec),
    [parentSpec, childSpec],
  );

  return (
    <WorkspacePanel
      open={open}
      title="Place child in 3D"
      layout="bleed"
      className="ss-workspace-panel--nested"
      dirty={dirty}
      leaveTitle="Leave placement?"
      leaveBody="The 3D pose has not been applied to the child link."
      onClose={onClose}
      actions={
        <Button
          variant="primary"
          disabled={!specsReady || Boolean(error)}
          onClick={() => {
            onApply(pose);
            setDirty(false);
            onClose();
          }}
        >
          Use this pose
        </Button>
      }
    >
      <div className="ss-placement">
        <div className="ss-placement-toolbar" role="toolbar">
          <Button
            variant={mode === "translate" ? "primary" : "secondary"}
            aria-pressed={mode === "translate"}
            onClick={() => setMode("translate")}
          >
            Translate
          </Button>
          <Button
            variant={mode === "rotate" ? "primary" : "secondary"}
            aria-pressed={mode === "rotate"}
            onClick={() => setMode("rotate")}
          >
            Rotate
          </Button>
          <Button
            variant={mode === "scale" ? "primary" : "secondary"}
            aria-pressed={mode === "scale"}
            onClick={() => setMode("scale")}
          >
            Scale
          </Button>
          <Button onClick={() => pushPose(dropPoseToZ0(pose))}>
            Drop to z=0
          </Button>
          <Button onClick={() => pushPose(initialPose)}>Reset</Button>
          <Button onClick={() => pushPose(IDENTITY_POSE)}>Identity</Button>
        </div>
        {error ? <p className="ss-placement-error">{error}</p> : null}
        {busy && !specsReady ? (
          <p className="ss-placement-hint">Loading scene maps…</p>
        ) : null}
        {parentSpec && childSpec ? (
          <ChildPlacementCanvas
            parentSpec={parentSpec}
            childSpec={childSpec}
            pose={pose}
            poseTick={poseTick}
            mode={mode}
            onPoseChange={onPoseChange}
          />
        ) : null}
        <p className="ss-placement-readout" id="ss-child-placement-readout">
          tx {fmt(pose.translation[0])} m · ty {fmt(pose.translation[1])} m · tz{" "}
          {fmt(pose.translation[2])} m · yaw {fmt(pose.rotation[2], 1)}°
        </p>
      </div>
    </WorkspacePanel>
  );
}
