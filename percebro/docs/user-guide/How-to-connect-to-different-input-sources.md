# How to connect to different inputs sources

## USB Camera

A basic example of using Percebro with the pv0078 Person Vehicle detector using a USB camera at `/dev/video0`. The MQTT broker in this case is just `localhost`:

        $ tools/scenescape-start percebro localhost --camera 0 --camerachain pv0078

By default, this will run on the CPU. To run on the GPU, use:

        $ tools/scenescape-start percebro localhost --camera 0 --camerachain pv0078=GPU

You can also use multiple cameras. The mqttid is generated automatically based on the system MAC address and input number, but it is best to assign an mqttid to the input instance, particularly if there are multiple inputs on the system:

        $ tools/scenescape-start percebro localhost --camera 0 --cameraid camera1 --camera 1 --cameraid camera2 --camerachain pv0078=GPU

## Stored Video

To test with a stored video, simply copy to the videos directory, and pass in the path to the video as the input as follows:

        $ tools/scenescape-start percebro localhost --camera /videos/video.mp4 --camerachain pv0078

If an mqttid is not provided, the system will generate one based on the video name.

Just like with cameras, multiple video files can be specified on the input:

        $ tools/scenescape-start percebro localhost --camera /videos/video1.mp4 --cameraid view1 \
                --camera /videos/video2.mp4 --cameraid view2 --camerachain pv0078

**Note:** Video playback will loop forever, but the output timestamps in the resulting JSON object will continue to increase based on the current system time.

## Real-time Playback

By default, Percebro processes every frame of video in the file. However, this usually causes the system to run in "slow motion" since inference frame rate is slower than the camera frame rate. Percebro provides the `--realtime` option to process the video as if it were running like a camera. If a video is captured at 30 fps, for example, and inferencing is only capable of running at 15 fps, Percebro will essentially use every second frame of the video.

**Note:** Using `--realtime` is computationally expensive since the system must continuously seek forward on the video and select the appropriate frame based on inferencing time. **Do not use `--realtime` when benchmarking inferencing performance.** It is also recommended to run the benchmarking on a dedicated system, and not on the Intel® SceneScape server.

An example of using `--realtime` with two video file inputs:

        $ tools/scenescape-start percebro 192.168.1.20 --camera path/to/video1.mp4 --cameraid view1 \
                --camera path/to/video2.mp4 --cameraid view2 --camerachain pv0078 --realtime

## Video Timing with Multiple Videos

When using multiple videos of the same scene, it is critical to synchronize the playback from all views. By default, Percebro processes all videos starting at the same time:

        $ tools/scenescape-start percebro 192.168.1.20 --camera path/to/video1.mp4 --cameraid view1 \
                --camera path/to/video2.mp4 --cameraid view2 --camerachain pv0078 --realtime

If the videos are not exactly synchronized and it is possible to determine or estimate the starting offset between each, use the option to manually add an offset (in fractions of seconds) to each.

        $ tools/scenescape-start percebro 192.168.1.20 --camera path/to/video1.mp4=+0.10 --cameraid view1 \
                --camera path/to/video2.mp4=-0.20 --cameraid view2 --camerachain pv0078 --realtime

Ideally, the videos are captured on time synchronized systems, which makes it easier for Percebro to synchronize playback even if recording started at different times.
When using the `--usetimestamps` flag, Percebro calculates the start time of the video as the video creation timestamp minus the length of the video:

        $ tools/scenescape-start percebro 192.168.1.20 --camera path/to/video1.mp4 --cameraid view1 \
                --camera path/to/video2.mp4 --cameraid view2 --camerachain pv0078 --realtime --usetimestamps

The above two methods can also be combined to make very specific manual adjustments to overcome any time synchronization issues:

        $ tools/scenescape-start percebro 192.168.1.20 --camera path/to/video1.mp4=+0.10 --cameraid view1 \
                --camera path/to/video2.mp4=-0.20 --cameraid view2 --camerachain pv0078 --realtime --usetimestamps

## RTSP and HTTP Capture

RTSP support, functionality, and performance vary with camera manufacturer. The following is a couple of general examples, but please refer to the camera's documentation for details on how to pull RTSP stream(s).

        $ tools/scenescape-start percebro 192.168.1.20 \
                --camera "rtsp://admin:password@192.168.1.21" --camerachain pv0078

HTTP is similar, but again refer to the camera's documentation for specifics. This method can also work for MJPEG capture.

        $ tools/scenescape-start percebro 192.168.1.20 \
                --camera "http://admin:password@192.168.1.22/video.cgi" --camerachain pv0078

## Distortion and Warping

Intel® SceneScape assumes the input to scene controller is from an undistorted image using a pinhole camera model. We recommend following the guidance [here](https://github.com/open-edge-platform/scenescape/blob/main/docs/user-guide/How-to-create-new-scene.md#camera-selection-considerations) for choosing cameras that work best with Intel® SceneScape. In brownfield scenarios where cameras are pre-installed and do not adhere to the recommended properties, follow the instructions below based on the type of camera:

## Warping
When dealing with a wide field of view camera ([greater than 115 degrees](https://www.mathworks.com/help/vision/ug/fisheye-calibration-basics.html)), a fisheye camera model works best. Append the "--unwarp" flag to the percebro command and provide the correct field of view. The vision pipeline will unwarp the image, compute the new intrinsics for the unwarped image and send it to the scene controller.

## Distortion
When you observe that straight lines in real world are not straight in your narrow field of view cameras (less than 115 degrees), your lens has geometric distortion. For better location accuracy as well as proper calibration, it is necessary to provide accurate distortion parameters to Intel® SceneScape. Intel® SceneScape provides tools/intrinsics script to generate camera intrinsics including distortion parameters using a video of a checkerboard calibration pattern. Once the distortion parameters are known, you can configure percebro by appending the following:
        --distortion <camera distortion coeffs '[k1,k2,p1,p2[,k3[,k4,k5,k6[,s1,s2,s3,s4[,taux,tauy]]]]]'>

**Note**: enabling undistortion or unwarping adds compute overhead that will reduce the throughput of your video analytics pipeline and will result in higher CPU utilization.
