// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { RegionEditorCard } from "./RegionEditorCard";
import { TripwireEditorCard } from "./TripwireEditorCard";
import { persistSceneGeometry } from "../../lib/roiPersist";
import { useAppToast } from "../../components/ToastProvider";
import { installSsMapFacade } from "../map/ssMap";
import {
  removeRoi as modelRemoveRoi,
  removeTripwire as modelRemoveTrip,
  upsertRoiMeta,
  upsertTripMeta,
} from "../map/geometryModel";
import {
  roiFromLoad,
  tripwireFromLoad,
  type RoiEntity,
  type RoiLoadJson,
  type TripwireEntity,
  type TripwireLoadJson,
} from "./types";
import "./editors.css";

type Props = {
  sceneId: string;
  isSuperuser: boolean;
  authToken: string;
  initialRegions: RoiLoadJson[];
  initialTripwires: TripwireLoadJson[];
};

function syncLegacySave(id: string, dirty: boolean): void {
  const el = document.getElementById(id) as
    HTMLButtonElement | HTMLInputElement | null;
  if (!el) {
    return;
  }
  el.disabled = !dirty;
  el.setAttribute("aria-disabled", dirty ? "false" : "true");
  el.title = dirty ? "Save unsaved changes" : "No unsaved changes";
  el.classList.toggle("ss-save-clean", !dirty);
  el.classList.toggle("ss-save-dirty", dirty);
}

function pushRoiToModel(roi: RoiEntity, points?: number[][]): void {
  upsertRoiMeta(roi.uuid, {
    title: roi.title,
    volumetric: roi.volumetric,
    height: roi.height,
    buffer_size: roi.buffer_size,
    range_max: roi.rangeMax,
    sectors: [
      { color: "green", color_min: roi.greenMin },
      { color: "yellow", color_min: roi.yellowMin },
      { color: "red", color_min: roi.redMin },
    ],
    ...(points
      ? {
          points: points.map(
            (p) => [Number(p[0]), Number(p[1])] as [number, number],
          ),
        }
      : {}),
  });
}

/**
 * React ROI / tripwire field cards. Tracks dirty state for legacy Save buttons.
 * Metadata lives in the typed geometry model; map still owns pixel editing.
 */
