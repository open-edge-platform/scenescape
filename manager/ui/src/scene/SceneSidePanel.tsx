// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import type { TabItem } from "../components/Tabs";
import {
  readStoredSceneTab,
  SCENE_TAB_EVENT,
  writeStoredSceneTab,
  type SceneControlTabId,
} from "../lib/sceneTab";
import { CameraStripEnhancer } from "./CameraStripEnhancer";
import { ControlTabEntities } from "./control/ControlTabEntities";
import { MqttSettingsPanel } from "./MqttSettingsPanel";
import { SceneHelpModals } from "./SceneHelpModals";
import { TabToolbar } from "./TabToolbar";
import type {
  SceneCameraBootstrap,
  SceneChildBootstrap,
  SceneSensorBootstrap,
} from "./types";
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

type Props = {
  tabs: TabItem[];
  cameraRates?: Record<string, string>;
  cameras?: SceneCameraBootstrap[];
  sensors?: SceneSensorBootstrap[];
  childrenLinks?: SceneChildBootstrap[];
  isSuperuser?: boolean;
  sceneId?: string;
  wssConnection?: string;
};

/**
 * Scene control tabs with React-owned toolbar (stable ids for sscape.js).
 */
export function SceneSidePanel({
  tabs,
  cameraRates = {},
  cameras = [],
  sensors = [],
  childrenLinks = [],
  isSuperuser = false,
  sceneId = "",
  wssConnection = "",
}: Props) {
  const [activeId, setActiveId] = useState<SceneControlTabId>(() =>
    readStoredSceneTab(sceneId),
  );
  const [panelsReady, setPanelsReady] = useState(false);
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
    writeStoredSceneTab(sceneId, activeId);
  }, [sceneId, activeId]);

  useEffect(() => {
    const onTab = (ev: Event) => {
      const detail = (ev as CustomEvent<{ tabId?: string }>).detail;
      const tabId = detail?.tabId;
      if (
        tabId === "cameras" ||
        tabId === "sensors" ||
        tabId === "regions" ||
        tabId === "tripwires" ||
        tabId === "children" ||
        tabId === "mqtt"
      ) {
        setActiveId(tabId);
      }
    };
    window.addEventListener(SCENE_TAB_EVENT, onTab);
    return () => window.removeEventListener(SCENE_TAB_EVENT, onTab);
  }, []);

  const selectTab = (tabId: string) => {
    if (
      tabId === "cameras" ||
      tabId === "sensors" ||
      tabId === "regions" ||
      tabId === "tripwires" ||
      tabId === "children" ||
      tabId === "mqtt"
    ) {
      setActiveId(tabId);
    }
  };

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
                  onClick={() => selectTab(tab.id)}
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
          <div className="ss-tabs-toolbar" data-active-tab={activeId}>
            <TabToolbar activeTab={activeId} isSuperuser={isSuperuser} />
          </div>
          {activeId === "cameras" ? (
            <CameraStripEnhancer rates={cameraRates} />
          ) : null}
        </div>
        <div className="ss-tabs-panels">
          <div ref={slotRef} className="ss-legacy-panels-slot" />
        </div>
      </div>
      <ControlTabEntities
        cameras={cameras}
        sensors={sensors}
        childrenLinks={childrenLinks}
        isSuperuser={isSuperuser}
        panelsReady={panelsReady}
      />
      <MqttSettingsPanel
        wssConnection={wssConnection}
        sceneId={sceneId}
        panelsReady={panelsReady}
      />
      <SceneHelpModals />
    </aside>
  );
}
