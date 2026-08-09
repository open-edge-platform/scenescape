// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import type { TabItem } from "../components/Tabs";
import { CameraStripEnhancer } from "./CameraStripEnhancer";
import "../components/Tabs.css";
import "./SceneSidePanel.css";

const PANE_BY_TAB: Record<string, string> = {
  cameras: "cameras",
  sensors: "sensors",
  regions: "regions",
  tripwires: "trips",
  children: "children",
  mqtt: "mqtt",
};

const LEGACY_TAB_LINK: Record<string, string> = {
  cameras: "cameras-tab",
  sensors: "sensors-tab",
  regions: "regions-tab",
  tripwires: "tripwires-tab",
  children: "children-tab",
  mqtt: "settings-tab",
};

/** Legacy control ids adopted into the active-tab toolbar (keeps jQuery handlers). */
const TAB_TOOLBAR_IDS: Record<string, string[]> = {
  cameras: ["camera-help", "live-view", "show-telemetry", "new-camera"],
  sensors: ["sensor-help", "new-sensor"],
  regions: ["roi-help", "new-roi", "save-rois"],
  tripwires: ["tripwire-help", "new-tripwire", "save-trips"],
  children: ["children-help", "new-child"],
  mqtt: [],
};

type HomeSlot = { parent: Node; next: ChildNode | null };

function resolveNode(id: string): HTMLElement | null {
  const el = document.getElementById(id);
  if (!el) {
    return null;
  }
  if (id === "live-view" || id === "show-telemetry") {
    return (el.closest(".scene-detail-live-toggle") as HTMLElement) || el;
  }
  return el;
}

type Props = {
  tabs: TabItem[];
};

/**
 * Scene control tabs: active-tab toolbar hosts help + New (+ live toggles / save)
 * on the same row as the tab labels. Legacy panel headers stay in DOM for parking.
 */
export function SceneSidePanel({ tabs }: Props) {
  const [activeId, setActiveId] = useState("cameras");
  const [panelsReady, setPanelsReady] = useState(false);
  const slotRef = useRef<HTMLDivElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const homeRef = useRef<Map<string, HomeSlot>>(new Map());

  useEffect(() => {
    const slot = slotRef.current;
    const panels = document.getElementById("scene-detail-panels");
    if (!slot || !panels) {
      return;
    }
    slot.appendChild(panels);
    panels.hidden = false;
    panels.classList.add("ss-legacy-panels-adopted");
    setPanelsReady(true);
    return () => {
      setPanelsReady(false);
      const parking = document.getElementById("ss-legacy-panels-parking");
      if (parking && panels.parentElement === slot) {
        parking.appendChild(panels);
        panels.hidden = true;
      }
    };
  }, []);

  useEffect(() => {
    Object.entries(PANE_BY_TAB).forEach(([tabId, paneId]) => {
      const pane = document.getElementById(paneId);
      if (!pane) {
        return;
      }
      const selected = tabId === activeId;
      pane.classList.toggle("show", selected);
      pane.classList.toggle("active", selected);
    });
  }, [activeId]);

  useEffect(() => {
    if (!panelsReady) {
      return;
    }
    const toolbar = toolbarRef.current;
    const home = homeRef.current;

    const restore = () => {
      home.forEach(({ parent, next }, id) => {
        const node = resolveNode(id);
        if (node && parent) {
          parent.insertBefore(node, next);
        }
      });
      home.clear();
    };

    restore();
    if (!toolbar) {
      return restore;
    }

    const ids = TAB_TOOLBAR_IDS[activeId] || [];
    ids.forEach((id) => {
      const node = resolveNode(id);
      if (!node || !node.parentNode) {
        return;
      }
      home.set(id, { parent: node.parentNode, next: node.nextSibling });
      toolbar.appendChild(node);
    });

    return restore;
  }, [activeId, panelsReady]);

  return (
    <aside className="ss-scene-side hide-fullscreen">
      <div className="ss-tabs">
        <div className="ss-tabs-chrome">
          <div className="ss-tabs-list" role="tablist" id="myTab">
            {tabs.map((tab) => {
              const selected = tab.id === activeId;
              const legacyId = LEGACY_TAB_LINK[tab.id] || `ss-tab-${tab.id}`;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  id={legacyId}
                  aria-selected={selected}
                  aria-controls={PANE_BY_TAB[tab.id] || tab.id}
                  className={`ss-tabs-tab${selected ? " is-active" : ""}`}
                  onClick={() => setActiveId(tab.id)}
                >
                  <span className="ss-tabs-label">{tab.label}</span>
                  {tab.count !== undefined && tab.count !== null ? (
                    <span className="ss-tabs-count">{tab.count}</span>
                  ) : null}
                  {tab.extra}
                </button>
              );
            })}
          </div>
          <div
            ref={toolbarRef}
            className="ss-tabs-toolbar"
            data-active-tab={activeId}
          />
          {activeId === "cameras" ? <CameraStripEnhancer /> : null}
        </div>
        <div className="ss-tabs-panels">
          <div ref={slotRef} className="ss-legacy-panels-slot" />
        </div>
      </div>
    </aside>
  );
}
