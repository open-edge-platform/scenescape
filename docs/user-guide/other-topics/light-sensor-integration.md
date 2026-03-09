# Controlling Scene Lighting with Physical Light Sensors

SceneScape automatically adjusts 3D scene lighting based on real-time data from physical light sensors via MQTT, creating a digital twin that reflects actual lighting conditions.

## Setup

### Create a Singleton Sensor

In the SceneScape UI, create a new sensor with:

- **Sensor ID**: Must match your publisher config (e.g., `warehouse_01_light`)
- **Type**: Environmental
- **Area**: **scene** (required; see note below)

**Important:** Only sensors with area="scene" control scene lighting. Localized sensors (area="circle" or "poly") tag objects but do not affect ambient illumination.

**Sensor identification:** The 3D viewer identifies light sensors by `subtype: "light"` in the message payload, or by the sensor ID ending with `_light` (e.g., `warehouse_01_light`).

### Configure Your Sensor Publisher

Publish to: `scenescape/data/sensor/{sensor_id}`

**Message format:**

```json
{
  "id": "warehouse_01_light",
  "timestamp": "<ISO 8601 UTC timestamp>",
  "value": 425,
  "subtype": "light"
}
```

The `value` field must be in **lux** (SI unit for illuminance).

### Light Intensity Conversion

Lux values convert to scene intensity: `intensity = value / 500` (clamped to 0.1-3.0 range)

- 500 lux → 1.0 intensity (normal lighting)
- 250 lux → 0.5 intensity (dim)
- 1000 lux → 2.0 intensity (bright)

## Usage

Start your sensor publisher and open the 3D scene viewer. The lighting automatically adjusts based on sensor values.

### Manual Control

The 3D viewer includes a GUI slider for manual light control:

- **Range**: 0.1 to 3.0
- **Default**: 1.0 (normal lighting)
- **Behavior**: Sensor values automatically override manual settings when new data arrives

**Typical lux values:**

| Lux  | Environment | Intensity |
| ---- | ----------- | --------- |
| 100  | Dim room    | 0.2       |
| 400  | Indoor      | 0.8       |
| 500  | Office      | 1.0       |
| 1000 | Bright      | 2.0       |

## Troubleshooting

**Scene not changing:**

- Verify sensor area="scene" in SceneScape UI
- Check sensor ID matches publisher exactly (case-sensitive)
- View browser console (F12) for error messages

**Wrong lighting levels:**

- Calibrate analog sensors against a reference lux meter
- Verify sensor reports actual lux values
- Check sensor placement (avoid direct sunlight)

**Multiple sensors:**

- Scene sensors (area="scene") control ambient lighting
- Localized sensors (area="circle"/"poly") tag objects only
- Most recent scene sensor value is applied
