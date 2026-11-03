# Node-RED based sample application

## Overview

This is a Node-RED based sample application that runs on top of the Scenescape platform. It demonstrates how to integrate and interact with Scenescape services using Node-RED flows that are connected to Scenescape's published MQTT topics.

## Usage

To start the Application

```bash
make up
```

Node-RED application will be available at `http://<HOST-IP>:1880`
Scenescape Dashboard will be available at `http://<HOST-IP>:1880/dashboard`

To stop the Application

```bash
make down
```
