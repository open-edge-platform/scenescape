// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/*
 * k6 MQTT workload for external-source ingestion. Each VU is one stable source
 * with a unique publisher ID and object IDs, bound to the load-test scene.
 */

import { fail, sleep } from "k6";
import mqtt from "k6/x/mqtt";

function getRequiredEnv(name) {
  if (!__ENV[name]) {
    fail(`${name} environment variable is required`);
  }
  return __ENV[name];
}

const sourceCount = Number(getRequiredEnv("EXTERNAL_SOURCE_COUNT"));
const objectCount = Number(getRequiredEnv("OBJECT_COUNT"));
const fps = Number(getRequiredEnv("EXTERNAL_FPS"));
const host = getRequiredEnv("MQTT_HOST");
const port = getRequiredEnv("MQTT_PORT");
const duration = getRequiredEnv("DEFAULT_TEST_DURATION");
const sourcePrefix = getRequiredEnv("EXTERNAL_SOURCE_PREFIX");

if (!Number.isInteger(sourceCount) || sourceCount < 1) {
  fail("EXTERNAL_SOURCE_COUNT must be a positive integer");
}
if (!Number.isInteger(objectCount) || objectCount < 1) {
  fail("OBJECT_COUNT must be a positive integer");
}
if (!Number.isFinite(fps) || fps <= 0) {
  fail("EXTERNAL_FPS must be greater than zero");
}

export const options = {
  discardResponseBodies: true,
  scenarios: {
    external_sources: {
      executor: "constant-vus",
      vus: sourceCount,
      duration,
    },
  },
};

const sourceId = `${sourcePrefix}${__VU}`;
const topic = `scenescape/external/${sourceId}/person`;
const clientId = `k6-${sourceId}`;
const publisher = new mqtt.Client(
  [host + ":" + port],
  "",
  "",
  false,
  clientId,
  100,
  "",
  "",
  "",
);

try {
  publisher.connect();
} catch (error) {
  fail(`fatal: could not connect to MQTT broker: ${error}`);
}

const columns = Math.ceil(Math.sqrt(objectCount));
const objects = [];
for (let index = 0; index < objectCount; index++) {
  objects.push({
    id: `${sourceId}-person-${index}`,
    category: "person",
    translation: [(index % columns) * 3, Math.floor(index / columns) * 3, 0],
    rotation: [0, 0, 0, 1],
    size: [0.4, 0.4, 1.7],
    confidence: 0.98,
  });
}

const message = {
  source_id: sourceId,
  pose: {
    reference_frame: "scene",
    translation: [__VU * 100, 0, 0],
    rotation: [0, 0, 0, 1],
  },
  objects,
};

export default function () {
  const iterationStart = Date.now();
  message.timestamp = new Date().toISOString();

  try {
    publisher.publish(topic, 1, JSON.stringify(message), false, 100);
  } catch (error) {
    fail(`fatal: could not publish external-source message: ${error}`);
  }

  const remaining = 1 / fps - (Date.now() - iterationStart) / 1000;
  if (remaining > 0) {
    sleep(remaining);
  }
}

export function teardown() {
  publisher.close(100);
}
