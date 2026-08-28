# Stream Manager — Event-Based Video Storage and Retrieval

## Architecture diagram

![Stream Manager architecture](scenescape-architecture-extension-Case-3.drawio.svg)

## Sequence diagram

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant Cam as Camera (NTP-synced)
    participant SMgr as Sensor Manager
    participant DLSPS as DL Streamer Pipeline Server
    participant Broker as MQTT Broker
    participant Ctrl as Scene Controller
    participant BL as Business Logic
    participant SM as Stream Manager
    participant VLM as VLM / downstream

    note over SMgr: Interactions with Sensor Manager are shown in purple

    rect rgb(230, 219, 255)
    note over Op, SMgr: Discovery + camera setup (Sensor Manager)
    Op->>SMgr: Discover cameras, configure NTP / ONVIF sync
    SMgr->>Cam: Configure NTP synchronization (ONVIF)
    BL->>SMgr: Query discovered sensors (namespace IDs)
    SMgr-->>BL: Sensors [{sensor_id, type, capabilities}]
    end

    rect rgb(238, 255, 240)
    note over BL, SM: Attach stream + buffering + event subscription
    alt Attach discovered sensor (source_kind: sensor)
        BL->>SM: POST /v1/streams {source_kind: sensor, sensor_id}
        SM->>SMgr: Resolve source for sensor_id
        SMgr-->>SM: Stream source endpoint
    else Attach manually by URL (source_kind: uri)
        BL->>SM: POST /v1/streams {source_kind: uri, source_uri}
        SM->>SM: Validate URL (scheme allowlist, block internal) + dedup source_uri
    end
    end

    rect rgb(238, 255, 240)
    SM->>Cam: Open stream (RTSP, 2nd viewer)
    SM-->>BL: 201 Created {stream_id, origin, sensor_id?}
    BL->>SM: PUT /v1/streams/{stream_id}/buffer {enabled, buffer_seconds}
    SM->>SM: Start pre-event in-memory buffering (ring buffer)
    SM-->>BL: 200 OK BufferStatus
    BL->>Broker: Subscribe to analytics event topics
    loop While buffering
        Cam-->>SM: Timestamped frames (ring buffer)
    end
    end

    rect rgb(255, 251, 235)
    note over Cam, Ctrl: Analytics pipeline (independent path)
    loop Per frame
        Cam-->>DLSPS: Frames
        DLSPS->>Broker: Detection metadata (timestamped)
        Broker->>Ctrl: Detection metadata
        Ctrl->>Broker: Analytics event (timestamped, visibility)
    end
    end

    rect rgb(255, 243, 243)
    note over Broker, SM: Event-triggered synchronized recording
    Broker->>BL: Analytics event + visibility + t_event
    BL->>BL: Select streams from visibility metadata
    BL->>SM: POST /v1/records/start {stream_ids, mode, pre_event_seconds}
    SM-->>BL: 201 Created {record_id}
    alt Open-ended recording
        Broker->>BL: Event completion
        BL->>SM: POST /v1/records/stop {record_id}
        SM-->>BL: 200 OK {state: completed}
    else Fixed duration
        SM->>SM: Auto-stop after duration
    end
    end

    rect rgb(235, 245, 255)
    note over BL, VLM: Retrieval (binary frame / clip) + analysis
    BL->>SM: GET /v1/records?stream-id&timestamp-start&timestamp-end
    SM-->>BL: 200 OK [record metadata]
    BL->>SM: GET /v1/records/{record-id}/clip?stream-id&range&format (or /frame)
    SM-->>BL: 200 OK (video/mp4 or image binary)
    BL->>VLM: Retrieved frames / clip for analysis
    VLM-->>BL: Analysis result
    BL->>Op: Alert (based on analysis result)
    end
