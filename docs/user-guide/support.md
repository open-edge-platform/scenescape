# Get Help

This page provides troubleshooting steps, FAQs, and resources to help you resolve common issues.

## Troubleshooting Common Issues
### 1. Failed login attempt by an unauthorized party disallows authorized user login for 5 seconds

Leaves the system vulnerable to a DDoS attack where the malicious agent repeatedly attempts logging in.

**Workaround**: Do not share the Intel® SceneScape URL with untrusted parties.

### 2. Postgres database will sometimes fail to start, resulting in an Internal Server Error (500) on login

**Workaround**: Restart Intel® SceneScape using `docker-compose down` followed by `docker-compose up -d` from the project directory.

### 4. "WARNING: Service <service name> uses an undefined secret file" console messages on startup

Several "undefined secret file" messages may be shown on startup, but the system should start normally.

### 5. When deploying Intel® SceneScape on a system with a zfs filesystem, container startup is slow

**Workaround**: Change the docker storage driver from the default 'overlay2' to 'zfs'.

### 6. Uploading files with unicode characters in filename results in 500 error from webserver

**Workaround**: Rename files to remove any unicode characters prior to uploading.

### 7. Renaming a scene causes data to stop flowing on the message bus and UI

Internally the system uses the scene name for subscribing to data, and there is a known issue where those internal subscriptions are not updated when the scene name is changed.

**Workaround**: Avoid renaming scenes in general. If a scene must be renamed, restart Intel® SceneScape using `docker-compose down` followed by `docker-compose up -d` from the project directory.

### 8. Issues are encountered when running in a virtual machine (VM)

Various issues may be encountered when running within virtual machines, including performance, access to hardware, networking, and more. Intel® SceneScape is currently not validated for operating within a virtual machine (VM).

**Mitigation**: Running Intel® SceneScape in a VM is not recommended, but there are some best practices for mitigating related issues. Contact Intel® technical support if running in a VM is absolutely required.

### 9. Images with either dimension larger than 2048 cause 2D calibration page map view to be empty in web UI

The issue is caused by limitations of VRAM on the GPU.

**Mitigation**: Use a system with a GPU that has a larger VRAM to run your web UI.

### 10. Direct API access to Kubernetes-only model directory uploader allows reading/writing other container files

During testing, a scenario was discovered where a user with admin access to the web UI could potentially read and write arbitrary files inside the container as the Apache web server user.

**Mitigation**: Only use the model directory uploader webpage via the browser. Ensure administrator accounts use a strong password and credentials are kept secure.

### 11. Markerless camera calibration may not correctly calibrate the camera pose

**Mitigation**: Markerless camera calibration is a beta feature that is still under development. Try a different calibration method in the interim.

### 12. No messages are observed on MQTT Explorer when using webuser account

**Mitigation**: From 1.2.0 release, Access Control Lists are enforced. Use SceneScape admin account credentials to observe all MQTT topics.

### 13. Enabling "Live View" results in memory utilization monotonically increases over time

**Mitigation**: "Live View" is meant for explainability and debugging. Disable "Live View" when SceneScape is deployed in production environments.

### 14. Upgrading database from previous release versions fails

**Mitigation**: Recreate the scene configuration in the new deployment
