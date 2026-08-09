// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  flushGeometryToHidden,
  getRoiList,
  getTripwireList,
  ingestStringifyRois,
  ingestStringifyTrips,
} from "./geometryModel";

type SsMapApi = {
  fit: () => void;
  numberRois: () => void;
  numberTripwires: () => void;
  stringifyRois: () => void;
  stringifyTripwires: () => void;
  syncFromLegacyStringify: () => void;
  getRois: () => ReturnType<typeof getRoiList>;
  getTripwires: () => ReturnType<typeof getTripwireList>;
  flushHidden: () => void;
};

function callLegacy(name: string): void {
  const fn = (window as unknown as Record<string, unknown>)[name];
  if (typeof fn === "function") {
    (fn as () => void)();
  }
}

/**
 * Stable facade over legacy Snap map helpers. Prefer this over ad-hoc globals.
 */
export function installSsMapFacade(): SsMapApi {
  const api: SsMapApi = {
    fit: () => callLegacy("fitSceneMapDisplay"),
    numberRois: () => callLegacy("numberRois"),
    numberTripwires: () => callLegacy("numberTripwires"),
    stringifyRois: () => {
      callLegacy("stringifyRois");
      api.syncFromLegacyStringify();
    },
    stringifyTripwires: () => {
      callLegacy("stringifyTripwires");
      api.syncFromLegacyStringify();
    },
    syncFromLegacyStringify: () => {
      const roiEl = document.getElementById("id_rois") as HTMLInputElement | null;
      const tripEl = document.getElementById(
        "tripwires",
      ) as HTMLInputElement | null;
      try {
        if (roiEl?.value) {
          ingestStringifyRois(JSON.parse(roiEl.value) as never[]);
        }
        if (tripEl?.value) {
          ingestStringifyTrips(JSON.parse(tripEl.value) as never[]);
        }
      } catch {
        /* ignore bad JSON */
      }
    },
    getRois: () => getRoiList(),
    getTripwires: () => getTripwireList(),
    flushHidden: () => flushGeometryToHidden(),
  };
  window.ssMap = api;
  return api;
}

declare global {
  interface Window {
    ssMap?: SsMapApi;
    fitSceneMapDisplay?: () => void;
    numberRois?: () => void;
    numberTripwires?: () => void;
    stringifyRois?: () => void;
    stringifyTripwires?: () => void;
  }
}
