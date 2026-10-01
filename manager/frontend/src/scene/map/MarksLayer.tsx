// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { memo, useEffect } from "react";
import {
  clearLiveMarks,
  configureLiveMarks,
  plotLiveMarks,
  setLiveMarksShowTrails,
  type SceneObjectMark,
} from "./liveMarks";

type Props = {
  scale: number;
  sceneYMax: number;
  assetMarkColors?: Record<string, string>;
};

/**
 * Mounts the React marks layer and listens for regulated-scene objects
 * dispatched from sscape.js (`ss-scene-objects`) when ssUseReactMap is on.
 */
export const MarksLayer = memo(function MarksLayer({
  scale,
  sceneYMax,
  assetMarkColors = {},
}: Props) {
  useEffect(() => {
    configureLiveMarks({ scale, sceneYMax, assetMarkColors });
  }, [scale, sceneYMax, assetMarkColors]);

  useEffect(() => {
    const trailsInput = document.getElementById(
      "show-trails",
    ) as HTMLInputElement | null;
    setLiveMarksShowTrails(Boolean(trailsInput?.checked));

    const onObjects = (ev: Event) => {
      const detail = (ev as CustomEvent<{ objects?: SceneObjectMark[] }>).detail;
      plotLiveMarks(detail?.objects);
    };
    const onTrails = (ev: Event) => {
      const detail = (ev as CustomEvent<{ show?: boolean }>).detail;
      setLiveMarksShowTrails(Boolean(detail?.show));
    };
    const onTrailsInput = () => {
      setLiveMarksShowTrails(Boolean(trailsInput?.checked));
    };

    window.addEventListener("ss-scene-objects", onObjects);
    window.addEventListener("ss-show-trails", onTrails);
    trailsInput?.addEventListener("change", onTrailsInput);
    return () => {
      window.removeEventListener("ss-scene-objects", onObjects);
      window.removeEventListener("ss-show-trails", onTrails);
      trailsInput?.removeEventListener("change", onTrailsInput);
      clearLiveMarks();
    };
  }, []);

  return <g className="ss-react-marks-layer" pointerEvents="none" />;
});
