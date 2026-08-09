// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState } from "react";

export type WorkspaceLayout = "stack" | "row";
/** auto = derive from map + viewport; stack/row = manual override */
export type WorkspaceLayoutMode = "auto" | WorkspaceLayout;

type Size = { w: number; h: number };

const STORAGE_KEY = "ss-workspace-layout-mode";

/** Minimum tab peek when scoring stack vs row (panels can grow past this). */
const PEEK_STACK_PX = 224;
const PEEK_ROW_PX = 256;
const MIN_MAP = 120;

function readViewport(): Size {
  return {
    w: Math.max(window.innerWidth || 0, 320),
    h: Math.max(window.innerHeight || 0, 320),
  };
}

function readStoredMode(): WorkspaceLayoutMode {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "auto" || raw === "stack" || raw === "row") {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return "auto";
}

function writeStoredMode(mode: WorkspaceLayoutMode): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

/**
 * Intrinsic map pixel size from legacy scene globals, SVG viewBox, or map img.
 */
export function readMapIntrinsicSize(): Size | null {
  const win = window as Window & {
    scene_map_width?: number;
    scene_y_max?: number;
  };
  if (
    typeof win.scene_map_width === "number" &&
    win.scene_map_width > 0 &&
    typeof win.scene_y_max === "number" &&
    win.scene_y_max > 0
  ) {
    return { w: win.scene_map_width, h: win.scene_y_max };
  }

  const svg = document.getElementById("svgout");
  if (svg) {
    const vb = svg.getAttribute("viewBox");
    if (vb) {
      const parts = vb.trim().split(/[\s,]+/).map(Number);
      if (
        parts.length === 4 &&
        Number.isFinite(parts[2]) &&
        Number.isFinite(parts[3]) &&
        parts[2] > 0 &&
        parts[3] > 0
      ) {
        return { w: parts[2], h: parts[3] };
      }
    }
  }

  const img = document.querySelector(
    "#ss-map-host #map img",
  ) as HTMLImageElement | null;
  if (img && img.naturalWidth > 0 && img.naturalHeight > 0) {
    return { w: img.naturalWidth, h: img.naturalHeight };
  }

  return null;
}

function mapFitArea(map: Size, regionW: number, regionH: number): number {
  const rw = Math.max(regionW, MIN_MAP);
  const rh = Math.max(regionH, MIN_MAP);
  const scale = Math.min(rw / map.w, rh / map.h);
  if (!Number.isFinite(scale) || scale <= 0) {
    return 0;
  }
  return map.w * scale * (map.h * scale);
}

export function chooseAutoLayout(
  viewport: Size,
  map: Size | null,
  chromeH: number,
): WorkspaceLayout {
  const availW = Math.max(viewport.w - 32, MIN_MAP);
  const availH = Math.max(viewport.h - chromeH, MIN_MAP);

  if (availW < 720 || availH / availW > 1.25) {
    return "stack";
  }

  if (!map) {
    return availW / availH >= 1.35 ? "stack" : "row";
  }

  const aspect = map.w / map.h;
  const stackArea = mapFitArea(map, availW, availH - PEEK_STACK_PX);
  const rowArea = mapFitArea(map, availW - PEEK_ROW_PX, availH);

  if (aspect >= 1.35) {
    return stackArea >= rowArea * 0.92 ? "stack" : "row";
  }
  if (aspect <= 1.05) {
    return rowArea >= stackArea * 0.92 ? "row" : "stack";
  }
  return rowArea > stackArea ? "row" : "stack";
}

type Options = {
  chromeHeightPx?: number;
};

export type WorkspaceLayoutState = {
  /** Resolved layout applied to the workspace. */
  layout: WorkspaceLayout;
  /** User preference: auto or a fixed orientation. */
  mode: WorkspaceLayoutMode;
  setMode: (mode: WorkspaceLayoutMode) => void;
  /** What auto would choose right now (for UI hints). */
  autoLayout: WorkspaceLayout;
};

/**
 * Workspace orientation: auto from map/viewport, or manual stack/row.
 * Manual choice is persisted in localStorage.
 */
export function useWorkspaceLayout(
  options: Options = {},
): WorkspaceLayoutState {
  const chrome = options.chromeHeightPx ?? 112;
  const [mode, setModeState] = useState<WorkspaceLayoutMode>(() =>
    typeof window !== "undefined" ? readStoredMode() : "auto",
  );
  const [autoLayout, setAutoLayout] = useState<WorkspaceLayout>(() =>
    chooseAutoLayout(readViewport(), null, chrome),
  );

  const setMode = useCallback((next: WorkspaceLayoutMode) => {
    setModeState(next);
    writeStoredMode(next);
  }, []);

  useEffect(() => {
    let frame = 0;
    const recompute = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const nextAuto = chooseAutoLayout(
          readViewport(),
          readMapIntrinsicSize(),
          chrome,
        );
        setAutoLayout((prev) => (prev === nextAuto ? prev : nextAuto));
        if (typeof window.fitSceneMapDisplay === "function") {
          window.fitSceneMapDisplay();
        }
      });
    };

    recompute();
    window.addEventListener("resize", recompute);
    window.addEventListener("ss-map-host-ready", recompute);

    const img = document.querySelector(
      "#ss-map-host #map img",
    ) as HTMLImageElement | null;
    if (img && !img.complete) {
      img.addEventListener("load", recompute);
    }

    const host = document.getElementById("ss-map-host");
    let ro: ResizeObserver | null = null;
    if (host && typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => recompute());
      ro.observe(host);
    }

    const poll = window.setInterval(recompute, 500);
    const stopPoll = window.setTimeout(() => window.clearInterval(poll), 8000);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", recompute);
      window.removeEventListener("ss-map-host-ready", recompute);
      img?.removeEventListener("load", recompute);
      ro?.disconnect();
      window.clearInterval(poll);
      window.clearTimeout(stopPoll);
    };
  }, [chrome, mode]);

  const layout: WorkspaceLayout = mode === "auto" ? autoLayout : mode;

  return { layout, mode, setMode, autoLayout };
}
