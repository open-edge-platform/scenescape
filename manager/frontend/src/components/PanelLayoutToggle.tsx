// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./PanelLayoutToggle.css";

export type PanelLayoutMode = "auto" | "stack" | "row";
export type PanelLayout = "stack" | "row";

export const PANEL_LAYOUT_KEY = "ss-workspace-panel-layout-mode";

export const PANEL_LAYOUT_OPTIONS: {
  mode: PanelLayoutMode;
  label: string;
  title: string;
}[] = [
  {
    mode: "auto",
    label: "Auto",
    title: "Place the settings panel automatically from viewport width",
  },
  {
    mode: "stack",
    label: "Below",
    title: "Put the settings panel under the main view",
  },
  {
    mode: "row",
    label: "Beside",
    title: "Put the settings panel beside the main view",
  },
];

export function readPanelLayoutMode(): PanelLayoutMode {
  try {
    const raw = window.localStorage.getItem(PANEL_LAYOUT_KEY);
    if (raw === "auto" || raw === "stack" || raw === "row") {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return "auto";
}

export function chooseAutoPanelLayout(): PanelLayout {
  return window.innerWidth >= 1200 ? "row" : "stack";
}

export function writePanelLayoutMode(mode: PanelLayoutMode): void {
  try {
    window.localStorage.setItem(PANEL_LAYOUT_KEY, mode);
  } catch {
    /* ignore */
  }
}

type Props = {
  layoutMode: PanelLayoutMode;
  onChange: (mode: PanelLayoutMode) => void;
};

/** Auto / Below / Beside control for workspace panel chrome. */
export function PanelLayoutToggle({ layoutMode, onChange }: Props) {
  return (
    <div
      className="ss-cal-layout"
      role="group"
      aria-label="Where to place the settings panel"
    >
      <span className="ss-cal-layout-caption" id="ss-panel-layout-caption">
        Panel layout
      </span>
      <div
        className="ss-cal-layout-toggle"
        aria-labelledby="ss-panel-layout-caption"
      >
        {PANEL_LAYOUT_OPTIONS.map((opt) => {
          const active = layoutMode === opt.mode;
          return (
            <button
              key={opt.mode}
              type="button"
              className={`ss-cal-layout-btn${active ? " is-active" : ""}`}
              title={opt.title}
              aria-pressed={active}
              onClick={() => onChange(opt.mode)}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
