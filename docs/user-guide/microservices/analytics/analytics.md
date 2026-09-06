<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/scenescape/tree/main/analytics">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/scenescape/blob/main/analytics/README.md">
     Readme
  </a>
</div>
hide_directive-->

# Analytics Service

The Analytics Microservice computes region, tripwire, and sensor analytics for objects
tracked in a Scenescape scene, and publishes the resulting detections and events for
downstream consumers.

## Overview

The Analytics service consumes unregulated tracked-object messages published by the Scene
Controller (or any upstream Tracker) on `scenescape/data/scene/{scene_id}/{thing_type}`,
together with raw sensor readings on `scenescape/data/sensor/{sensor_id}`. It correlates
those inputs and publishes:

- **Regulated (rate-controlled) detections** aggregating all object categories into a single
  message per scene.
- **Region and tripwire events**, including enter/exit detection and dwell-time tracking.
- **Sensor-correlated object state**, tagging tracked objects with readings from
  environmental and attribute sensors located inside their measurement area.

The Scene Controller itself performs no sensor correlation, regulated output, or
region/tripwire event publishing in any mode — that functionality is owned exclusively by
this service. See the [Scene Controller](../controller/controller.md) overview for the
unregulated tracking output this service consumes.

## Input/Output Message Formats

For details on the MQTT message formats accepted and produced by the Analytics service, see
[Analytics Service Data Formats](./data_formats.md).

## Supporting Resources

- [Data Formats](./data_formats.md)
- [API Reference](./api-reference.md)
- [Analytics Service README](https://github.com/open-edge-platform/scenescape/blob/main/analytics/README.md)
- [Scene Controller](../controller/controller.md)

<!--hide_directive
:::{toctree}
:hidden:

API Reference <api-reference.md>
data_formats.md

:::
hide_directive-->
