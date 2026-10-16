// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/*

This is a k6 test script that simulates Scenescape detection messages over MQTT.

Grid-based placement across a 1280x720 pixel frame.  Objects are arranged on a
grid sized to NUM_OBJECTS so that every pair is well-separated in world space
(>> 2 m at the configured camera height of 50 m).

Environment configuration (all set via k6 --env or OS environment):

  Required:
    OBJECT_COUNT          Number of detected objects per camera per frame
    CAMERA_FPS            Frames per second each simulated camera publishes
    MQTT_HOST             MQTT broker address (e.g. "ssl://broker" or "tcp://broker")
    MQTT_PORT             MQTT broker port (e.g. 8883 for TLS, 1883 for plain)
    CAMERA_COUNT          Number of simulated cameras (maps to k6 VUs)
    DEFAULT_TEST_DURATION k6 test duration string (e.g. "30s", "5m")
    CAMERA_ID_PREFIX      Prefix for camera IDs; each VU becomes {prefix}{VU}
    LOAD_MODE             Detection geometry: 2d (default), 3d, or mixed
    MIXED_3D_RATIO        Fraction of detections using 3D geometry in mixed mode

  Required when MQTT_HOST starts with ssl://, mqtts://, or wss://:
    CA_ROOT               Path to CA root certificate
    CLIENT_CERT_PATH      Path to client certificate
    CLIENT_KEY_PATH       Path to client private key

*/

// Helper function to get required environment variables
function getRequiredEnv(varName, friendlyName = varName) {
  if (!__ENV[varName]) {
    fail(`${friendlyName} environment variable is required`);
  }
  return __ENV[varName];
}

// test configuration
const objectCount = getRequiredEnv("OBJECT_COUNT");
const fps = getRequiredEnv("CAMERA_FPS");
const host = getRequiredEnv("MQTT_HOST");
const port = getRequiredEnv("MQTT_PORT");
const cameraCount = getRequiredEnv("CAMERA_COUNT");
const testDuration = getRequiredEnv("DEFAULT_TEST_DURATION");
const loadMode = __ENV.LOAD_MODE || "2d";
const mixed3dRatio = Number(__ENV.MIXED_3D_RATIO || "0.5");
if (!["2d", "3d", "mixed"].includes(loadMode)) {
  fail(`LOAD_MODE must be one of 2d, 3d, or mixed; got ${loadMode}`);
}
if (!Number.isFinite(mixed3dRatio) || mixed3dRatio < 0 || mixed3dRatio > 1) {
  fail(`MIXED_3D_RATIO must be between 0 and 1; got ${__ENV.MIXED_3D_RATIO}`);
}
// camera id
const cameraIdPrefix = getRequiredEnv("CAMERA_ID_PREFIX");
const cameraId = `${cameraIdPrefix}${__VU}`;

// SSL/TLS configuration - only required for secure connections
const isSecure =
  host.startsWith("ssl://") ||
  host.startsWith("mqtts://") ||
  host.startsWith("wss://");
const caRoot = isSecure ? getRequiredEnv("CA_ROOT") : "";
const clientCertPath = isSecure ? getRequiredEnv("CLIENT_CERT_PATH") : "";
const clientCertKeyPath = isSecure ? getRequiredEnv("CLIENT_KEY_PATH") : "";

// scene topic

const sceneTopic = `scenescape/data/camera/${cameraId}`;
// Connect IDs one connection per VU
const k6PubId = `k6-pub-${__VU}`;

// k6 scenario options
export const options = {
  discardResponseBodies: true,
  scenarios: {
    cameras: {
      executor: "constant-vus",
      vus: cameraCount,
      duration: testDuration,
    },
  },
};

import { fail, sleep } from "k6";
import mqtt from "k6/x/mqtt";
// create publisher client
const mqttTimeoutMs = 100;
const cleanSession = false;
const publisher = new mqtt.Client(
  [host + ":" + port],
  "",
  "",
  cleanSession,
  k6PubId,
  mqttTimeoutMs,
  caRoot,
  clientCertPath,
  clientCertKeyPath,
);

// connect to the mqtt broker
try {
  publisher.connect();
} catch (error) {
  fail(`fatal could not connect to broker for publish ${error}`);
}

