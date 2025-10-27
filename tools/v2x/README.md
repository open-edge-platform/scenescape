# MQTT to V2X PSM Bridge

Bridge service that converts SceneScape pedestrian detection data to V2X Personal Safety Messages (PSM).

## Overview

This tool subscribes to SceneScape MQTT topics containing pedestrian detection data and automatically converts it to V2X Personal Safety Messages, which are then posted to a V2X Hub API. This enables vehicles to receive real-time alerts about pedestrian locations for enhanced road safety.

## Features

- **Real-time conversion**: Subscribes to SceneScape MQTT streams and processes detections in real-time
- **Geospatial transformation**: Converts coordinates from WGS84 to Web Mercator format required by V2X
- **Speed calculation**: Computes pedestrian speed from velocity vectors
- **Configurable**: All settings via environment variables

## Requirements

- Python 3.10+
- SceneScape MQTT broker access
- V2X Hub API endpoint

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## Configuration

All configuration is done via environment variables:

### MQTT Configuration

| Variable        | Description                  | Default                                |
| --------------- | ---------------------------- | -------------------------------------- |
| `MQTT_SERVER`   | MQTT broker address          | `localhost`                            |
| `MQTT_PORT`     | MQTT broker port             | `1883`                                 |
| `MQTT_USERNAME` | MQTT username                | `admin`                                |
| `MQTT_PASSWORD` | MQTT password                | _(empty)_                              |
| `MQTT_USE_TLS`  | Enable TLS for MQTT          | `true`                                 |
| `REGION_ID`     | SceneScape region ID or name | `97781c36-b53a-4749-87e6-8815da99bac7` |

### V2X Configuration

| Variable          | Description                   | Default                 |
| ----------------- | ----------------------------- | ----------------------- |
| `V2X_API_URL`     | V2X Hub API endpoint          | `http://127.0.0.1:9000` |
| `V2X_API_TIMEOUT` | API request timeout (seconds) | `5`                     |

### Logging Configuration

| Variable    | Description                                           | Default |
| ----------- | ----------------------------------------------------- | ------- |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | `INFO`  |

## Usage

### Basic Usage

```bash
# Run with defaults
python mqqt_psm.py
```

### With Custom Configuration

```bash
# Set environment variables
export MQTT_SERVER=broker.example.com
export MQTT_USERNAME=my-user
export MQTT_PASSWORD=my-password
export REGION_ID=intersection-main-street
export V2X_API_URL=http://v2xhub.example.com:9000
export LOG_LEVEL=DEBUG

# Run the bridge
python mqqt_psm.py
```

### Using a `.env` File

Create a `.env` file:

```bash
MQTT_SERVER=broker.example.com
MQTT_USERNAME=my-user
MQTT_PASSWORD=my-password
REGION_ID=intersection-main-street
V2X_API_URL=http://v2xhub.example.com:9000
LOG_LEVEL=INFO
```

Run with:

```bash
# Load environment variables
set -a; source .env; set +a

# Run the bridge
python mqqt_psm.py
```

### Docker Usage

Build the image:

```bash
docker build -t scenescape-v2x-bridge .
```

Run with host networking to access both MQTT and V2X Hub via localhost:

```bash
docker run --network host \
  -e REGION_ID=my-region \
  -e MQTT_PASSWORD=$SUPASS \
  scenescape-v2x-bridge
```

Or in docker-compose:

```yaml
services:
  v2x-bridge:
    build: tools/v2x
    network_mode: host
    environment:
      - REGION_ID=${REGION_ID}
      - MQTT_PASSWORD=${SUPASS}
```

## How It Works

1. **Subscribe**: Connects to MQTT broker and subscribes to `scenescape/data/region/{REGION_ID}/#`
2. **Filter**: Processes only pedestrian detections from the stream
3. **Transform**: Converts geospatial coordinates and calculates speed
4. **Generate**: Creates V2X PSM XML messages with pedestrian data
5. **Publish**: Posts PSM messages to V2X Hub API

## Data Flow

```
SceneScape Detection
    ↓ (MQTT)
MQTT Broker
    ↓ (subscribe)
PSM Bridge
    ├─ Filter pedestrians
    ├─ Calculate speed
    ├─ Transform coordinates
    └─ Generate PSM XML
    ↓ (HTTP POST)
V2X Hub API
    ↓
V2X Infrastructure
```

## PSM Message Format

The bridge generates Personal Safety Messages following the J2735 standard:

- **Basic Type**: Pedestrian
- **Position**: Latitude, longitude, elevation (in microdegrees)
- **Speed**: Calculated from velocity vector (m/s)
- **Heading**: Direction of movement (degrees)
- **Accuracy**: Position accuracy indicators
- **Cluster Info**: Pedestrian grouping information

## Related Documentation

- [SceneScape Documentation](https://github.com/open-edge-platform/scenescape)
- [V2X Hub Documentation](https://github.com/usdot-fhwa-OPS/V2X-Hub)
- [J2735 PSM Standard](https://standards.sae.org/j2735_202007/)
