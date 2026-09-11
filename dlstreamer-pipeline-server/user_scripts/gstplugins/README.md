# SceneScape GStreamer plugins

This folder contains SceneScape's custom GStreamer elements used by the DL
Streamer Pipeline Server. These are **not standalone scripts** — they are
GStreamer plugins meant to be loaded in runtime.

For working, end-to-end usage, see the example pipeline, e.g. [queuing-config.json](../../queuing-config.json)
and the video-source compose file [docker-compose.video-source.yml](../../../sample_data/demo_scenes/docker-compose.video-source.yml)
