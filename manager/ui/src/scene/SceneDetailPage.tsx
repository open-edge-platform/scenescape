// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import {
  SCENE_TAB_COUNTS_EVENT,
  type SceneTabCounts,
} from "../lib/sceneTab";
import { PageHeader } from "../components/PageHeader";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ToastProvider } from "../components/ToastProvider";
import { LegacyConfirmHost } from "../components/LegacyConfirmHost";
import { SceneMapPane } from "./SceneMapPane";
import { SceneSidePanel } from "./SceneSidePanel";
import { RoiTripwireEditors } from "./editors/RoiTripwireEditors";
import { SceneWorkspaceSheets } from "../sheets/SceneWorkspaceSheets";
import { postDjangoDelete } from "../lib/djangoDelete";
import { useWorkspaceLayout } from "./useWorkspaceLayout";
import type { WorkspaceLayoutMode } from "./useWorkspaceLayout";
import { useWorkspaceDensity } from "./useWorkspaceDensity";
import { WorkspaceSplitter } from "./WorkspaceSplitter";
import { useMqttConnected, useCameraRates } from "./useLiveChrome";
import type { SceneDetailBootstrap } from "./types";
import type { TabItem } from "../components/Tabs";
import "./SceneDetailPage.css";

type Props = {
  bootstrap: SceneDetailBootstrap;
};

function countLabel(n: number): string {
  return String(n);
}

function sceneDetailBack(urls: SceneDetailBootstrap["urls"]): {
  href: string;
  label: string;
} {
  const from =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("from")
      : null;
  if (from === "cam-list" && urls.camList) {
    return { href: urls.camList, label: "Cameras" };
  }
  if (from === "sensor-list" && urls.sensorList) {
    return { href: urls.sensorList, label: "Sensors" };
  }
  return { href: urls.scenesHome, label: "Scenes" };
}

const LAYOUT_OPTIONS: {
  mode: WorkspaceLayoutMode;
  label: string;
  title: string;
  icon: string;
}[] = [
  {
    mode: "auto",
    label: "Auto",
    title: "Automatic tab layout from map and screen size",
    icon: "bi-magic",
  },
  {
    mode: "stack",
    label: "Below",
    title: "Tabs below the map",
    icon: "bi-distribute-vertical",
  },
  {
    mode: "row",
    label: "Side",
    title: "Tabs beside the map",
    icon: "bi-layout-sidebar-reverse",
  },
];

