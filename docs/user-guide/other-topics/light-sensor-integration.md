# Controlling Scene Lighting with Physical Light Sensors

SceneScape can automatically adjust the 3D scene lighting based on real-time data from physical light sensors in your environment. This creates a digital twin that reflects actual lighting conditions.

## Overview

SceneScape's singleton sensor infrastructure allows you to connect environmental sensors (light, temperature, humidity, etc.) to your scenes. When you publish light sensor data via MQTT, the 3D viewer automatically adjusts the scene's ambient lighting to match the physical environment.

This feature enables:

- **Realistic digital twins** - Scene lighting matches actual room conditions
- **Dynamic visualization** - Real-time lighting adjustments as conditions change
- **Manual override** - GUI controls for testing or manual adjustments
- **Multiple sensors** - Support for various environmental sensors beyond just light

## Prerequisites

- A physical light sensor connected via MQTT (e.g., Arduino with light sensor, BH1750 module, etc.)
- Sensor data publisher that sends to SceneScape's MQTT broker
- Admin access to create singleton sensors in SceneScape

## Setup

### 1. Create a Singleton Sensor

In the SceneScape UI:

1. Go to your scene page
2. Click **"+ New Sensor"** in the Sensors section
3. Fill in the form:
   - **Sensor ID**: `warehouse_01_light` (must match your publisher config)
   - **Name**: "Room Light Sensor" (descriptive name)
   - **Type**: Environmental
   - **Scene**: Select your scene
   - **Area**: **Scene** (required for scene lighting control - see note below)
4. Click **Create**

**Important:** To control the 3D scene's ambient lighting, the sensor's measurement area **must be set to "Scene"**. Sensors with area types "Circle" or "Polygon" will only tag tracked objects within their measurement area and will not affect scene lighting. This ensures that localized sensors don't incorrectly control overall scene illumination.

### 2. Configure Your Sensor Publisher

Your sensor must publish data in SceneScape's singleton sensor format to the topic: `scenescape/data/sensor/{sensor_id}`

**Required message format:**

```json
{
  "id": "your_sensor_id_light",
  "timestamp": "2026-01-16T10:30:45.123Z",
  "value": 350,
  "subtype": "light"
}
```

**Message fields:**

- `id` - Must match the sensor ID created in SceneScape
- `timestamp` - ISO 8601 format in UTC
- `value` - Numeric sensor reading in SI units (lux for light sensors, °C for temperature, % for humidity)
- `subtype` - Sensor type identifier (e.g., "light", "temperature")

**Example configuration for an Arduino-based publisher:**

**Example configuration for an Arduino-based publisher:**

```json
{
  "sensor_id": "warehouse_01",
  "mqtt_broker": "your-scenescape-host",
  "mqtt_port": 1883,
  "mqtt_username": "scenectrl",
  "mqtt_password": "your-password",
  "mqtt_use_tls": true,
  "mqtt_tls_insecure": true
}
```

**Example: Raw sensor readings from hardware:**

```json
{
  "light": 425,
  "temperature": 22.5,
  "humidity": 45.0
}
```

**Result: Three separate MQTT messages are published:**

Each sensor reading is published as a separate message in SceneScape singleton format:

```json
// Message 1 - to topic: scenescape/data/sensor/warehouse_01_light
{
  "id": "warehouse_01_light",
  "timestamp": "2026-01-16T10:30:45.123Z",
  "value": 425,
  "subtype": "light"
}

// Message 2 - to topic: scenescape/data/sensor/warehouse_01_temperature
{
  "id": "warehouse_01_temperature",
  "timestamp": "2026-01-16T10:30:45.123Z",
  "value": 22.5,
  "subtype": "temperature"
}

// Message 3 - to topic: scenescape/data/sensor/warehouse_01_humidity
{
  "id": "warehouse_01_humidity",
  "timestamp": "2026-01-16T10:30:45.123Z",
  "value": 45.0,
  "subtype": "humidity"
}
```

Create a corresponding singleton sensor in SceneScape for each sensor type you want to use (e.g., one for light, one for temperature, etc.).

## How Light Sensing Works

### Message Flow

