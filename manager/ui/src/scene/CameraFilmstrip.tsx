// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import type { SceneCameraBootstrap } from "./types";
import "./CameraFilmstrip.css";

type Props = {
  cameras: SceneCameraBootstrap[];
  camCreateUrl: string | null;
};

type Rates = Record<string, string>;

export function CameraFilmstrip({ cameras, camCreateUrl }: Props) {
  const [rates, setRates] = useState<Rates>({});

  useEffect(() => {
    const setCameraRate = (sensorId: string, text: string) => {
      setRates((prev) => {
        if (prev[sensorId] === text) {
          return prev;
        }
        return { ...prev, [sensorId]: text };
      });
    };
    const clearRates = () => setRates({});

    const prev = window.ssSceneTelemetry || {};
    window.ssSceneTelemetry = {
      ...prev,
      setCameraRate,
      clearRates,
    };

    const onRate = (ev: Event) => {
      const detail = (ev as CustomEvent<{ sensorId: string; text: string }>)
        .detail;
      if (detail?.sensorId) {
        setCameraRate(detail.sensorId, detail.text ?? "");
      }
    };
    const onClear = () => clearRates();
    window.addEventListener("ss-camera-rate", onRate);
    window.addEventListener("ss-telemetry-clear", onClear);

    return () => {
      window.removeEventListener("ss-camera-rate", onRate);
      window.removeEventListener("ss-telemetry-clear", onClear);
      if (window.ssSceneTelemetry?.setCameraRate === setCameraRate) {
        const next = { ...window.ssSceneTelemetry };
        delete next.setCameraRate;
        delete next.clearRates;
        window.ssSceneTelemetry = next;
      }
    };
  }, []);

  return (
    <div className="ss-filmstrip hide-fullscreen">
      <div className="ss-filmstrip-header">
        <h3 className="ss-filmstrip-title">Cameras</h3>
        {camCreateUrl ? (
          <a
            className="ss-btn ss-btn--primary ss-btn--sm"
            href={camCreateUrl}
            id="new-camera"
            title="Add a new camera"
          >
            + Camera
          </a>
        ) : null}
      </div>
      {cameras.length === 0 ? (
        <p className="ss-filmstrip-empty">No cameras in this scene yet.</p>
      ) : (
        <ul className="ss-filmstrip-list">
          {cameras.map((cam) => (
            <li key={cam.id} className="ss-filmstrip-card">
              <a href={cam.calibrateUrl} className="ss-filmstrip-link">
                <span className="ss-filmstrip-name">{cam.name}</span>
                <span className="ss-filmstrip-id">{cam.sensorId}</span>
                <span
                  className="ss-filmstrip-rate rate"
                  data-sensor-id={cam.sensorId}
                  id={`rate-${cam.sensorId}`}
                >
                  {rates[cam.sensorId] || "--"}
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
