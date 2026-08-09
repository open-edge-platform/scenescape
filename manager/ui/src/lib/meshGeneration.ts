// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

function csrfToken(): string {
  const input = document.querySelector(
    'input[name="csrfmiddlewaretoken"]',
  ) as HTMLInputElement | null;
  if (input?.value) {
    return input.value;
  }
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export async function startMeshGeneration(sceneId: string): Promise<string> {
  const resp = await fetch(`/scene/generate-mesh/${sceneId}/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: new FormData(),
  });
  const data = (await resp.json().catch(() => ({}))) as {
    success?: boolean;
    request_id?: string;
    error?: string;
  };
  if (!resp.ok || data.success === false) {
    throw new Error(data.error || `Generate mesh failed (HTTP ${resp.status})`);
  }
  if (!data.request_id) {
    throw new Error("Generate mesh response missing request_id");
  }
  return data.request_id;
}

export async function pollMeshStatus(
  sceneId: string,
  requestId: string,
  opts?: { timeoutMs?: number; intervalMs?: number },
): Promise<void> {
  const timeout = opts?.timeoutMs ?? 15 * 60 * 1000;
  const interval = opts?.intervalMs ?? 1500;
  const start = Date.now();
  while (true) {
    if (Date.now() - start > timeout) {
      throw new Error("Timed out waiting for mesh generation.");
    }
    const resp = await fetch(
      `/scene/generate-mesh-status/${sceneId}/?request_id=${encodeURIComponent(requestId)}`,
      { credentials: "same-origin", headers: { Accept: "application/json" } },
    );
    const data = (await resp.json().catch(() => ({}))) as {
      success?: boolean;
      state?: string;
      error?: string;
    };
    if (!resp.ok) {
      throw new Error(data.error || "Status check failed");
    }
    if (data.success === false) {
      throw new Error(data.error || "Mesh generation failed");
    }
    if (data.state === "complete") {
      return;
    }
    if (data.state === "failed") {
      throw new Error(data.error || "Mesh generation failed");
    }
    await new Promise((r) => setTimeout(r, interval));
  }
}

export async function checkMappingServiceAvailable(
  authToken: string,
): Promise<boolean> {
  if (!authToken) {
    return false;
  }
  try {
    const resp = await fetch("/mapping-service/status/", {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Token ${authToken}`,
      },
    });
    if (!resp.ok) {
      return false;
    }
    const status = (await resp.json()) as { available?: boolean };
    return Boolean(status.available);
  } catch {
    return false;
  }
}
