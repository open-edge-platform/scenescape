// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Button } from "../components/Button";
import { useAppToast } from "../components/ToastProvider";
import {
  checkMappingServiceAvailable,
  pollMeshStatus,
  startMeshGeneration,
} from "../lib/meshGeneration";
import "./SceneMapSetupHelper.css";

type Props = {
  sceneId: string;
  authToken: string;
  cameraCount: number;
  setupReconstruct?: boolean;
  onMeshComplete?: () => void;
};

type MappingState = "checking" | "available" | "unavailable";

const MAPPING_ENABLE_HINT =
  "Start mapping with: docker compose --profile mapping up -d  (or make demo-all)";

export function SceneMapSetupHelper({
  sceneId,
  authToken,
  cameraCount,
  setupReconstruct = false,
  onMeshComplete,
}: Props) {
  const toast = useAppToast();
  const [mapping, setMapping] = useState<MappingState>("checking");
  const [rechecking, setRechecking] = useState(false);
  const [meshBusy, setMeshBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshMapping = useCallback(async () => {
    setRechecking(true);
    const ok = await checkMappingServiceAvailable(authToken);
    setMapping(ok ? "available" : "unavailable");
    setRechecking(false);
  }, [authToken]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      const ok = await checkMappingServiceAvailable(authToken);
      if (!cancelled) {
        setMapping(ok ? "available" : "unavailable");
      }
    };
    void run();
    const timer = window.setInterval(() => {
      void run();
    }, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [authToken]);

  const runGenerateMesh = async () => {
    setMeshBusy(true);
    setError(null);
    try {
      const requestId = await startMeshGeneration(sceneId);
      toast.show("Mesh generation started…", "info");
      await pollMeshStatus(sceneId, requestId);
      toast.show("Mesh generated — map and cameras updated", "ok");
      onMeshComplete?.();
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Mesh generation failed";
      setError(msg);
      toast.show(msg, "bad");
    } finally {
      setMeshBusy(false);
    }
  };

  const finishSetup = setupReconstruct;
  const mappingOk = mapping === "available";
  const mappingDown = mapping === "unavailable";
  const hasCameras = cameraCount >= 1;

  let title = "Scene map required";
  let body =
    "This scene has no map yet. Provide a floor plan or geospatial basemap, or reconstruct from cameras when mapping is available.";
  let primary: ReactNode = null;

  if (hasCameras && mappingDown) {
    title = finishSetup
      ? "Finish setup — tracking is blocked"
      : "Tracking is blocked";
    body =
      "Cameras are connected, but this scene has no map and the mapping service is not available. Tracking needs a map and calibrated cameras. Upload or position a geospatial map (then calibrate manually), or start the mapping service and generate a mesh to create the map and calibrate automatically.";
    primary = (
      <>
        <a className="ss-btn ss-btn--primary" href="?ss=scene-manage&map=map_upload">
          Upload a map
        </a>
        <a
          className="ss-btn ss-btn--secondary"
          href="?ss=scene-manage&map=geospatial_map"
        >
          Use geospatial map
        </a>
      </>
    );
  } else if (hasCameras && mappingOk) {
    title = finishSetup ? "Finish setup — generate mesh" : "Ready to generate map";
    body =
      "Cameras are connected and the mapping service is available. Generate a mesh to create the scene map and auto-calibrate cameras. Tracking cannot run until this completes (or you upload a map and calibrate manually).";
    primary = (
      <>
        <Button
          type="button"
          variant="primary"
          id="generate_mesh"
          disabled={meshBusy}
          onClick={() => void runGenerateMesh()}
        >
          {meshBusy ? "Generating…" : "Generate Mesh"}
        </Button>
        <a className="ss-btn ss-btn--secondary" href="?ss=scene-manage&map=map_upload">
          Upload a map instead
        </a>
      </>
    );
  } else if (!hasCameras && mappingOk) {
    title = finishSetup ? "Finish setup — add cameras" : "Add cameras to reconstruct";
    body =
      "This scene has no map. Add cameras that cover the space, then generate a mesh to create the map and calibrate. You can also upload a floor plan or use a geospatial basemap.";
    primary = (
      <>
        <a className="ss-btn ss-btn--primary" href="?ss=cam-create">
          + New Camera
        </a>
        <a className="ss-btn ss-btn--secondary" href="?ss=scene-manage&map=map_upload">
          Upload a map
        </a>
        <a
          className="ss-btn ss-btn--secondary"
          href="?ss=scene-manage&map=geospatial_map"
        >
          Geospatial map
        </a>
      </>
    );
  } else if (!hasCameras && mappingDown) {
    title = "Provide a scene map";
    body =
      "This scene has no map, and the mapping service is not running. Upload a floor plan or geospatial basemap to enable calibration and tracking, or start mapping if you plan to reconstruct from cameras.";
    primary = (
      <>
        <a className="ss-btn ss-btn--primary" href="?ss=scene-manage&map=map_upload">
          Upload a map
        </a>
        <a
          className="ss-btn ss-btn--secondary"
          href="?ss=scene-manage&map=geospatial_map"
        >
          Use geospatial map
        </a>
      </>
    );
  }

  return (
    <div
      className="ss-map-setup-helper"
      role="region"
      aria-label="Scene map setup"
      data-mapping={mapping}
      data-cameras={cameraCount}
    >
      <div className="ss-map-setup-helper-card ss-empty-state">
        <h3 className="ss-map-setup-helper-title">{title}</h3>
        <p className="ss-map-setup-helper-body">{body}</p>
        {error ? <p className="ss-map-setup-helper-error">{error}</p> : null}
        <div className="ss-map-setup-helper-actions">{primary}</div>
        {mappingDown ? (
          <div className="ss-map-setup-helper-secondary">
            <p className="ss-map-setup-helper-hint">{MAPPING_ENABLE_HINT}</p>
            <Button
              type="button"
              variant="secondary"
              disabled={rechecking || meshBusy}
              onClick={() => void refreshMapping()}
            >
              {rechecking ? "Checking…" : "Check again"}
            </Button>
          </div>
        ) : null}
        {mapping === "checking" ? (
          <p className="ss-map-setup-helper-hint">Checking mapping service…</p>
        ) : null}
      </div>
    </div>
  );
}
