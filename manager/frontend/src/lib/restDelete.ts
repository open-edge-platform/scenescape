// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { api } from "./rest";

export type RestDeleteKind =
  | "camera"
  | "sensor"
  | "child"
  | "scene"
  | "asset";

export type ParsedDeleteTarget = {
  kind: RestDeleteKind;
  uid: string;
};

const DELETE_PATH =
  /\/(cam|singleton_sensor|child|scene|asset)\/delete\/([^/]+)\/?$/;

/**
 * Map a Django DeleteView path to ManageThing DELETE `/api/v1/{kind}/{uid}`.
 * Camera/sensor uids may be pk (resolved server-side) or sensor_id.
 */
export function parseDeleteTarget(
  hrefOrPath: string,
): ParsedDeleteTarget | null {
  let path = hrefOrPath;
  try {
    if (/^https?:/i.test(hrefOrPath)) {
      path = new URL(hrefOrPath).pathname;
    }
  } catch {
    /* use as-is */
  }
  const m = path.match(DELETE_PATH);
  if (!m) {
    return null;
  }
  const [, slug, uid] = m;
  const kindMap: Record<string, RestDeleteKind> = {
    cam: "camera",
    singleton_sensor: "sensor",
    child: "child",
    scene: "scene",
    asset: "asset",
  };
  const kind = kindMap[slug];
  if (!kind || !uid) {
    return null;
  }
  return { kind, uid: decodeURIComponent(uid) };
}

export function inferDeleteLabel(href: string, linkText: string): string {
  if (href.includes("/cam/")) {
    return "camera";
  }
  if (href.includes("/singleton_sensor/")) {
    return "sensor";
  }
  if (href.includes("/child/")) {
    return "child scene link";
  }
  if (/\/scene\/delete\//.test(href)) {
    return "scene";
  }
  if (href.includes("/asset/")) {
    return "asset";
  }
  const text = linkText.trim().toLowerCase();
  if (text.includes("camera")) {
    return "camera";
  }
  if (text.includes("sensor")) {
    return "sensor";
  }
  if (text.includes("child")) {
    return "child scene link";
  }
  if (text.includes("scene")) {
    return "scene";
  }
  if (text.includes("asset")) {
    return "asset";
  }
  return "item";
}

export async function restDeleteTarget(
  token: string,
  target: ParsedDeleteTarget,
): Promise<void> {
  switch (target.kind) {
    case "camera":
      await api.deleteCamera(token, target.uid);
      return;
    case "sensor":
      await api.deleteSensor(token, target.uid);
      return;
    case "child":
      await api.deleteChild(token, target.uid);
      return;
    case "scene":
      await api.deleteScene(token, target.uid);
      return;
    case "asset":
      await api.deleteAsset(token, target.uid);
      return;
    default:
      throw new Error(`Unsupported delete kind: ${target.kind}`);
  }
}

/**
 * Token REST delete only. Navigates to fallbackHref on success.
 * Django DeleteView URLs remain as hrefs for bookmarks; the UI never POSTs them.
 */
export async function deleteViaRest(
  deleteUrl: string,
  token: string,
  fallbackHref = "/",
): Promise<void> {
  if (!token) {
    throw new Error(
      "Authentication token required to delete. Sign out and sign in again, then retry.",
    );
  }
  const target = parseDeleteTarget(deleteUrl);
  if (!target) {
    throw new Error("Unrecognized delete URL");
  }
  await restDeleteTarget(token, target);
  window.location.href = fallbackHref;
}
