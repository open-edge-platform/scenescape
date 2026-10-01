// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export type ChromeActiveNav =
  | "scenes"
  | "cameras"
  | "sensors"
  | "models"
  | "assets"
  | null;

export type ChromeBootstrap = {
  authenticated: boolean;
  username: string;
  isStaff: boolean;
  isKubernetes: boolean;
  appName: string;
  appVersion: string;
  appGitCommit: string;
  docsVersion: string;
  urls: {
    home: string;
    scenes: string;
    cameras: string;
    sensors: string;
    /** Present only when Models routes are registered (Kubernetes). */
    models?: string;
    assets: string;
    admin: string;
    signOut: string;
    docs: string;
    support: string;
    intel: string;
    intelLogo: string;
  };
  /** Optional server hint; client may also derive from pathname. */
  activeNav?: ChromeActiveNav;
};

/** Derive active nav from the current path (works for static shells later). */
export function activeNavFromPath(pathname: string): ChromeActiveNav {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/" || /^\/[0-9a-f-]{36}$/i.test(path)) {
    return "scenes";
  }
  if (path.startsWith("/cameras") || path.startsWith("/cam/")) {
    return "cameras";
  }
  if (path.startsWith("/sensors") || path.startsWith("/singleton_sensor")) {
    return "sensors";
  }
  if (path.startsWith("/models") || path.startsWith("/model")) {
    return "models";
  }
  if (path.startsWith("/assets") || path.startsWith("/asset")) {
    return "assets";
  }
  return null;
}
