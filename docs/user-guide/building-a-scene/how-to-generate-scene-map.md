# How to Generate a Scene Map Using the Mapping Service

This guide provides step-by-step instructions to automatically generate a 3D scene map from camera feeds using Intel® SceneScape's mapping service. By completing this guide, you will:

- Build and launch all Intel® SceneScape services including the mapping service
- Create a new scene with a placeholder map image
- Add cameras and verify video frames are being processed
- Generate a 3D mesh reconstruction of the scene
- Visualize the generated mesh in both 2D and 3D views
- Enable multi-camera tracking using the generated mesh

---

## Prerequisites

- A system meeting the hardware requirements for Intel® SceneScape
- Docker and Docker Compose installed
- Multiple cameras covering the scene from different angles
- Basic familiarity with the Intel® SceneScape user interface

---

## Overview

The mapping service uses advanced computer vision techniques to reconstruct a 3D mesh of your scene from multiple camera views. This automated approach eliminates the need to manually create floor plans or CAD drawings, significantly reducing setup time and improving calibration accuracy.

---

## Step 1: Build All Services

Before launching the demo, build all Intel® SceneScape services including the mapping and clustering services:

```bash
SUPASS=your_password make build-all
```

This command will:

- Build all core services (controller, manager, autocalibration, model_installer)
- Build experimental services (mapping and cluster_analytics)
- Generate security certificates and secrets
- Install required AI models

> **Note**: The build process may take 15-30 minutes depending on your system. This is a one-time operation unless you need to rebuild services.

---

## Step 2: Launch Services with Mapping

To start all services including both mapping and cluster analytics:

```bash
SUPASS=your_password make demo-all
```

For successive runs, you can use Docker Compose directly:

### Launch all cores services and experimental services

```bash
docker compose --profile experimental up -d
```

### Launch all cores services and mapping service

```bash
docker compose --profile mapping up -d
```

> **Note**: The `--profile` flag allows you to selectively enable experimental services. Use `experimental` for both clustering and mapping, or `mapping` to start just the mapping service along with all core services.

### Verify Services are Running

Check that all services are healthy:

```bash
docker compose ps
```

You should see services including `mapping` with a status of `healthy`.

> **Important**: During the first deployment, the mapping service downloads required model weights (approximately 1-2GB). This can take several minutes and the service will show as unhealthy during this time. Subsequent runs will use the cached weights available in the Docker volume and start much faster.

---

## Step 3: Create a New Scene with Placeholder Map

1. Open your web browser and navigate to the Intel® SceneScape URL.
2. Log in using the credentials you configured (username: `admin`, password: your `SUPASS` value)
3. Click on **Scenes** in the navigation menu
4. Click **+ New Scene**
5. Fill in the scene details:
   - **Scene Name**: Enter a descriptive name for your scene
   - **Map File**: Upload a placeholder image (any simple image will work, as it will be replaced by the generated mesh)
   - **Scale**: Enter any positive value (e.g., `50` pixels per meter) - this will be updated after mesh generation

6. Click **Save New Scene**

> **Note**: The placeholder map image is temporary. Once the 3D mesh is generated, the system will create a top-down render of the mesh to replace the placeholder.

---

## Step 4: Add Cameras and Verify Video Frames

1. Click on your newly created scene to open it
2. Add camera by clicking on "+ New Camera" below the scene map, then filling in the camera details as required.

> **Note**: The camera ID _must_ match the `cameraid` set in DL Streamer Pipeline config file for ex: dlstreamer-pipeline-server/config.json, or the scene controller will not be able to associate the camera with its instance in Intel® SceneScape.

Using the above example, the form should look like this for the `video0` camera:

![Creating a new camera](../images/ui/new-camera.png)

3. Click **Save Camera**
4. Repeat for all cameras in your scene

### Verify Video Frames

After adding cameras, verify that video frames are being received:

1. Navigate to the scene details page
2. You should see live video thumbnails from each camera
3. Verify that the video streams are active and showing the correct views

> **Note**: Ensure cameras have overlapping fields of view for the mapping service to successfully reconstruct the scene.

---

## Step 5: Generate the Scene Mesh

Once cameras are configured and streaming:

1. On the scene details page, navigate to the scene settings page by clicking the "Edit" icon.
2. Click **Generate Mesh** button at the bottom of the page

> **Note**: The "Generate Mesh" button is only available when the mapping service is healthy. If you don't see this button:
>
> - Verify the mapping service is running: `docker compose ps mapping`
> - Check the mapping service logs: `docker compose logs mapping`
> - Ensure the service shows as `healthy` in the status

