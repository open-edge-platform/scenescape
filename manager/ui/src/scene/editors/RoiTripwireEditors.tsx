// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { RegionEditorCard } from "./RegionEditorCard";
import { TripwireEditorCard } from "./TripwireEditorCard";
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
  initialRegions: RoiLoadJson[];
  initialTripwires: TripwireLoadJson[];
};

function syncLegacySave(id: string, dirty: boolean): void {
  const el = document.getElementById(id) as
    | HTMLButtonElement
    | HTMLInputElement
    | null;
  if (!el) {
    return;
  }
  el.disabled = !dirty;
  el.setAttribute("aria-disabled", dirty ? "false" : "true");
  el.title = dirty ? "Save unsaved changes" : "No unsaved changes";
  el.classList.toggle("ss-save-clean", !dirty);
  el.classList.toggle("ss-save-dirty", dirty);
}

/**
 * React ROI / tripwire field cards. Tracks dirty state for legacy Save buttons.
 */
export function RoiTripwireEditors({
  sceneId,
  isSuperuser,
  initialRegions,
  initialTripwires,
}: Props) {
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
    syncLegacySave("save-rois", roiDirty);
  }, [roiDirty]);

  useEffect(() => {
    syncLegacySave("save-trips", tripDirty);
  }, [tripDirty]);

  useEffect(() => {
    /* Baseline hidden JSON after legacy map init; then watch for geometry edits. */
    const roiInput = document.getElementById("id_rois") as HTMLInputElement | null;
    const tripInput = document.getElementById(
      "tripwires",
    ) as HTMLInputElement | null;
    let roiBase = roiInput?.value ?? "";
    let tripBase = tripInput?.value ?? "";
    const arm = window.setTimeout(() => {
      roiBase = roiInput?.value ?? "";
      tripBase = tripInput?.value ?? "";
    }, 1200);
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
    };
  }, []);

  useEffect(() => {
    const addRoi = (payload: Partial<RoiEntity> & { svgId: string; uuid: string }) => {
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
      const detail = (
        ev as CustomEvent<Parameters<typeof addTripwire>[0]>
      ).detail;
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
    document.getElementById(svgId)?.remove();
    setRois((prev) => prev.filter((r) => r.svgId !== svgId));
    window.requestAnimationFrame(() => {
      window.numberRois?.();
      window.stringifyRois?.();
      const values = window.getRoiValues?.(
        "form-control roi-title",
        "roi",
      ) as string[] | undefined;
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
    document.getElementById(svgId)?.remove();
    setTripwires((prev) => prev.filter((t) => t.svgId !== svgId));
    window.requestAnimationFrame(() => {
      window.numberTripwires?.();
      window.stringifyTripwires?.();
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
