// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";
import "./MqttSettingsPanel.css";

type Props = {
  wssConnection: string;
  sceneId: string;
  panelsReady: boolean;
};

declare global {
  interface Window {
    ssEnsureMqttScene?: () => void;
  }
}

/**
 * MQTT tab content is Django-rendered (stable #broker / #connect for sscape.js).
 * This hook re-runs MQTT wiring after React adopts the panels.
 */
export function MqttSettingsPanel({
  wssConnection,
  sceneId,
  panelsReady,
}: Props) {
  useEffect(() => {
    if (!panelsReady) {
      return;
    }
    const broker = document.getElementById("broker") as HTMLInputElement | null;
    const topic = document.getElementById("topic") as HTMLInputElement | null;
    if (broker && wssConnection && !broker.value) {
      broker.value = wssConnection;
    }
    if (topic && sceneId && !topic.value) {
      topic.value = `scenescape/regulated/scene/${sceneId}`;
    }
    window.ssEnsureMqttScene?.();
  }, [panelsReady, wssConnection, sceneId]);

  return null;
}
