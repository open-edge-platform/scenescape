# Release Notes 2025: Intel® SceneScape

## Version 2025.2

**December 7, 2025**

**New**

- Dynamic Camera Configuration: Support for dynamic camera configuration in Kubernetes deployments with support for GPU offload and model chaining
- REST API in Autocalibration: New REST API endpoints for autocalibration service
- Object Clustering: New object clustering service that enables analyzing properties of object clusters like shape, size, count and motion patterns
- 3D Mapping Service: New mapping service that creates 3D meshes and calibrates cameras from camera inputs
- Geospatial Map Creation: Integrated geospatial map creation and Scene LLA configuration
- Time-Chunked Tracker: Improved tracker performance through time-chunked processing to track 100 objects at 15fps on PantherLake
- Point Cloud Map Upload: Users can now upload point cloud maps
- V2X Plugin: Readily deployable V2X plugin to convert SceneScape messages to V2X format

**Improved**

- Faster Deployment: Faster kubernetes deployment along with reduced dependencies and technical debt
- Container Security: Updated services image to run as non-root user
- Documentation: Improved architecture and how-to documentation
- Simplify Manager Service: leverage docker hub hosted postgres image as database and use manager solely as web server for providing API endpoints and web UI
- OpenTelemetry Integration: Added metrics and tracing to scene controller using OpenTelemetry
- EMT OS Compatibility: Adjusted deploy.sh to run on EMT OS (ITEP-76868)

## Version 1.4.0

**August 20, 2025**

**New**

- Volumetric regions of interest
- Scene import/export
- Enhanced tracker performance to handle 50 tracks reliably
- Switch from Percebro to DL Streamer Pipeline Server as the Video Analytics engine
- Native support for Geospatial Coordinate output

**Improved**

- Refactor build systems, remove unnecessary dependencies, and optimize image sizes
- Optimized build time - ~10 mins
- Align to containerization best practices by leveraging volumes, secrets and configs
- Documentation Updates
- CI/CD Improvements
- Security Enhancements

## Version 1.3.0

**May 24, 2025**

**New**

This release refactors Intel® SceneScape into components, such that:

- Scene Controller, Scene Manager and Auto Calibration Docker images can be built independently.
- Functionality will work with third party MQTT broker and third party time synchronization service.
- Scene Controller can consume object detections from Deep Learning Streamer Pipeline Server.
- Except for Scene Manager service at initialization, all other services can operate independent of each other.
- Reduced Docker image sizes

**Known Issues**

1. Failed login attempt by an unauthorized party disallows authorized user login for 5 seconds

   Leaves the system vulnerable to a DDoS attack where the malicious agent repeatedly attempts logging in.

   _Workaround_: Do not share the Intel® SceneScape URL with untrusted parties.

2. Markerless camera calibration may not correctly calibrate the camera pose

   _Mitigation:_ Markerless camera calibration is a beta feature that is still under development. Try a different calibration method in the interim.

3. Errors may be encountered when using very long tripwire and regions of interest names

   Tripwire and region names are identified for user experience design improvement in a future release.

   _Workaround_: Use short, descriptive names with no spaces for tripwires and regions of interest.

4. Singleton Sensor Issue: Users advised not to use administration module for sensor creation

   Container failure with this exception:

   `manager.models.Sensor.cam.RelatedObjectDoesNotExist: Sensor has no cam`

   This only occurs when using the Admin panel to create sensors.

   _Workaround_: Use the Sensor menu link at the top of the web interface to add and calibrate sensors.

5. "WARNING: Service <service name> uses an undefined secret file" console messages on startup

   Several "undefined secret file" messages may be shown on startup, but the system should start normally.

6. When using USB cameras, "GStreamer warning: Cannot query video position" message is displayed on the console

   This is normal for USB cameras, and the message can be ignored.

7. When deploying Intel® SceneScape on a system with a zfs filesystem, container startup is slow

   _Workaround_: Change the docker storage driver from the default 'overlay2' to 'zfs'.

8. Uploading files with unicode characters in filename results in 500 error from webserver

   _Workaround_: Rename files to remove any unicode characters prior to uploading.

9. Security: Runaway creation of GLB files

   During testing, a very rare scenario was discovered where GLB files were repeatedly created, resulting in significant disk usage.

   _Mitigation:_ Do not utilize an untrusted network for your Intel® SceneScape deployment, and carefully manage the credentials for accessing the system within your organization. If the situation is encountered, stop the Intel® SceneScape containers and contact your Intel representative for support.

10. Sensor regions do not publish to the `scenescape/data` topic

    Sensor regions do not behave exactly like standard regions of interest, and there is a known issue where they do not publish updated locations of contained objects as they move to the `scenescape/data` topic. They only publish events to the `scenescape/event` topic when objects interact with the sensor region.

    _Workaround:_ If motion of objects within the sensor region is required for the use case, use a standard region of interest over the top of the same area.

11. Tripwire data is only published to the `scenescape/event` topic and not to the scenescape/data topic

    Tripwires are "event-only" analytics, so no tripwire data will flow under the scenescape/data topic by design. Regions of Interest (ROI) do publish updates as objects move within the region bounds, but since tripwires have no area (2D) or volume (3D), only tripwire crossing events are published under the scenescape/event/tripwire parent topic.

    _Mitigation:_ Utilize the scenescape/event/tripwire topic for subscribing to tripwire events.

12. Issues are encountered when running in a virtual machine (VM)

    Various issues may be encountered when running within virtual machines, including performance, access to hardware, networking, and more. Intel® SceneScape is currently not validated for operating within a virtual machine (VM).

    _Mitigation:_ Running Intel® SceneScape in a VM is not recommended, but there are some best practices for mitigating related issues. Contact Intel technical support if running in a VM is absolutely required.

13. Access for Users in UI and REST API restricted to Superuser status

    User authorization control is currently limited to superuser or admin status. Future versions will include support for authorization based on individual user permissions.

14. Images with either dimension larger than 2048 cause 2D calibration page map view to be empty in web UI

    The issue is caused by limitations of VRAM on the GPU.

    _Mitigation:_ Use a system with a GPU that has a larger VRAM to run your web UI.

15. Direct API access to Kubernetes-only model directory uploader allows reading/writing other container files

    During testing, a scenario was discovered where a user with admin access to the web UI could potentially read and write arbitrary files inside the container as the Apache web server user.

    _Mitigation:_ Only use the model directory uploader webpage via the browser. As always, ensure administrator accounts use a strong password and credentials are kept secure.

### Limitations

During the Docker build process, packages are installed from public repositories. Intel has no control over the public repositories. Specific versions of packages might be removed by the owners at any time, which may break the Docker image build. The Docker build targets the latest available versions of software packages from the public repositories while keeping the same major version.

Between Intel® SceneScape releases, it is possible that packages in public apt repositories get upgraded to newer versions. Although it is possible for these upgraded software packages to work without issues with the current Intel® SceneScape 1.3.0 release, you assume all risks associated with the use of the upgraded packages. Compatibility was tested using the versions mentioned in "Package versions" file.

Note: Performance varies by use, configuration and other factors. Learn more at
[Intel Performance Index](https://edc.intel.com/content/www/us/en/products/performance/benchmarks/overview/).

Contact your Intel representative if you encounter issues that are a result of using different versions of software packages from public repositories than the ones provided with this release.