// ---------------------------------------------------------------------------
// Frame geometry — objects are placed on a grid inside this pixel area.
// The camera in scenes.json is at 50 m height with f=905, giving ~5.5 cm/px.
// A grid cell of ~36 px already exceeds the 2.0 m tracking threshold.
// ---------------------------------------------------------------------------
const FRAME_W = 1280;
const FRAME_H = 720;
const MARGIN = 40; // px margin from frame edges
const CAMERA_FX = 905;
const CAMERA_FY = 905;
const CAMERA_CX = FRAME_W / 2;
const CAMERA_CY = FRAME_H / 2;
const CAMERA_HEIGHT_M = 50;
const BBOX_WIDTH_PX = 195;
const BBOX_HEIGHT_PX = 360;
const IDENTITY_ROTATION = [0, 0, 0, 1];

// Movement state for each person object
const personMovementState = [];

// Simple seeded random number generator (Mulberry32)
class SeededRandom {
  constructor(seed) {
    // Ensure seed is a 32-bit unsigned integer
    this.state = seed >>> 0;
  }

  // Mulberry32 generator step
  next() {
    let t = (this.state += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    const result = ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    return result;
  }
}

// Compute grid dimensions for objectCount objects inside the usable area.
const usableW = FRAME_W - 2 * MARGIN;
const usableH = FRAME_H - 2 * MARGIN;
const gridCols = Math.ceil(Math.sqrt(objectCount));
const gridRows = Math.ceil(objectCount / gridCols);
const cellW = usableW / gridCols;
const cellH = usableH / gridRows;

// Maximum random jitter (px) within a cell — kept small so objects never
// drift into a neighbour's cell.  At 50 m camera height 5 px ≈ 0.28 m.
const JITTER = Math.min(5, cellW / 4, cellH / 4);

// Initialize one object anchored to its grid cell.
function initializePersonMovement(personId, startTime) {
  const col = personId % gridCols;
  const row = Math.floor(personId / gridCols);
  const centerX = MARGIN + (col + 0.5) * cellW;
  const centerY = MARGIN + (row + 0.5) * cellH;

  const rng = new SeededRandom(personId);

  // Start and end positions: small random offsets within the cell
  const startX = centerX + (rng.next() - 0.5) * JITTER * 2;
  const startY = centerY + (rng.next() - 0.5) * JITTER * 2;
  const endX = centerX + (rng.next() - 0.5) * JITTER * 2;
  const endY = centerY + (rng.next() - 0.5) * JITTER * 2;

  return {
    personId: personId,
    startTime: startTime,
    startX: startX,
    startY: startY,
    endX: endX,
    endY: endY,
    duration: 4.0 + rng.next() * 4.0, // 4–8 s
    width: 65,
    height: 90,
    confidence: 0.98,
    currentX: Math.round(startX),
    currentY: Math.round(startY),
  };
}

// Linear interpolation; resets to a new path when complete.
function updatePersonPosition(movementState, currentTime) {
  const elapsed = (currentTime - movementState.startTime) / 1000;
  const progress = Math.min(elapsed / movementState.duration, 1.0);

  movementState.currentX = Math.round(
    movementState.startX +
      (movementState.endX - movementState.startX) * progress,
  );
  movementState.currentY = Math.round(
    movementState.startY +
      (movementState.endY - movementState.startY) * progress,
  );

  if (progress >= 1.0) {
    const newState = initializePersonMovement(
      movementState.personId,
      currentTime,
    );
    Object.assign(movementState, newState);
  }
}

function uses3dGeometry(personId) {
  if (loadMode === "3d") {
    return true;
  }
  if (loadMode !== "mixed") {
    return false;
  }
  return personId % 100 < mixed3dRatio * 100;
}

function makeBoundingBox(movementState) {
  return {
    x: movementState.currentX - BBOX_WIDTH_PX / 2,
    y: movementState.currentY - BBOX_HEIGHT_PX / 2,
    width: BBOX_WIDTH_PX,
    height: BBOX_HEIGHT_PX,
  };
}

function pixelToGround(pixelX, pixelY) {
  // Load-test cameras use [0, 0, 50] translation and [-180, 0, 0] rotation.
  return {
    x: ((pixelX - CAMERA_CX) * CAMERA_HEIGHT_M) / CAMERA_FX,
    y: (-(pixelY - CAMERA_CY) * CAMERA_HEIGHT_M) / CAMERA_FY,
  };
}

function sensorMeasurementForBoundingBox(bbox) {
  const foot = pixelToGround(bbox.x + bbox.width / 2, bbox.y + bbox.height);
  const bottomLeft = pixelToGround(bbox.x, bbox.y + bbox.height);
  const bottomRight = pixelToGround(bbox.x + bbox.width, bbox.y + bbox.height);
  const topLeft = pixelToGround(bbox.x, bbox.y);

  const width = Math.hypot(
    bottomRight.x - bottomLeft.x,
    bottomRight.y - bottomLeft.y,
  );
  const cameraToTopLeft = Math.hypot(topLeft.x, topLeft.y, CAMERA_HEIGHT_M);
  const topToBottom = Math.hypot(
    topLeft.x - bottomLeft.x,
    topLeft.y - bottomLeft.y,
  );
  const elevation = Math.atan2(CAMERA_HEIGHT_M, cameraToTopLeft);
  const height = Math.sin(elevation) * topToBottom;

  // Match the bbox path's footprint-center offset before converting world XY
  // to sensor XY.  With this scene pose, world XY = [sensor X, -sensor Y].
  const bearing = Math.hypot(foot.x, foot.y);
  const offset = bearing > 1e-9 ? width / 2 : 0;
  const worldX = foot.x + (bearing > 1e-9 ? (foot.x / bearing) * offset : 0);
  const worldY = foot.y + (bearing > 1e-9 ? (foot.y / bearing) * offset : 0);

  return {
    translation: [worldX, -worldY, CAMERA_HEIGHT_M],
    size: [width, width, height],
    rotation: IDENTITY_ROTATION,
  };
}

function detectionGeometryForMovement(movementState, use3d) {
  const bbox = makeBoundingBox(movementState);
  return use3d
    ? sensorMeasurementForBoundingBox(bbox)
    : { bounding_box_px: bbox };
}

function createDetection(personId, movementState) {
  return {
    category: "person",
    confidence: movementState.confidence,
    id: personId + 1,
    ...detectionGeometryForMovement(movementState, uses3dGeometry(personId)),
  };
}

function updateDetectionGeometry(detection, movementState) {
  const use3d = Object.prototype.hasOwnProperty.call(detection, "translation");
  Object.assign(detection, detectionGeometryForMovement(movementState, use3d));
}

// Precompute base message structure with realistic person objects
function createBaseMessage(objectCount) {
  const objectArray = [];
  const startTime = Date.now();

  // Initialize movement states for all persons
  for (let i = 0; i < objectCount; i++) {
    const movementState = initializePersonMovement(i, startTime + i * 500); // Stagger start times
    personMovementState.push(movementState);
    objectArray.push(createDetection(i, movementState));
  }

  return {
    id: cameraId,
    debug_mac: "ed:b4:87:49:01:e0",
    timestamp: "", // Will be updated each iteration
    debug_timestamp_end: "", // Will be updated each iteration
    debug_processing_time: Math.random() * 0.05 + 0.02, // Variable processing time
    rate: fps,
    objects: {
      person: objectArray,
    },
  };
}

// Function to update only timestamps in the message
function updateTimestamps(baseMessage) {
  const now = new Date();
  baseMessage.timestamp = now.toISOString();
  baseMessage.debug_timestamp_end = new Date(now.getTime() + 25).toISOString();
}

// Function to update positions using realistic movement patterns
function updatePositions(baseMessage) {
  const currentTime = Date.now();

  baseMessage.objects.person.forEach((person, index) => {
    const movementState = personMovementState[index];

    // Update person's position based on movement pattern
    updatePersonPosition(movementState, currentTime);

    updateDetectionGeometry(person, movementState);

    // Fixed confidence
    person.confidence = movementState.confidence;
  });
}

// Precompute the base message structure once
let baseMessage = createBaseMessage(objectCount);

export default function () {
  const iterStart = Date.now();

  // Update positions only every 10th iteration
  if (__ITER % 10 === 0) {
    updatePositions(baseMessage);
  }
  updateTimestamps(baseMessage);

  const k6Message = JSON.stringify(baseMessage);

  // publish the message to the topic
  const qos = 1;
  const retainPolicy = false;
  try {
    publisher.publish(sceneTopic, qos, k6Message, retainPolicy, mqttTimeoutMs);
  } catch (error) {
    fail(`fatal could not publish message ${error}`);
  }

  // Compensate for work + ACK time so each VU sustains exactly `fps` msg/s
  const elapsedSec = (Date.now() - iterStart) / 1000;
  const remaining = 1 / fps - elapsedSec;
  if (remaining > 0) {
    sleep(remaining);
  }
}

export function teardown() {
  publisher.close(mqttTimeoutMs);
}
