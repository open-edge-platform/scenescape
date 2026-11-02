// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Pure 2D ring helpers for region editing; rings are [[x, y], ...] in canvas pixels.

/**
 * Outer ring of the union of two overlapping outlines, or null when they are
 * disjoint (nothing to union) or the result can't be trusted.
 */
function unionPolygons(ringA, ringB) {
  var areaA = Math.abs(ringSignedArea(ringA));
  var areaB = Math.abs(ringSignedArea(ringB));

  // A real union covers every input vertex, adds no area beyond A+B, and is simple
  var acceptable = function (ring) {
    if (!ring || ring.length < 3) return false;

    var a = Math.abs(ringSignedArea(ring));
    if (a < Math.max(areaA, areaB) - 0.5 || a > areaA + areaB + 0.5)
      return false;
    if (!isSimplePolygon(ring)) return false;

    return ringA.concat(ringB).every(function (p) {
      return pointInRing(ring, p) || pointOnRingBoundary(ring, p);
    });
  };

  var result = unionAttempt(ringA, ringB);
  if (acceptable(result)) return result;

  // Shared/collinear edges make the walk degenerate; a sub-pixel nudge breaks
  // the tie without visibly moving the outline.
  var nudged = ringB.map(function (p) {
    return [p[0] + 1e-4, p[1] + 1e-4];
  });
  result = unionAttempt(ringA, nudged);

  return acceptable(result) ? result : null;
}

/** One union walk: insert crossings into both rings, then trace the outer boundary. */
function unionAttempt(ringA, ringB) {
  var A = ensureCCW(ringA);
  var B = ensureCCW(ringB);

  var perEdgeA = A.map(function () {
    return [];
  });
  var perEdgeB = B.map(function () {
    return [];
  });
  var found = 0;

  for (var i = 0; i < A.length; i++) {
    for (var j = 0; j < B.length; j++) {
      var hit = segmentIntersection(
        A[i],
        A[(i + 1) % A.length],
        B[j],
        B[(j + 1) % B.length],
      );
      if (!hit) continue;

      var key = pointKey(hit.point);
      perEdgeA[i].push({ t: hit.t, pt: hit.point, key: key });
      perEdgeB[j].push({ t: hit.u, pt: hit.point, key: key });
      found++;
    }
  }

  if (!found) {
    if (pointInRing(B, A[0])) return B.slice();
    if (pointInRing(A, B[0])) return A.slice();
    return null; // disjoint
  }

  var augA = augmentRing(A, perEdgeA);
  var augB = augmentRing(B, perEdgeB);
  var indexA = crossingIndex(augA);
  var indexB = crossingIndex(augB);

  // Start somewhere guaranteed to be on the union's outer boundary
  var start = -1;
  for (var k = 0; k < augA.length; k++) {
    if (!augA[k].inter && !pointInRing(B, augA[k].pt)) {
      start = k;
      break;
    }
  }
  if (start < 0) return B.slice(); // A lies entirely within B

  var result = [];
  var onA = true;
  var idx = start;
  var maxSteps = (augA.length + augB.length) * 4;

  for (var step = 0; step < maxSteps; step++) {
    var node = (onA ? augA : augB)[idx];

    if (!result.length || !samePoint(result[result.length - 1], node.pt)) {
      result.push(node.pt);
    }

    // At a crossing, hand over to the other outline to stay on the outside
    if (node.inter) {
      var target = (onA ? indexB : indexA)[node.key];
      if (target !== undefined) {
        onA = !onA;
        idx = target;
      }
    }

    idx = (idx + 1) % (onA ? augA : augB).length;

    if (onA && idx === start) {
      if (
        result.length > 1 &&
        samePoint(result[0], result[result.length - 1])
      ) {
        result.pop();
      }
      return result.length >= 3 ? result : null;
    }
  }

  return null; // walk never closed
}

/** Ring vertices with crossing points spliced in, in order along each edge. */
function augmentRing(ring, perEdge) {
  var out = [];

  for (var i = 0; i < ring.length; i++) {
    out.push({ pt: ring[i], inter: false, key: null });

    perEdge[i]
      .slice()
      .sort(function (a, b) {
        return a.t - b.t;
      })
      .forEach(function (hit) {
        var last = out[out.length - 1];
        if (samePoint(last.pt, hit.pt)) {
          last.inter = true;
          last.key = hit.key;
          return;
        }
        out.push({ pt: hit.pt, inter: true, key: hit.key });
      });
  }

  while (out.length > 1 && samePoint(out[0].pt, out[out.length - 1].pt)) {
    if (out[out.length - 1].inter) {
      out[0].inter = true;
      out[0].key = out[out.length - 1].key;
    }
    out.pop();
  }

  return out;
}

function crossingIndex(augmented) {
  var index = {};
  augmented.forEach(function (node, i) {
    if (node.inter && index[node.key] === undefined) index[node.key] = i;
  });
  return index;
}

function ensureCCW(ring) {
  return ringSignedArea(ring) < 0 ? ring.slice().reverse() : ring;
}

function pointKey(p) {
  return p[0].toFixed(6) + "|" + p[1].toFixed(6);
}

function samePoint(a, b) {
  return Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6;
}

