// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import { TabList, type TabItem } from "../components/Tabs";
import {
  readStoredSceneTab,
  SCENE_TAB_EVENT,
  writeStoredSceneTab,
  type SceneControlTabId,
} from "../lib/sceneTab";
import { CameraStripEnhancer } from "./CameraStripEnhancer";
import {
  CamerasPanelContent,
  ChildrenPanelContent,
  SensorsPanelContent,
  usePublishEntityTabCounts,
} from "./control/ControlTabEntities";
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

type Props = {
  tabs: TabItem[];
  cameraRates?: Record<string, string>;
  cameras?: SceneCameraBootstrap[];
  sensors?: SceneSensorBootstrap[];
  childrenLinks?: SceneChildBootstrap[];
  isSuperuser?: boolean;
  sceneId?: string;
  wssConnection?: string;
  authToken?: string;
  onSensorsChange?: Dispatch<SetStateAction<SceneSensorBootstrap[]>>;
};

function SceneControlPanel({
  paneId,
  tabId,
  activeId,
  children,
}: {
  paneId: string;
  tabId: string;
  activeId: string;
  children: ReactNode;
}) {
  const selected = tabId === activeId;
  return (
    <div
      role="tabpanel"
      id={paneId}
      aria-labelledby={`ss-tab-${tabId}`}
      hidden={!selected}
      className={`ss-tabs-panel scene-detail-panel-wrap${selected ? " is-active" : ""}`}
    >
      <div className="card scene-detail-panel">
        <div className="card-body">{children}</div>
      </div>
    </div>
  );
}

/**
 * Scene control tabs with React-owned panels (stable ids for sscape.js).
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
  authToken = "",
  onSensorsChange,
}: Props) {
  const [activeId, setActiveId] = useState<SceneControlTabId>(() =>
    readStoredSceneTab(sceneId),
  );

  usePublishEntityTabCounts(cameras, sensors, childrenLinks);

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

  const selectTab = useCallback((tabId: string) => {
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
  }, []);

  return (
    <aside className="ss-scene-side hide-fullscreen">
      <div className="ss-tabs">
        <div className="ss-tabs-chrome">
          <TabList
            id="ss-scene-tablist"
            tabs={tabs}
            activeId={activeId}
            onChange={selectTab}
            tabPanelId={(tab) => PANE_BY_TAB[tab.id] || tab.id}
          />
          <div className="ss-tabs-toolbar" data-active-tab={activeId}>
            <TabToolbar activeTab={activeId} isSuperuser={isSuperuser} />
          </div>
          {activeId === "cameras" ? (
            <CameraStripEnhancer rates={cameraRates} />
          ) : null}
        </div>
        <div className="ss-tabs-panels" id="ss-scene-tab-panels">
          <SceneControlPanel
            paneId="cameras"
            tabId="cameras"
            activeId={activeId}
          >
            <div id="ss-cameras-mount">
              <CamerasPanelContent
                cameras={cameras}
                isSuperuser={isSuperuser}
              />
            </div>
          </SceneControlPanel>

          <SceneControlPanel
            paneId="sensors"
            tabId="sensors"
            activeId={activeId}
          >
            <div id="ss-sensors-mount">
              <SensorsPanelContent
                sensors={sensors}
                isSuperuser={isSuperuser}
                authToken={authToken}
                onSensorsChange={onSensorsChange}
              />
            </div>
          </SceneControlPanel>

          <SceneControlPanel
            paneId="regions"
            tabId="regions"
            activeId={activeId}
          >
            <div id="roi-fields" className="top-buffer" />
            <div id="no-regions" className="ss-empty-state" hidden />
          </SceneControlPanel>

          <SceneControlPanel
            paneId="trips"
            tabId="tripwires"
            activeId={activeId}
          >
            <div id="tripwire-fields" className="top-buffer" />
            <div id="no-tripwires" className="ss-empty-state" hidden />
          </SceneControlPanel>

          <SceneControlPanel
            paneId="children"
            tabId="children"
            activeId={activeId}
          >
            <div id="childrenlist">
              <input
                type="hidden"
                name="children"
                id="scene_children"
                value={String(childrenLinks.length)}
                readOnly
              />
              <div id="ss-children-mount">
                <ChildrenPanelContent
                  childrenLinks={childrenLinks}
                  isSuperuser={isSuperuser}
                />
              </div>
            </div>
          </SceneControlPanel>

          <SceneControlPanel paneId="mqtt" tabId="mqtt" activeId={activeId}>
            <MqttSettingsPanel
              wssConnection={wssConnection}
              sceneId={sceneId}
            />
          </SceneControlPanel>
        </div>
      </div>
      <SceneHelpModals />
    </aside>
  );
}
