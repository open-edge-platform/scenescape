# Design Document: Using WebRTC for Video Streaming

- **Author(s)**: [Patryk Iracki](https://github.com/Irakus)
- **Date**: 2025-09-15
- **Status**: [Proposed]
- **Related ADRs**: N/A

---

## 1. Overview

Replacing the current video streaming from MQTT-based to WebRTC-based to improve performance and user experience.

## 2. Goals

- Stop publishing video frames over MQTT
- Implement WebRTC for video streaming
- Reduce latency for each stream
- Reduce resource consumption on DLStreamer Pipeline Server

## 3. Non-Goals

- Using WebRTC for calibration service

## 4. Background / Context

### Current Design

```mermaid
flowchart LR
    subgraph Cameras["IP Cameras"]
        C1["Camera 1<br/>(RTSP H.264)"]
        C2["Camera 2<br/>(RTSP MJPEG)"]
    end

    subgraph Mqtt["MQTT<br/>"]
        RawStream["Raw video stream"]
        AnnotatedStream["Annotated video stream"]
        VideoMetadata["Video metadata"]
    end

    subgraph AI["DL Streamer Pipeline"]
        subgraph gvapython["gvapython"]
        CustomPreProcess["Custom pre-processing"]
        CustomPostProcess["Custom post-processing"]
        end
        Detect["Inference<br/>(Object Detection)"]
        CustomPreProcess --> Detect --> CustomPostProcess
    end

    subgraph Browser["Web Browser"]
        Scene["Scene Page<br/>(AI Stream)"]
        AutoCalib["Autocalibration Page<br/>(Raw Stream)"]
    end

    %% Camera flows into DLS
    C1 --> CustomPreProcess
    C2 --> CustomPreProcess

    %% DLS publishes to 3 MQTT topics
    CustomPostProcess --> RawStream
    CustomPostProcess --> AnnotatedStream
    CustomPostProcess --> VideoMetadata

    %% Web UI subscribes to 2 MQTT topics
    AnnotatedStream --> Scene
    RawStream --> AutoCalib
```

As of now, MQTT was used as single channel for all data, including video frames. This approach has several drawbacks:

- High latency due to MQTT protocol overhead
- Increased CPU and memory usage on the server side
- Scalability issues with multiple concurrent video streams
  To achieve this, there's a custom python script used in DLStreamer pipeline that takes raw video frames, draws overlays and watermarks, encodes them to JPEG and publishes to MQTT broker. On the client side, the web application subscribes to the MQTT topic, decodes JPEG frames and displays them in an HTML image and canvas elements. This approach is not optimal for real-time video streaming due to the overhead of encoding/decoding and the limitations of MQTT for high-frequency data transmission.
  Even though the current solution is not optimal and efficient, it ensures that all data is synchronised since it's transmitted over a single channel.
  Another positive aspect is reliability of MQTT protocol, which ensures that all messages are delivered, even in case of temporary network issues. This is particularly important for scenarios where data integrity is crucial.
  Camera feed is transported to MediaMTX server over RTSP, from which DLStreamer pulls the video stream.

## 5. Proposed Design

```mermaid
flowchart LR
    subgraph Cameras["IP Cameras"]
        C1["Camera 1<br/>(RTSP H.264)"]
        C2["Camera 2<br/>(RTSP MJPEG)"]
    end

    subgraph FFMPEG["Video Adapter<br/>(FFMPEG)"]
        Transcode["Transcoding<br/>(MJPEG → H.264)"]
    end

    subgraph MediaServer["Media Server<br/>(mediamtx)"]
        RouteRTSP["Routing<br/>(RTSP)"]
        Repack["Protocol Repackaging<br/>(H.264 RTSP → WebRTC)"]
        RouteWebRTC["Routing<br/>(WebRTC)"]
    end

    subgraph AI["DL Streamer Pipeline"]
        subgraph gvapython["gvapython"]
            CustomPreProcess["Custom pre-processing"]
        end
        Detect["Inference<br/>(Object Detection)"]
        Overlay["Overlay Bounding Boxes"]
    end

    subgraph Browser["Web Browser"]
        Scene["Scene Page<br/>(AI Stream)"]
        AutoCalib["Autocalibration Page<br/>(Raw Stream)"]
    end

    %% Camera flows into Media Server
    C1 --> Transcode
    C2 --> Transcode

    %% FFMPEG converts video and sends to Media Server
    Transcode --> RouteRTSP

    %% Raw stream path → Autocalibration
    RouteRTSP --> Repack
    Repack --> AutoCalib

    %% AI pipeline path → Scene
    RouteRTSP --> CustomPreProcess
    CustomPreProcess --> Detect --> Overlay --> RouteWebRTC
    RouteWebRTC --> Scene

```

In python script, only frames needed for autocalibration will be published to MQTT as they're only transmitted one-time and on demand when autocalibration button is pressed by user.
MediaMTX server will be used to handle WebRTC connections.
On the client side, the web application will establish a WebRTC connection to MediaMTX server to receive video streams. This will involve setting up signaling, ICE candidates, and media tracks.
Overlays and watermarks provided by DLStreamer will be dropped. Instead, native DLStreamer bounding boxes will be used.
Live-view button will be replaced from Scene Details as WebRTC stream is not that easy to start/stop as MQTT stream. Instead, live-view will be always active when user is on Scene Details page.
For raw camera feed, as they're already available in MediaMTX server, at least a consistent naming convention will be needed, as web app only knows topic names of DLStreamer output streams.
With MQTT there were no requirements for video format, as each frame was encoded to JPEG image. With WebRTC, video codec must be supported by both MediaMTX server and web browsers. Videos can no longer contain b-frames.
Nginx will be added as a reverse proxy in front of MediaMTX server to handle TLS termination and provide a secure connection for Web app.
For browser to connect to MediaMTX server, a valid TLS certificate must be used. Instead of accepting insecure connection in browser, user guide should include instructions on how to import Scenescape CA certificate.

## 6. Alternatives Considered

### Displaying DLStreamer output in all places

```mermaid
flowchart LR
    subgraph Cameras["IP Cameras"]
        C1["Camera 1<br/>(RTSP H.264)"]
        C2["Camera 2<br/>(RTSP MJPEG)"]
    end

    subgraph MediaServer["Media Server<br/>(mediamtx)"]
        RouteWebRTC["Routing<br/>(WebRTC)"]
    end

    subgraph AI["DL Streamer Pipeline"]
        subgraph gvapython["gvapython"]
            CustomPreProcess["Custom pre-processing"]
        end
        Detect["Inference<br/>(Object Detection)"]
        Overlay["Overlay Bounding Boxes"]
    end

    subgraph Browser["Web Browser"]
        Scene["Scene Page<br/>(AI Stream)"]
        AutoCalib["Autocalibration Page<br/>(Raw Stream)"]
    end

    %% Camera flows into Media Server
    C1 --> CustomPreProcess
    C2 --> CustomPreProcess

    %% Raw stream path → Autocalibration
    RouteWebRTC --> AutoCalib

    %% AI pipeline path → Scene
    CustomPreProcess --> Detect --> Overlay --> RouteWebRTC
    RouteWebRTC --> Scene

```

This approach would simplify the architecture, as no adapter would be needed for videos. This would allow us to only limit cameras to DLStreamer-supported formats. However, this would force us to use only annotated feed for both Scene Detail and Camera Calibration views.
This would also remove the need of common naming convention for raw camera feeds and DLStreamr-processed videos.

### Staying with current implementation

- Staying with MQTT: for few cameras and low frame rates, MQTT might be sufficient, but it doesn't scale well with more cameras and higher frame rates.

## 7. Risks and Mitigations

- When video is out of user view, browsers stop buffering it. Reconnection can take a while - TBD
- Lost synchronization between video and other dlstreamer data - TBD
- Only DLStreamer output topics are known to web app - raw camera feed topic naming convention must be established
- WebRTC is less reliable at delivering every single frame compared to MQTT - TBD
- WebRTC has more strict requirements for video format - Adding ffmpeg-based adapter component for connecting cameras to ensure WebRTC-compatible video format

## 8. Rollout / Migration Plan

Upgrade from current version would require user to restart DLStreamer Pipelines and Web App. No frame data is persisted long-time, so no migration of data is needed.

## 9. Testing & Monitoring

We'll need a setup with a lot of cameras and/or higher frame rates to observe performance improvement.

## 10. Open Questions

### Video Formats

WebRTC has limited support on Video Codecs which may also vary between browsers.
Documenation for supported codecs:

- https://www.rfc-editor.org/rfc/rfc7742.txt
- https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/WebRTC_codecs

Overview:

- Mandatory (Must Support)
  - VP8
  - H.264 (Constrained Baseline Profile)
- Optional (May Support)
  - VP9
  - AV1
  - H.265/HEVC (limited browser support)
- Legacy/Deprecated
  - H.264 (other profiles - limited support)
- Browser Support Notes:
  - Chrome/Edge: VP8, H.264, VP9, AV1
  - Firefox: VP8, H.264, VP9, AV1 (experimental)
  - Safari: VP8, H.264, VP9 (limited), H.265 (Safari-specific)

Aside from that, for quick start of transmission, more keyframes are needed. Our sample videos have keyframes every 10 seconds and that causes long delays when starting the stream. Ideal keyframe interval is 1-2 seconds.

## 11. References

- https://www.rfc-editor.org/rfc/rfc7742.txt
- https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/WebRTC_codecs
