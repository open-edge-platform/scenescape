// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** MQTT topic fragments — keep in sync with manager/static/js/constants.js. */
export const APP_NAME = "scenescape";
export const CMD_CAMERA = "/cmd/camera/";
export const DATA_REGULATED = "/regulated/scene/";
export const IMAGE_CAMERA = "/image/camera/";
export const SYS_CHILDSCENE_STATUS = "/sys/child/status";

export function sceneRegulatedTopic(sceneId: string): string {
  return `${APP_NAME}${DATA_REGULATED}${sceneId}`;
}

export function sceneEventTopic(sceneId: string): string {
  return `${APP_NAME}/event/+/${sceneId}/+/+`;
}

export function cameraImageTopic(): string {
  return `${APP_NAME}${IMAGE_CAMERA}+`;
}

export function cameraCmdTopic(sensorId: string): string {
  return `${APP_NAME}${CMD_CAMERA}${sensorId}`;
}

export function childStatusTopic(): string {
  return `${APP_NAME}${SYS_CHILDSCENE_STATUS}/+`;
}
