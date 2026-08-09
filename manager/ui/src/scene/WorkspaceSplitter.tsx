// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useRef, type PointerEvent as ReactPointerEvent } from "react";
import type { WorkspaceLayout } from "./useWorkspaceLayout";

type Props = {
  layout: WorkspaceLayout;
  panelSizePx: number;
  onResize: (panelSizePx: number) => void;
  disabled?: boolean;
};

/**
 * Drag handle between map and inspector. Panel size is measured from the
 * trailing edge of the workspace body.
 */
export function WorkspaceSplitter({
  layout,
  panelSizePx,
  onResize,
  disabled,
}: Props) {
  const dragging = useRef(false);

  const onPointerDown = useCallback(
    (ev: ReactPointerEvent<HTMLDivElement>) => {
      if (disabled) {
        return;
      }
      ev.preventDefault();
      const handle = ev.currentTarget;
      handle.setPointerCapture(ev.pointerId);
      dragging.current = true;
      document.body.classList.add("ss-workspace-resizing");

      const body = handle.closest(".ss-workspace-body") as HTMLElement | null;
      if (!body) {
        return;
      }

      const onMove = (e: PointerEvent) => {
        if (!dragging.current) {
          return;
        }
        const rect = body.getBoundingClientRect();
        if (layout === "stack") {
          onResize(rect.bottom - e.clientY);
        } else {
          onResize(rect.right - e.clientX);
        }
      };

      const onUp = (e: PointerEvent) => {
        dragging.current = false;
        document.body.classList.remove("ss-workspace-resizing");
        try {
          handle.releasePointerCapture(e.pointerId);
        } catch {
          /* ignore */
        }
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        if (typeof window.fitSceneMapDisplay === "function") {
          window.fitSceneMapDisplay();
        }
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    },
    [disabled, layout, onResize],
  );

  return (
    <div
      className={`ss-workspace-splitter ss-workspace-splitter--${layout}`}
      role="separator"
      aria-orientation={layout === "stack" ? "horizontal" : "vertical"}
      aria-label="Resize control panel"
      aria-valuenow={Math.round(panelSizePx)}
      aria-disabled={disabled || undefined}
      tabIndex={disabled ? -1 : 0}
      onPointerDown={onPointerDown}
      onKeyDown={(e) => {
        if (disabled) {
          return;
        }
        const step = e.shiftKey ? 32 : 16;
        if (
          (layout === "stack" && e.key === "ArrowUp") ||
          (layout === "row" && e.key === "ArrowLeft")
        ) {
          e.preventDefault();
          onResize(panelSizePx + step);
        } else if (
          (layout === "stack" && e.key === "ArrowDown") ||
          (layout === "row" && e.key === "ArrowRight")
        ) {
          e.preventDefault();
          onResize(panelSizePx - step);
        }
      }}
    />
  );
}
