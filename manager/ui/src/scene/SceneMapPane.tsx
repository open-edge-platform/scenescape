// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef } from "react";
import { LEGACY_MAP_IDS, notifyMapHostReady } from "../map/legacyMapHost";
import "./SceneMapPane.css";

function refitMap(): void {
  if (typeof window.fitSceneMapDisplay === "function") {
    window.fitSceneMapDisplay();
  }
}

/**
 * Adopts the Django-rendered map host into the React layout without remounting
 * the Snap.svg subtree (ids stay stable for sscape.js).
 */
export function SceneMapPane() {
  const slotRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const slot = slotRef.current;
    const host = document.getElementById(LEGACY_MAP_IDS.host);
    if (!slot || !host) {
      return;
    }
    slot.appendChild(host);
    host.hidden = false;
    notifyMapHostReady();

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
        // Skip no-op fits — ResizeObserver + fitSceneMapDisplay can feedback.
        if (w === lastW && h === lastH && lastW >= 0) {
          return;
        }
        lastW = w;
        lastH = h;
        refitMap();
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
      const parking = document.getElementById("ss-legacy-map-parking");
      if (parking && host.parentElement === slot) {
        parking.appendChild(host);
        host.hidden = true;
      }
    };
  }, []);

  return (
    <div className="ss-scene-map-pane">
      <div ref={slotRef} className="ss-scene-map-slot" />
    </div>
  );
}
