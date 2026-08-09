// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState } from "react";
import type { WorkspaceLayout } from "./useWorkspaceLayout";

const SIZE_KEY = "ss-workspace-panel-size";
const FOCUS_KEY = "ss-workspace-map-focus";

const DEFAULT_STACK_PX = 224;
const DEFAULT_ROW_PX = 320;
const MIN_STACK_PX = 140;
const MAX_STACK_PX = 520;
const MIN_ROW_PX = 220;
const MAX_ROW_PX = 560;

type StoredSizes = {
  stack: number;
  row: number;
};

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

function readSizes(): StoredSizes {
  try {
    const raw = window.localStorage.getItem(SIZE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoredSizes>;
      return {
        stack: clamp(
          Number(parsed.stack) || DEFAULT_STACK_PX,
          MIN_STACK_PX,
          MAX_STACK_PX,
        ),
        row: clamp(
          Number(parsed.row) || DEFAULT_ROW_PX,
          MIN_ROW_PX,
          MAX_ROW_PX,
        ),
      };
    }
  } catch {
    /* ignore */
  }
  return { stack: DEFAULT_STACK_PX, row: DEFAULT_ROW_PX };
}

function writeSizes(sizes: StoredSizes): void {
  try {
    window.localStorage.setItem(SIZE_KEY, JSON.stringify(sizes));
  } catch {
    /* ignore */
  }
}

function readFocus(): boolean {
  try {
    return window.localStorage.getItem(FOCUS_KEY) === "1";
  } catch {
    return false;
  }
}

function writeFocus(v: boolean): void {
  try {
    window.localStorage.setItem(FOCUS_KEY, v ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export type WorkspaceDensityState = {
  panelSizePx: number;
  setPanelSizePx: (px: number) => void;
  mapFocus: boolean;
  setMapFocus: (v: boolean) => void;
  toggleMapFocus: () => void;
  minPx: number;
  maxPx: number;
};

/**
 * Persisted inspector size + map-only focus for the scene workspace.
 */
export function useWorkspaceDensity(
  layout: WorkspaceLayout,
): WorkspaceDensityState {
  const [sizes, setSizes] = useState<StoredSizes>(() =>
    typeof window !== "undefined"
      ? readSizes()
      : { stack: DEFAULT_STACK_PX, row: DEFAULT_ROW_PX },
  );
  const [mapFocus, setMapFocusState] = useState(() =>
    typeof window !== "undefined" ? readFocus() : false,
  );

  const minPx = layout === "stack" ? MIN_STACK_PX : MIN_ROW_PX;
  const maxPx = layout === "stack" ? MAX_STACK_PX : MAX_ROW_PX;
  const panelSizePx = layout === "stack" ? sizes.stack : sizes.row;

  const setPanelSizePx = useCallback(
    (px: number) => {
      const next = clamp(px, minPx, maxPx);
      setSizes((prev) => {
        const updated =
          layout === "stack"
            ? { ...prev, stack: next }
            : { ...prev, row: next };
        writeSizes(updated);
        return updated;
      });
    },
    [layout, minPx, maxPx],
  );

  const setMapFocus = useCallback((v: boolean) => {
    setMapFocusState(v);
    writeFocus(v);
  }, []);

  const toggleMapFocus = useCallback(() => {
    setMapFocusState((prev) => {
      const next = !prev;
      writeFocus(next);
      return next;
    });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && mapFocus) {
        setMapFocus(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mapFocus, setMapFocus]);

  return {
    panelSizePx,
    setPanelSizePx,
    mapFocus,
    setMapFocus,
    toggleMapFocus,
    minPx,
    maxPx,
  };
}
