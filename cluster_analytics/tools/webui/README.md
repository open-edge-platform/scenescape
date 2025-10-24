# Cluster Analytics WebUI

This directory contains the Web User Interface (WebUI) for the Cluster Analytics service. The WebUI provides real-time visualization of object detection and clustering results from multiple camera scenes.

## Overview

The WebUI is a Flask-SocketIO based web application that displays:
- Real-time object detection data from multiple scenes
- Clustering results with configurable DBSCAN parameters
- Interactive controls for adjusting clustering parameters per scene and category
- Visualization of object positions and cluster formations

## Architecture

The WebUI has been separated from the main Cluster Analytics service into the `tools/webui` directory for better organization and maintainability. It runs as part of the main Cluster Analytics service.

### Directory Structure

```
tools/webui/
├── web_ui.py                  # Core WebUI module
├── requirements-webui.txt     # WebUI-specific dependencies
├── templates/                 # HTML templates
│   └── index.html
├── static/                    # Static assets (JavaScript, CSS)
│   └── visualization.js
└── README.md                  # This file
```

## Running the WebUI

The WebUI runs automatically as part of the Cluster Analytics service and is enabled by default.

### Starting the Service with WebUI

```bash
cd cluster_analytics/src
python3 cluster_analytics.py
```

The WebUI will be available at `http://localhost:5000`

### Configuration Options

To disable the WebUI:
```bash
python3 cluster_analytics.py --no-webui
```

To change the WebUI port:
```bash
python3 cluster_analytics.py --webui-port 8080
```

## Installation

### Installing WebUI Dependencies

The WebUI has its own set of dependencies separate from the main Cluster Analytics service:

```bash
pip3 install -r requirements-webui.txt
```

### Dependencies

Key dependencies include:
- **Flask**: Web framework
- **Flask-SocketIO**: Real-time bidirectional communication
- **python-socketio**: SocketIO client/server implementation

All dependencies are pinned with SHA256 hashes for supply chain security.

## Features

### Scene Selection
- View and select from multiple camera scenes
- Each scene shows real-time object detection data

### Clustering Visualization
- Visual representation of detected objects and their clusters
- Color-coded clusters for easy identification
- Real-time updates as new detection data arrives

### Parameter Configuration
- Adjust DBSCAN clustering parameters (eps and min_samples) per category
- Scene-specific configuration support
- Reset to default values
- Immediate re-clustering with updated parameters

### Refresh Rate Control
- Configure update frequency (real-time or throttled)
- Reduce bandwidth/CPU usage with throttled updates

## API Endpoints

### HTTP Endpoints
- `GET /`: Main visualization page
- `GET /api/scenes`: List of available scenes with names
- `GET /api/scene/<scene_id>`: Get data for a specific scene

### SocketIO Events

#### Client → Server
- `connect`: Client connection established
- `disconnect`: Client disconnection
- `select_scene`: Select a scene for visualization
- `set_refresh_rate`: Configure update frequency
- `get_clustering_config`: Request clustering parameters
- `update_clustering_config`: Update clustering parameters
- `reset_clustering_config`: Reset parameters to defaults

#### Server → Client
- `available_scenes`: List of available scenes
- `scene_data`: Object detection data for a scene
- `clusters_update`: Updated clustering results
- `clustering_config`: Current clustering parameters
- `clustering_config_updated`: Confirmation of parameter update
- `refresh_rate_updated`: Confirmation of refresh rate change

## Integration with Cluster Analytics

The WebUI runs integrated with the Cluster Analytics service and hooks into it to:

1. Receive object detection data from DATA_REGULATED MQTT topics
2. Display clustering results computed by the analytics engine
3. Allow users to configure DBSCAN parameters
4. Trigger re-clustering when parameters change

The integration is done through the `ClusterAnalyticsContext` class, which the WebUI receives as a constructor parameter.

## Development

### Adding New Features

1. Modify `web_ui.py` for backend logic
2. Update `templates/index.html` for UI structure
3. Update `static/visualization.js` for frontend interactivity
4. Test with the full Cluster Analytics service

## Security Considerations

- The WebUI accepts connections from any origin (`cors_allowed_origins="*"`)
- For production deployments, consider restricting CORS origins
- All dependencies include SHA256 hashes for verification
- Uses Flask's `allow_unsafe_werkzeug` - review for production use

## Troubleshooting

### WebUI Not Starting

1. Check that dependencies are installed: `pip3 install -r requirements-webui.txt`
2. Verify port is not already in use: `lsof -i :5000`
3. Check logs for import errors or missing dependencies

### No Data Displayed

1. Ensure Cluster Analytics service is receiving MQTT data
2. Check browser console for JavaScript errors
3. Verify SocketIO connection is established
4. Confirm scenes are being published to DATA_REGULATED topics

### Import Errors

If you see import errors related to `scene_common`:
- Ensure `scene_common` is installed or available in Python path
- The WebUI automatically adds parent directories to path when imported from cluster_analytics_context.py