/** Intersection of two segments with both parameters, or null if they don't meet. */
function segmentIntersection(p1, p2, p3, p4) {
  var d1x = p2[0] - p1[0];
  var d1y = p2[1] - p1[1];
  var d2x = p4[0] - p3[0];
  var d2y = p4[1] - p3[1];

  var denom = d1x * d2y - d1y * d2x;
  if (Math.abs(denom) < 1e-12) return null; // parallel or collinear

  var t = ((p3[0] - p1[0]) * d2y - (p3[1] - p1[1]) * d2x) / denom;
  var u = ((p3[0] - p1[0]) * d1y - (p3[1] - p1[1]) * d1x) / denom;
  if (t < -1e-9 || t > 1 + 1e-9 || u < -1e-9 || u > 1 + 1e-9) return null;

  return { point: [p1[0] + t * d1x, p1[1] + t * d1y], t: t, u: u };
}

function pointInRing(ring, p) {
  var inside = false;

  for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    var xi = ring[i][0],
      yi = ring[i][1];
    var xj = ring[j][0],
      yj = ring[j][1];

    if (yi > p[1] !== yj > p[1]) {
      var xint = ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi;
      if (p[0] < xint) inside = !inside;
    }
  }

  return inside;
}

function pointOnRingBoundary(ring, p) {
  for (var i = 0; i < ring.length; i++) {
    var a = ring[i];
    var b = ring[(i + 1) % ring.length];
    var len = Math.sqrt(
      (b[0] - a[0]) * (b[0] - a[0]) + (b[1] - a[1]) * (b[1] - a[1]),
    );
    if (len < 1e-9) continue;

    var cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]);
    if (Math.abs(cross) / len > 1e-3) continue;

    var dot = (p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1]);
    if (dot >= -1e-6 && dot <= len * len + 1e-6) return true;
  }

  return false;
}

/**
 * Build one ring out of two, opening each at the span between its selected
 * vertices and connecting the loose ends. Each outline can open on either of the
 * two spans between its picks, so all combinations are tried and the largest
 * non-self-intersecting result wins (i.e. the one that discards the least area).
 */
function bridgeRings(A, ai1, ai2, B, bi1, bi2) {
  if (ai1 < 0 || ai2 < 0 || bi1 < 0 || bi2 < 0) return null;
  if (ai1 === ai2 || bi1 === bi2) return null;

  var aArcs = [ringArc(A, ai2, ai1), ringArc(A, ai1, ai2)];
  var bArcs = [];
  [ringArc(B, bi1, bi2), ringArc(B, bi2, bi1)].forEach(function (arc) {
    bArcs.push(arc, arc.slice().reverse());
  });

  var best = null;

  aArcs.forEach(function (aArc) {
    bArcs.forEach(function (bArc) {
      var ring = aArc.concat(bArc);
      if (ring.length < 3 || !isSimplePolygon(ring)) return;

      var area = Math.abs(ringSignedArea(ring));
      if (!best || area > best.area) {
        best = { ring: ring, area: area };
      }
    });
  });

  return best ? best.ring : null;
}

/** Ring vertices from index `from` forward to `to`, both inclusive. */
function ringArc(pts, from, to) {
  var arc = [];
  var i = from;

  for (;;) {
    arc.push(pts[i]);
    if (i === to) break;
    i = (i + 1) % pts.length;
  }

  return arc;
}

function ringSignedArea(ring) {
  var sum = 0;
  for (var i = 0; i < ring.length; i++) {
    var next = ring[(i + 1) % ring.length];
    sum += ring[i][0] * next[1] - next[0] * ring[i][1];
  }
  return sum / 2;
}

/** True when no two non-adjacent edges of the ring cross. */
function isSimplePolygon(ring) {
  var n = ring.length;

  for (var i = 0; i < n; i++) {
    for (var j = i + 1; j < n; j++) {
      // Skip edges sharing an endpoint (consecutive, plus the closing wrap-around)
      if (j === i + 1 || (i === 0 && j === n - 1)) continue;

      if (
        segmentsCross(ring[i], ring[(i + 1) % n], ring[j], ring[(j + 1) % n])
      ) {
        return false;
      }
    }
  }

  return true;
}

/** Proper segment intersection (shared endpoints and collinear touching don't count). */
function segmentsCross(p1, p2, p3, p4) {
  var orientation = function (a, b, c) {
    var v = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1]);
    if (v > 1e-9) return 1;
    if (v < -1e-9) return 2;
    return 0;
  };

  var o1 = orientation(p1, p2, p3);
  var o2 = orientation(p1, p2, p4);
  var o3 = orientation(p3, p4, p1);
  var o4 = orientation(p3, p4, p2);

  return o1 !== 0 && o2 !== 0 && o3 !== 0 && o4 !== 0 && o1 !== o2 && o3 !== o4;
}

/** Project point `p` onto segment [a, b], clamped to the segment's endpoints. */
function closestPointOnSegment(p, a, b) {
  var abx = b[0] - a[0];
  var aby = b[1] - a[1];
  var lengthSq = abx * abx + aby * aby;

  if (lengthSq === 0) return a;

  var t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / lengthSq;
  t = Math.max(0, Math.min(1, t));

  return [a[0] + t * abx, a[1] + t * aby];
}

export { unionPolygons, bridgeRings, closestPointOnSegment };
