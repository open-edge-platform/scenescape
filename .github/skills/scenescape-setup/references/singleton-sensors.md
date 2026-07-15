<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Singleton sensors (non-perceptual data sources)

Read this when the user wants to feed a scene with data that isn't derived from a vision
pipeline — a temperature reading, a light level, a badge swipe, a beam-break, or any other
external value that should tag the object tracks near it. In the manager these are called
"Sensors" in the nav bar and "singleton sensors" throughout the product docs and code (the
`SingletonSensor` model, `/singleton_sensor/...` URLs); you may also see the readings themselves
described as "scalar sensor readings."

## Two sensor types — pick the right one

`singleton_type` has exactly two values. Choosing correctly matters because it changes how the
value is expected to behave over time:

| Type            | Use when the value...                                                      | Examples                                    |
| ---------------- | ---------------------------------------------------------------------------- | -------------------------------------------- |
| `environmental` | varies continuously and should be tagged/updated on every reading           | temperature, humidity, air quality, light level (lux) |
| `attribute`     | is a discrete identifier or event tied to a presence, published occasionally | badge/RFID read, boolean beam-break or pressure-mat trigger |

**Not to be confused with attribute persistence:** a `singleton_type: attribute` sensor is an
*external, non-vision* data source (e.g. a badge reader publishing over MQTT). This is unrelated
to `persist_attributes` in `tracker-config.json`, which keeps *vision-pipeline-detected*
attributes (color, license plate, age/gender) from resetting between frames — see
[attribute-persistence.md](./attribute-persistence.md) for that instead. If the value comes from
the camera/AI pipeline, use attribute persistence; if it comes from a separate physical or virtual
sensor publishing its own MQTT messages, use a singleton sensor here.

## Measurement area: scene vs. circle/poly

A sensor's `area` controls which object tracks get tagged with its readings:

- **`scene`** — applies to every object in the scene. No shape to define; fully REST-scriptable.
- **`circle`** / **`poly`** — applies only to objects inside a smaller zone. The shape is drawn
  visually on the scene map, so **guide the user to the web UI** instead of asking them to supply
  raw coordinates:
  1. Sign in to the manager web UI (`https://web.scenescape.intel.com`, superuser credentials in
     `secrets/supass`).
  2. Open **Sensors** in the nav bar (`/singleton_sensor/list/`), then **Create**
     (`/singleton_sensor/create/`).
  3. Select the scene, choose `circle` or `poly` as the area, and draw the shape on the map.
  4. Fill in name, sensor ID, and `singleton_type`, then save.

  Only fall back to supplying `points`/`center`+`radius` directly over REST if the user already
  has exact scene-map coordinates from another source (e.g. scripted from a floor-plan
  pixels-per-meter conversion) — most users will find the UI far more intuitive for this step.

## Creating a scene-wide sensor via REST

This is the one case that's fully scriptable without the UI, since there's no shape to draw:

```bash
curl -sk -X POST https://web.scenescape.intel.com/api/v1/sensor \
    -H "Authorization: Token $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "lobby_temperature",
        "scene": "<scene-uid>",
        "area": "scene",
        "singleton_type": "environmental"
    }'
```

Optional color-coded thresholds (for UI visualization of the sensor's reading):

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
Add this as an additional key in the same create/update payload.

## Publishing readings

Creating the sensor only registers it — readings must be published separately over MQTT to
`scenescape/data/sensor/<sensor_id>`:

```json
{
  "id": "lobby_temperature",
  "timestamp": "2026-07-15T21:33:09.832Z",
  "value": 22.5
}
```

`value` accepts any JSON value (numeric for `environmental`, or a string/boolean/identifier for
`attribute`). See `docs/user-guide/microservices/controller/data_formats.md` in the SceneScape
repo for the full message schema.

## Notes

- If `sensor_id` is omitted on create, it defaults to `name` with spaces replaced by underscores.
- List existing sensors: `GET https://web.scenescape.intel.com/api/v1/sensors`.
- Delete: `curl -sk -X DELETE https://web.scenescape.intel.com/api/v1/sensor/<sensor_id> -H "Authorization: Token $TOKEN"`.
