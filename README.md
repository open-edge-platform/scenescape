# Intel® SceneScape

Scene-based AI software solution.

## Overview

Intel® SceneScape is a scene-based analytics system that utilizes sensor data from multiple sources, like cameras, located throughout the scene. Top-down and 3D views of the scene are used, various events are supported based on objects moving in the scene, and the contextualized scene data is all available over MQTT*.

These instructions will build and locally deploy demonstration scenes that allow interactions with Intel® SceneScape's capabilities. Afterward, Intel® SceneScape can be customized for a use case with additional cameras, sensors, models, and scene maps for live interaction.

> **Note:** See [How-to-create-new-scene.md](docs/user-guide/How-to-create-new-scene.md) for setting up a scene with live cameras.

### Prerequisites

* To run and interact with the demo scenes that the Intel® SceneScape release package provides, one computer is needed. The `./deploy.sh` script has been tested to work with [Ubuntu* 22.04 Desktop](https://releases.ubuntu.com/22.04/).
* The computer must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage. This configuration is the minimum to run the out of the box demos and more compute resources maybe be required for additional models, cameras, and/or sensors.
* For the initial build of the `./deploy.sh` process the computer must have a correctly configured connection to the Internet for acquiring the needed build tools. When using a proxy, the proxy will need to be correctly configured for the console environment, OS package installer, and [Docker](https://docs.docker.com/network/proxy/)*. Deployed containers can run without an internet connection.
* When deploying a live scene, a scale floor plan of the scene is needed either in a 3D scene scan in .glb format or in a 2D web image format (JPG, PNG, or GIF) that is about 600 to 1000 pixels wide. Walls and fiducial markers on the floor plan must be at least twice as accurate as the desired tracking accuracy (e.g. accuracy < 1 meter requires a floor plan accurate to < 0.5 meters).
* It is not recommended to initially use a virtual machine. Once Intel® SceneScape is configured for a specific use case and the system resource requirements are understood, then a multicore VM could be configured for deployment and execution. Windows Subsystem for Linux* (WSL) is not supported.

## Installation and First Run

These operations must be executed when logged in as a standard (non-root) user. **Do NOT use root or sudo.**

Extract or clone the project files to the target system. From the project directory (e.g. ~/scenescape), run:

```console
$ ./deploy.sh
```
The script will prompt to create and confirm a "superuser" password (SUPASS). This is the password to log in to the web interface. It is recommended the SUPASS to be different from the password for the system user.

If this is the first time deploying Intel® SceneScape on this system, the system will prompt to enter the user’s sudo password to enable installation of host software packages like Docker*. This password is not stored by Intel® SceneScape or used
outside of installing the required prerequisite software.

The deployment process will take some time as dependent components are downloaded, integrated, and tested. When `deploy.sh` completes successfully, the system will be running.

Note: The `deploy.sh` is intended run on a system for initial build/deployment and then for subsequent Intel® SceneScape release upgrades. In order to stop/re-start the system, follow the instructions in 'Stopping the system' and 'Starting the system'.

### Viewing the Web Interface Locally
If installing and running from Ubuntu* 22.04 Desktop UI, a web browser client should open to the localhost login page.

### Viewing the Web Interface Remotely
To connect remotely, use ```"https://<ip_address>"``` or ```"https://<hostname>"```, using the correct IP address or hostname of the remote Intel® SceneScape system. First time a web client connects to a Intel® SceneScape web server a certificate warning will appear. Click the prompts to continue to the site. For example, in Chrome* click "Advanced" and then "Proceed to &lt;ip_address> (unsafe)".

> **Note:** These certificate warnings are expected due to the use of a self-signed certificate for initial deployment purposes. This certificate is generated at deploy time and is unique to the instance.

### Logging In
Enter "admin" for the user name and the value entered earlier for SUPASS.

### Stopping the System

To stop the containers, use the following command in the project directory:

```console
$ docker compose down --remove-orphans
```
### Starting the System

To start after the first time, use the following command in the project directory:

```console
$ docker compose up -d
```
## Learn More ##

* For more information on integrating camera and sensor data with Intel® SceneScape, see [How-to-integrate-cameras-and-sensors.md](docs/user-guide/How-to-integrate-cameras-and-sensors.md).
* To set up a scene with live cameras, see [How-to-create-new-scene.md](docs/user-guide/How-to-create-new-scene.md).
* To automatically calibrate cameras using AprilTag markers, see [How-to-autocalibrate-cameras-using-apriltags.md](docs/user-guide/How-to-autocalibrate-cameras-using-apriltags.md).

## Contributing

We welcome contributions! Check out our [Contributing Guide](CONTRIBUTING.md) to get started.

## License ##

Intel® SceneScape repository is licensed under [LIMITED EDGE SOFTWARE DISTRIBUTION LICENSE](LICENSE).

## Disclaimers ##

Depending on your deployment, Intel® SceneScape may utilize FFmpeg and/or GStreamer.

FFmpeg is an open source project licensed under LGPL and GPL. See [https://www.ffmpeg.org/legal.html](https://www.ffmpeg.org/legal.html). You are solely responsible for determining if your use of FFmpeg requires any additional licenses. Intel is not responsible for obtaining any such licenses, nor liable for any licensing fees due, in connection with your use of FFmpeg.

GStreamer is an open source framework licensed under LGPL. See [https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html](https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html). You are solely responsible for determining if your use of GStreamer requires any additional licenses. Intel is not responsible for obtaining any such licenses, nor liable for any licensing fees due, in connection with your use of GStreamer.
