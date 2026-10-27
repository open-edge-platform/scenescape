-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation
-- SPDX-License-Identifier: Apache-2.0

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS scenescape_events (
  event_id UUID NOT NULL DEFAULT gen_random_uuid(),
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  occurred_at TIMESTAMPTZ NOT NULL,
  deployment_id TEXT NOT NULL DEFAULT 'default',
  event_type TEXT NOT NULL,
  scene_id TEXT,
  region_id TEXT,
  tripwire_id TEXT,
  track_id TEXT,
  identity_id TEXT,
  camera_id TEXT,
  source_topic TEXT NOT NULL,
  source_message_id TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (occurred_at, event_id)
);

SELECT create_hypertable('scenescape_events', 'occurred_at', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS scenescape_events_scene_time
  ON scenescape_events (deployment_id, scene_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS scenescape_events_identity_time
  ON scenescape_events (deployment_id, identity_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS scenescape_events_region_time
  ON scenescape_events (deployment_id, region_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS scenescape_events_tripwire_time
  ON scenescape_events (deployment_id, tripwire_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS scenescape_events_type_time
  ON scenescape_events (deployment_id, event_type, occurred_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS scenescape_events_dedup
  ON scenescape_events (occurred_at, deployment_id, source_topic, source_message_id);

CREATE TABLE IF NOT EXISTS scenescape_graph_edges (
  edge_id BIGSERIAL PRIMARY KEY,
  deployment_id TEXT NOT NULL DEFAULT 'default',
  relation TEXT NOT NULL,
  src_kind TEXT NOT NULL,
  src_id TEXT NOT NULL,
  dst_kind TEXT NOT NULL,
  dst_id TEXT NOT NULL,
  scene_id TEXT,
  valid_from TIMESTAMPTZ NOT NULL,
  valid_to TIMESTAMPTZ,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS scenescape_graph_edges_src
  ON scenescape_graph_edges (deployment_id, src_kind, src_id, relation);

CREATE INDEX IF NOT EXISTS scenescape_graph_edges_dst
  ON scenescape_graph_edges (deployment_id, dst_kind, dst_id, relation);

CREATE INDEX IF NOT EXISTS scenescape_graph_edges_scene
  ON scenescape_graph_edges (deployment_id, scene_id);
