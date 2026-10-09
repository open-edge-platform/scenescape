# SceneScape GStreamer plugins

This folder contains SceneScape's custom GStreamer elements used by the DL
Streamer Pipeline Server. These are **not standalone scripts** — they are
GStreamer plugins meant to be loaded in runtime.

For working, end-to-end usage, see the example pipeline, e.g. [queuing-config.json](../../../sample_data/demo_scenes/Queuing/queuing-config.json),
the video-source compose file [compose.queuing-video.yml](../../../sample_data/demo_scenes/Queuing/compose.queuing-video.yml),
and the main [docker-compose.yml](../../../docker-compose.yml)