function SceneDetailInner({ bootstrap }: Props) {
  const { scene, urls, isSuperuser } = bootstrap;
  const { layout, mode, setMode, autoLayout } = useWorkspaceLayout();
  const { panelSizePx, setPanelSizePx, mapFocus, toggleMapFocus } =
    useWorkspaceDensity(layout);
  const [sceneRate, setSceneRate] = useState("--");
  const [sceneDeleteOpen, setSceneDeleteOpen] = useState(false);
  const [sceneDeleteBusy, setSceneDeleteBusy] = useState(false);
  const [sceneDeleteError, setSceneDeleteError] = useState<string | null>(null);
  const mqttConnected = useMqttConnected();
  const cameraRates = useCameraRates();
  const [cameras, setCameras] = useState(bootstrap.cameras);
  const [sensors, setSensors] = useState(bootstrap.sensors || []);
  const [childrenLinks, setChildrenLinks] = useState(bootstrap.children || []);
  const [tabCounts, setTabCounts] = useState({
    cameras: bootstrap.cameras.length,
    sensors: bootstrap.counts.sensors,
    regions: bootstrap.counts.regions,
    tripwires: bootstrap.counts.tripwires,
    children: bootstrap.counts.children,
  });

  /*
   * Prefer React SVG map when a map URL is available (Phase 4 dual-run).
   * Set during render (not an effect) so it's already true before
   * SceneMapPane's own mount effect reads it — child effects run before
   * parent effects, so an effect here would race the first render.
   */
  window.ssUseReactMap = Boolean(scene.mapUrl);

  useEffect(() => {
    const setSceneRateCb = (hz: string) => setSceneRate(hz || "--");
    window.ssSceneTelemetry = {
      ...(window.ssSceneTelemetry || {}),
      setSceneRate: setSceneRateCb,
    };
    const onSceneRate = (ev: Event) => {
      const detail = (ev as CustomEvent<{ hz: string }>).detail;
      if (detail?.hz !== undefined) {
        setSceneRateCb(detail.hz);
      }
    };
    const onClear = () => setSceneRate("--");
    window.addEventListener("ss-scene-rate", onSceneRate);
    window.addEventListener("ss-telemetry-clear", onClear);
    return () => {
      window.removeEventListener("ss-scene-rate", onSceneRate);
      window.removeEventListener("ss-telemetry-clear", onClear);
    };
  }, []);

  useEffect(() => {
    const onCounts = (ev: Event) => {
      const detail = (ev as CustomEvent<SceneTabCounts>).detail;
      if (!detail || typeof detail !== "object") {
        return;
      }
      setTabCounts((prev) => {
        const next = { ...prev };
        (["cameras", "sensors", "regions", "tripwires", "children"] as const).forEach(
          (key) => {
            const n = detail[key];
            if (typeof n === "number" && Number.isFinite(n) && n >= 0) {
              next[key] = n;
            }
          },
        );
        return next;
      });
    };
    window.addEventListener(SCENE_TAB_COUNTS_EVENT, onCounts);
    return () => window.removeEventListener(SCENE_TAB_COUNTS_EVENT, onCounts);
  }, []);

  useEffect(() => {
    const id = window.requestAnimationFrame(() => {
      if (typeof window.fitSceneMapDisplay === "function") {
        window.fitSceneMapDisplay();
      }
    });
    return () => window.cancelAnimationFrame(id);
  }, [mapFocus, panelSizePx, layout]);

  const confirmSceneDelete = useCallback(async () => {
    if (!urls.sceneDelete) {
      return;
    }
    setSceneDeleteBusy(true);
    setSceneDeleteError(null);
    try {
      await postDjangoDelete(urls.sceneDelete, urls.scenesHome || "/");
    } catch (e) {
      setSceneDeleteBusy(false);
      setSceneDeleteError(e instanceof Error ? e.message : "Delete failed");
    }
  }, [urls.sceneDelete, urls.scenesHome]);

  const tabs: TabItem[] = [
    { id: "cameras", label: "Cameras", count: countLabel(tabCounts.cameras) },
    {
      id: "sensors",
      label: "Sensors",
      count: countLabel(tabCounts.sensors),
    },
    {
      id: "regions",
      label: "Regions",
      count: countLabel(tabCounts.regions),
    },
    {
      id: "tripwires",
      label: "Tripwires",
      count: countLabel(tabCounts.tripwires),
    },
    {
      id: "children",
      label: "Children",
      count: countLabel(tabCounts.children),
    },
    {
      id: "mqtt",
      label: "MQTT",
      extra: (
        <span
          id="mqtt_status"
          className={`scene-detail-mqtt-pill${mqttConnected ? " connected" : ""}`}
          title={mqttConnected ? "MQTT connected" : "MQTT disconnected"}
          data-ss-mqtt={mqttConnected ? "connected" : "disconnected"}
        >
          <i className="bi bi-arrow-down-up" aria-hidden="true" />
          <span className="ss-mqtt-label">
            {mqttConnected ? "MQTT" : "MQTT"}
          </span>
        </span>
      ),
    },
  ];

  const actions = (
    <>
      <div className="scene-rate ss-scene-rate">
        Rate: <span id="scene-rate">{sceneRate}</span> Hz
      </div>
      <div
        className="ss-layout-toggle"
        role="group"
        aria-label="Control panel layout"
      >
        {LAYOUT_OPTIONS.map((opt) => {
          const active = mode === opt.mode;
          const hint = opt.mode === "auto" ? ` (now ${autoLayout})` : "";
          return (
            <button
              key={opt.mode}
              type="button"
              className={`ss-layout-toggle-btn${active ? " is-active" : ""}`}
              title={`${opt.title}${hint}`}
              aria-pressed={active}
              onClick={() => setMode(opt.mode)}
            >
              <i className={`bi ${opt.icon}`} aria-hidden="true" />
              <span className="ss-layout-toggle-label">{opt.label}</span>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        className={`ss-layout-toggle-btn ss-map-focus-btn${mapFocus ? " is-active" : ""}`}
        title={mapFocus ? "Show control panel (Esc)" : "Map only focus"}
        aria-pressed={mapFocus}
        onClick={toggleMapFocus}
      >
        <i
          className={`bi ${mapFocus ? "bi-layout-sidebar" : "bi-arrows-fullscreen"}`}
          aria-hidden="true"
        />
        <span className="ss-layout-toggle-label">
          {mapFocus ? "Panel" : "Map"}
        </span>
      </button>
      <a
        className="btn btn-secondary btn-sm"
        id="export-scene"
        href="#"
        title={`Export ${scene.name}`}
      >
        <i className="bi bi-box-arrow-up" aria-hidden="true" />
      </a>
      <a
        className="btn btn-secondary btn-sm"
        id="3d-view"
        href={urls.scene3d}
        title={`View ${scene.name} in 3D`}
      >
        3D
      </a>
      {isSuperuser ? (
        <a
          className="btn btn-secondary btn-sm"
          id="scene-edit"
          href="?ss=scene-manage"
          title={`Edit ${scene.name}`}
        >
          <i className="bi bi-pencil" aria-hidden="true" />
        </a>
      ) : null}
      {isSuperuser && urls.sceneDelete ? (
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          id="scene-delete"
          title={`Delete ${scene.name}`}
          onClick={() => {
            setSceneDeleteError(null);
            setSceneDeleteOpen(true);
          }}
        >
          <i className="bi bi-trash" aria-hidden="true" />
        </button>
      ) : null}
    </>
  );

  const deleteImpact = bootstrap.deleteImpact;

  return (
    <div
      className={`ss-scene-detail ss-scene-detail--workspace ss-workspace--${layout}${mapFocus ? " ss-workspace--map-focus" : ""}`}
      data-workspace-layout={layout}
      data-workspace-mode={mode}
      data-map-focus={mapFocus ? "1" : "0"}
      style={
        {
          "--ss-panel-size": `${panelSizePx}px`,
        } as CSSProperties
      }
    >
      <PageHeader
        title={scene.name}
        back={sceneDetailBack(urls)}
        actions={actions}
      />
      <div className="ss-workspace-body">
        <div className="ss-workspace-main">
          <SceneMapPane mapUrl={scene.mapUrl} />
        </div>
        <WorkspaceSplitter
          layout={layout}
          panelSizePx={panelSizePx}
          onResize={setPanelSizePx}
          disabled={mapFocus}
        />
        <SceneSidePanel
          tabs={tabs}
          cameraRates={cameraRates}
          cameras={cameras}
          sensors={sensors}
          childrenLinks={childrenLinks}
          isSuperuser={isSuperuser}
          sceneId={scene.id}
          wssConnection={bootstrap.scene.wssConnection || ""}
          authToken={bootstrap.authToken}
          onSensorsChange={setSensors}
        />
      </div>
      <RoiTripwireEditors
        sceneId={scene.id}
        isSuperuser={isSuperuser}
        authToken={bootstrap.authToken}
        initialRegions={bootstrap.regions || []}
        initialTripwires={bootstrap.tripwires || []}
      />
      <SceneWorkspaceSheets
        sceneId={scene.id}
        authToken={bootstrap.authToken}
        isSuperuser={isSuperuser}
        isKubernetes={Boolean(bootstrap.isKubernetes)}
        scenes={bootstrap.scenes || []}
        cameras={cameras}
        sensors={sensors}
        onCamerasChange={setCameras}
        onSensorsChange={setSensors}
        onChildrenChange={setChildrenLinks}
        mapUrl={scene.mapUrl}
        mapScale={scene.scale}
      />
      <ConfirmDialog
        open={sceneDeleteOpen}
        title="Delete scene?"
        confirmLabel="Delete scene"
        danger
        busy={sceneDeleteBusy}
        onConfirm={confirmSceneDelete}
        onCancel={() => {
          if (!sceneDeleteBusy) {
            setSceneDeleteOpen(false);
          }
        }}
      >
        <p>
          Are you sure you want to delete <strong>{scene.name}</strong>?
        </p>
        <p>If you proceed, the following cannot be undone:</p>
        <ul>
          <li>The scene will be permanently deleted</li>
          {(deleteImpact?.sensors ?? 0) > 0 ? (
            <li>
              {deleteImpact?.sensors} camera(s) and/or sensor(s) will be
              orphaned
            </li>
          ) : null}
          {(deleteImpact?.regions ?? 0) > 0 ? (
            <li>{deleteImpact?.regions} region(s) will be deleted</li>
          ) : null}
          {(deleteImpact?.tripwires ?? 0) > 0 ? (
            <li>{deleteImpact?.tripwires} tripwire(s) will be deleted</li>
          ) : null}
        </ul>
        {sceneDeleteError ? (
          <p className="ss-confirm-error">{sceneDeleteError}</p>
        ) : null}
      </ConfirmDialog>
    </div>
  );
}

export function SceneDetailPage({ bootstrap }: Props) {
  return (
    <ToastProvider>
      <LegacyConfirmHost>
        <SceneDetailInner bootstrap={bootstrap} />
      </LegacyConfirmHost>
    </ToastProvider>
  );
}