1. Physical light sensor measures ambient illuminance in lux (SI unit: lx)
2. Publisher formats data and sends via MQTT to `scenescape/data/sensor/{sensor_id}`
3. SceneScape 3D viewer receives the message
4. Scene lighting automatically adjusts to match the sensor value

### Sensor Format

The 3D viewer subscribes to `scenescape/data/sensor/+` and processes messages with `subtype: "light"`.

**Example message:**

```json
{
  "id": "warehouse_01_light",
  "timestamp": "2026-01-16T10:30:45.123Z",
  "value": 425,
  "subtype": "light"
}
```

**Note:** The `value` field for light sensors must be in **lux** (lx), the SI unit for illuminance.

### Light Intensity Conversion

The 3D scene converts lux values from your sensor to scene light intensity (0.0-2.0 range):

**Conversion formula:** `intensity = min(value / 500, 2.0)`

- 500 lux → 1.0 intensity (normal lighting)
- 250 lux → 0.5 intensity (dim)
- 1000 lux → 2.0 intensity (bright)

**Clamping:** Values are clamped to a minimum of 0.1 to ensure the scene is never completely dark.

### Result

- **Intensity 0.1-0.5**: Dim scene (low light)
- **Intensity 1.0**: Normal lighting
- **Intensity 1.5-2.0**: Bright scene (high light)

## Using the Feature

### Start Publishing Sensor Data

Run your sensor publisher to begin sending light data:

```bash
python your_sensor_publisher.py
```

**You should see output like:**

```text
Connected to MQTT broker
Sensor data received: {'light': 425}
Published to scenescape/data/sensor/warehouse_01_light: light=425
```

### View in the 3D Scene

1. Open your scene in the SceneScape 3D viewer
2. The scene lighting will automatically adjust based on sensor values
3. Open the control panel to see the "light intensity" slider showing current value
4. Open browser console (F12) to see sensor update messages:

   ```text
   Subscribed to scenescape/data/sensor/+
   Light sensor (warehouse_01_light): value=425 -> intensity=0.850
   ```

### Manual Control

The 3D viewer includes a GUI slider for manual light control:

- **Range**: 0.0 to 2.0
- **Default**: 1.0 (normal lighting)
- **Behavior**: Sensor values override manual settings when new data arrives
- **Use case**: Testing different lighting levels without changing physical conditions

## Sensor Value Guidelines

### Light Sensor Requirements

All light sensors must report illuminance in **lux** (lx), the SI unit for illuminance (lumens per square meter).

Common light sensors that measure in lux:

- **BH1750** - Digital ambient light sensor (1-65535 lux range)
- **TSL2561** - Digital light sensor (0.1-40000 lux range)
- **VEML7700** - High accuracy ambient light sensor (0-120000 lux)

### Typical Lux Values

| Lux Value | Environment | Scene Intensity |
|-----------|-------------|-----------------|
| 50-100 | Very dim room | 0.1-0.2 |
| 200-400 | Typical indoor | 0.4-0.8 |
| 500 | Well-lit office | 1.0 |
| 750-1000 | Bright room | 1.5-2.0 |
| 1000+ | Very bright (near window) | 2.0 (max) |

### Converting Analog Sensors to Lux

If using analog sensors (photoresistors, etc.), you must calibrate and convert readings to lux before publishing:

```arduino
int sensorValue = analogRead(A0);
// Calibrate this mapping based on your specific sensor and environment
float lux = map(sensorValue, 0, 1023, 0, 1000);
```

**Important:** Use a reference lux meter to calibrate your analog sensor for accurate readings.

## Troubleshooting

### Scene Lighting Not Changing

**Check sensor is registered:**

- Verify the singleton sensor exists in SceneScape UI
- Sensor ID must match exactly (case-sensitive)
- Example: If publishing to `warehouse_01_light`, sensor ID must be `warehouse_01_light`

**Check browser console (F12):**

```text
# Should see subscription message on page load:
Subscribed to scenescape/data/sensor/+

# Should see updates when sensor publishes:
Light sensor (warehouse_01_light): value=425 -> intensity=0.850
```

**Check publisher output:**

```text
# Should see successful publish messages:
Published to scenescape/data/sensor/warehouse_01_light: light=425
```

**Verify MQTT connection:**

