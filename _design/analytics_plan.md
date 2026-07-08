````md
# Analytics Extraction Plan

## Goal

Extract Analytics from the Controller into an independent service while preserving existing behavior, MQTT contracts, and downstream compatibility.

The extraction should be performed incrementally, with architecture cleanup first and process separation later.

---

# Phase 1: Define a Stable Analytics Contract

## Objective

Remove direct dependencies on Controller internal data structures.

## Activities

- Define dedicated analytics models:
  - `AnalyticsFrame`
  - `AnalyticsObject`
  - `AnalyticsEvent`
  - `AnalyticsConfig`

- Identify the minimum set of fields required by analytics.
- Separate analytics contracts from:
  - `MovingObject`
  - `ChainData`
  - Tracker internals
  - Re-ID internals

## Deliverable

```text
Tracker -> Analytics Contract -> Analytics Engine
```

Analytics becomes consumer of a stable API instead of Controller internals.

---

# Phase 2: Extract Analytics into a Dedicated Library

## Objective

Move analytics logic out of `scene.py`.

## Activities

Extract:

- Region analytics
- Tripwire analytics
- Event generation
- Sensor analytics

Possible structure:

```text
analytics/
├── engine.py
├── region.py
├── tripwire.py
├── sensors.py
├── models.py
└── state.py
```

Controller becomes only an orchestrator.

Instead of:

```python
scene._updateEvents(...)
```

it becomes:

```python
analytics.process(frame)
```

## Deliverable

Reusable analytics package with no Controller-specific logic.

---

# Phase 3: Introduce Analytics-Owned State

## Objective

Move state ownership from Controller to Analytics.

## Activities

Create:

```text
AnalyticsStateStore
```

Responsibilities:

- Region enter/exit tracking
- Dwell time tracking
- Tripwire debounce state
- Sensor state/history
- Object history used by analytics

## Deliverable

Analytics manages all state required to reproduce existing behavior.

No dependency on Controller runtime state.

---

# Phase 4: Introduce MQTT Adapters

## Objective

Allow Analytics to consume tracked data independently.

## Activities

Create adapters:

```text
MQTT Scene Data
        ↓
AnalyticsFrame
        ↓
Analytics Engine
        ↓
Analytics Events
```

Implement:

- Scene-data ingestion adapter
- Analytics event publisher adapter

Reuse the existing analytics-only flow as much as possible.

## Deliverable

Analytics package can operate as a standalone process.

---

# Phase 5: Run in Shadow Mode

## Objective

Validate behavioral compatibility.

## Activities

Run:

```text
Controller Analytics
        +
Analytics Service
```

simultaneously.

Compare:

- Region enter events
- Region exit events
- Dwell calculations
- Tripwire events
- Sensor events

Investigate and eliminate differences.

## Deliverable

Verified behavioral parity.

---

# Phase 6: Move Publication Responsibility

## Objective

Transfer output ownership to Analytics.

## Stage A

```text
Analytics -> Controller -> MQTT
```

Controller remains publisher.

## Stage B

```text
Analytics -> MQTT
```

Analytics publishes directly.

## Deliverable

Controller no longer owns analytics outputs.

---

# Phase 7: Address Scene Hierarchy

## Objective

Handle parent-child scene event propagation.

## Activities

Evaluate ownership of:

- Event republishing
- Coordinate transformation
- Hierarchy event aggregation

Do not block initial extraction on hierarchy support.

Recommended approach:

```text
Analytics v1
    without hierarchy

Analytics v2
    with hierarchy support
```

## Deliverable

Separate, well-defined hierarchy integration strategy.

---

# Target Architecture

```text
                   +-------------------+
                   |     Tracker       |
                   +-------------------+
                             |
                             |
                        scene-data
                             |
                             v
                   +-------------------+
                   | Analytics Service |
                   +-------------------+
                    |       |        |
                    |       |        |
                    v       v        v
                 Events  Region   Regulated
                          Data    Outputs
```

Future evolution:

```text
Tracker
    |
    +--> Analytics Service
    |
    +--> Re-ID Service
    |
    +--> Projection Service
    |
    +--> Hierarchy Service
```

---

# Input/Output Consumer/Producer MQTT topics

                           +------------------+
                           | Analytics        |
                           +------------------+

Consumes:
----------
scenescape/data/scene/*
scenescape/data/sensor/*
scene configuration

Produces:
----------
scenescape/regulated/scene/*
scenescape/data/region/*
scenescape/event/region/*
scenescape/event/tripwire/*
scenescape/event/sensor/*

# Recommended First Implementation Task

1. Create `AnalyticsObject` and `AnalyticsFrame`.
2. Remove direct dependencies on `MovingObject`.
3. Introduce Analytics library boundaries.
4. Keep everything in-process initially.
5. Extract the service only after contract and state ownership are clean.

This minimizes risk and turns service extraction into an integration task rather than a major architectural rewrite.
````
