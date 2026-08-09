// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import type { TabItem } from "../components/Tabs";
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

const TAB_ICONS: Record<string, string> = {
  cameras: "bi-camera-video",
  sensors: "bi-thermometer",
  regions: "bi-bounding-box",
  tripwires: "bi-distribute-horizontal",
  children: "bi-diagram-2",
  mqtt: "bi-broadcast",
};

type Props = {
  tabs: TabItem[];
};

export function SceneSidePanel({ tabs }: Props) {
  const [activeId, setActiveId] = useState("cameras");
  const slotRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const slot = slotRef.current;
    const panels = document.getElementById("scene-detail-panels");
    if (!slot || !panels) {
      return;
    }
    slot.appendChild(panels);
    panels.hidden = false;
    panels.classList.add("ss-legacy-panels-adopted");
    return () => {
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

  return (
    <aside className="ss-scene-side hide-fullscreen">
      <div className="ss-tabs">
        <div className="ss-tabs-list" role="tablist" id="myTab">
          {tabs.map((tab) => {
            const selected = tab.id === activeId;
            const legacyId = LEGACY_TAB_LINK[tab.id] || `ss-tab-${tab.id}`;
            const icon = TAB_ICONS[tab.id];
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
                <span className="ss-tabs-main">
                  {icon ? (
                    <i
                      className={`bi ${icon} ss-tabs-icon`}
                      aria-hidden="true"
                    />
                  ) : null}
                  <span className="ss-tabs-label">{tab.label}</span>
                </span>
                {tab.count !== undefined && tab.count !== null ? (
                  <span className="ss-tabs-count">{tab.count}</span>
                ) : null}
                {tab.extra}
              </button>
            );
          })}
        </div>
        <div className="ss-tabs-panels">
          <div ref={slotRef} className="ss-legacy-panels-slot" />
        </div>
      </div>
    </aside>
  );
}
