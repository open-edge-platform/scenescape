// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";

/**
 * MQTT connected flag mirrored from #mqtt_status (legacy jQuery toggles the class).
 */
export function useMqttConnected(): boolean {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const sync = () => {
      const el = document.getElementById("mqtt_status");
      const next = Boolean(el?.classList.contains("connected"));
      setConnected((prev) => (prev === next ? prev : next));
    };
    sync();
    const el = document.getElementById("mqtt_status");
    let mo: MutationObserver | null = null;
    if (el) {
      mo = new MutationObserver(sync);
      mo.observe(el, { attributes: true, attributeFilter: ["class"] });
    }
    const onEvt = (ev: Event) => {
      const detail = (ev as CustomEvent<{ connected?: boolean }>).detail;
      if (typeof detail?.connected === "boolean") {
        setConnected((prev) =>
          prev === detail.connected ? prev : Boolean(detail.connected),
        );
      } else {
        sync();
      }
    };
    window.addEventListener("ss-mqtt-status", onEvt);
    return () => {
      mo?.disconnect();
      window.removeEventListener("ss-mqtt-status", onEvt);
    };
  }, []);

  return connected;
}

/**
 * Camera rates keyed by sensor id (ssSceneTelemetry + ss-camera-rate events).
 */
export function useCameraRates(): Record<string, string> {
  const [rates, setRates] = useState<Record<string, string>>({});

  useEffect(() => {
    const apply = (sensorId: string, text: string) => {
      setRates((prev) => {
        if (prev[sensorId] === text) {
          return prev;
        }
        return { ...prev, [sensorId]: text };
      });
    };

    const setCameraRate = (sensorId: string, text: string) => {
      apply(sensorId, text);
    };
    const clearRates = () => setRates({});

    window.ssSceneTelemetry = {
      ...(window.ssSceneTelemetry || {}),
      setCameraRate,
      clearRates,
    };

    const onRate = (ev: Event) => {
      const detail = (ev as CustomEvent<{ sensorId?: string; text?: string; hz?: string }>)
        .detail;
      if (!detail?.sensorId) {
        return;
      }
      apply(detail.sensorId, detail.text || detail.hz || "--");
    };
    const onClear = () => clearRates();
    window.addEventListener("ss-camera-rate", onRate);
    window.addEventListener("ss-telemetry-clear", onClear);
    return () => {
      window.removeEventListener("ss-camera-rate", onRate);
      window.removeEventListener("ss-telemetry-clear", onClear);
    };
  }, []);

  return rates;
}
