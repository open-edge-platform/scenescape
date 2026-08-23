<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Physical World Grounding — Design Documents

Proposed architecture for using Scenescape as **physical ontological grounding** for mission agents: connecting disconnected model and enterprise outputs into shared meaning, with calibrated confidence for semi-autonomous and autonomous decisions—not another inference+rules stack.

| Doc | Phase | Summary | Demo companion |
|-----|-------|---------|----------------|
| [00 — Overview and roadmap](00-overview-and-roadmap.md) | Program | Vision, layering, third-party map, risks | [D0 Trust Triangle](06-demo-companions.md#6-d0--trust-triangle-pattern--overview) |
| [01 — Propose / Ground / Validate](01-propose-ground-validate.md) | Pattern | Shared vocabulary, claim/evidence/fact model | [D0 Trust Triangle](06-demo-companions.md#6-d0--trust-triangle-pattern--overview) |
| [02 — Fact projection and claim bus](02-fact-projection-and-claim-bus.md) | **P1** | MQTT → evidence/claims; proposer adapters | [D1 Claim Radar](06-demo-companions.md#7-d1--claim-radar-phase-1) |
| [03 — World model and identity](03-world-model-and-identity.md) | **P2** | Durable graph, dossiers, agent API | [D2 World Time Machine](06-demo-companions.md#8-d2--world-time-machine-phase-2) |
| [04 — Ontology packs and validator](04-ontology-packs-and-validator.md) | **P3** | Core + vertical packs; trust policies | [D3 Policy Arena](06-demo-companions.md#9-d3--policy-arena-phase-3) |
| [05 — Mission constraints and agent loop](05-mission-constraints-and-agent-loop.md) | **P4** | Goals, monitors, actuate-and-verify | [D4 Mission Cockpit](06-demo-companions.md#10-d4--mission-cockpit-phase-4) |
| [06 — Demo and app companions](06-demo-companions.md) | All | Contrast apps: connect → mean → trust-to-act | Catalog + scripts + [OEP reuse](06-demo-companions.md#12-open-edge-platform-reuse-extend-dont-rebuild) |

**Status:** all documents `Proposed` (2026-08-23). Implementation should land phase ADRs when technology choices freeze.
