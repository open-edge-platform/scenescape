# Design Document: Feature X

- **Author(s)**: [Patryk Iracki](https://github.com/Irakus)
- **Date**: 2025-09-15
- **Status**: [Draft]
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

As of now, MQTT was used as single channel for all data, including video frames. This approach has several drawbacks:
- High latency due to MQTT protocol overhead
- Increased CPU and memory usage on the server side
- Scalability issues with multiple concurrent video streams
To achieve this, there's a custom python script used in DLStreamer pipeline that takes raw video frames, draws overlays and watermarks, encodes them to JPEG and publishes to MQTT broker. On the client side, the web application subscribes to the MQTT topic, decodes JPEG frames and displays them in an HTML image and canvas elements. This approach is not optimal for real-time video streaming due to the overhead of encoding/decoding and the limitations of MQTT for high-frequency data transmission.
Even though the current solution is not optimal and efficient, it ensures that all data is synchronised since it's transmitted over a single channel.
Another positive aspect is reliability of MQTT protocol, which ensures that all messages are delivered, even in case of temporary network issues. This is particularly important for scenarios where data integrity is crucial.
Camera feed is transported to MediaMTX server over RTSO, from which DLStreamer pulls the video stream.

## 5. Proposed Design

In python script, only frames needed for autocalibration will be published to MQTT as they're only transmitted one-time and on demand when autocalibration button is pressed by user.
MediaMTX server will be used to handle WebRTC connections.
On the client side, the web application will establish a WebRTC connection to MediaMTX server to receive video streams. This will involve setting up signaling, ICE candidates, and media tracks.
Overlays and watermarks provided by DLStreamer will be dropped. Instead, native DLStreamer bounding boxes will be used.
Live-view button will be replaced from Scene Details as WebRTC stream is not that easy to start/stop as MQTT stream. Instead, live-view will be always active when user is on Scene Details page.
For raw camera feed, as the're already available in MediaMTX server, at least a consistent naming convention will be needed, as web app only knows topic names of DLStreamer output streams.
With MQTT there were no requirements for video format, as each frame was encoded to JPEG image. With WebRTC, video codec must be supported by both MediaMTX server and web browsers. Videos can no longer contain b-frames.
Nginx will be added as a reverse proxy in front of MediaMTX server to handle TLS termination and provide a secure connection for Web app.

## 6. Alternatives Considered

- Staying with MQTT: for few cameras and low frame rates, MQTT might be sufficient, but it doesn't scale well with more cameras and higher frame rates.

## 7. Risks and Mitigations

- When video is out of user view, browsers stop buffering it. Reconnection can take a while - TBD
- Lost synchronization between video and other dlstreamer data - TBD
- Only DLStreamer output topics are known to web app - raw camera feed topic naming convention must be established
- WebRTC is less reliable at delivering every single frame compared to MQTT - TBD

## 8. Rollout / Migration Plan

This is a breaking change as it will remove frame publishing over MQTT.

## 9. Testing & Monitoring

We'll need a setup with a lot of cameras and/or higher frame rates to observe performance improvement.

## 10. Open Questions

- Who should handle input video format adjustment? Should we add and adapter component that will ensure WebRTC-compatible video format?

## 11. References

TBD