```

## API summary

| Method | Endpoint | What it does | Parameters | Returns |
| --- | --- | --- | --- | --- |
| GET | `/v1/sensors` | _Optional._ List sensors discovered via Sensor Manager, available to attach | query: `type`, `available`, `limit`, `cursor` | `200` `SensorList` `{ items[Sensor{ sensor_id, type, capabilities, available }], next_cursor }`; `502` if Sensor Manager unreachable |
| GET | `/v1/streams` | List attached streams | query: `state`, `limit`, `cursor` | `200` `StreamList` `{ items[Stream], next_cursor }` |
| POST | `/v1/streams` | Attach a stream from a discovered sensor or manually by URL; optionally initialize buffering | body (`oneOf` on `source_kind`\*): sensor → `sensor_id`\*; uri → `source_uri`\*; plus `name`, `buffer{ enabled, buffer_seconds }` | `201` `Stream` + `Location`; `400` invalid/blocked URL; `404` unknown sensor; `409` duplicate `sensor_id` or `source_uri` |
| GET | `/v1/streams/{stream-id}` | Get metadata of a stream (incl. `sensor_id`) | path: `stream-id`\* | `200` `Stream`; `404` |
| DELETE | `/v1/streams/{stream-id}` | Detach a stream and stop its buffering | path: `stream-id`\* | `204`; `409` if being recorded |
| PUT | `/v1/streams/{stream-id}/buffer` | Configure the in-memory pre-event buffer (time window) | path: `stream-id`\*; body: `enabled`\*, `buffer_seconds` | `200` `BufferStatus` `{ ..., buffered_seconds, oldest_buffered_at }` |
| GET | `/v1/records` | List recordings and metadata | query: `stream-id`, `timestamp-start`, `timestamp-end`, `state`, `limit`, `cursor` | `200` `RecordList` `{ items[Record], next_cursor }` |
| POST | `/v1/records` | Import (upload) an external recording | body (multipart): `file`\*, `sensor_id`, `label` | `201` `Record` + `Location`; `413` too large |
| POST | `/v1/records/start` | Start one synchronized recording spanning multiple streams | header: `Idempotency-Key`; body: `stream_ids`\*, `mode` (`open`\|`fixed`), `duration_seconds` (req if `fixed`), `pre_event_seconds`, `event_id`, `label` | `201` `Record` + `Location`; `404` unknown stream; `409` key reuse |
| POST | `/v1/records/stop` | Stop an in-progress recording | body: `record_id`\* | `200` `Record`; `404`; `409` not stoppable |
| GET | `/v1/records/{record-id}` | Get recording metadata incl. per-stream tracks | path: `record-id`\* | `200` `Record` `{ ..., tracks[RecordTrack] }`; `404` |
| DELETE | `/v1/records/{record-id}` | Delete a recording | path: `record-id`\* | `204`; `409` if in progress |
| GET | `/v1/records/{record-id}/frame` | Retrieve a single frame from one stream (nearest to timestamp) | path: `record-id`\*; query: `stream-id`\*, `timestamp`\*, `format` (`jpeg`\|`png`) | `200` binary `image/jpeg`\|`image/png` + `X-Frame-Timestamp`; `404` |
| GET | `/v1/records/{record-id}/clip` | Retrieve a video clip from one stream over a range | path: `record-id`\*; query: `stream-id`\*, `timestamp-start`\*, `timestamp-end` \| `duration-seconds`, `format` (`mp4`\|`mkv`\|`webm`) | `200` binary `video/mp4`\|`video/x-matroska`\|`video/webm`; `404` |

\* = required. Streams are either **discovered** (`GET /v1/sensors`) and **attached by `sensor_id`** (Sensor Manager namespace, `source_kind: sensor`) or **attached manually by URL** (`source_kind: uri`, `source_uri`) outside that namespace. `Stream` reports its `origin` (`sensor`\|`uri`); `sensor_id` is null for URL-attached streams. Manual URLs are restricted to a scheme allowlist and de-duplicated by normalized `source_uri` (SSRF protection). **Optional camera control** (PTZ / NTP) is provided by the **Sensor Manager API** (not Stream Manager) and is called by Business Logic using the same `sensor_id`. All timestamps are RFC 3339 UTC; errors use `application/problem+json` (RFC 9457); auth is a bearer token.
