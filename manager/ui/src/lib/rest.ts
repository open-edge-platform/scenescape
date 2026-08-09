// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export type RestError = {
  status: number;
  message: string;
  body?: unknown;
};

const API_BASE = "/api/v1";

function authHeader(token: string): HeadersInit {
  return token ? { Authorization: `Token ${token}` } : {};
}

async function parseError(resp: Response): Promise<RestError> {
  let body: unknown;
  let message = resp.statusText || `HTTP ${resp.status}`;
  try {
    body = await resp.json();
    if (body && typeof body === "object") {
      const obj = body as Record<string, unknown>;
      if (typeof obj.detail === "string") {
        message = obj.detail;
      } else {
        const first = Object.values(obj).find(
          (v) => Array.isArray(v) && v.length && typeof v[0] === "string",
        ) as string[] | undefined;
        if (first?.[0]) {
          message = first[0];
        } else if (Array.isArray(obj.non_field_errors) && obj.non_field_errors[0]) {
          message = String(obj.non_field_errors[0]);
        }
      }
    }
  } catch {
    /* ignore */
  }
  return { status: resp.status, message, body };
}

export async function restJson<T>(
  method: string,
  path: string,
  token: string,
  body?: unknown,
): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      ...authHeader(token),
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    throw await parseError(resp);
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

export async function restForm<T>(
  method: string,
  path: string,
  token: string,
  form: FormData,
): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      ...authHeader(token),
      Accept: "application/json",
    },
    body: form,
  });
  if (!resp.ok) {
    throw await parseError(resp);
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

export const api = {
  createCamera: (token: string, data: unknown) =>
    restJson("POST", "/camera", token, data),
  updateCamera: (token: string, uid: string, data: unknown) =>
    restJson("PUT", `/camera/${encodeURIComponent(uid)}`, token, data),
  getCamera: (token: string, uid: string) =>
    restJson<Record<string, unknown>>(
      "GET",
      `/camera/${encodeURIComponent(uid)}`,
      token,
    ),
  createSensor: (token: string, data: unknown) =>
    restJson("POST", "/sensor", token, data),
  updateSensor: (token: string, uid: string, data: unknown) =>
    restJson("PUT", `/sensor/${encodeURIComponent(uid)}`, token, data),
  getSensor: (token: string, uid: string) =>
    restJson<Record<string, unknown>>(
      "GET",
      `/sensor/${encodeURIComponent(uid)}`,
      token,
    ),
  createChild: (token: string, data: unknown) =>
    restJson("POST", "/child", token, data),
  updateChild: (token: string, uid: string, data: unknown) =>
    restJson("PUT", `/child/${encodeURIComponent(uid)}`, token, data),
  getChild: (token: string, uid: string) =>
    restJson<Record<string, unknown>>(
      "GET",
      `/child/${encodeURIComponent(uid)}`,
      token,
    ),
  createScene: (token: string, form: FormData) =>
    restForm("POST", "/scene", token, form),
  updateScene: (token: string, uid: string, form: FormData) =>
    restForm("PUT", `/scene/${encodeURIComponent(uid)}`, token, form),
  getScene: (token: string, uid: string) =>
    restJson<Record<string, unknown>>(
      "GET",
      `/scene/${encodeURIComponent(uid)}`,
      token,
    ),
  getScenes: (token: string) =>
    restJson<{ results?: unknown[] } | unknown[]>("GET", "/scenes", token),
  importScene: (token: string, form: FormData) =>
    restForm("POST", "/import-scene/", token, form),
  createAsset: (token: string, form: FormData) =>
    restForm("POST", "/asset", token, form),
  updateAsset: (token: string, uid: string, form: FormData) =>
    restForm("PUT", `/asset/${encodeURIComponent(uid)}`, token, form),
  getAsset: (token: string, uid: string) =>
    restJson<Record<string, unknown>>(
      "GET",
      `/asset/${encodeURIComponent(uid)}`,
      token,
    ),
};
