<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Scenescape

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/scenescape/tree/release-2026.2.0">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/scenescape/blob/release-2026.2.0/README.md">
     Readme
  </a>
    <a class="icon_download" href="https://github.com/open-edge-platform/scenescape/releases">
     Download
  </a>
</div>
hide_directive-->

Scenescape is a software framework that enables spatial awareness by integrating data from cameras and other sensors into scenes. It simplifies application development by providing near-real-time, actionable data about the state of the scene, including what, when, and where objects are present, along with their sensed attributes and environment. This scene-based approach makes it easy to incorporate and fuse sensor inputs, enabling analysis of past events, monitoring of current activities, and prediction of future outcomes from scene data.

Even with a single camera, transitioning to a scene paradigm offers significant advantages. Applications are written against the scene data directly, allowing for flexibility in modifying the sensor setup. You can move, modify, remove, or add cameras and sensors without changing your application or business logic. As you enhance your sensor array, the data quality improves, leading to better insights and decisions without altering your underlying application logic.

Scenescape turns raw sensor data into actionable insights by representing objects, people, and vehicles within a scene. Applications can access this information to make informed decisions, such as identifying safety hazards, detecting equipment issues, managing queues, correcting product placements, or responding to emergencies.

## How It Works

Scenescape uses advanced AI algorithms and hardware to process data from cameras and sensors, maintaining a dynamic scene graph that includes 3D spatial information and time-based changes. This enables developers to write applications that interact with a digital version of the environment in near real-time, allowing for responsive and adaptive application behavior based on the latest sensor data.

The framework leverages the Intel® Distribution of OpenVINO™ toolkit to efficiently handle sensor data, enabling developers to write applications that can be deployed across various Intel® hardware accelerators like CPUs, GPUs, VPUs, FPGAs, and GNAs. This ensures optimized performance and scalability.

A key goal of Scenescape is to make writing applications and business logic faster, simpler, and easier. By defining each scene with a fixed local coordinate system, spatial context is provided to sensor data. Scenes can represent various environments, such as buildings, ships, aircraft, or campuses, and can be linked to a global geographical coordinate system if needed. Scenescape manages:

- Multiple scenes, each with its own coordinate system.
- A single parent scene for each sensor at any given time.
- The precise location and orientation of cameras and sensors within the scene, stored in the Scenescape database. This information is crucial for interpreting sensor data correctly.
- Compatibility with glTF scene graph representations.

Scenescape is built on a collection of containerized services that work together to deliver comprehensive functionality, ensuring seamless integration and operation.

![Scenescape architecture diagram](./_assets/architecture.png "architecture diagram")
Figure 1: Architecture Diagram

### **Scene Controller**

Processes input metadata from camera pipelines and sensors, performs multi-camera and multi-object tracking, maintains and updates the current state of the scene, and publishes unregulated tracked-object data. For more information, refer to [Scene Controller Microservice](./microservices/controller/controller.md).

For details on the controller input and output message formats, see [Scene Controller Message Formats](./microservices/controller/data_formats.md).

### **Analytics**

Consumes unregulated tracked-object data from the Scene Controller and raw sensor readings, then computes region, tripwire, and sensor-correlation analytics, publishing regulated detections and analytics events. For more information, refer to [Analytics Microservice](./microservices/analytics/analytics.md).

For details on the analytics input and output message formats, see [Analytics Message Formats](./microservices/analytics/data_formats.md).

### **Deep Learning Streamer Pipeline Server**

Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server) is a Python-based, interoperable containerized microservice for easy development and deployment of video analytics pipelines. For more information, refer to [Deep Learning Streamer Pipeline Server](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/microservices/dlstreamer-pipeline-server/docs/user-guide).

### **Auto Camera Calibration**

Computes camera parameters utilizing known priors and camera feed. For more information, refer to [Auto Camera Calibration](./microservices/auto-calibration/auto-calibration.md).

### **MQTT Broker**