The mesh generation process will:

- Capture frames from all cameras
- Perform monocular depth estimation
- Reconstruct a 3D point cloud and mesh of the scene
- Align the mesh to the first quadrant and rotate the floor to align with the XY plane
- Automatically calibrate camera poses relative to the reconstructed scene

> **Note**: Mesh generation typically takes 2-5 minutes depending on scene complexity and the number of cameras.

---

## Step 6: Save Settings

Once mesh generation is complete:

1. Click **Save Settings** to apply the generated mesh to your scene

This will:

- Replace the placeholder map with a top-down render of the 3D mesh
- Update camera parameters based on the reconstruction
- Enable proper of objects tracking in the scene

---

## Step 7: View the Top-Down Mesh Render

Return to the scene details page:

1. Click on **Scenes** in the navigation menu
2. Select your scene
3. Observe the scene map, which now displays the top-down render of the generated mesh

## Step 8: Verify 3D Mesh Alignment

To inspect the 3D mesh and camera poses:

1. Click on the "3D" button for the scene.
2. In the 3D view, you should see:
   - The reconstructed 3D mesh properly aligned in the first quadrant
   - The mesh floor rotated to align with the XY plane
   - Camera poses correctly positioned in the 3D space
   - Camera frustums showing each camera's field of view

The 3D visualization allows you to:

- Verify camera placement and orientation
- Check mesh quality and coverage
- Confirm proper scene alignment

> **Note**: Camera poses are automatically calculated during mesh generation and should already be correctly aligned. Manual calibration is not needed.

---

## Step 9: Verify Multi-Camera Tracking

If objects (people, vehicles, etc.) are visible in your camera feeds:

1. Observe the scene in either 2D or 3D view
2. Multi-camera tracking should automatically begin, showing:
   - Detected objects from all cameras
   - Unified tracks across multiple camera views
   - Object positions correctly mapped to the 3D mesh

The mapping service provides:

- Accurate object localization in 3D space
- Consistent tracking across camera boundaries
- Proper ground plane alignment for object positioning

---

## Important Notes

### Reconstruction Scale

> **Warning**: The scale of the reconstructed mesh may not match real-world measurements exactly. This is a known limitation of monocular depth estimation, which cannot determine absolute scale without additional reference information.

To address scale inaccuracies:

- Use the generated mesh for spatial relationships and topology rather than precise measurements
- For applications requiring accurate dimensions, manual scale calibration may be necessary

### Best Practices

For optimal mesh generation results:

- **Camera Coverage**: Ensure cameras have good overlapping coverage of the scene
- **Lighting**: Maintain consistent, well-lit conditions during mesh generation
- **Static Scene**: Keep the scene as static as possible during mesh capture (avoid moving objects)
- **Camera Placement**: Position cameras at different heights and angles for better 3D reconstruction
- **Texture**: Scenes with visual texture and features reconstruct better than blank surfaces

---

## Stopping Services

To stop all Intel® SceneScape services:

```bash
docker compose down
```

To stop services and remove volumes (this will delete all data):

```bash
docker compose down -v
```

---

## Troubleshooting

### Mapping Service Not Healthy

If the mapping service remains unhealthy:

1. Check service logs: `docker compose logs mapping`
2. Verify model weights are downloading: Look for download progress in logs
3. Ensure sufficient disk space for model weights (~2GB)
4. Check network connectivity if behind a proxy

### Generate Mesh Button Not Visible

If you don't see the "Generate Mesh" button:

1. Verify mapping service is running: `docker compose ps | grep mapping`
2. Ensure you're using the correct profile: `--profile mapping` or `--profile experimental`
3. Check that the mapping service shows as healthy
4. Refresh the browser page after the service becomes healthy

### Poor Mesh Quality

If the generated mesh has issues:

1. Verify cameras have sufficient overlapping coverage (>20% overlap)
2. Check lighting conditions in the scene
3. Ensure cameras are properly focused
4. Consider adding more cameras for better coverage
5. Remove or minimize moving objects during mesh generation

---

## Supporting Resources

- [How to Create and Configure a New Scene](how-to-create-new-scene.md)
- [How to Configure DLStreamer Video Pipeline](../other-topics/how-to-configure-dlstreamer-video-pipeline.md)
- [Intel® SceneScape README](https://github.com/open-edge-platform/scenescape/blob/main/README.md)
