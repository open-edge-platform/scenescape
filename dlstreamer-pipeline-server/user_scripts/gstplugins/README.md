# SceneScape GStreamer plugins

This folder contains SceneScape's custom GStreamer elements used by the DL
Streamer Pipeline Server. These are **not standalone scripts** — they are
GStreamer plugins meant to be loaded in runtime.

For working, end-to-end usage, see the example pipeline, e.g. [queuing-config.json](../../../sample_data/demo_scenes/Queuing/queuing-config.json),
the video-source compose file [queuing-video-compose.yaml](../../../sample_data/demo_scenes/Queuing/queuing-video-compose.yaml),
and the main [docker-compose.yml](../../../docker-compose.yml)
