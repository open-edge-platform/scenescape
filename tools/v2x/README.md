# MQTT to V2X PSM Bridge

Bridge service that converts SceneScape pedestrian detection data to V2X Personal Safety Messages (PSM).

## Overview

This tool subscribes to SceneScape MQTT topics containing pedestrian detection data and automatically converts it to V2X Personal Safety Messages, which are then posted to a V2X Hub API. This enables vehicles to receive real-time alerts about pedestrian locations for enhanced road safety.

## Features

- **Real-time conversion**: Subscribes to SceneScape MQTT streams and processes detections in real-time
- **Multi-region support**: Automatically subscribes to all SceneScape regions
- **ASN.1 compliant**: Proper conversion of all fields to J2735 ASN.1 format
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

| Variable        | Description              | Default     |
| --------------- | ------------------------ | ----------- |
| `MQTT_SERVER`   | MQTT broker address      | `localhost` |
| `MQTT_PORT`     | MQTT broker port         | `1883`      |
| `MQTT_USERNAME` | MQTT username            | `admin`     |
| `MQTT_PASSWORD` | MQTT password            | _(empty)_   |
| `MQTT_USE_TLS`  | Enable TLS for MQTT      | `true`      |

> **Note**: The bridge automatically subscribes to **all regions** using the wildcard topic `scenescape/data/region/+/#`

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
python mqtt_psm.py
```

### With Custom Configuration

```bash
# Set environment variables
export MQTT_SERVER=broker.example.com
export MQTT_USERNAME=my-user
export MQTT_PASSWORD=my-password
export V2X_API_URL=http://v2xhub.example.com:9000
export LOG_LEVEL=DEBUG

# Run the bridge
python mqtt_psm.py
```

### Using a `.env` File

Create a `.env` file:

```bash
MQTT_SERVER=broker.example.com
MQTT_USERNAME=my-user
MQTT_PASSWORD=my-password
V2X_API_URL=http://v2xhub.example.com:9000
LOG_LEVEL=INFO
```

Run with:

```bash
# Load environment variables
set -a; source .env; set +a

# Run the bridge
python mqtt_psm.py
```

### Docker Usage

Build the image:

```bash
docker build -t scenescape-v2x-bridge .
```

Run with host networking to access both MQTT and V2X Hub via localhost:

```bash
docker run --network host \
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
      - MQTT_PASSWORD=${SUPASS}
```

## How It Works

1. **Subscribe**: Connects to MQTT broker and subscribes to `scenescape/data/region/+/#` (all regions)
2. **Filter**: Processes only pedestrian detections from the stream
3. **Transform**: Converts geospatial coordinates to ASN.1 format (microdegrees) and calculates speed
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

The bridge generates Personal Safety Messages following the J2735 standard with proper ASN.1 encoding:

- **Basic Type**: Pedestrian
- **Position**: Latitude, longitude (in 1/10th microdegrees), elevation (in decimeters)
- **Speed**: Calculated from velocity vector, in units of 0.02 m/s
- **Heading**: Direction of movement, in units of 0.0125 degrees
- **Accuracy**: Position accuracy indicators (semiMajor, semiMinor, orientation)
- **ID**: 4-byte hex identifier generated from pedestrian UUID

## Related Documentation

- [SceneScape Documentation](https://github.com/open-edge-platform/scenescape)
- [V2X Hub Documentation](https://github.com/usdot-fhwa-OPS/V2X-Hub)
- [J2735 PSM Standard](https://standards.sae.org/j2735_202007/)
