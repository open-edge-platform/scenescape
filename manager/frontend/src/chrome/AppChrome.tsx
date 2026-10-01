// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo } from "react";
import { AboutModal } from "./AboutModal";
import { NavTrailingControls } from "./NavTrailingControls";
import {
  activeNavFromPath,
  type ChromeActiveNav,
  type ChromeBootstrap,
} from "./types";

function navClass(id: ChromeActiveNav, active: ChromeActiveNav): string {
  return `nav-link${active === id ? " active" : ""}`;
}

type Props = {
  bootstrap: ChromeBootstrap;
};

/**
 * Manager navbar + about modal. Hard-contract ids match the former Django
 * base.html chrome (skill freeze table).
 */
export function AppChrome({ bootstrap }: Props) {
  const active = useMemo(
    () => bootstrap.activeNav ?? activeNavFromPath(window.location.pathname),
    [bootstrap.activeNav],
  );

  useEffect(() => {
    const about = document.getElementById("nav-about");
    const modal = document.getElementById("ss-about-modal");
    const w = window as unknown as {
      jQuery?: (
        el: Element,
      ) => {
        on: (ev: string, fn: (e: Event) => void) => void;
        off?: (ev: string, fn: (e: Event) => void) => void;
        modal: (action: string) => void;
      };
    };
    if (!about || !modal || typeof w.jQuery === "undefined") {
      return;
    }
    const $about = w.jQuery(about);
    const handler = (ev: Event) => {
      ev.preventDefault();
      ev.stopPropagation();
      w.jQuery!(modal).modal("show");
    };
    $about.on("click", handler);
    return () => {
      $about.off?.("click", handler);
    };
  }, [bootstrap.authenticated]);

  const { urls } = bootstrap;

  return (
    <>
      <nav className="navbar navbar-expand-md navbar-dark bg-dark fixed-top hide-fullscreen">
        <button
          className="navbar-toggler navbar-toggler-right"
          type="button"
          data-toggle="collapse"
          data-target="#navbarMain"
          aria-controls="navbarMain"
          aria-expanded="false"
          aria-label="Toggle navigation"
        >
          <span className="navbar-toggler-icon" />
        </button>
        <a className="navbar-brand" href={urls.home} id="home">
          <span className="ss-brand-stack">
            <span className="ss-wordmark">{bootstrap.appName}</span>
            <span className="ss-brand-version" id="navbar-version">
              Version {bootstrap.appVersion}
            </span>
          </span>
        </a>

        {bootstrap.authenticated ? (
          <div className="collapse navbar-collapse" id="navbarMain">
            <ul className="navbar-nav mr-auto">
              <li className="nav-item">
                <a
                  className={navClass("scenes", active)}
                  id="nav-scenes"
                  href={urls.scenes}
                >
                  Scenes
                </a>
              </li>
              <li className="nav-item">
                <a
                  className={navClass("cameras", active)}
                  id="nav-cameras"
                  href={urls.cameras}
                >
                  Cameras
                </a>
              </li>
              <li className="nav-item">
                <a
                  className={navClass("sensors", active)}
                  id="nav-sensors"
                  href={urls.sensors}
                >
                  Sensors
                </a>
              </li>
              {bootstrap.isKubernetes && urls.models ? (
                <li className="nav-item">
                  <a
                    className={navClass("models", active)}
                    id="nav-models"
                    href={urls.models}
                  >
                    Models
                  </a>
                </li>
              ) : null}
              <li className="nav-item">
                <a
                  className={navClass("assets", active)}
                  id="nav-object-library"
                  href={urls.assets}
                >
                  Object Library
                </a>
              </li>
              <li className="nav-item dropdown ss-nav-hover">
                <a
                  className="nav-link dropdown-toggle"
                  href="#"
                  id="nav-help"
                  role="button"
                  data-toggle="dropdown"
                  aria-haspopup="true"
                  aria-expanded="false"
                >
                  Help
                </a>
                <div className="dropdown-menu" aria-labelledby="nav-help">
                  <a
                    className="dropdown-item"
                    id="nav-docs"
                    href={urls.docs}
                    target="docs"
                    rel="noopener noreferrer"
                  >
                    Documentation
                  </a>
                  <a
                    className="dropdown-item"
                    id="nav-support"
                    href={urls.support}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Support
                  </a>
                  <a
                    className="dropdown-item"
                    href="#"
                    id="nav-about"
                    data-toggle="modal"
                    data-target="#ss-about-modal"
                  >
                    About
                  </a>
                </div>
              </li>
            </ul>

            <div className="ss-nav-trailing">
              <ul className="navbar-nav navbar-right">
                <li className="nav-item dropdown ss-nav-hover">
                  <a
                    className="nav-link dropdown-toggle"
                    href="#"
                    id="navbar-username"
                    role="button"
                    data-toggle="dropdown"
                    aria-haspopup="true"
                    aria-expanded="false"
                  >
                    {bootstrap.username}
                  </a>
                  <div
                    className="dropdown-menu dropdown-menu-right"
                    aria-labelledby="navbar-username"
                  >
                    {bootstrap.isStaff ? (
                      <>
                        <a
                          className="dropdown-item"
                          id="nav-admin"
                          href={urls.admin}
                          target="admin"
                        >
                          Admin
                        </a>
                        <div className="dropdown-divider" />
                      </>
                    ) : null}
                    <a
                      className="dropdown-item"
                      id="nav-sign-out"
                      href={urls.signOut}
                    >
                      Log out
                    </a>
                  </div>
                </li>
              </ul>
              <NavTrailingControls
                intelHref={urls.intel}
                logoSrc={urls.intelLogo}
              />
            </div>
          </div>
        ) : (
          <div className="ss-nav-trailing">
            <NavTrailingControls
              intelHref={urls.intel}
              logoSrc={urls.intelLogo}
            />
          </div>
        )}
      </nav>
      <AboutModal
        appName={bootstrap.appName}
        appVersion={bootstrap.appVersion}
        appGitCommit={bootstrap.appGitCommit}
      />
    </>
  );
}
