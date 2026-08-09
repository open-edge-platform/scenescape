// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef } from "react";
import { LEGACY_MAP_IDS, notifyMapHostReady } from "../map/legacyMapHost";
import "./SceneMapPane.css";

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

    const refit = () => {
      if (typeof window.fitSceneMapDisplay === "function") {
        window.fitSceneMapDisplay();
      }
    };
    const onResize = () => refit();
    window.addEventListener("resize", onResize);

    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => refit());
      observer.observe(slot);
    }

    // Layout may settle after adopt; refit once more on next frame.
    const raf = window.requestAnimationFrame(refit);

    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
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
