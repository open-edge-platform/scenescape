<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Integrate External Applications

This guide explains how to connect an application to Scenescape, subscribe to scene data and spatial events over MQTT, and deploy the bundled sample application.

## Prerequisites

Deploy Scenescape before connecting an application. Follow the [Deployment Guide](./deployment/index.md) to prepare images and choose Docker Compose or Kubernetes. For the sample application below, use [Deploy Scenescape on Docker](./deployment/deploy-docker.md) or [Deploy the Demo](./deployment/deploy-demo.md).

A running deployment alone does not produce object data. Configure a scene and active camera or sensor inputs, or use the demo's bundled scenes and video sources.

## Concepts and Integration Interfaces

MQTT is the shared transport for camera and sensor inputs, tracked-object data, scene updates, and spatial analytics events. Applications subscribe through the broker and parse JSON payloads using the [Controller Data Formats](../microservices/controller/data_formats.md) and [Analytics Data Formats](../microservices/analytics/data_formats.md). Use the REST API over HTTPS for configuration and discovery.

| Topic                  | What your application needs to know                                                                                                                                  | Learn more                                                                                                                                               |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Scenes and coordinates | A scene represents a physical space with a shared coordinate system. Cameras and sensors contribute data to that space.                                              | [Build a Scene](./build-a-scene/index.md)                                                                                                                |
| Cameras and sensors    | Input pipelines publish detections or readings; calibration places camera detections in scene coordinates.                                                           | [Integrate Cameras and Sensors](./integrate-cameras-and-sensors.md), [Calibrate Cameras](./calibrate-cameras/index.md)                                   |
| Object tracking        | The Scene Controller combines detections into tracked objects and publishes per-category scene updates.                                                              | [Scene Controller](../microservices/controller/controller.md), [Controller Data Formats](../microservices/controller/data_formats.md)                    |
| Spatial analytics      | Analytics publishes rate-controlled scene updates and events for regions of interest (ROIs) and tripwires. ROIs describe areas; tripwires detect boundary crossings. | [Configure Spatial Analytics](./build-a-scene/configure-spatial-analytics.md), [Work with Spatial Analytics Data](./work-with-spatial-analytics-data.md) |
| REST API               | Discover scene, region, and tripwire identifiers and manage configuration over HTTPS. REST is not the live object-data stream.                                       | [API Reference](../api-reference.md), [REST Discovery Examples](./work-with-spatial-analytics-data.md#discovering-existing-rois-and-tripwires-via-api)   |

If your application supplies detections rather than consuming results, see [Publish an External Source Adapter](./publish-external-source-adapter.md).

## Connect Your Application

1. Use the REST API or web UI to identify the scenes, regions, and tripwires your application needs. See [REST API Authentication](./work-with-spatial-analytics-data.md#rest-api-authentication).
2. Connect an MQTT client over TLS to a reachable Scenescape broker endpoint. Within the Docker network, the bundled broker is `broker.scenescape.intel.com` on port `1883`; this listener uses TLS despite the port number. A client outside that network needs an explicitly configured, reachable endpoint, not the container hostname.
3. Subscribe to the topics needed by your application:

   | Data                                      | MQTT topic                                                        | Payload reference                                                                                          |
   | ----------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
   | Rate-controlled scene state               | `scenescape/regulated/scene/{scene_id}`                           | [Regulated Scene Output](../microservices/analytics/data_formats.md#regulated-scene-output-message-format) |
   | ROI events, such as occupancy updates     | `scenescape/event/region/{scene_id}/{region_id}/{event_type}`     | [Region Event Output](../microservices/analytics/data_formats.md#region-event-output-message-format)       |
   | Tripwire crossing events                  | `scenescape/event/tripwire/{scene_id}/{tripwire_id}/{event_type}` | [Tripwire Event Output](../microservices/analytics/data_formats.md#tripwire-event-output-message-format)   |
   | Unregulated, per-category tracked objects | `scenescape/data/scene/{scene_id}/{thing_type}`                   | [Data Scene Output](../microservices/controller/data_formats.md#data-scene-output-message-format)          |

   Replace the placeholders with identifiers from your deployment. MQTT `+` matches one topic level and `#` matches the remaining levels. The sample uses wildcards to monitor multiple scenes; production applications should narrow subscriptions to their intended scope.

4. Handle incoming messages in your application and implement your business logic. For discovery requests, event payloads, and Python and JavaScript examples, see [Work with Spatial Analytics Data](./work-with-spatial-analytics-data.md).

## Example: Deploy the Sample Application

The repository includes a [Node-RED sample application](https://github.com/open-edge-platform/scenescape/blob/main/sample_data/sample_app/README.md) under `sample_data/sample_app`. Its bundled [flows](https://github.com/open-edge-platform/scenescape/blob/main/sample_data/sample_app/flows/flows.json) subscribe to:

- `scenescape/regulated/scene/#` for object counts by category.
- `scenescape/event/region/+/#` for ROI occupancy.
- `scenescape/event/tripwire/+/#` for tripwire crossing events.

The flows aggregate these messages into a dashboard. This demonstrates consuming Scenescape output without modifying its services.

### 1. Prepare Scenescape

Complete the [Docker deployment](./deployment/deploy-docker.md) and configure active inputs, or follow [Deploy the Demo](./deployment/deploy-demo.md) for ready-made scenes and video sources.

The sample's Compose file joins the existing Docker network `scenescape_scenescape`, created by a Scenescape deployment using the default Compose project name `scenescape`. If you use another project name, update the sample's [Compose network configuration](https://github.com/open-edge-platform/scenescape/blob/main/sample_data/sample_app/compose.app.yml) to match your deployment before starting it. The bundled sample deployment does not target Kubernetes.

Port `1880` on the host must be available.

### 2. Start the Application

From the Scenescape repository root:

```bash
make sample-app-up
```

This builds the sample's container image and starts Node-RED in the background. Alternatively, run `make up` from `sample_data/sample_app`.

Check the container status and logs from the repository root:

```bash
docker compose -f sample_data/sample_app/compose.app.yml ps
docker compose -f sample_data/sample_app/compose.app.yml logs --tail=100 nodered
```

### 3. Open and Configure Node-RED

- Editor: `http://<HOST-IP>:1880`
- Dashboard: `http://<HOST-IP>:1880/dashboard`

Replace `<HOST-IP>` with the Docker host's address, or use `localhost` when browsing on that host.

> **Security:** The sample publishes the Node-RED HTTP port on all host interfaces and does not configure editor authentication. Restrict access to a trusted development environment. The bundled MQTT TLS configuration also disables server-certificate verification; it is not a production-ready security configuration.

In the editor, open a **Scenes**, **ROIs**, or **Tripwire** MQTT input node and edit its shared **Scenescape-broker** connection:

1. Confirm the broker is `broker.scenescape.intel.com`, port `1883`, with TLS enabled.
2. Configure its TLS settings to trust your deployment's CA certificate, generated at `manager/secrets/certs/scenescape-ca.pem`, and enable server-certificate verification. Make the CA available to Node-RED through its TLS configuration; do not copy private keys into the flows.
3. If your broker enforces authentication, enter a dedicated application's MQTT credentials in the connection's security settings.
4. Save the settings and click **Deploy**.

Follow the [Hardening Guide](../additional-resources/hardening-guide.md) before exposing either the application or broker beyond the trusted deployment network.

### 4. Verify Data Arrives

In the editor, confirm the MQTT input nodes report a connected status. Open the dashboard and check that scenes and object counts update while inputs are active.

To see ROI occupancy and tripwire events, [configure spatial analytics](./build-a-scene/configure-spatial-analytics.md) and ensure tracked objects enter the regions or cross the tripwires. A connected MQTT client alone does not guarantee these events will be generated.

If no data appears, check the Node-RED logs, broker connection settings, active input pipelines, and topic identifiers. See [Troubleshooting](../troubleshooting.md).

### 5. Stop the Application

From the repository root:

```bash
make sample-app-down
```

Alternatively, run `make down` from `sample_data/sample_app`. This stops the sample without stopping Scenescape. Node-RED data is retained in the sample's named Docker volume.
