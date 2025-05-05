I built a debugging tool for testing the scene controller. It allows single stepping through data in order to watch how objects are being matched up from one frame to another. Another thing it can do is print the FPS of the scene controller. To use it requires a little bit of setup.

First thing to do is preprocess the video files using percebro:

               percebro/percebro --preprocess -i sample_data/apriltag-cam1.mp4 --mqttid camera1 -i sample_data/apriltag-cam2.mp4 --mqttid camera2 -m retail

That will create two json files with all of the output from inference done on every single frame. Next you need to create a scene.json file which describes the scene. Most of the values are what is in the database:

    {
        "name": "Demo",
        "map": "sample_data/HazardZoneSceneLarge.png",
        "scale": 100,
        "sensors": {
            "camera1": {
            "camera homography": [[278, 61], [621, 132], [559, 460], [66, 289]],
            "map homography": [[10, 105], [304, 108], [305, 401], [10, 398]],
            "width": 640,
            "height": 480,
            "intrinsics": {"fov":70}
        },
            "camera2": {
            "camera homography": [[31, 228], [423, 266], [537, 385], [79, 343]],
            "map homography": [[106, 109], [400, 105], [498, 204], [204, 205]],
            "width": 640,
            "height": 480,
            "intrinsics": {"fov":70}
        },
            "camera3": {
            "camera homography": [[137, 328], [425, 162], [596, 208], [578, 443]],
            "map homography": [[9, 105], [399, 106], [400, 305], [109, 397]],
            "width": 640,
            "height": 480,
            "intrinsics": {"fov":70}
        }
        }
    }

Then you can run the tracker:

               tracker/tracker --config scene.json apriltag-cam1.json apriltag-cam2.json

It will bring up a map window, push space to start and stop it. It will also bring up the video windows once it’s started.
