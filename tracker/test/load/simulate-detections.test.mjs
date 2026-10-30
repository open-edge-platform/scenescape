// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createContext, SourceTextModule, SyntheticModule } from "node:vm";

const source = await readFile(
  new URL("./simulate-detections.js", import.meta.url),
  "utf8",
);

async function generate(overrides = {}, camera = 1) {
  let message;
  const context = createContext({
    __ENV: {
      OBJECT_COUNT: "4",
      CAMERA_FPS: "15",
      MQTT_HOST: "tcp://broker",
      MQTT_PORT: "1883",
      CAMERA_COUNT: "4",
      DEFAULT_TEST_DURATION: "1m",
      CAMERA_ID_PREFIX: "camera-",
      ...overrides,
    },
    __VU: camera,
    __ITER: 0,
  });
  const mocks = {
    k6: {
      fail: (message) => {
        throw new Error(message);
      },
      sleep: () => {},
    },
    "k6/x/mqtt": {
      default: {
        Client: class {
          connect() {}
          publish(_topic, _qos, payload) {
            message = JSON.parse(payload);
          }
          close() {}
        },
      },
    },
    "k6/encoding": {
      default: {
        b64encode: (bytes) => Buffer.from(bytes).toString("base64"),
      },
    },
  };
  const module = new SourceTextModule(source, { context });
  await module.link((specifier) => {
    const mock = mocks[specifier];
    assert.ok(mock, `Unexpected import: ${specifier}`);
    return new SyntheticModule(
      Object.keys(mock),
      function () {
        for (const [name, value] of Object.entries(mock)) {
          this.setExport(name, value);
        }
      },
      { context },
    );
  });
  await module.evaluate();
  module.namespace.default();
  module.namespace.teardown();
  return message;
}

test("default workload has no metadata or embeddings", async () => {
  const message = await generate();
  assert.equal(message.objects.person.length, 4);
  for (const person of message.objects.person) {
    assert.equal(person.metadata, undefined);
  }
});

for (const dimensions of [256, 512]) {
  test(`base64 preserves ${dimensions} deterministic float32 dimensions`, async () => {
    const config = {
      REID_EMBEDDING_DIMENSIONS: String(dimensions),
      EXTRA_METADATA: "age_gender",
    };
    const floats = await generate(config);
    const encoded = await generate({
      ...config,
      REID_EMBEDDING_ENCODING: "base64",
    });
    const otherCamera = await generate(
      { ...config, REID_EMBEDDING_ENCODING: "base64" },
      2,
    );
    for (let i = 0; i < floats.objects.person.length; i++) {
      const expected = floats.objects.person[i].metadata;
      const actual = encoded.objects.person[i].metadata;
      const bytes = Buffer.from(actual.reid.embedding_vector, "base64");
      assert.equal(bytes.length, dimensions * 4);
      assert.equal(actual.reid.embedding_dimensions, dimensions);
      assert.equal(actual.reid.model_name, "load-test");
      assert.deepEqual(actual.age, expected.age);
      assert.deepEqual(actual.gender, expected.gender);
      assert.equal(
        actual.reid.embedding_vector,
        otherCamera.objects.person[i].metadata.reid.embedding_vector,
      );
      let norm = 0;
      for (let dimension = 0; dimension < dimensions; dimension++) {
        const value = bytes.readFloatLE(dimension * 4);
        assert.equal(
          value,
          Math.fround(expected.reid.embedding_vector[0][dimension]),
        );
        norm += value * value;
      }
      assert.ok(Math.abs(norm - 1) < 1e-6);
    }
    assert.notEqual(
      encoded.objects.person[0].metadata.reid.embedding_vector,
      encoded.objects.person[1].metadata.reid.embedding_vector,
    );
    assert.ok(JSON.stringify(encoded).length < JSON.stringify(floats).length);
  });
}

test("semantic metadata is independent of embeddings and geometry", async () => {
  for (const mode of ["2d", "3d", "mixed"]) {
    const message = await generate({
      LOAD_MODE: mode,
      MIXED_3D_RATIO: "0.02",
      EXTRA_METADATA: "age_gender",
    });
    for (const person of message.objects.person) {
      assert.ok(person.metadata.age);
      assert.ok(person.metadata.gender);
      assert.equal(person.metadata.reid, undefined);
    }
  }
});

test("mixed geometry adds embeddings only to pixel detections", async () => {
  const message = await generate({
    LOAD_MODE: "mixed",
    MIXED_3D_RATIO: "0.02",
    REID_EMBEDDING_DIMENSIONS: "512",
    REID_EMBEDDING_ENCODING: "base64",
  });
  assert.ok(message.objects.person.some((person) => person.translation));
  assert.ok(message.objects.person.some((person) => person.bounding_box_px));
  for (const person of message.objects.person) {
    assert.equal(
      Boolean(person.metadata?.reid),
      Boolean(person.bounding_box_px),
    );
  }
});

test("invalid encoding, metadata profile, and dimensions fail explicitly", async () => {
  for (const overrides of [
    { REID_EMBEDDING_ENCODING: "unsupported" },
    { EXTRA_METADATA: "unsupported" },
    { REID_EMBEDDING_DIMENSIONS: "-1" },
    { REID_EMBEDDING_DIMENSIONS: "1.5" },
    { REID_EMBEDDING_DIMENSIONS: "4097" },
  ]) {
    await assert.rejects(generate(overrides), /must be/);
  }
});
