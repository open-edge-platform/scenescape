# MQTT Payload Encoding Performance Analysis

Performance comparison of current vs proposed SceneScape pipeline architecture.

**Current:** DL Streamer → MQTT → Controller (Python monolith)  
**Proposed:** DL Streamer → MQTT → Tracker (C++) → MQTT → Analytics

## Summary

**Performance improvements (1000 objects/frame):**
- **Phase 1 - Split architecture with JSON:** 1,370μs → 1,290μs per frame (**6% faster than current**)
- **Phase 2 - Migrate to Protobuf:** 1,290μs → 733μs per frame (**43% faster than Phase 1**, **87% faster than current**)

**Note:** Results based on localhost deployment. Network deployments (LAN/WAN) experience additional transfer delays where Protobuf's smaller message sizes become more critical.

## Current Architecture (Python + JSON)

**Technology:**
- Language: Python
- Encoding: JSON
- Process: DLS → MQTT → Controller (monolith = Tracker + Analytics)

**Performance (1000 objects/frame, localhost):**

| Stage | Message | Operation | Time (μs) |
|-------|---------|-----------|-----------|
| DLS | Detection | Serialize | 152 |
| DLS → Controller | Detection | MQTT Transfer | 152 |
| Controller | Detection | Deserialize | 416 |
| Controller | Regulated | Serialize | 650 |
| **Total** | | | **1,370** |

**Message sizes:**
- Detection JSON: ~100KB (MQTT transfer: 152μs)

*Regulated message stays in-process within Controller, no MQTT transfer needed*

## Phase 1: Split Architecture with JSON

**Technology:**
- Language: Python (DLS, Analytics), C++ (Tracker)
- Encoding: JSON (same as current)
- Process: DLS → MQTT → Tracker (C++) → MQTT → Analytics

**Performance (1000 objects/frame):**

**Localhost:**

| Stage | Message | Operation | Time (μs) | Speedup vs Current |
|-------|---------|-----------|-----------|-------------------|
| DLS | Detection | Serialize | 152 | - |
| DLS → Tracker | Detection | MQTT Transfer | 152 | - |
| Tracker | Detection | Deserialize | 111 | **73% faster** |
| Tracker | Regulated | Serialize | 305 | **113% faster** |
| Tracker → Analytics | Regulated | MQTT Transfer | 335 | - |
| Analytics | Regulated | Deserialize | 235 | - |
| **Total** | | | **1,290** | **6% faster** |

**Message sizes:**
- Detection JSON: ~100KB (MQTT transfer: 152μs)
- Regulated JSON: ~250KB (MQTT transfer: 335μs)

**Benefits:**
- Simplifies initial migration - no protobuf schema changes needed
- Validates architecture split independently
- C++ processing provides modest performance improvement (6%)
- Provides foundation for Phase 2 protobuf migration

## Phase 2: Migrate to Protobuf

**Technology:**
- Language: Python (DLS, Analytics), C++ (Tracker)
- Encoding: Protocol Buffers
- Process: DLS → MQTT → Tracker (C++) → MQTT → Analytics

**Performance (1000 objects/frame, localhost):**

| Stage | Message | Operation | Time (μs) | Speedup vs Current | Speedup vs Phase 1 |
|-------|---------|-----------|-----------|-------------------|-----------------|
| DLS | Detection | Serialize | 43 | **253% faster** | **253% faster** |
| DLS → Tracker | Detection | MQTT Transfer | 87 | **75% faster** | **43% faster** |
| Tracker | Detection | Deserialize | 115 | **262% faster** | 3% slower |
| Tracker | Regulated | Serialize | 112 | **480% faster** | **172% faster** |
| Tracker → Analytics | Regulated | MQTT Transfer | 228 | - | **47% faster** |
| Analytics | Regulated | Deserialize | 148 | - | **59% faster** |
| **Total** | | | **733** | **87% faster** | **43% faster** |

**Message sizes:**
- Detection Protobuf: ~37KB, 63% smaller than JSON (MQTT transfer: 87μs)
- Regulated Protobuf: ~178KB, 29% smaller than JSON (MQTT transfer: 228μs)

**Benefits:**
- Dramatic performance improvement (43% over Phase 1, 87% overall)
- Smaller messages reduce MQTT broker load and network bandwidth
- Essential for network deployments where transfer delays dominate

## Recommended Phased Approach

**Phase 1: Split Architecture with JSON**
- Separate Tracker (C++) from Analytics while maintaining JSON compatibility
- 6% performance improvement on localhost
- Simpler migration - no schema changes needed
- Validates architecture split independently

**Phase 2: Migrate to Protobuf**
- Replace JSON with Protocol Buffers across pipeline
- Additional 43% improvement (87% total vs current)
- Smaller messages (29-63% reduction) reduce MQTT broker load
- Critical for network deployments where transfer delays dominate

## MQTT Overhead Model (Localhost)

**Localhost (loopback):** 50μs base + 1μs/KB (~1GB/s effective throughput)

**⚠️ Important:** This is a theoretical estimate based on localhost measurements. Actual MQTT overhead depends on broker implementation, system call overhead, and message processing. Network deployments will show significantly higher latency due to TCP/IP overhead and network delays.