- Confirm broker hostname/IP is correct
- Check MQTT credentials are valid
- Verify TLS settings match broker configuration
- Test MQTT connectivity with mosquitto_sub:
  ```bash
  mosquitto_sub -h your-broker -t "scenescape/data/sensor/#" -u scenectrl -P password
  ```

### Lighting Values Seem Wrong

The scene may be too bright or too dim for your sensor values.

**Possible causes:**

- **Sensor not calibrated** - Analog sensors need calibration against a reference lux meter
- **Wrong sensor range** - Verify your sensor is reporting actual lux values
- **Environmental factors** - Sensor placement affects readings (e.g., direct sunlight vs ambient)

**Solutions:**

- Calibrate your sensor against known lux values
- Verify sensor datasheet specifications and output range
- Ensure sensor placement represents the environment accurately

### Sensor ID Mismatch

If sensor data isn't being processed:

- **Publisher ID**: Check what your publisher sends in the `id` field
- **SceneScape ID**: Must match exactly in the singleton sensor configuration
- **Topic**: Verify the MQTT topic includes the correct sensor ID

Common pattern: Base sensor ID + underscore + sensor type

- Publisher config: `sensor_id: "warehouse_01"`
- Sensor type: `"light"`
- Resulting ID: `warehouse_01_light`

### Sensor Not Controlling Scene Lighting

If your light sensor is publishing data but the scene lighting isn't changing:

**Check sensor area configuration:**

- Open the sensor in SceneScape UI
- Verify **Area** is set to **"Scene"**
- Sensors with "Circle" or "Polygon" areas will not control scene lighting

**Check browser console for messages:**

```text
# If area is not "scene", you'll see:
Light sensor (warehouse_01_light): area="circle" - not controlling scene lighting (only "scene" area sensors affect ambient light)

# If sensor is not found:
Light sensor (warehouse_01_light): sensor not found in SensorManager - not controlling scene lighting
```

**Why this restriction?** Localized sensors (circle/polygon areas) measure lighting in specific zones and shouldn't affect the entire scene's ambient lighting. Only scene-wide sensors should control overall illumination.

## Advanced Usage

### Multiple Sensor Types

SceneScape's singleton sensor system supports various environmental sensors. Currently, light sensors control scene illumination. Future enhancements could include:

- **Temperature sensors** → Adjust color temperature (warm/cool lighting)
- **Humidity sensors** → Add atmospheric effects (fog, haze)
- **Motion sensors** → Trigger scene events or highlighting
- **Air quality sensors** → Visual indicators or color shifts

All sensors use the same MQTT topic pattern: `scenescape/data/sensor/{sensor_id}`

The `subtype` field determines how the data is processed. Light sensors are identified by `subtype: "light"` or by having "light" in the sensor ID.

### Multiple Light Sensors

You can have multiple light sensors in different areas:

**Scene-wide sensors (Area = "Scene"):**

- Control the overall ambient lighting of the 3D scene
- Represents general room illumination
- Most recently received value is applied to scene lighting
- Example: `warehouse_ambient_light` with Area = "Scene"

**Localized sensors (Area = "Circle" or "Polygon"):**

- Measure lighting in specific zones but do **not** control scene lighting
- Tag tracked objects with light levels when they enter the measurement area
- Useful for monitoring lighting conditions in specific locations
- Example: `warehouse_zone_a_light` with Area = "Circle" covering workstation

**Best practice:** Use one scene-wide sensor for ambient lighting control, and additional localized sensors for zone-specific monitoring without affecting overall scene illumination.

### Custom Sensor Implementations

Any system that can publish MQTT messages can control scene lighting:

- **IoT platforms** (Home Assistant, Node-RED, etc.)
- **Industrial sensors** (Modbus, OPC-UA gateways)
- **Cloud services** (AWS IoT, Azure IoT Hub)
- **Custom applications** (Python, Node.js, Java, etc.)

Just ensure messages follow the singleton sensor format and publish to the correct topic.

## Related Documentation

- [How to Integrate Cameras and Sensors](../using-intel-scenescape/how-to-integrate-cameras-and-sensors.md) - General singleton sensor documentation
- [Metadata Schema](https://github.com/open-edge-platform/scenescape/blob/release-2025.2/controller/src/schema/metadata.schema.json) - Singleton sensor message format specification
