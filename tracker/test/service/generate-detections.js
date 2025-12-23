/*

This is a k6 test script that simulates SceneScape detection messages over MQTT.

Simple movement simulation for 1200x1140 pixel map with basic movement patterns.

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
// camera id
const cameraIdPrefix = getRequiredEnv("CAMERA_ID_PREFIX");
const cameraId = `${cameraIdPrefix}${__VU}`;

// SSL/TLS configuration - only required for secure connections
const isSecure = host.startsWith("ssl://") || host.startsWith("mqtts://") || host.startsWith("wss://");
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
            executor: 'constant-vus',
            vus: cameraCount,
            duration: testDuration,
        },
    },
};


import { fail, sleep } from 'k6';
import http from 'k6/http';
import exec from 'k6/execution';
import mqtt from 'k6/x/mqtt';
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
    clientCertKeyPath
);

// connect to the mqtt broker
try {
    publisher.connect()
}
catch (error) {
    fail(`fatal could not connect to broker for publish ${error}`);
}

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
    let t = this.state += 0x6D2B79F5;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    const result = ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    return result;
  }

  // Optional: reset the generator to a new seed
  reseed(newSeed) {
    this.state = newSeed >>> 0;
  }
}

// Simple movement patterns for 1200x1140 map
function initializePersonMovement(personId, startTime) {
    const patterns = [
        // Left to right
        { startX: 100, endX: 1100, startY: 400, endY: 400, duration: 6.0 },
        // Top to bottom
        { startX: 600, endX: 600, startY: 100, endY: 1000, duration: 5.0 },
        // Diagonal
        { startX: 200, endX: 1000, startY: 200, endY: 900, duration: 7.0 }
    ];
    
    const pattern = patterns[personId % patterns.length];
    // we get deterministic randomness per personId
    const rng = new SeededRandom(personId);

    return {
        personId: personId,
        startTime: startTime,
        startX: pattern.startX + (rng.next() - 0.5) * 50,
        startY: pattern.startY + (rng.next() - 0.5) * 50,
        endX: pattern.endX + (rng.next() - 0.5) * 50,
        endY: pattern.endY + (rng.next() - 0.5) * 50,
        duration: pattern.duration + (rng.next() - 0.5) * 1.0,
        width: 65,  // Fixed width
        height: 90, // Fixed height
        confidence: 0.98,
        currentX: 0,
        currentY: 0
    };
}

// Simple position calculation based on time elapsed
function updatePersonPosition(movementState, currentTime) {
    const elapsed = (currentTime - movementState.startTime) / 1000;
    const progress = Math.min(elapsed / movementState.duration, 1.0);
    
    // Simple linear interpolation
    movementState.currentX = Math.round(
        movementState.startX + (movementState.endX - movementState.startX) * progress
    );
    movementState.currentY = Math.round(
        movementState.startY + (movementState.endY - movementState.startY) * progress
    );
    
    // Reset if completed
    if (progress >= 1.0) {
        const newState = initializePersonMovement(movementState.personId, currentTime);
        Object.assign(movementState, newState);
    }
}

// Precompute base message structure with realistic person objects
function createBaseMessage(objectCount) {
    const objectArray = [];
    const startTime = Date.now();

    // Initialize movement states for all persons
    for (let i = 0; i < objectCount; i++) {
        const movementState = initializePersonMovement(i, startTime + i * 500); // Stagger start times
        personMovementState.push(movementState);
        
        objectArray.push({
            "category": "person",
            "confidence": movementState.confidence,
            "center_of_mass": {
                "x": 0,
                "y": 0,
                "width": 65,
                "height": 90
            },
            "bounding_box_px": {
                "x": 0,
                "y": 0,
                "width": 195,
                "height": 360
            }, 
            "id": i + 1
        });
    }

    return {
        "id": cameraId,
        "debug_mac": "ed:b4:87:49:01:e0",
        "timestamp": "", // Will be updated each iteration
        "debug_timestamp_end": "", // Will be updated each iteration
        "debug_processing_time": Math.random() * 0.05 + 0.02, // Variable processing time
        "rate": fps, 
        "objects": {
            "person": objectArray
        }
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
        
        // Update center of mass
        person.center_of_mass.x = movementState.currentX;
        person.center_of_mass.y = movementState.currentY;
        person.center_of_mass.width = movementState.width;
        person.center_of_mass.height = movementState.height;
        
        // Update bounding box (fixed size)
        const bboxWidth = 195;  // Fixed bounding box width
        const bboxHeight = 360; // Fixed bounding box height
        
        person.bounding_box_px.x = movementState.currentX - bboxWidth/2;
        person.bounding_box_px.y = movementState.currentY - bboxHeight/2;
        person.bounding_box_px.width = bboxWidth;
        person.bounding_box_px.height = bboxHeight;
        
        // Fixed confidence
        person.confidence = movementState.confidence;
    });
}

// Precompute the base message structure once
let baseMessage = createBaseMessage(objectCount);

export default function () {    
    // Update positions on every iteration for smooth movement tracking
    updatePositions(baseMessage);
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
    // throttle each VU to `fps` messages per second
    sleep(1 / fps);
}

export function teardown() {    
    publisher.close(mqttTimeoutMs);
}
