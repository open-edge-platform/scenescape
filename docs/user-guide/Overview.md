# Intel® SceneScape
Scene-based AI software solution.

## Overview

Intel® SceneScape is a software platform that reaches beyond vision-based AI to realize spatial awareness from sensor data. It transforms data from many sensors to create and provide live updates to a 4D digital twin of your physical space. Digital twins can be applied to your use cases to look at past analytics, track what is happening in the present, and make predictive decisions for the future.

Intel® SceneScape unlocks business applications from raw sensor data by providing a digital twin of each scene. Objects, people, and vehicles within the scene are represented as overlays on the dynamic structure of the digital twin. Applications, autonomous systems, and mobile systems securely access the digital twin to make decisions about the state of the scene, such as whether a person is in danger, a part is worn or broken, someone has been waiting in line too long, a product has been mis-shelved, or a child has called out for help.

Intel® SceneScape is part of the Intel® Tiber™ Edge Platform, a solution designed to solve edge challenges across industries. The platform enables enterprises to develop, deploy, run, manage, and scale edge applications with cloud-like simplicity, taking advantage of an unmatched partner ecosystem.​

## How It Works

Powerful AI algorithms and AI hardware crunch all available sensor data to maintain the 4D scene graph (3D plus time), as quickly and accurately as possible. This enables users to see what is happening in near real time.
With the Intel® Distribution of OpenVINO™ toolkit, Intel® SceneScape is able to use raw sensor data to create the 4D semantic digital replica by ingesting detections from 2D cameras and mapping them into the digital twin. The Intel® Distribution of OpenVINO™ toolkit also helps to abstract the different types of Intel® hardware accelerators, including CPU, GPU, VPU, FPGA, and GNA, enabling developers to write code once and deploy it.
A scene is defined by a fixed local coordinate system against which all sensors are provisioned to provide spatial context to sensor data. While geographical coordinates may be suitable for many applications, scenes usually use a fixed local Cartesian coordinate system. That scene could be a building, a ship, an aircraft, or a campus that has the global geographical coordinate system as a parent. To provide this context to sensor data, Intel® SceneScape manages:
-   A unique scene and scene coordinate system.
-   Exactly one scene parent for each sensor at a given time.
-   The location of cameras, microphones, thermometers, and all other sensors within the scene. Maintained in the
Intel® SceneScape database, sensor position and orientation, along with characteristics such as camera and microphone
polar patterns provide critical data to for determining context from raw sensor data.
-   Alignment with existing scene graph technologies and standards such as glTF2, X3D3, and Open Geospatial Consortium (OGC) 3D Tiles4.

Intel® SceneScape is composed of several containerized services which work together to provide the end-to-end functionality of the system.

![SceneScape architecture diagram](images/architecture.png)
Figure 1: Architecture Diagram

### Scene Controller

Maintains the current state of the scene, including tracked objects, cameras, and sensors. For more information, refer to [Scene Controller Microservice](/controller/README.md)

### Percebro

OpenVINO-based computer vision pipeline tool. For more information, refer to [Percebro Microservice](/percebro/README.md)

### Auto Camera Calibration

Computes camera parameters utilizing known priors and camera feed. For more information, refer to [Auto Camera Calibration](/autocalibration/README.md)

### MQTT Broker

Mosquitto MQTT broker which acts as the primary message bus connecting sensors, internal components, and applications, including the web interface.

### Web Server

Apache web server providing a Django-based web UI which allows users to view updates to the scene graph and manage scenes, cameras, sensors, and analytics. It also serves the Intel® SceneScape REST API.

### NTP Server

Time server which maintains the reference clock and keeps clients, such as Percebro, in sync.

### SQL Database

PostgreSQL database server which stores static information used by the web UI and the scene controller. No video or object location data is stored by Intel® SceneScape.

## Supporting Resources

-   [Getting Started Guide](Getting-Started-Guide.md)
-   [API Reference](api-reference.md)
-   How camera normalization is implemented in Intel® SceneScape[Camera normalization](convert-object-detections-to-normalized-image-space.md)
