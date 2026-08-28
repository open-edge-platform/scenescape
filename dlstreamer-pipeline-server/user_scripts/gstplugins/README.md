# SceneScape GStreamer plugins

This folder contains SceneScape's custom GStreamer elements used by the DL
Streamer Pipeline Server. These are **not standalone scripts** — they are
GStreamer plugins meant to be loaded in runtime.

| File | Element | Role |
| --- | --- | --- |
| `sscape_timestamp_fields.py` | (library) | MQTT timestamp field names and source selection |
| `sscape_rtcp_ntp.py` | (library) | SR parse + RTP/NTP mapping |
| `sscape_rtp_ntp.py` | `sscape_rtp_ntp` | Per-packet RTP→NTP from RTCP Sender Reports |
| `sscape_post_decode_timestamp_capture.py` | `sscape_timestamp_capture` | Attach RTCP and post-decode clocks; select MQTT `timestamp` |
| `sscape_post_inference_data_publish.py` | `sscape_post_inference_data_publish` | MQTT metadata publish |

MQTT `timestamp` is the selected clock. `timestamp_src` is that field's name
(`timestamp_rtcp` or `timestamp_post_decode`) so a consumer can do
`payload[payload["timestamp_src"]]`. Both clocks stay on the message. Switch
at runtime:

```
scenescape/cmd/camera/<id>
{"command":"timestamp_source","timestamp_source":"timestamp_rtcp"}
```

For working, end-to-end usage, see the example pipeline, e.g. [queuing-config.json](../../queuing-config.json)
and demo compose file [docker-compose-dl-streamer-example.yml](../../../sample_data/docker-compose-dl-streamer-example.yml)
