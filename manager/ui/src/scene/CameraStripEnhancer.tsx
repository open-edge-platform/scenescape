// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import "./CameraStrip.css";

const FIT_KEY = "ss-camera-strip-fit";

export type CameraStripFit = "contain" | "cover";

function readFit(): CameraStripFit {
  try {
    const v = window.localStorage.getItem(FIT_KEY);
    if (v === "cover" || v === "contain") {
      return v;
    }
  } catch {
    /* ignore */
  }
  return "contain";
}

function writeFit(fit: CameraStripFit): void {
  try {
    window.localStorage.setItem(FIT_KEY, fit);
  } catch {
    /* ignore */
  }
}

function applyCardState(card: HTMLElement): void {
  const img = card.querySelector(
    "img[data-ss-card-sensor], img[id^='card-preview-']",
  ) as HTMLImageElement | null;
  const offline = card.querySelector(".cam-offline") as HTMLElement | null;
  const rateEl = card.querySelector(".rate") as HTMLElement | null;
  const rateText = (rateEl?.textContent || "").trim();
  const hasFrame =
    Boolean(img) &&
    !img!.classList.contains("display-none") &&
    (img!.naturalWidth > 0 || Boolean(img!.currentSrc || img!.src));
  const online =
    hasFrame ||
    (rateText !== "" && rateText !== "--" && !Number.isNaN(Number(rateText)));

  card.classList.toggle("is-online", online);
  card.classList.toggle("is-offline", !online);
  card.dataset.ssRate = rateText || "--";

  let badge = card.querySelector(".ss-camera-strip-badge") as HTMLElement | null;
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "ss-camera-strip-badge";
    badge.setAttribute("aria-hidden", "true");
    const header = card.querySelector(".card-header") || card;
    header.appendChild(badge);
  }
  badge.textContent = online ? "Live" : "Offline";
  badge.classList.toggle("is-online", online);
  badge.classList.toggle("is-offline", !online);

  if (offline) {
    offline.hidden = online;
  }
}

/**
 * Reactive camera strip: fit mode + live/offline badges over legacy cards.
 */
export function CameraStripEnhancer() {
  const [fit, setFit] = useState<CameraStripFit>(() =>
    typeof window !== "undefined" ? readFit() : "contain",
  );

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.ssCameraFit = fit;
    writeFit(fit);
    const pane = document.getElementById("cameras");
    if (pane) {
      pane.dataset.ssCameraFit = fit;
      pane.classList.add("ss-camera-strip");
    }
  }, [fit]);

  useEffect(() => {
    const pane = document.getElementById("cameras");
    if (!pane) {
      return;
    }
    pane.classList.add("ss-camera-strip");

    const refresh = () => {
      pane.querySelectorAll<HTMLElement>(".camera-card").forEach(applyCardState);
    };
    refresh();

    const mo = new MutationObserver(() => refresh());
    mo.observe(pane, {
      subtree: true,
      childList: true,
      attributes: true,
      characterData: true,
      attributeFilter: ["class", "src", "style"],
    });
    const poll = window.setInterval(refresh, 1500);

    return () => {
      mo.disconnect();
      window.clearInterval(poll);
    };
  }, []);

  return (
    <div
      className="ss-camera-strip-controls"
      role="group"
      aria-label="Camera thumbnail fit"
    >
      <button
        type="button"
        className={`ss-camera-strip-fit${fit === "contain" ? " is-active" : ""}`}
        aria-pressed={fit === "contain"}
        title="Fit entire frame (contain)"
        onClick={() => setFit("contain")}
      >
        Contain
      </button>
      <button
        type="button"
        className={`ss-camera-strip-fit${fit === "cover" ? " is-active" : ""}`}
        aria-pressed={fit === "cover"}
        title="Fill card (cover)"
        onClick={() => setFit("cover")}
      >
        Cover
      </button>
    </div>
  );
}