Mosquitto MQTT broker which acts as the primary message bus connecting sensors, internal components, and applications, including the web interface.

### **Web Server**

Apache web server providing a Django-based web UI which allows users to view updates to the scene graph and manage scenes, cameras, sensors, and analytics. It also serves the Scenescape REST API.

### **NTP Server**

Time server which maintains the reference clock and keeps clients in sync.

### **SQL Database**

PostgreSQL database server which stores static information used by the web UI and the scene controller. No video or object location data is stored by Scenescape.

## Supporting Resources

- [Installation](./get-started/installation.md)
- [API Reference](./api-reference.md)
- [Camera normalization](./additional-resources/convert-object-detections-to-normalized-image-space.md)
- [Troubleshooting](./troubleshooting.md)
- [Release Notes](./release-notes.md)

<!--hide_directive
:::{toctree}
:hidden:

Go back to Libraries <https://docs.openedgeplatform.intel.com/2026.2/ai-libraries.html>

:::

:::{toctree}
:hidden:
:caption: Get Started

Scenescape Overview <https://docs.openedgeplatform.intel.com/2026.2/scenescape/index.html>
Installation <./get-started/installation.md>
System Requirements <./get-started/system-requirements.md>

:::

:::{toctree}
:hidden:
:caption: How-to Guides

Deploy Scenescape <./how-to-guides/deploy-scenescape-using-prebuilt-containers.md>
Use the UI and Online Documentation <./how-to-guides/ui-tutorial.md>
Build a Scene <./how-to-guides/build-a-scene/index.md>
Integrate Cameras and Sensors <./how-to-guides/integrate-cameras-and-sensors.md>
Publish External Source Adapter <./how-to-guides/publish-external-source-adapter.md>
Calibrate Cameras <./how-to-guides/calibrate-cameras/index.md>
Work with Spatial Analytics Data <./how-to-guides/work-with-spatial-analytics-data.md>
Run the LiDAR-Intersection Fusion Demo <./how-to-guides/run-lidar-intersection-demo.md>

:::

:::{toctree}
:hidden:
:caption: Microservices

Analytics <./microservices/analytics/analytics.md>
Auto Camera Calibration <./microservices/auto-calibration/auto-calibration.md>
Cluster Analytics <./microservices/cluster-analytics/cluster-analytics.md>
Scene Controller <./microservices/controller/controller.md>
Mapping Service <./microservices/mapping-service/mapping-service.md>
API Reference <./api-reference.md>

:::

:::{toctree}
:hidden:
:caption: Other Topics

Defining Object Properties <./other-topics/how-to-define-object-properties.md>
Enabling Re-identification <./other-topics/how-to-enable-reidentification.md>
Enabling Observability (Experimental) <./other-topics/how-to-enable-observability.md>
Integrating Geti™ AI Models <./other-topics/how-to-integrate-geti-trained-model.md>
Configuring DL Streamer Video Pipeline <./other-topics/how-to-configure-dlstreamer-video-pipeline.md>
Model configuration file format <./other-topics/model-configuration-file-format.md>
Running License Plate Recognition with 3D Object Detection <./other-topics/how-to-run-LPR-with-3D-object-detection.md>
Managing Files in Volumes <./other-topics/how-to-manage-files-in-volumes.md>
Controlling Scene Lighting with Physical Light Sensors <./other-topics/light-sensor-integration.md>
Viewing Re-identification Metrics <./other-topics/how-to-view-reid-metrics.md>

:::

:::{toctree}
:hidden:
:caption: Additional Resources

Hardening Guide <./additional-resources/hardening-guide.md>
How to Upgrade <./additional-resources/how-to-upgrade.md>
Converting Bounding Boxes to Normalized Image Space <./additional-resources/convert-object-detections-to-normalized-image-space.md>

:::

:::{toctree}
:hidden:
:caption: ----------------------

./troubleshooting.md
Release Notes <./release-notes.md>

:::
hide_directive-->
