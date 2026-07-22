---
name: external-source-adapter
description: Write or review Scenescape external-source converter/adapter scripts that map native telemetry (MAVLink, ROS 2, NMEA, CAN, UWB/RTLS, proprietary) into the Scene Controller external_source MQTT contract. Use when the task involves external sources, publishers, adapters, converters, source_id, or scenescape/external topics.
---

# External-Source Adapter Skill

Help a user or agent write a small converter that publishes into
`scenescape/external/{scene_id}/{thing_type}` with a `source_id` payload.

## Mandatory Reads (In Order)

Before writing or changing converter code or docs:

1. This skill.
2. User guide:
   `docs/user-guide/how-to-guides/publish-external-source-adapter.md`
3. Canonical contract:
   `docs/user-guide/microservices/controller/data_formats.md`
   (section **External Source Input Message Format** and its subsections).
4. When validating payloads against schema definitions:
   `controller/src/schema/metadata.schema.json`
   (`external_source`, `external_pose`, `external_detection`).
5. If an example adapter already exists for the protocol or a close cousin, read
   it before inventing a new layout:
   `tools/external_source_adapters/` (for example `mavlink_to_external_source.py`).

Architecture background (optional):
`docs/adr/0014-unified-external-source-ingestion.md`.

## Hard Rule — No Contract Duplication

The field tables, required-field lists, pose-trust rules, identity/collision
guidance, rejection reasons, and full JSON examples are defined only in
`data_formats.md` (backed by the schema).

- Do **not** copy those tables, field lists, or examples into this skill, into
  generated code comments, or into new documentation pages.
- Cite the relevant `data_formats.md` anchors (or the how-to checklist) instead.
- If the contract and a snippet appear to disagree, trust `data_formats.md` /
  the schema and fix the snippet.

## Preferred Layout

- Put runnable example adapters under `tools/external_source_adapters/`.
- Keep protocol-specific dependencies in that directory's `requirements.txt`
  (for example `pymavlink`). Do **not** add them to core Scenescape runtime
  requirements unless the product explicitly adopts the protocol.
- Follow the how-to's `SCENESCAPE_*` environment-variable naming for scene id,
  source id, broker, MQTT auth, and root cert.
- Reuse `scene_common.mqtt.PubSub` and `PubSub.DATA_EXTERNAL` rather than a
  one-off MQTT client, unless the user requires otherwise.
- When adding or renaming an example adapter, update
  `tools/external_source_adapters/README.md` and add a See Also link from the
  how-to — do not paste the script into `data_formats.md`.

## Agent Checklist When Writing a Converter

1. Target an explicit `scene_id` and `thing_type`; do not invent scene discovery.
2. Choose a persistent `source_id` and per-object `id` (see Choosing a
   `source_id` in `data_formats.md`); never mint fresh UUIDs on each restart.
3. Map native observations into source-local `translation` (metres) relative to
   the source origin described by `pose`.
4. Choose `reference_frame` (`wgs84` vs `scene`) correctly; honor
   `CONTROLLER_TRUSTED_POSITIONING_SOURCES` for `scene` poses.
5. Convert the source's native orientation (euler, DCM, etc.) into the
   contract's quaternion `(x, y, z, w)`. Do not invent alternate rotation
   field shapes.
6. Use ISO 8601 UTC timestamps (`scene_common.timestamp.get_iso_time` is fine).
7. **Pose-only sources** (GNSS/attitude with no separate detections): either
   publish `pose` with an empty `objects` array (cache refresh), or report the
   platform itself as one object at `[0, 0, 0]` using the same persistent id as
   `source_id` — see Choosing a `source_id` in `data_formats.md`. Do not mint a
   second identity for "the vehicle."
8. Publish over authenticated MQTT with the Scenescape CA cert (see the how-to
   skeleton using `scene_common.mqtt.PubSub` and `PubSub.DATA_EXTERNAL`).
9. Keep credentials in environment variables or secret files — never hard-code
   and never ship default passwords.
10. Do **not** add controller-side ID remapping, lookup caches, or identity
    allowlists; translation belongs in the adapter.
11. Prefer linking readers to `data_formats.md` examples over inventing new
    sample payloads.

## Out of Scope (Refuse / Defer)

Do not implement or imply as part of an adapter task:

- Multi-scene discovery, fan-out, or boundary arbitration
- Cross-source fusion or camera/external deduplication
- Per-source identity trust allowlists (identity is trusted by default with
  collision detection — see `data_formats.md`)
- Changes to Scene Controller pose cache, identity registry, or schema unless
  the user explicitly requested a contract change
- Broker mTLS/ACL binding of credentials to `source_id`s
- Promoting a protocol library into core Scenescape dependencies "for
  convenience"

## Maintenance (Anti-Drift)

When the external-source contract changes:

1. Update `controller/src/schema/metadata.schema.json` and the External Source
   section of `docs/user-guide/microservices/controller/data_formats.md` first.
2. Then only adjust broken links, checklist wording, or the how-to MQTT skeleton
   in `docs/user-guide/how-to-guides/publish-external-source-adapter.md` and
   this skill.
3. If example adapters under `tools/external_source_adapters/` break against the
   new contract, fix their mapping code and README pointers — still without
   copying field tables into the README.
4. Do **not** re-document fields here. This skill stays a thin procedure +
   pointer document.
