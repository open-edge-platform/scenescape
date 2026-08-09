// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "../components/Button";

export type PosePair = {
  cam: [number, number];
  map: [number, number, number];
};

type Props = {
  mapUrl: string | null;
  cameraImageUrl: string | null;
  initialPairs?: PosePair[];
  disabled?: boolean;
  onChange: (pairs: PosePair[]) => void;
};

type Pending = "cam" | "map" | null;

/**
 * Two-pane point correspondence editor (camera frame + scene map).
 * Replaces the Django calibrate iframe for manual pose picking.
 */
export function PointCorrespondencePane({
  mapUrl,
  cameraImageUrl,
  initialPairs = [],
  disabled,
  onChange,
}: Props) {
  const [pairs, setPairs] = useState<PosePair[]>(initialPairs);
  const [pending, setPending] = useState<Pending>("cam");
  const [draftCam, setDraftCam] = useState<[number, number] | null>(null);
  const camRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onChange(pairs);
  }, [pairs, onChange]);

  const clickNorm = (
    ev: React.MouseEvent,
    el: HTMLDivElement | null,
  ): [number, number] | null => {
    if (!el) {
      return null;
    }
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return null;
    }
    const x = ((ev.clientX - rect.left) / rect.width) * 1000;
    const y = ((ev.clientY - rect.top) / rect.height) * 1000;
    return [x, y];
  };

  const onCamClick = (ev: React.MouseEvent) => {
    if (disabled || pending !== "cam") {
      return;
    }
    const pt = clickNorm(ev, camRef.current);
    if (!pt) {
      return;
    }
    setDraftCam(pt);
    setPending("map");
  };

  const onMapClick = (ev: React.MouseEvent) => {
    if (disabled || pending !== "map" || !draftCam) {
      return;
    }
    const pt = clickNorm(ev, mapRef.current);
    if (!pt) {
      return;
    }
    const next: PosePair[] = [
      ...pairs,
      { cam: draftCam, map: [pt[0], pt[1], 0] },
    ];
    setPairs(next);
    setDraftCam(null);
    setPending("cam");
  };

  const reset = useCallback(() => {
    setPairs([]);
    setDraftCam(null);
    setPending("cam");
  }, []);

  const undo = () => {
    setPairs((prev) => prev.slice(0, -1));
    setDraftCam(null);
    setPending("cam");
  };

  return (
    <div className="ss-point-corr">
      <div className="ss-point-corr-toolbar">
        <span className="ss-workspace-panel-hint">
          {pending === "cam"
            ? "Click a point on the camera frame"
            : "Click the matching point on the map"}
          {" · "}
          {pairs.length} pair{pairs.length === 1 ? "" : "s"}
        </span>
        <Button type="button" variant="secondary" disabled={disabled} onClick={undo}>
          Undo
        </Button>
        <Button type="button" variant="secondary" disabled={disabled} onClick={reset}>
          Reset points
        </Button>
      </div>
      <div className="ss-point-corr-panes">
        <div
          ref={camRef}
          className={`ss-point-corr-pane${pending === "cam" ? " is-active" : ""}`}
          onClick={onCamClick}
          role="presentation"
        >
          <div className="ss-point-corr-label">Camera</div>
          {cameraImageUrl ? (
            <img src={cameraImageUrl} alt="Camera frame" />
          ) : (
            <div className="ss-point-corr-empty">
              Camera preview unavailable — place points on the empty frame in
              normalized coordinates.
            </div>
          )}
          <svg className="ss-point-corr-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none">
            {pairs.map((p, i) => (
              <g key={`c-${i}`}>
                <circle cx={p.cam[0]} cy={p.cam[1]} r={8} fill="#0054ae" />
                <text x={p.cam[0] + 10} y={p.cam[1] - 10} fill="#001e50" fontSize="28">
                  {i + 1}
                </text>
              </g>
            ))}
            {draftCam ? (
              <circle cx={draftCam[0]} cy={draftCam[1]} r={8} fill="#da2e56" />
            ) : null}
          </svg>
        </div>
        <div
          ref={mapRef}
          className={`ss-point-corr-pane${pending === "map" ? " is-active" : ""}`}
          onClick={onMapClick}
          role="presentation"
        >
          <div className="ss-point-corr-label">Scene map</div>
          {mapUrl ? (
            <img src={mapUrl} alt="Scene map" />
          ) : (
            <div className="ss-point-corr-empty">Map preview unavailable.</div>
          )}
          <svg className="ss-point-corr-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none">
            {pairs.map((p, i) => (
              <g key={`m-${i}`}>
                <circle cx={p.map[0]} cy={p.map[1]} r={8} fill="#008a00" />
                <text x={p.map[0] + 10} y={p.map[1] - 10} fill="#001e50" fontSize="28">
                  {i + 1}
                </text>
              </g>
            ))}
          </svg>
        </div>
      </div>
    </div>
  );
}

export function pairsToTransforms(pairs: PosePair[]): number[] {
  const cam = pairs.flatMap((p) => [p.cam[0], p.cam[1]]);
  const map = pairs.flatMap((p) => [p.map[0], p.map[1], p.map[2]]);
  return [...cam, ...map];
}
