// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Query-string sheet contract: ?ss=<action>&id=<optional> */

export type SheetAction =
  | "cam-create"
  | "cam-edit"
  | "sensor-create"
  | "sensor-edit"
  | "child-create"
  | "child-edit"
  | "scene-create"
  | "scene-edit"
  | "scene-import"
  | "asset-create"
  | "asset-edit"
  | "calibrate-cam"
  | "calibrate-sensor"
  | null;

export type SheetQuery = {
  action: SheetAction;
  id: string | null;
};

const ACTIONS = new Set<string>([
  "cam-create",
  "cam-edit",
  "sensor-create",
  "sensor-edit",
  "child-create",
  "child-edit",
  "scene-create",
  "scene-edit",
  "scene-import",
  "asset-create",
  "asset-edit",
  "calibrate-cam",
  "calibrate-sensor",
]);

export function parseSheetQuery(
  search: string = window.location.search,
): SheetQuery {
  const params = new URLSearchParams(search);
  const raw = params.get("ss");
  const action =
    raw && ACTIONS.has(raw) ? (raw as Exclude<SheetAction, null>) : null;
  return { action, id: params.get("id") };
}

/** Remove ss/id from the URL without reloading. */
export function clearSheetQuery(): void {
  const url = new URL(window.location.href);
  if (!url.searchParams.has("ss") && !url.searchParams.has("id")) {
    return;
  }
  url.searchParams.delete("ss");
  url.searchParams.delete("id");
  const next = url.pathname + (url.search ? url.search : "") + url.hash;
  window.history.replaceState({}, "", next);
}

export function buildSheetUrl(
  path: string,
  action: Exclude<SheetAction, null>,
  id?: string | number | null,
): string {
  const url = new URL(path, window.location.origin);
  url.searchParams.set("ss", action);
  if (id !== undefined && id !== null && String(id) !== "") {
    url.searchParams.set("id", String(id));
  }
  return url.pathname + url.search;
}
