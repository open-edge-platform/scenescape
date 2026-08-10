# Use Environmental and Attribute Sensor Types in Scenescape

This guide provides step-by-step instructions to integrate and use environmental and attribute sensor types in Scenescape. By completing this guide, you will:

- Understand the differences between environmental and attribute sensors.
- Learn how to configure and publish sensor data to Scenescape.
- Verify that sensor data is properly associated with tracked scene objects.

This task is important for enhancing your scene graph with real-world sensor data, enabling deeper insights from environmental context and object-specific attributes. If you're new to Scene Graphs or Scenescape, see [Integrating Cameras and Sensors](../integrate-cameras-and-sensors.md).

---

## Prerequisites

Before you begin, ensure the following:

- **Access and Permissions**: When using Scenescape secure broker for publishing sensor data, refer to [user access controls](https://github.com/open-edge-platform/scenescape/blob/release-2026.1.0/manager/config/user_access_config.json) and [access levels](https://github.com/open-edge-platform/scenescape/blob/release-2026.1.0/scene_common/src/scene_common/options.py).

If you're new to these concepts, see:

- [Scenescape README](https://github.com/open-edge-platform/scenescape/blob/release-2026.1.0/README.md)
- [MQTT Intro](https://mqtt.org/getting-started/)

---

## Steps to Integrate Environmental and Attribute Sensors

### 1. Understand Sensor Types

**Environmental Sensors** measure a property (e.g., temperature) for all objects within a defined measurement zone.
**Attribute Sensors** detect a property (e.g., badge ID) for a specific object and persist that value even after the object leaves the measurement area.

---

### 2. Configure and Use an Environmental Sensor

#### Create the Sensor

1. Log in to Scenescape.
2. Click on a scene.
3. Click on `Sensors` at the bottom of the scene.
4. Click `New Sensor` to create a sensor.
5. In the New Sensor form, fill out `Sensor ID`, `Name` and `Scene` fields.
6. Update the `Type of Sensor` to environmental.
7. Click `Add New Sensor` to save.

### Modify the Sensor

1. Click on `Sensors` at the bottom of the scene.
2. You will see the created sensor. Then click on the `manage` button.
3. In the Manage Sensor view, you can update attributes like Measurement area (Entire Scene, Circle or Custom region), Name, Sensor id, Scene, Singleton type, Color Range, etc. For more details on how to use the Color Range, refer to [Visualizing ROI and Sensor Areas](./visualize-regions.md).
4. Cick on `Save Sensor `to persist the modified sensor.

#### Publish Environmental Sensor Readings

From a third party application, publish sensor data to the topic `scenescape/data/sensor/<sensorName>`

> **Notes:**
>
> - Refer to [Singleton Sensor Data](../integrate-cameras-and-sensors.md#singleton-sensor-data) on what a sensor data looks and how to publish sensor data.

#### Verify the Results

Check the scene graph for objects within the sensor region:

![Sensor JSON Data Example](../../_assets/environment_sensor.png)

**Expected Results**:

- All tracked objects within the region are tagged with the temperature value in their scene graph updates.

---

### 3. Configure and Use an Attribute Sensor

#### Step 1: Create the Sensor

1. Log in to Scenescape.
2. Click on a scene.
3. Click on `Sensors` at the bottom of the scene.
4. Click `New Sensor` to create a sensor.
5. In the New Sensor form, fill out `Sensor ID`, `Name` and `Scene` fields.
6. Update the `Type of Sensor` to attribute.
7. Click `Add New Sensor` to save.

Refer to [Modify the Sensor](#modify-the-sensor) on how to modify the attribute sensor.

#### Step 2: Publish Attribute Sensor Readings

From a third party application, publish sensor data to the topic `scenescape/data/sensor/<sensorName>`

> **Notes:**
>
> - Refer to [Singleton Sensor Data](../integrate-cameras-and-sensors.md#singleton-sensor-data) on what a sensor data looks and how to publish sensor data.

#### Step 3: Verify the Results

Check updates for the target object:

![Sensor JSON Data Example](../../_assets/attribute_sensor.png)

**Expected Results**:

- The object receives and retains the badge ID even after leaving the sensor zone.

---

## REST API Reference

Sensors can also be created, updated, listed, and deleted over the REST API instead of the UI —
useful for scripting a scene-wide sensor that has no shape to draw.

```bash
curl -sk -X POST https://<manager-host>/api/v1/sensor \
    -H "Authorization: Token $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "lobby_temperature",
        "scene": "<scene-uid>",
        "area": "scene",
        "singleton_type": "environmental"
    }'
```

For the full field reference (all accepted fields, `area`/`singleton_type` enum values), see the
canonical OpenAPI spec: [API Reference](../../api-reference.md) (source:
`docs/user-guide/api-docs/api.yaml`, `Singleton` schema). The API reference doesn't capture these
validation rules, which only live in server-side logic:

- `center`+`radius` are required when `area` is `circle`; `points` is required when `area` is
  `poly`.
- If `sensor_id` isn't supplied on create, it defaults to `name` with spaces replaced by
  underscores.
- `color_ranges.sectors[].color` must be one of `green`, `yellow`, or `red`:
  ```json
  {
    "color_ranges": {
      "sectors": [
        { "color": "green", "color_min": "0" },
        { "color": "yellow", "color_min": "2" },
        { "color": "red", "color_min": "5" }
      ],
      "range_max": 10
    }
  }
  ```

## Supporting Resources

- [Visualize ROI and Sensor Areas](./visualize-regions.md)
- [Scenescape README](https://github.com/open-edge-platform/scenescape/blob/release-2026.1.0/README.md)
