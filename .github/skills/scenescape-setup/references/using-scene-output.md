<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Building something with the deployed scene's output

Read this once a deployment reaches `DEPLOY COMPLETE` and the user wants to _use_ the tracked-object
data for something — an alert, a dashboard, a count, an integration with another system — rather
than just view it in the web UI. This is the handoff point from "deploy SceneScape" to "build an
application on top of SceneScape."

## Ask what the user is trying to accomplish

Don't assume the goal from the deployment context alone (e.g. "warehouse" doesn't imply "count
forklifts"). A short clarifying question upfront avoids wiring up the wrong topic or event type:

> "Now that the scene is tracking, what do you want to do with that data? For example: trigger an
> alert when someone enters/leaves an area, count objects over time, integrate with another
> system, or something else?"

The answer determines which of the paths below to take — often more than one applies.

## Common paths

| Goal                                                                | What to use                                                                   |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Consume live tracked-object positions/attributes as they update     | Subscribe to `scenescape/regulated/scene/<scene_uid>` (below)                 |
| Fire an action when objects enter/exit a specific area              | Create a **region** (ROI), subscribe to its event topic (below)               |
| Fire an action when an object crosses a line (e.g. entry/exit door) | Create a **tripwire**, subscribe to its event topic (below)                   |
| Tag tracked objects with external sensor data (badge, temperature)  | [singleton-sensors.md](./singleton-sensors.md)                                |
| Keep a vision-detected attribute from flickering between frames     | [attribute-persistence.md](./attribute-persistence.md)                        |
| Get more accurate size/shape reasoning for a specific object class  | [object-library.md](./object-library.md)                                      |
| Tracking quality itself is the problem (flicker, wrong Re-ID, etc.) | [tuning-tracker.md](./tuning-tracker.md) / [tuning-reid.md](./tuning-reid.md) |

After wiring up the first path, circle back and ask if the user wants another — most real
integrations combine at least two (e.g. a region for dwell-time counting _and_ a tripwire for
entry/exit events).

## Consuming the regulated scene topic

`scenescape/regulated/scene/<scene_uid>` is the primary output topic — one rate-controlled message
per scene update containing every tracked object (position, velocity, size, attributes, any tagged
sensor readings). This is the right starting point for most integrations (dashboards, counting,
custom alerting logic) since it needs no additional scene configuration.

```bash
docker run --rm --network <project>_scenescape \
  -v <deploy_dir>/secrets/certs/scenescape-ca.pem:/ca.pem:ro \
  eclipse-mosquitto:2 \
  mosquitto_sub -h broker.scenescape.intel.com -p 1883 \
  --cafile /ca.pem --insecure \
  -t 'scenescape/regulated/scene/<scene_uid>' -C 1 -W 120
```

Each message's `objects` array has one entry per tracked object: `category`/`type`, `translation`
(scene-metre position), `velocity`, `visibility` (which cameras see it), and a `metadata` map for
any pipeline-detected attributes (age, gender, license plate, etc. depending on the model). See
`docs/user-guide/microservices/controller/data_formats.md` in the SceneScape repo (section
"Regulated Scene Output Message Format") for the full field reference.

For a one-off application, poll this topic directly; for anything long-running, have the consumer
app subscribe persistently rather than re-invoking `mosquitto_sub -C 1` in a loop.

## Regions (ROIs) and tripwires — event-driven paths

Regions and tripwires publish their own event topics (only when something crosses/enters/exits,
not on every tick), which is usually a better fit than filtering the full regulated topic yourself
when the goal is "notify me when X happens" rather than "give me continuous state."

- **Region** (`scenescape/event/region/<scene_uid>/<region_id>/objects`) — publishes `counts`,
  `entered`, `exited`, and the current `objects` inside the region whenever membership changes.
  Good for occupancy/dwell-time/zone-based alerting.
- **Tripwire** (`scenescape/event/tripwire/<scene_uid>/<tripwire_id>/objects`) — publishes once per
  crossing, with a `direction` field (`1`/`-1`) on each crossing object. Good for entry/exit
  counting across a doorway or line.

**Both are drawn shapes, so guide the user to the web UI rather than asking for raw coordinates**
(same reasoning as [singleton-sensors.md](./singleton-sensors.md)'s circle/poly guidance — a region
is a polygon and a tripwire is a line, and both are meant to be drawn on the scene map):

1. Sign in to the manager web UI (`https://web.scenescape.intel.com`, superuser credentials in
   `secrets/supass`).
2. Open the scene's detail page, then use the **Regions** or **Tripwires** panel to draw the
   shape directly on the scene map.
3. Note the region/tripwire name shown after saving — the `region_id`/`tripwire_id` in the MQTT
   topic is its UUID, which can be read back via `GET /api/v1/regions` or `GET /api/v1/tripwires`
   if the exact ID isn't visible in the UI.

Subscribe to the resulting topic the same way as the regulated-scene example above, substituting
the region/tripwire topic and IDs.

## Notes

- All of the above are read-only from the agent's perspective once wired up — the actual
  alerting/dashboard/integration logic runs in the user's own consumer application, subscribing to
  these MQTT topics (or scripting against them) independently of the deployment scripts in this
  skill.
- If the user's goal implies a specific downstream system (a ticketing tool, a database, a
  notification service), that integration code is outside this skill's scope — the deliverable
  here is getting the right SceneScape topic/event wired up and confirmed working (e.g. one
  observed message), then handing off.