export function RoiTripwireEditors({
  sceneId,
  isSuperuser,
  authToken,
  initialRegions,
  initialTripwires,
}: Props) {
  const toast = useAppToast();
  const [rois, setRois] = useState<RoiEntity[]>(() =>
    initialRegions
      .map((r) => roiFromLoad(r, sceneId))
      .filter((r): r is RoiEntity => Boolean(r)),
  );
  const [tripwires, setTripwires] = useState<TripwireEntity[]>(() =>
    initialTripwires
      .map((t) => tripwireFromLoad(t, sceneId))
      .filter((t): t is TripwireEntity => Boolean(t)),
  );
  const [roiDirty, setRoiDirty] = useState(false);
  const [tripDirty, setTripDirty] = useState(false);

  const roisRef = useRef(rois);
  const tripsRef = useRef(tripwires);
  roisRef.current = rois;
  tripsRef.current = tripwires;

  useEffect(() => {
    installSsMapFacade();
    initialRegions.forEach((raw) => {
      const uuid = String(raw.uuid || "").trim();
      if (!uuid) {
        return;
      }
      const entity = roiFromLoad(raw, sceneId);
      if (!entity) {
        return;
      }
      pushRoiToModel(entity, raw.points);
    });
    initialTripwires.forEach((raw) => {
      const uuid = String(raw.uuid || "").trim();
      if (!uuid) {
        return;
      }
      upsertTripMeta(uuid, {
        title: (raw.title || "").trim(),
        points: (raw.points || []).map(
          (p) => [Number(p[0]), Number(p[1])] as [number, number],
        ),
      });
    });
  }, [initialRegions, initialTripwires, sceneId]);

  useEffect(() => {
    const persist = async (options?: { preferHidden?: boolean } | string[]) => {
      const opts = options && !Array.isArray(options) ? options : undefined;
      if (opts?.preferHidden) {
        window.ssMap?.syncFromLegacyStringify?.();
      } else if (!window.ssUseReactMap) {
        window.ssMap?.stringifyRois();
        window.ssMap?.stringifyTripwires();
      } else {
        window.ssMap?.flushHidden();
      }
      await persistSceneGeometry(authToken, sceneId, opts);
      toast.show("Regions saved", "ok");
      window.location.reload();
    };
    window.ssPersistGeometry = persist;
    return () => {
      if (window.ssPersistGeometry === persist) {
        delete window.ssPersistGeometry;
      }
    };
  }, [authToken, sceneId, toast]);

  useEffect(() => {
    syncLegacySave("save-rois", roiDirty);
  }, [roiDirty]);

  useEffect(() => {
    syncLegacySave("save-trips", tripDirty);
  }, [tripDirty]);

  useEffect(() => {
    /* Baseline hidden JSON after legacy map init; then watch for geometry edits. */
    const roiInput = document.getElementById(
      "id_rois",
    ) as HTMLInputElement | null;
    const tripInput = document.getElementById(
      "tripwires",
    ) as HTMLInputElement | null;
    let roiBase = roiInput?.value ?? "";
    let tripBase = tripInput?.value ?? "";
    const arm = window.setTimeout(() => {
      roiBase = roiInput?.value ?? "";
      tripBase = tripInput?.value ?? "";
      window.ssMap?.syncFromLegacyStringify();
    }, 1200);
    const onGeom = () => {
      setRoiDirty(true);
      setTripDirty(true);
    };
    window.addEventListener("ss-geometry-stringified", onGeom);
    const poll = window.setInterval(() => {
      if (roiInput && roiInput.value !== roiBase) {
        setRoiDirty(true);
      }
      if (tripInput && tripInput.value !== tripBase) {
        setTripDirty(true);
      }
    }, 600);
    return () => {
      window.clearTimeout(arm);
      window.clearInterval(poll);
      window.removeEventListener("ss-geometry-stringified", onGeom);
    };
  }, []);

  useEffect(() => {
    const addRoi = (
      payload: Partial<RoiEntity> & { svgId: string; uuid: string },
    ) => {
      setRois((prev) => {
        if (prev.some((r) => r.svgId === payload.svgId)) {
          return prev;
        }
        return [
          ...prev,
          {
            svgId: payload.svgId,
            uuid: payload.uuid,
            title: payload.title || "",
            volumetric: payload.volumetric ?? false,
            height: payload.height ?? 1.0,
            buffer_size: payload.buffer_size ?? 0.0,
            greenMin: payload.greenMin ?? 0,
            yellowMin: payload.yellowMin ?? 2,
            redMin: payload.redMin ?? 5,
            rangeMax: payload.rangeMax ?? 10,
            topic:
              payload.topic ||
              `scenescape/event/region/${sceneId}/${payload.uuid}/count`,
          },
        ];
      });
      setRoiDirty(true);
      window.requestAnimationFrame(() => {
        window.numberRois?.();
      });
    };

    const addTripwire = (
      payload: Partial<TripwireEntity> & { svgId: string; uuid: string },
    ) => {
      setTripwires((prev) => {
        if (prev.some((t) => t.svgId === payload.svgId)) {
          return prev;
        }
        return [
          ...prev,
          {
            svgId: payload.svgId,
            uuid: payload.uuid,
            title: payload.title || "",
            topic:
              payload.topic ||
              `scenescape/event/tripwire/${sceneId}/${payload.uuid}/objects`,
          },
        ];
      });
      setTripDirty(true);
      window.requestAnimationFrame(() => {
        window.numberTripwires?.();
      });
    };

    window.ssRoiEditors = {
      addRoi,
      addTripwire,
      hasRoi: (svgId: string) => roisRef.current.some((r) => r.svgId === svgId),
      hasTripwire: (svgId: string) =>
        tripsRef.current.some((t) => t.svgId === svgId),
    };

    const onRoiAdd = (ev: Event) => {
      const detail = (ev as CustomEvent<Parameters<typeof addRoi>[0]>).detail;
      if (detail?.svgId) {
        addRoi(detail);
      }
    };
    const onTripAdd = (ev: Event) => {
      const detail = (ev as CustomEvent<Parameters<typeof addTripwire>[0]>)
        .detail;
      if (detail?.svgId) {
        addTripwire(detail);
      }
    };
    window.addEventListener("ss-roi-form-add", onRoiAdd);
    window.addEventListener("ss-tripwire-form-add", onTripAdd);

    return () => {
      window.removeEventListener("ss-roi-form-add", onRoiAdd);
      window.removeEventListener("ss-tripwire-form-add", onTripAdd);
      delete window.ssRoiEditors;
    };
  }, [sceneId]);

  useEffect(() => {
    const noRegions = document.getElementById("no-regions");
    if (noRegions) {
      noRegions.style.display = rois.length ? "none" : "";
    }
  }, [rois.length]);

  useEffect(() => {
    const noTrips = document.getElementById("no-tripwires");
    if (noTrips) {
      noTrips.style.display = tripwires.length ? "none" : "";
    }
  }, [tripwires.length]);

  useEffect(() => {
    const empty = document.getElementById("no-regions");
    if (!empty) {
      return;
    }
    empty.hidden = rois.length > 0;
    if (rois.length === 0) {
      empty.innerHTML = "";
      const p = document.createElement("p");
      p.textContent = "No regions of interest defined.";
      empty.appendChild(p);
      if (isSuperuser) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-primary btn-sm";
        btn.id = "empty-new-roi";
        btn.textContent = "+ New Region";
        empty.appendChild(btn);
      }
    }
  }, [rois.length, isSuperuser]);

  useEffect(() => {
    const empty = document.getElementById("no-tripwires");
    if (!empty) {
      return;
    }
    empty.hidden = tripwires.length > 0;
    if (tripwires.length === 0) {
      empty.innerHTML = "";
      const p = document.createElement("p");
      p.textContent = "No tripwires defined.";
      empty.appendChild(p);
      if (isSuperuser) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-primary btn-sm";
        btn.id = "empty-new-tripwire";
        btn.textContent = "+ New Tripwire";
        empty.appendChild(btn);
      }
    }
  }, [tripwires.length, isSuperuser]);

  const removeRoi = async (svgId: string) => {
    const ok = window.ssConfirm
      ? await window.ssConfirm({
          title: "Remove region?",
          message: "Are you sure you wish to remove this ROI?",
          confirmLabel: "Remove",
          danger: true,
        })
      : window.confirm("Are you sure you wish to remove this ROI?");
    if (!ok) {
      return;
    }
    const uuid = svgId.replace(/^roi_/, "");
    document.getElementById(svgId)?.remove();
    modelRemoveRoi(uuid);
    setRois((prev) => prev.filter((r) => r.svgId !== svgId));
    window.requestAnimationFrame(() => {
      window.ssMap?.numberRois();
      window.ssMap?.stringifyRois();
      const values = window.getRoiValues?.("form-control roi-title", "roi") as
        string[] | undefined;
      if (values && window.saveRois) {
        window.saveRois(values);
      }
    });
  };

  const removeTripwire = async (svgId: string) => {
    const ok = window.ssConfirm
      ? await window.ssConfirm({
          title: "Remove tripwire?",
          message: "Are you sure you wish to remove this tripwire?",
          confirmLabel: "Remove",
          danger: true,
        })
      : window.confirm("Are you sure you wish to remove this tripwire?");
    if (!ok) {
      return;
    }
    const uuid = svgId.replace(/^tripwire_/, "");
    document.getElementById(svgId)?.remove();
    modelRemoveTrip(uuid);
    setTripwires((prev) => prev.filter((t) => t.svgId !== svgId));
    window.requestAnimationFrame(() => {
      window.ssMap?.numberTripwires();
      window.ssMap?.stringifyTripwires();
      const values = window.getRoiValues?.(
        "form-control tripwire-title",
        "tripwire",
      ) as string[] | undefined;
      if (values && window.saveRois) {
        window.saveRois(values);
      }
    });
  };

  const roiHost = document.getElementById("roi-fields");
  const tripHost = document.getElementById("tripwire-fields");

  return (
    <>
      {roiHost
        ? createPortal(
            <>
              {rois.map((roi, index) => (
                <RegionEditorCard
                  key={roi.svgId}
                  roi={roi}
                  index={index}
                  isSuperuser={isSuperuser}
                  onChange={(next) => {
                    setRoiDirty(true);
                    pushRoiToModel(next);
                    setRois((prev) =>
                      prev.map((r) => (r.svgId === next.svgId ? next : r)),
                    );
                  }}
                  onRemove={removeRoi}
                />
              ))}
            </>,
            roiHost,
          )
        : null}
      {tripHost
        ? createPortal(
            <>
              {tripwires.map((trip, index) => (
                <TripwireEditorCard
                  key={trip.svgId}
                  tripwire={trip}
                  index={index}
                  isSuperuser={isSuperuser}
                  onChange={(next) => {
                    setTripDirty(true);
                    upsertTripMeta(next.uuid, { title: next.title });
                    setTripwires((prev) =>
                      prev.map((t) => (t.svgId === next.svgId ? next : t)),
                    );
                  }}
                  onRemove={removeTripwire}
                />
              ))}
            </>,
            tripHost,
          )
        : null}
    </>
  );
}
