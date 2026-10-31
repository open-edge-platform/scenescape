# Manage a Scene Mapped from a Handheld Device

This guide explains how to set up a Scenescape scene for mapping from a
handheld application, connect the application to that scene, and use the
resulting map.

## Create and connect a scene

1. Log in to Scenescape as a user with edit access.
2. Create a new scene. Leave the map blank and enter a starting **pixels per
   meter** value. If you do not know the value yet, use a guess such as `100`.
3. Open the scene's **3D** view.
4. In **Scene Settings**, select **scene QR code**. Scenescape displays a QR
   code containing the scene details.
5. In the handheld application, choose **New Scene** and use the device camera
   to scan the QR code.
6. Enter the scene password in the handheld application, then save and open the
   scene. The scene will initially be blank; the QR code establishes its
   connection to Scenescape.

## Map and upload the scene

1. Use the handheld application to map the scene.
2. When mapping is ready to share, choose **Upload** in the handheld
   application to send the map to Scenescape.
3. Refresh the Scenescape 3D view and verify that the uploaded map is visible.
4. Add and calibrate any additional cameras as usual.

Handheld applications may also extend a map or operate in localization and
detection modes. When connected to the scene, their map contributions and
camera updates flow into Scenescape, where handheld cameras can move and detect
objects in the scene.

## Using multiple handheld devices

### Devices using the same mapping method

Devices using the same mapping method automatically share mapping artifacts.
Join each additional device to the same scene by scanning its QR code or
entering the scene details manually, then download the map to that device.

### Devices using different mapping methods

Different mapping methods cannot automatically localize to each other's maps.
To align devices using different methods:

1. Place at least three AprilTags on the scene floor, as far apart as possible.
2. Set the AprilTag size in each handheld application's configuration.
3. Make sure each tag is clearly visible while mapping from every device.
4. Keep the tags in the same positions while mapping with each device.

After uploading maps to Scenescape, inspect them in the 3D viewer. In
**Scene Settings**, select the map mesh to use and choose **set as default**.

There are several Scenescape handheld applications. Refer to the documentation
for your specific device for its mapping, upload, and localization instructions.
