// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { getCsrfToken } from "../lib/djangoDelete";

export type TreeNode = { [name: string]: TreeNode | null };

export type LoadResponse = {
  path: string;
  folder_name: string;
  depth: number;
  tree: TreeNode;
};

const API = "/api/v1/model-directory/";

async function readError(resp: Response): Promise<string> {
  try {
    const text = (await resp.text()).trim();
    if (text) {
      return text;
    }
  } catch {
    /* ignore */
  }
  return resp.statusText || `HTTP ${resp.status}`;
}

async function request(
  method: string,
  query: string,
  body?: FormData,
): Promise<string> {
  const resp = await fetch(`${API}${query}`, {
    method,
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "text/plain, application/json",
    },
    body,
  });
  const text = (await resp.text()).trim();
  if (!resp.ok) {
    throw new Error(text || resp.statusText || `HTTP ${resp.status}`);
  }
  return text;
}

export async function loadTree(
  path = "",
  folderName = ".",
): Promise<LoadResponse> {
  const params = new URLSearchParams({
    action: "load",
    path,
    folder_name: folderName,
    format: "json",
  });
  const resp = await fetch(`${API}?${params}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json", "X-CSRFToken": getCsrfToken() },
  });
  if (!resp.ok) {
    throw new Error(await readError(resp));
  }
  return (await resp.json()) as LoadResponse;
}

export async function checkExists(
  path: string,
  folderName: string,
): Promise<boolean> {
  const params = new URLSearchParams({
    action: "check",
    path,
    folder_name: folderName,
  });
  const resp = await fetch(`${API}?${params}`, {
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCsrfToken() },
  });
  if (!resp.ok) {
    throw new Error(await readError(resp));
  }
  const text = (await resp.text()).trim().toLowerCase();
  return text === "true" || text === "1";
}

export async function createFolder(
  path: string,
  folderName: string,
): Promise<string> {
  const form = new FormData();
  form.append("path", path);
  form.append("action", "create");
  form.append("folder_name", folderName);
  return request("POST", "", form);
}

export async function uploadFile(path: string, file: File): Promise<string> {
  const form = new FormData();
  form.append("path", path);
  form.append("action", "upload");
  form.append("file", file);
  return request("POST", "", form);
}

export async function extractZip(path: string, file: File): Promise<string> {
  const form = new FormData();
  form.append("path", path);
  form.append("action", "extract");
  form.append("file", file);
  return request("POST", "", form);
}

export async function deleteItem(
  path: string,
  folderName: string,
): Promise<string> {
  const params = new URLSearchParams({ path, folder_name: folderName });
  const form = new FormData();
  form.append("path", path);
  form.append("folder_name", folderName);
  return request("DELETE", `?${params}`, form);
}

export function joinPath(parent: string, name: string): string {
  if (!name) {
    return parent;
  }
  if (!parent) {
    return name;
  }
  return `${parent.replace(/\/+$/, "")}/${name}`;
}

export function modelUrlPath(relPath: string): string {
  return `/models/${relPath.replace(/^\/+/, "")}`;
}

export function isZipFile(file: File): boolean {
  return (
    file.type === "application/zip" ||
    file.type === "application/x-zip-compressed" ||
    file.name.toLowerCase().endsWith(".zip")
  );
}

export function zipStem(fileName: string): string {
  return fileName.replace(/\.zip$/i, "");
}

const DISALLOWED = /[\\/:*?"<>|]/g;

export function sanitizeFolderName(raw: string): string {
  return raw.replace(DISALLOWED, "");
}

export function folderNameError(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) {
    return "Folder name is required";
  }
  if (trimmed === "." || trimmed === "..") {
    return "Folder name is invalid";
  }
  if (DISALLOWED.test(trimmed)) {
    return 'Special characters \\ / : * ? " < > | are not allowed';
  }
  return null;
}
