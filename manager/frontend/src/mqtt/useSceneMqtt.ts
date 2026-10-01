// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef } from "react";
import {
  attachLegacySceneHandlers,
  connectMqtt,
  endMqttClient,
  rewriteBrokerUrl,
  setMqttConnected,
  type MqttClientLike,
} from "./client";

type Options = {
  sceneId: string;
  /** Initial broker URL from bootstrap (may contain localhost). */
  wssConnection: string;
  enabled?: boolean;
};

/**
 * Own scene-detail MQTT connect/disconnect. Sets window.ssMqttClient and
 * attaches legacy Snap handlers so marks/events keep working.
 */
export function useSceneMqtt({
  sceneId,
  wssConnection,
  enabled = true,
}: Options): void {
  const clientRef = useRef<MqttClientLike | null>(null);

  useEffect(() => {
    if (!enabled || !sceneId) {
      return;
    }
    window.ssReactOwnsMqtt = true;

    const brokerInput = document.getElementById(
      "broker",
    ) as HTMLInputElement | null;
    const brokerAddress = document.getElementById("broker-address");

    const rewritten = rewriteBrokerUrl(
      brokerInput?.value || wssConnection || "",
    );
    if (brokerInput) {
      brokerInput.value = rewritten;
    }
    if (brokerAddress) {
      brokerAddress.textContent = window.location.hostname;
    }

    const wireStatus = (client: MqttClientLike) => {
      const onUp = () => {
        if (window.ssMqttClient === client) {
          setMqttConnected(true);
        }
      };
      const onDown = () => {
        // Ignore close from a client that was already replaced.
        if (window.ssMqttClient && window.ssMqttClient !== client) {
          return;
        }
        setMqttConnected(false);
      };
      client.on("connect", onUp);
      client.on("close", onDown);
      if (client.connected) {
        onUp();
      }
    };

    const connect = () => {
      const url =
        rewriteBrokerUrl(brokerInput?.value || wssConnection || "") ||
        rewritten;
      if (brokerInput) {
        brokerInput.value = url;
      }
      console.log("Attempting to connect to " + url);
      endMqttClient(clientRef.current);
      endMqttClient(window.ssMqttClient);
      const client = connectMqtt(url);
      if (!client) {
        return;
      }
      clientRef.current = client;
      window.ssMqttClient = client;
      sessionStorage.setItem("connectToMqtt", "true");
      wireStatus(client);
      attachLegacySceneHandlers(client);
    };

    const disconnect = () => {
      sessionStorage.setItem("connectToMqtt", "false");
      endMqttClient(clientRef.current);
      endMqttClient(window.ssMqttClient);
      clientRef.current = null;
      window.ssMqttClient = undefined;
      setMqttConnected(false);
    };

    const onConnectClick = (ev: Event) => {
      ev.preventDefault();
      connect();
    };
    const onDisconnectClick = (ev: Event) => {
      ev.preventDefault();
      disconnect();
    };

    const connectBtn = document.getElementById("connect");
    const disconnectBtn = document.getElementById("disconnect");
    connectBtn?.addEventListener("click", onConnectClick);
    disconnectBtn?.addEventListener("click", onDisconnectClick);

    let retryTimer: number | undefined;

    const teardown = () => {
      if (retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
      connectBtn?.removeEventListener("click", onConnectClick);
      disconnectBtn?.removeEventListener("click", onDisconnectClick);
      // Tear down on leave; StrictMode remount reconnects via wantConnect.
      const owned = clientRef.current;
      endMqttClient(owned);
      if (window.ssMqttClient === owned) {
        window.ssMqttClient = undefined;
      }
      clientRef.current = null;
      setMqttConnected(false);
      window.ssReactOwnsMqtt = false;
    };

    const wantConnect = sessionStorage.getItem("connectToMqtt") !== "false";
    if (wantConnect) {
      // Broker input may appear when MQTT tab portals in; retry briefly.
      const tryConnect = () => {
        const el = document.getElementById("broker") as HTMLInputElement | null;
        if (el || wssConnection) {
          if (el && !el.value && wssConnection) {
            el.value = rewriteBrokerUrl(wssConnection);
          }
          connect();
          return true;
        }
        return false;
      };
      if (!tryConnect()) {
        retryTimer = window.setTimeout(() => {
          tryConnect();
        }, 200);
      }
    }

    return teardown;
  }, [enabled, sceneId, wssConnection]);
}
