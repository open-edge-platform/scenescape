// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef } from "react";
import {
  mqttPayloadToJson,
  type MqttClientLike,
} from "./client";
import { APP_NAME, CMD_CAMERA, IMAGE_CAMERA, cameraImageTopic } from "./topics";

function isLiveViewEnabled(): boolean {
  const el = document.getElementById("live-view") as HTMLInputElement | null;
  return Boolean(el?.checked);
}

function cameraStripHasPreview(img: HTMLImageElement): boolean {
  if (img.classList.contains("display-none")) {
    return false;
  }
  const src = img.currentSrc || img.getAttribute("src") || "";
  if (!src || src.includes("offline.png")) {
    return false;
  }
  return img.naturalWidth > 0 || src.startsWith("data:image");
}

function publishGetImages(client: MqttClientLike): void {
  const imgs = document.querySelectorAll<HTMLImageElement>(".snapshot-image");
  if (!imgs.length) {
    return;
  }
  try {
    client.subscribe(cameraImageTopic());
  } catch {
    /* already subscribed */
  }
  const topics = new Set<string>();
  imgs.forEach((img) => {
    const primary =
      img.getAttribute("data-topic") || img.getAttribute("topic") || "";
    const byName = img.getAttribute("data-topic-name") || "";
    if (primary) {
      topics.add(primary);
    }
    if (byName) {
      topics.add(byName);
    }
  });
  topics.forEach((topic) => {
    client.publish(topic, "getimage");
  });
}

function applyCameraFrame(sensorId: string, imageB64: string): void {
  const live = isLiveViewEnabled();
  const previewImgs = document.querySelectorAll<HTMLImageElement>(
    `[id='${sensorId}'], [id='card-preview-${sensorId}'], [data-ss-card-sensor='${sensorId}'], [data-ss-card-name='${sensorId}']`,
  );
  previewImgs.forEach((img) => {
    if (!live && cameraStripHasPreview(img)) {
      return;
    }
    img.setAttribute("src", `data:image/jpeg;base64,${imageB64}`);
    img.classList.remove("display-none");
    img.parentElement?.querySelectorAll(".cam-offline").forEach((el) => {
      const node = el as HTMLElement;
      node.style.display = "none";
      node.hidden = true;
    });
  });
  if (live && window.ssMqttClient) {
    window.ssMqttClient.publish(
      `${APP_NAME}${CMD_CAMERA}${sensorId}`,
      "getimage",
    );
  }
}

/**
 * Own camera-strip getimage / JPEG frames when React scene map is active.
 */
export function useCameraStripMqtt(enabled = true): void {
  const boundClientRef = useRef<MqttClientLike | null>(null);
  const onMessageRef = useRef<(topic: unknown, data: unknown) => void>(
    () => undefined,
  );

  useEffect(() => {
    if (!enabled) {
      return;
    }
    window.ssReactOwnsCameraStrip = true;

    const onMessage = (topic: unknown, data: unknown) => {
      const t = String(topic || "");
      if (!t.includes(IMAGE_CAMERA)) {
        return;
      }
      const parsed = mqttPayloadToJson(data);
      if (!parsed || typeof parsed !== "object") {
        return;
      }
      const msg = parsed as { image?: string };
      if (!msg.image || !document.querySelector(".snapshot-image")) {
        return;
      }
      const id = t.split("camera/")[1];
      if (!id) {
        return;
      }
      applyCameraFrame(id, msg.image);
    };
    onMessageRef.current = onMessage;

    const unbind = (client: MqttClientLike | null) => {
      if (!client) {
        return;
      }
      client.removeListener?.("message", onMessage);
      client.off?.("message", onMessage);
    };

    const bindClient = (client: MqttClientLike | undefined) => {
      if (!client) {
        return;
      }
      if (boundClientRef.current && boundClientRef.current !== client) {
        unbind(boundClientRef.current);
      }
      if (boundClientRef.current === client) {
        publishGetImages(client);
        return;
      }
      client.on("message", onMessage);
      boundClientRef.current = client;
      publishGetImages(client);
      window.setTimeout(() => publishGetImages(client), 500);
      window.setTimeout(() => publishGetImages(client), 1500);
    };

    const onConnected = () => {
      bindClient(window.ssMqttClient);
    };

    const onLiveChange = (ev: Event) => {
      const input = ev.target as HTMLInputElement | null;
      if (!input || input.id !== "live-view") {
        return;
      }
      if (input.checked) {
        document.getElementById("ss-tab-cameras")?.click();
        document.querySelectorAll(".camera-card").forEach((el) => {
          el.classList.add("live-view");
        });
        if (window.ssMqttClient) {
          publishGetImages(window.ssMqttClient);
        }
      } else {
        document.querySelectorAll(".camera-card").forEach((el) => {
          el.classList.remove("live-view");
        });
      }
    };

    window.addEventListener("ss-mqtt-connected", onConnected);
    document.addEventListener("change", onLiveChange);
    if (window.ssMqttClient) {
      bindClient(window.ssMqttClient);
    }

    return () => {
      window.ssReactOwnsCameraStrip = Boolean(window.ssUseReactMap);
      window.removeEventListener("ss-mqtt-connected", onConnected);
      document.removeEventListener("change", onLiveChange);
      unbind(boundClientRef.current);
      boundClientRef.current = null;
    };
  }, [enabled]);
}

/** Re-request strip frames (cameras tab remount). */
export function refreshCameraStrip(): void {
  if (window.ssMqttClient) {
    publishGetImages(window.ssMqttClient);
  }
}
