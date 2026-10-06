#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""End-to-end check of the ctrl+click vertex merge, against real regions.

Non-destructive: operates only on the in-browser canvas state and never submits
the form, so nothing is persisted. Dispatches genuine MouseEvents (with ctrlKey)
on the actual vertex circles, exercising the real CSS/pointer-events and Snap.svg
handler wiring rather than just the geometry helpers.
"""

import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from selenium.webdriver.common.by import By

from tests.ui.browser import Browser

WEB_URL = "https://web.scenescape.intel.com"
AUTH_FILE = os.path.join(
  os.path.dirname(__file__), "..", "..", "manager", "secrets", "browser.auth"
)

# Two scenarios: overlapping regions must take the union path, separated ones the
# vertex-bridge path. Coordinates are scene meters.
SCENARIOS = [
  {
    "name": "OVERLAPPING (union path)",
    "expect_vertices": 8,
    "regions": [
      {
        "title": "MergeA",
        "uuid": "aaaaaaaa-0000-4000-8000-000000000001",
        "points": [[2, 2], [14, 2], [14, 8], [2, 8]],
      },
      {
        "title": "MergeB",
        "uuid": "bbbbbbbb-0000-4000-8000-000000000002",
        "points": [[10, 5], [22, 5], [22, 11], [10, 11]],
      },
    ],
  },
  {
    "name": "SEPARATED (bridge path)",
    "expect_vertices": 8,
    "regions": [
      {
        "title": "MergeA",
        "uuid": "aaaaaaaa-0000-4000-8000-000000000003",
        "points": [[2, 2], [14, 2], [14, 6], [2, 6]],
      },
      {
        "title": "MergeB",
        "uuid": "bbbbbbbb-0000-4000-8000-000000000004",
        "points": [[20, 2], [32, 2], [32, 6], [20, 6]],
      },
    ],
  },
]


def credentials():
  with open(AUTH_FILE) as f:
    auth = json.load(f)
  return auth["user"], auth["password"]


def js_click(browser, element, ctrl=False):
  """Dispatch a real click (optionally with ctrl) on an SVG element."""
  browser.execute_script(
    """
    const el = arguments[0], ctrl = arguments[1];
    const r = el.getBoundingClientRect();
    const opts = {
      bubbles: true, cancelable: true, view: window,
      clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
      ctrlKey: ctrl,
    };
    el.dispatchEvent(new MouseEvent('mousedown', opts));
    el.dispatchEvent(new MouseEvent('mouseup', opts));
    el.dispatchEvent(new MouseEvent('click', opts));
    """,
    element,
    ctrl,
  )


def poly_points(group):
  raw = group.find_element(By.TAG_NAME, "polygon").get_attribute("points")
  nums = [float(v) for v in raw.replace(",", " ").split()]
  return [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]


def centroid(pts):
  return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def segments_cross(p1, p2, p3, p4):
  def orient(a, b, c):
    v = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
    return 1 if v > 1e-9 else (2 if v < -1e-9 else 0)

  o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
  o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
  return 0 not in (o1, o2, o3, o4) and o1 != o2 and o3 != o4


def is_simple(ring):
  n = len(ring)
  for i in range(n):
    for j in range(i + 1, n):
      if j == i + 1 or (i == 0 and j == n - 1):
        continue
      if segments_cross(ring[i], ring[(i + 1) % n], ring[j], ring[(j + 1) % n]):
        return False
  return True


def rings_overlap(a, b):
  return any(
    segments_cross(a[i], a[(i + 1) % len(a)], b[j], b[(j + 1) % len(b)])
    for i in range(len(a))
    for j in range(len(b))
  )


def ring_area(ring):
  total = 0
  for i in range(len(ring)):
    nxt = ring[(i + 1) % len(ring)]
    total += ring[i][0] * nxt[1] - nxt[0] * ring[i][1]
  return total / 2


def find_scene_with_regions(browser):
  # Collect hrefs up front: navigating invalidates cached element references
  hrefs = []
  for link in browser.find_elements(By.TAG_NAME, "a"):
    href = link.get_attribute("href") or ""
    tail = href.rstrip("/").split("/")[-1]
    if tail.count("-") == 4 and "/scene/" not in href and href not in hrefs:
      hrefs.append(href)

  for href in hrefs:
    browser.get(href)
    time.sleep(2)
    try:
      browser.find_element(By.ID, "regions-tab").click()
    except Exception:
      continue
    time.sleep(2)
    if browser.find_elements(By.ID, "svgout"):
      return href

  return None


def seed_regions(browser, regions):
  """Draw regions straight onto the canvas via the page's own drawRoi export.

  Purely client-side: nothing is posted, so no saved data is touched.
  """
  return browser.execute_async_script(
    """
    const specs = arguments[0];
    const done = arguments[1];
    import('/static/js/sscape.js').then((m) => {
      specs.forEach((s) => {
        m.drawRoi({
          type: 'roi', points: s.points, title: s.title, uuid: s.uuid,
          volumetric: false, height: 0, buffer_size: 0,
          sectors: { thresholds: {}, range_max: 0 },
        }, s.uuid, 'roi');
      });
      m.numberRois();
      m.stringifyRois();
      done(document.querySelectorAll('g.roi').length);
    }).catch((e) => done('ERROR: ' + e.message));
    """,
    regions,
  )


def run_scenario(browser, scene_url, scenario):
  print(f"\n=== {scenario['name']} ===")

  # Reload so the canvas starts clean for each scenario
  browser.get(scene_url)
  time.sleep(2)
  browser.find_element(By.ID, "regions-tab").click()
  time.sleep(1.5)

  browser.set_script_timeout(30)
  seeded = seed_regions(browser, scenario["regions"])
  if not isinstance(seeded, int) or seeded < 2:
    print(f"FAIL: could not seed regions ({seeded})")
    return False
  time.sleep(0.5)

  groups = browser.find_elements(By.CSS_SELECTOR, "g.roi")
  before_count = len(groups)
  print(f"regions before merge: {before_count}")

  infos = [(g, poly_points(g)) for g in groups]
  best = None
  for i in range(len(infos)):
    for j in range(i + 1, len(infos)):
      d = math.dist(centroid(infos[i][1]), centroid(infos[j][1]))
      if best is None or d < best[0]:
        best = (d, i, j)
  _, ia, ib = best
  group_a, pts_a = infos[ia]
  group_b, pts_b = infos[ib]
  id_a, id_b = group_a.get_attribute("id"), group_b.get_attribute("id")
  print(f"merging {len(pts_a)}-pt + {len(pts_b)}-pt regions")

  cen_a, cen_b = centroid(pts_a), centroid(pts_b)
  overlapping = rings_overlap(pts_a, pts_b)
  print(f"outlines overlap: {overlapping}")

  def facing_edge_handles(gid, pts, target):
    """Circles for the consecutive vertex pair whose edge midpoint faces `target`.

    Circle DOM order matches polygon point order, so indices line up.
    """
    handles = browser.find_element(By.ID, gid).find_elements(
      By.CSS_SELECTOR, "circle.is-handle"
    )
    if len(handles) < 2:
      return []
    n = len(pts)
    best_i, best_d = 0, None
    for i in range(n):
      a, b = pts[i], pts[(i + 1) % n]
      mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
      d = math.dist(mid, target)
      if best_d is None or d < best_d:
        best_i, best_d = i, d
    return [handles[best_i], handles[(best_i + 1) % len(handles)]]

  # --- Region A: select, then ctrl+click the two vertices of the edge facing B ---
  js_click(browser, browser.find_element(By.ID, id_a).find_element(By.TAG_NAME, "polygon"))
  time.sleep(0.5)
  handles_a = browser.find_element(By.ID, id_a).find_elements(By.CSS_SELECTOR, "circle.is-handle")
  print(f"A handles exposed on select: {len(handles_a)}")
  if len(handles_a) < 2:
    print("FAIL: left-clicking region A did not expose vertex handles")
    return False

  for c in facing_edge_handles(id_a, pts_a, cen_b):
    js_click(browser, c, ctrl=True)
  time.sleep(0.4)

  picked = browser.find_elements(By.CSS_SELECTOR, "circle.merge-vertex")
  print(f"vertices picked after A: {len(picked)}")
  if len(picked) != 2:
    print("FAIL: ctrl+click did not register exactly 2 picks on A")
    return False

  # --- Region B: select, then ctrl+click the two vertices of the edge facing A ---
  js_click(browser, browser.find_element(By.ID, id_b).find_element(By.TAG_NAME, "polygon"))
  time.sleep(0.5)
  handles_b = browser.find_element(By.ID, id_b).find_elements(By.CSS_SELECTOR, "circle.is-handle")
  print(f"B handles exposed on select: {len(handles_b)}")
  if len(handles_b) < 2:
    print("FAIL: left-clicking region B did not expose vertex handles")
    return False

  still_picked = browser.find_elements(By.CSS_SELECTOR, "circle.merge-vertex")
  print(f"picks still highlighted after switching region: {len(still_picked)}")

  for c in facing_edge_handles(id_b, pts_b, cen_a):
    js_click(browser, c, ctrl=True)
  time.sleep(0.8)

  # --- Verify ---
  after = browser.find_elements(By.CSS_SELECTOR, "g.roi")
  after_ids = [g.get_attribute("id") for g in after]
  print(f"regions after merge: {len(after)} (was {before_count})")

  if len(after) != before_count - 1:
    print(f"FAIL: expected {before_count - 1} regions, got {len(after)}")
    return False
  if id_b in after_ids or id_a not in after_ids:
    print("FAIL: wrong region survived the merge")
    return False

  merged = poly_points(browser.find_element(By.ID, id_a))
  print(f"merged outline: {len(merged)} vertices (A had {len(pts_a)}, B had {len(pts_b)})")

  if not is_simple(merged):
    print("FAIL: merged outline self-intersects")
    return False
  print("merged outline is simple")

  expected = scenario.get("expect_vertices")
  if expected is not None and len(merged) != expected:
    print(f"FAIL: expected {expected} vertices, got {len(merged)}")
    return False

  merged_area = abs(ring_area(merged))
  area_a, area_b = abs(ring_area(pts_a)), abs(ring_area(pts_b))
  print(f"areas: A={area_a:.0f} B={area_b:.0f} merged={merged_area:.0f}")
  if merged_area < max(area_a, area_b) - 1:
    print("FAIL: merged region is smaller than one of its inputs")
    return False
  if overlapping and merged_area > area_a + area_b + 1:
    print("FAIL: union added area beyond A+B")
    return False

  leftover = browser.find_elements(By.CSS_SELECTOR, "circle.merge-vertex")
  if leftover:
    print(f"FAIL: {len(leftover)} merge highlights left over")
    return False
  print("merge selection cleared")

  saved = json.loads(
    browser.execute_script("return document.getElementById('id_rois').value;")
  )
  if len(saved) != before_count - 1:
    print(f"FAIL: hidden field has {len(saved)} entries, expected {before_count - 1}")
    return False
  print(f"#id_rois entries: {len(saved)}")

  print("PASS")
  return True


def main():
  user, password = credentials()
  browser = Browser(headless=True)

  try:
    if not browser.login(user, password, WEB_URL):
      print("LOGIN FAILED")
      return 1

    scene_url = find_scene_with_regions(browser)
    if not scene_url:
      print("FAIL: no usable scene found")
      return 1
    print("scene:", scene_url)

    results = [run_scenario(browser, scene_url, s) for s in SCENARIOS]

    print("\n" + "=" * 50)
    for scenario, ok in zip(SCENARIOS, results):
      print(f"{'PASS' if ok else 'FAIL'}  {scenario['name']}")
    print("(nothing was saved)")

    return 0 if all(results) else 1

  finally:
    browser.quit()


if __name__ == "__main__":
  sys.exit(main())
