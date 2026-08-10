// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export type SceneCameraBootstrap = {
  id: string;
  sensorId: string;
  name: string;
  calibrateUrl: string;
  calibrateHref: string;
  cmdTopic: string;
  deleteUrl: string | null;
};

export type SceneSensorBootstrap = {
  id: string;
  sensorId: string;
  name: string;
  iconUrl: string | null;
  areaJson: string;
  calibrateHref: string;
  editHref: string;
  deleteUrl: string | null;
};

export type SceneChildBootstrap = {
  id: string;
  name: string;
  childType: string;
  remoteChildId: string | null;
  detailUrl: string | null;
  thumbnailUrl: string | null;
  mapUrl: string | null;
  /** REST ManageThing uid (local: child scene UUID; remote: remote_child_id). */
  restUid: string;
  editHref: string;
  deleteUrl: string | null;
};

export type SceneDetailBootstrap = {
  scene: {
    id: string;
    name: string;
    scale: number | null;
    mapUrl: string | null;
    thumbnailUrl: string | null;
    wssConnection?: string | null;
  };
  cameras: SceneCameraBootstrap[];
  sensors: SceneSensorBootstrap[];
  children: SceneChildBootstrap[];
  regions: import("./editors/types").RoiLoadJson[];
  tripwires: import("./editors/types").TripwireLoadJson[];
  counts: {
    sensors: number;
    regions: number;
    tripwires: number;
    children: number;
  };
  urls: {
    scenesHome: string;
    scene3d: string;
    sceneEdit: string | null;
    sceneDelete: string | null;
    camCreate: string | null;
  };
  deleteImpact?: {
    sensors: number;
    regions: number;
    tripwires: number;
  };
  scenes?: { id: string; name: string }[];
  authToken: string;
  isSuperuser: boolean;
  /** True when Manager runs in Kubernetes; advanced camera pipeline fields apply. */
  isKubernetes: boolean;
  appVersion: string | null;
};

declare global {
  interface Window {
    ssSceneTelemetry?: {
      setSceneRate?: (hz: string) => void;
      setCameraRate?: (sensorId: string, text: string) => void;
      clearRates?: () => void;
    };
    fitSceneMapDisplay?: () => void;
    numberRois?: () => void;
    numberTripwires?: () => void;
    stringifyRois?: () => void;
    stringifyTripwires?: () => void;
    saveRois?: (values: string[]) => void;
    getRoiValues?: (className: string, kind: string) => string[];
    ssMqttClient?: {
      subscribe: (topic: string) => void;
      publish: (topic: string, payload: string) => void;
      on: (ev: string, fn: (...args: unknown[]) => void) => void;
      removeListener?: (ev: string, fn: (...args: unknown[]) => void) => void;
      off?: (ev: string, fn: (...args: unknown[]) => void) => void;
      end?: (force?: boolean) => void;
    };
    ssEnsureMqttScene?: () => void;
    ssRoiEditors?: {
      addRoi: (payload: {
        svgId: string;
        uuid: string;
        title?: string;
        volumetric?: boolean;
        height?: number;
        buffer_size?: number;
        greenMin?: number;
        yellowMin?: number;
        redMin?: number;
        rangeMax?: number;
        topic?: string;
      }) => void;
      addTripwire: (payload: {
        svgId: string;
        uuid: string;
        title?: string;
        topic?: string;
      }) => void;
      hasRoi?: (svgId: string) => boolean;
      hasTripwire?: (svgId: string) => boolean;
    };
  }
}

export {};
