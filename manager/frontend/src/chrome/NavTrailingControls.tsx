// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";

declare global {
  interface Window {
    ssTheme?: {
      initThemeToggle?: () => void;
    };
  }
}

/** Theme toggle + Intel mark — hard-contract #ss-theme-toggle. */
export function NavTrailingControls({
  intelHref,
  logoSrc,
}: {
  intelHref: string;
  logoSrc: string;
}) {
  useEffect(() => {
    window.ssTheme?.initThemeToggle?.();
  }, []);

  return (
    <>
      <div className="ss-theme-toggle-host">
        <div
          className="ss-theme-toggle"
          id="ss-theme-toggle"
          role="group"
          aria-label="Color theme"
        >
          <button
            type="button"
            className="ss-theme-toggle__btn"
            data-ss-theme="light"
            aria-pressed="true"
          >
            Light
          </button>
          <button
            type="button"
            className="ss-theme-toggle__btn"
            data-ss-theme="dark"
            aria-pressed="false"
          >
            Dark
          </button>
        </div>
      </div>
      <a
        className="navbar-powered-by"
        href={intelHref}
        target="_blank"
        rel="noopener noreferrer"
        title="Powered by Intel"
      >
        <span className="powered-by-label">Powered by</span>
        <img className="intel-logo" src={logoSrc} alt="Intel" />
      </a>
    </>
  );
}
