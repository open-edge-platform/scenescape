// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { sceneMapBitmapUrl } from "./sceneMapBitmap";
import type { SceneDetailBootstrap } from "../scene/types";

function setHidden(
  id: string,
  name: string,
  value: string,
  parent: ParentNode,
): HTMLInputElement {
  let el = document.getElementById(id) as HTMLInputElement | null;
  if (!el) {
    el = document.createElement("input");
    el.type = "hidden";
    el.id = id;
    el.name = name;
    parent.appendChild(el);
  }
  el.value = value;
  return el;
}

function toggleSwitch(
  id: string,
  labelText: string,
  title: string,
): HTMLDivElement {
  const wrap = document.createElement("div");
  wrap.className = "custom-control custom-switch map-view-toggle";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.className = "custom-control-input";
  input.id = id;
  input.setAttribute("aria-labelledby", `${id}-label`);
  const label = document.createElement("label");
  label.className = "custom-control-label";
  label.htmlFor = id;
  label.title = title;
  label.id = `${id}-label`;
  label.textContent = labelText;
  wrap.append(input, label);
  return wrap;
}

/**
 * Build legacy map host + geometry hidden fields from bootstrap so the
 * Django template only needs the React root. Must run before sscape.js
 * document.ready / imagesLoaded (call from scene-detail entry before React).
 *
 * Hard-contract ids: docs/design/manager-ui-backend-contract.md,
 * .github/skills/manager-ui/SKILL.md.
 */
export function ensureSceneDetailDom(bootstrap: SceneDetailBootstrap): void {
  const scene = bootstrap.scene;
  const mapHref = sceneMapBitmapUrl(scene);

  let parking = document.getElementById("ss-legacy-map-parking");
  if (!parking) {
    parking = document.createElement("div");
    parking.id = "ss-legacy-map-parking";
    parking.className = "ss-legacy-parking";
    parking.hidden = true;
    const root = document.getElementById("ss-scene-detail-root");
    if (root?.parentNode) {
      root.parentNode.insertBefore(parking, root.nextSibling);
    } else {
      document.body.appendChild(parking);
    }
  }

  let host = document.getElementById("ss-map-host");
  if (!host) {
    host = document.createElement("div");
    host.id = "ss-map-host";
    host.className = "scene-map";
    parking.appendChild(host);
  }

  let controls = document.getElementById("map-controls");
  if (!controls) {
    controls = document.createElement("div");
    controls.id = "map-controls";
    controls.className = "hide-print";
    const toggles = document.createElement("div");
    toggles.className = "map-view-toggles";
    toggles.append(
      toggleSwitch("show-trails", "Show Trails", "Toggle Show Trails"),
      toggleSwitch("show-telemetry", "Show Telemetry", "Toggle Show Telemetry"),
      toggleSwitch("coloring-switch", "Visualize ROIs", "Toggle Coloring"),
    );
    controls.appendChild(toggles);
    host.insertBefore(controls, host.firstChild);
  }

  let stage = host.querySelector(".scene-map-stage") as HTMLElement | null;
  if (!stage) {
    stage = document.createElement("div");
    stage.className = "scene-map-stage";
    host.appendChild(stage);
  }

  let map = document.getElementById("map");
  if (!map) {
    map = document.createElement("div");
    map.id = "map";
    stage.insertBefore(map, stage.firstChild);
  }

  if (mapHref && !map.querySelector("img")) {
    const img = document.createElement("img");
    img.src = mapHref;
    img.alt = scene.name || "Scene map";
    map.appendChild(img);
  }

  setHidden(
    "scale",
    "scale",
    scene.scale != null ? String(scene.scale) : "",
    map,
  );
  setHidden("scene", "scene", String(scene.id), map);

  let svg = document.getElementById("svgout") as SVGSVGElement | null;
  if (!svg) {
    svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.id = "svgout";
  }
  // Template may stub #svgout before sscape.js; adopt it into the map stage.
  if (svg.parentNode !== stage) {
    stage.appendChild(svg);
  }
  const blank = !scene.thumbnailUrl || !scene.mapUrl;
  svg.classList.add("display-none");
  if (blank) {
    svg.classList.add("blank-map-svgout");
  } else {
    svg.classList.remove("blank-map-svgout");
  }
  if (!svg.querySelector("title")) {
    const title = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "title",
    );
    title.textContent = `${scene.name || "Scene"} View`;
    const desc = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "desc",
    );
    desc.textContent =
      "Graphical view of the scene map and objects moving within the scene.";
    svg.append(title, desc);
  }

  if (!document.getElementById("fullscreen")) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "btn btn-sm btn-secondary scene-map-fullscreen-btn hide-print";
    btn.id = "fullscreen";
    btn.title = "Full screen map view";
    btn.setAttribute("aria-pressed", "false");
    btn.innerHTML =
      '<i class="bi bi-arrows-fullscreen" aria-hidden="true"></i>' +
      '<span class="sr-only">Full screen map view</span>';
    stage.appendChild(btn);
  }

  const anchor = parking.parentNode || document.body;
  setHidden(
    "id_rois",
    "rois",
    JSON.stringify(bootstrap.regions ?? []),
    anchor,
  );
  setHidden(
    "tripwires",
    "tripwires",
    JSON.stringify(bootstrap.tripwires ?? []),
    anchor,
  );
  setHidden(
    "id_child_rois",
    "child_rois",
    bootstrap.childRoiJson ?? "[]",
    anchor,
  );
  setHidden(
    "child_tripwires",
    "child_tripwires",
    bootstrap.childTripwireJson ?? "[]",
    anchor,
  );
  setHidden(
    "child_sensors",
    "child_sensors",
    bootstrap.childSensorJson ?? "[]",
    anchor,
  );
}
