// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LEGACY_MAP_IDS, notifyMapHostReady } from "../map/legacyMapHost";
import { ReactSceneMap } from "./map/ReactSceneMap";
import "./SceneMapPane.css";

function refitMap(): void {
  if (typeof window.fitSceneMapDisplay === "function") {
    window.fitSceneMapDisplay();
  }
}

/**
 * Marks stay in native map pixels on the Snap overlay. Match the React
 * map's viewBox so resize only changes display scale, not coordinates.
 */
function syncSnapToReact(stage: HTMLElement): void {
  const reactSvg = stage.querySelector(
    "svg.ss-react-scene-map",
  ) as SVGSVGElement | null;
  const snap = stage.querySelector(
    "svg.ss-snap-legacy, svg#svgout-snap",
  ) as SVGSVGElement | null;
  if (!reactSvg || !snap) {
    return;
  }
  const vb = reactSvg.getAttribute("viewBox");
  const par =
    reactSvg.getAttribute("preserveAspectRatio") || "xMidYMid meet";
  if (vb) {
    snap.setAttribute("viewBox", vb);
  }
  snap.setAttribute("preserveAspectRatio", par);
  snap.removeAttribute("width");
  snap.removeAttribute("height");
  snap.style.width = "100%";
  snap.style.height = "100%";
}

type Props = {
  mapUrl?: string | null;
  mapWidth?: number;
  mapHeight?: number;
};

/**
 * Adopts the Django-rendered map host into the React layout.
 * When ssUseReactMap is set, overlays ReactSceneMap on the map stage only
 * (so #map-controls toggles stay visible below the stage).
 */
export function SceneMapPane({
  mapUrl = null,
  mapWidth = 1280,
  mapHeight = 720,
}: Props) {
  const slotRef = useRef<HTMLDivElement>(null);
  const [hostReady, setHostReady] = useState(false);
  const [naturalSize, setNaturalSize] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const useReactMap = Boolean(window.ssUseReactMap) && Boolean(mapUrl);

  useEffect(() => {
    // Load the map image ourselves so ReactSceneMap's viewBox / scale math
    // matches the real map (sscape.js may remove the legacy <img> once its
    // own load handler fires).
    if (!useReactMap || !mapUrl) {
      setNaturalSize(null);
      return;
    }
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (!cancelled && img.naturalWidth > 0 && img.naturalHeight > 0) {
        setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight });
      }
    };
    img.src = mapUrl;
    return () => {
      cancelled = true;
    };
  }, [useReactMap, mapUrl]);

  useEffect(() => {
    const slot = slotRef.current;
    const host = document.getElementById(LEGACY_MAP_IDS.host);
    if (!slot || !host) {
      return;
    }
    slot.appendChild(host);
    host.hidden = false;
    if (useReactMap) {
      document.body.classList.add("ss-use-react-map");
      const svg = host.querySelector(
        "svg#svgout, svg.ss-snap-legacy, svg#svgout-snap",
      );
      if (svg) {
        svg.classList.add("ss-snap-legacy");
        // Hard contract `#svgout` belongs to the visible map. Relinquish the
        // id from the hidden Snap canvas so Selenium / layout find React.
        if (svg.id === "svgout") {
          svg.id = "svgout-snap";
        }
      }
    }
    notifyMapHostReady();
    setHostReady(true);

    let raf = 0;
    let lastW = -1;
    let lastH = -1;
    const scheduleRefit = () => {
      if (raf) {
        return;
      }
      raf = window.requestAnimationFrame(() => {
        raf = 0;
        const w = Math.round(slot.clientWidth);
        const h = Math.round(slot.clientHeight);
        if (w === lastW && h === lastH && lastW >= 0) {
          return;
        }
        lastW = w;
        lastH = h;
        if (!useReactMap) {
          refitMap();
        } else {
          const stageEl = host.querySelector(
            ".scene-map-stage",
          ) as HTMLElement | null;
          if (stageEl) {
            syncSnapToReact(stageEl);
          }
          refitMap();
        }
      });
    };

    window.addEventListener("resize", scheduleRefit);

    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => scheduleRefit());
      observer.observe(slot);
    }

    scheduleRefit();

    return () => {
      if (raf) {
        window.cancelAnimationFrame(raf);
      }
      window.removeEventListener("resize", scheduleRefit);
      observer?.disconnect();
      document.body.classList.remove("ss-use-react-map");
      const snap = host.querySelector("svg#svgout-snap, svg.ss-snap-legacy");
      if (snap && snap.id === "svgout-snap") {
        // Avoid duplicate id if React layer still mounts briefly on teardown.
        const reactSvg = host.querySelector("svg.ss-react-scene-map");
        if (!reactSvg || reactSvg.id !== "svgout") {
          snap.id = "svgout";
        }
      }
      const parking = document.getElementById("ss-legacy-map-parking");
      if (parking && host.parentElement === slot) {
        parking.appendChild(host);
        host.hidden = true;
      }
    };
  }, [useReactMap]);

  useEffect(() => {
    if (!useReactMap || !hostReady) {
      return;
    }
    const host = document.getElementById(LEGACY_MAP_IDS.host);
    const stageEl = host?.querySelector(".scene-map-stage") as HTMLElement | null;
    if (stageEl) {
      syncSnapToReact(stageEl);
    }
  }, [useReactMap, hostReady, naturalSize]);

  const host = hostReady ? document.getElementById(LEGACY_MAP_IDS.host) : null;
  const stage =
    host?.querySelector(".scene-map-stage") ??
    null;

  return (
    <div className="ss-scene-map-pane">
      <div ref={slotRef} className="ss-scene-map-slot" />
      {useReactMap && stage && mapUrl && naturalSize
        ? createPortal(
            <div className="ss-react-map-layer">
              <img
                className="ss-react-map-bg"
                src={mapUrl}
                alt=""
                draggable={false}
              />
              <ReactSceneMap
                mapWidth={naturalSize.width || mapWidth}
                mapHeight={naturalSize.height || mapHeight}
              />
            </div>,
            stage,
          )
        : null}
    </div>
  );
}
