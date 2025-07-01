
# Streamer

This tool can be used to stream existing video files over RTSP. See utils_streamer.py for a list of supported video formats.

## Pre-requisites

These scripts require FFMPEG and docker to be installed locally.

## Overview

The start_rtsp.py script will instantiate an rtsp server (rtsp-simple-server) and will instantiate an ffmpeg instance for every video found in the provided directory.
The streams will be called, by default, same as the input file name (without the extension).
Example: ./start_rtsp.py apriltag-cam1.mp4 will stream at rtsp://hostname:8554/apriltag-cam1

If you want them all to have the same prefix, you can use the '--base_name' option:

```
./start_rtsp.py --base_name <prefix> <videos-folder>
```

The path will then be:

```
rtsp://<server-ip>:8554/<prefix>1
rtsp://<server-ip>:8554/<prefix>2
...
```


## Usage + Examples

1. Provide the path to a directory containing videos to stream.
```
./start_rtsp.py <path1> ... <pathN>
```
Where the provided paths are either a directory containing video files, or a path to a video file.
This will pull rtsp-simple-streamer, start it, and start ffmpeg to stream videos found under the provided paths.


2. Stream all the videos starting with 'demo', but name them camera1, camera2, ... :
```
./start_rtsp.py demo*mp4 --base_name camera
```

3. Provide the path, request video to be re-sized:
```
./start_rtsp.py -s 1280x720 <path1> ... <pathN>
```
This will re-size the video to the requested size. Format is same as FFMPEG -s command (WxH)

4. In case there's already a server up, you can specify the --skip_server flag, so a new server is not created.
You will probably also want to specify what camera id to start from:

```
./start_rtsp.py --skip_server --start_id 4 <path1> ... <pathN>
```

5. If you want to request transcoding, with a particular set of options, you can use the --encoder and --extra flags:
```
./start_rtsp.py --encoder libx264 --extra "-preset veryfast -tune zerolatency -pix_fmt yuv420p" <path1> ... <pathN>
```

or

```
./start_rtsp.py --encoder mjpeg --extra "-huffman 0 -q:v 5" <path1> ... <pathN>
```



This will pass along the extra flags to the transcoder session.
By default, the streamer will not re-encode video (it will use the 'copy' transcoder).

Note that, the vlc_playback.py must be executed via a VNC connection in order to see the actual image.
Also, to add a new extension to the list of the supported video extension, edit utils_streamer.py.
