<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Persisting object attributes across detection gaps

Read this when the user wants attributes like color, license plate, or person
attributes (age/gender/PPE) to "stick" to a tracked object even on frames where the AI
pipeline didn't re-detect that attribute, instead of the value resetting/disappearing.

**Not to be confused with attribute-type singleton sensors:** this page is about attributes that
come _from the vision/AI pipeline_ (a camera detecting a person's shirt color, for example). If
the value instead comes from a separate physical or virtual sensor publishing its own MQTT
messages (e.g. a badge reader), see [singleton-sensors.md](./singleton-sensors.md)'s `attribute`
sensor type instead.

## What it configures

The scene controller's `persist_attributes` field (in `tracker-config.json`, alongside the
tracking/timing parameters covered in [tuning-tracker.md](./tuning-tracker.md)) tells the tracker
which detection-result attributes to carry forward on a tracked object between updates, instead of
an intermittently-reported value (e.g. a license-plate reader that only reads the plate every few
frames) flickering in the UI. Default (key absent): `{}` — no attributes are persisted.

See [How to Configure the Tracker#persisting-object-attributes-across-detection-gaps](https://github.com/open-edge-platform/scenescape/blob/main/docs/user-guide/microservices/controller/how-to-configure-tracker.md#persisting-object-attributes-across-detection-gaps)
(or the local path `docs/user-guide/microservices/controller/how-to-configure-tracker.md`) for the
full field reference and JSON format.

## How to apply

1. Add or edit the `persist_attributes` key in `<deploy_dir>/controller/tracker-config.json`
   (same file documented in [tuning-tracker.md](./tuning-tracker.md); this key can be added
   alongside the timing/motion parameters there, it is not mutually exclusive with them).
2. Restart the scene controller to pick up the change:
   ```bash
   docker compose up -d --force-recreate scene
   ```

## Notes

- Only list attributes that are actually present in the detection pipeline's output metadata —
  persisting a key that never appears has no effect.
- This does not create new attributes; it only prevents existing ones from being cleared when a
  given frame's detection doesn't include them.
