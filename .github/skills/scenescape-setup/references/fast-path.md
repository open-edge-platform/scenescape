<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Fast Path (repeat or resume deployments)

Read when the user wants to re-run or resume an existing `deploy_dir` without changing inputs.

If `<deploy_dir>/deploy-inputs.json` already exists and the user's new request does not change
streams, camera IDs, or the scene name, skip re-asking Step 1 questions:

1. Show the loaded `deploy-inputs.json` values to the user and confirm they still apply.
2. Run the orchestrator with `--deploy-dir` + `--skill-dir` only (no `--streams`/`--camera-ids`/
   `--scene-name`) — inputs are loaded automatically and validated against any values the user
   did provide.
3. If the user mentions a camera/stream change, treat it as a new deployment: re-run Step 1 in
   full and use `--fresh`.

For a restricted environment where the read-back cannot expose the file's contents, still show a
three-field confirmation block for the persisted `streams`, `camera_ids`, and `scene_name`; say
they are loaded from `deploy-inputs.json` rather than inventing replacement inputs. A resume
command must omit `--resume`, `--streams`, `--camera-ids`, and `--scene-name`.

**Implicit Fast Path trigger**: When the user says "continue", "resume", "it stopped partway
through", "pick up where we left off", or similar for a named `deploy_dir`, treat that statement
as confirmation that `deploy-inputs.json` already exists at that path. Apply the Fast Path
directly — show the user the Fast Path procedure (what values will be loaded and what command
will be run) without falling back to Step 1 questions. State: "The stopped-deployment signal
confirms `deploy-inputs.json` exists, so I am skipping Step 1 questions." Only fall back to
Step 1 if:

- The user explicitly says the directory is wrong or no prior run exists.
- You attempt to read `deploy-inputs.json` and the file is genuinely absent **and** the user did
  not give any "resume/continue" signal — a new fresh deployment was intended.

For an explicit resume signal, do not test the local sandbox for file existence or treat a
missing local path as a contradiction. The signal is sufficient confirmation: show the read-back
command, show the resume command, and state that `.deploy-state.json` selects the next
incomplete step. Use this exact sentence in the response: "The orchestrator resumes from the
step recorded in `.deploy-state.json` rather than restarting from step 1."

For a camera or stream change, read the existing inputs before creating the replacement set. If
the read-back is unavailable, say that the new set replaces only the named camera/stream while
retaining every other persisted camera, stream, and the scene name, then explicitly ask the user
to confirm or provide that existing list. Do not proceed with only the changed camera. State
that a changed camera or stream set is not eligible for the Fast Path resume.

In that unavailable-read-back case, do not execute a write or `--fresh` launch. State: "I could
not read the existing deployment inputs. Please provide or confirm the retained camera IDs,
streams, and scene name before the fresh redeploy." Then show the exact `--fresh` orchestrator
command marked **pending confirmation**. Never present retained-camera placeholders as runnable
values. Use both of these exact sentences in the response:

- "`--fresh` clears `.deploy-state.json` and the old `deploy-inputs.json`."
- "This `--fresh` run re-executes all phases (bootstrap, calibrate, scene) rather than only
  recalibrating the changed camera."

When the read-back *is* available and the user has confirmed the full updated camera/stream set,
still include both exact `--fresh` sentences above when showing the launch command.
