// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";
import "./MqttSettingsPanel.css";

type Props = {
  wssConnection: string;
  sceneId: string;
};

declare global {
  interface Window {
    ssEnsureMqttScene?: () => void;
  }
}

/**
 * MQTT tab content with hard-contract ids (#broker, #connect, …) for sscape.js.
 */
export function MqttSettingsPanel({ wssConnection, sceneId }: Props) {
  useEffect(() => {
    window.ssEnsureMqttScene?.();
  }, [wssConnection, sceneId]);

  const topicDefault = sceneId
    ? `scenescape/regulated/scene/${sceneId}`
    : "scenescape/regulated/scene/";

  return (
    <div className="ss-mqtt-settings" id="ss-mqtt-mount">
      <div className="ss-mqtt-settings-grid">
        <div className="ss-mqtt-settings-controls">
          <div className="ss-mqtt-field">
            <label className="ss-mqtt-label" htmlFor="broker" id="label-broker">
              WSS Connection
            </label>
            <input
              type="text"
              className="form-control"
              id="broker"
              aria-labelledby="label-broker"
              defaultValue={wssConnection}
            />
          </div>
          <div className="ss-mqtt-field">
            <label className="ss-mqtt-label" htmlFor="topic" id="label-topic">
              Scene Data Topic
            </label>
            <input
              type="text"
              className="form-control"
              id="topic"
              aria-labelledby="label-topic"
              defaultValue={topicDefault}
            />
          </div>
          <div className="ss-mqtt-actions">
            <button type="button" className="ss-btn ss-btn--primary" id="connect">
              Connect
            </button>
            <button
              type="button"
              className="ss-btn ss-btn--secondary"
              id="disconnect"
            >
              Disconnect
            </button>
          </div>
        </div>
        <table className="table table-bordered table-sm ss-mqtt-client-table">
          <thead>
            <tr>
              <th colSpan={2}>Client Settings</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Broker</th>
              <td id="broker-address" />
            </tr>
            <tr>
              <th scope="row">Validate Certificate</th>
              <td>Off</td>
            </tr>
            <tr>
              <th scope="row">Encryption (TLS)</th>
              <td>On</td>
            </tr>
            <tr>
              <th scope="row">Protocol</th>
              <td>mqtt://</td>
            </tr>
            <tr>
              <th scope="row">Port</th>
              <td>1883</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
