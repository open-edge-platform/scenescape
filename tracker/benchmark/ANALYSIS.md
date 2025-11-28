# MQTT Payload Encoding Performance Analysis

Performance comparison of current vs proposed SceneScape pipeline architecture.

**Current:** DL Streamer → MQTT → Controller (Python monolith)  
**Proposed:** DL Streamer → MQTT → Tracker (C++) → MQTT → Analytics

> **⚠️ Disclaimer:** MQTT transfer times are estimated using theoretical models (localhost: 50μs base + 1μs/KB; LAN: 50μs base + 2.3μs/KB). These values have not been empirically validated through actual MQTT benchmarks. The overall performance improvements shown should be considered approximations pending real-world MQTT latency measurements.

## Summary

**Localhost deployment:**
- **Controller split only (keeping JSON):** 1,370μs → 1,290μs per frame (**6% faster**)
- **Controller split with protobuf migration:** 1,370μs → 733μs per frame (**87% faster**)

**LAN deployment (1Gb Ethernet):**
- **Controller split only (keeping JSON):** 1,498μs → 1,708μs per frame (**14% slower** - degrades performance!)
- **Controller split with protobuf migration:** 1,498μs → 1,012μs per frame (**48% faster**)

## Current Architecture (Python + JSON)

**Technology:**
- Language: Python
- Encoding: JSON
- Process: DLS → MQTT → Controller (monolith = Tracker + Analytics)

**Performance (1000 objects/frame):**

**Localhost:**

| Stage | Message | Operation | Time (μs) |
|-------|---------|-----------|-----------|
| DLS | Detection | Serialize | 152 |
| DLS → Controller | Detection | MQTT Transfer | 152 |
| Controller | Detection | Deserialize | 416 |
| Controller | Regulated | Serialize | 650 |
| **Total** | | | **1,370** |

**LAN (1Gb Ethernet):**

| Stage | Message | Operation | Time (μs) |
|-------|---------|-----------|-----------|
| DLS | Detection | Serialize | 152 |
| DLS → Controller | Detection | MQTT Transfer | 280 |
| Controller | Detection | Deserialize | 416 |
| Controller | Regulated | Serialize | 650 |
| **Total** | | | **1,498** |

*Regulated message stays in-process within Controller, no MQTT transfer needed*

## Proposed Architecture Option 1: Split Architecture with JSON

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

**LAN (1Gb Ethernet):**

| Stage | Message | Operation | Time (μs) | Speedup vs Current |
|-------|---------|-----------|-----------|-------------------|
| DLS | Detection | Serialize | 152 | - |
| DLS → Tracker | Detection | MQTT Transfer | 280 | - |
| Tracker | Detection | Deserialize | 111 | **73% faster** |
| Tracker | Regulated | Serialize | 305 | **113% faster** |
| Tracker → Analytics | Regulated | MQTT Transfer | 625 | - |
| Analytics | Regulated | Deserialize | 235 | - |
| **Total** | | | **1,708** | **14% slower** |

**Message sizes:**
- Detection JSON: ~100KB
  - Localhost MQTT: 152μs
  - LAN MQTT: 280μs
- Regulated JSON: ~250KB
  - Localhost MQTT: 335μs
  - LAN MQTT: 625μs ← **Network bottleneck on LAN**

## Proposed Architecture Option 2: Split Architecture with Protobuf

**Technology:**
- Language: Python (DLS, Analytics), C++ (Tracker)
- Encoding: Protocol Buffers
- Process: DLS → MQTT → Tracker (C++) → MQTT → Analytics

**Performance (1000 objects/frame):**

**Localhost:**

| Stage | Message | Operation | Time (μs) | Speedup vs Current | Speedup vs JSON |
|-------|---------|-----------|-----------|-------------------|-----------------|
| DLS | Detection | Serialize | 43 | **253% faster** | **253% faster** |
| DLS → Tracker | Detection | MQTT Transfer | 87 | **75% faster** | **43% faster** |
| Tracker | Detection | Deserialize | 115 | **262% faster** | 3% slower |
| Tracker | Regulated | Serialize | 112 | **480% faster** | **172% faster** |
| Tracker → Analytics | Regulated | MQTT Transfer | 228 | - | **47% faster** |
| Analytics | Regulated | Deserialize | 148 | - | **59% faster** |
| **Total** | | | **733** | **87% faster** | **76% faster** |

**LAN (1Gb Ethernet):**

| Stage | Message | Operation | Time (μs) | Speedup vs Current | Speedup vs JSON |
|-------|---------|-----------|-----------|-------------------|-----------------|
| DLS | Detection | Serialize | 43 | **253% faster** | **253% faster** |
| DLS → Tracker | Detection | MQTT Transfer | 135 | **107% faster** | **52% faster** |
| Tracker | Detection | Deserialize | 115 | **262% faster** | 3% slower |
| Tracker | Regulated | Serialize | 112 | **480% faster** | **172% faster** |
| Tracker → Analytics | Regulated | MQTT Transfer | 459 | - | **36% faster** |
| Analytics | Regulated | Deserialize | 148 | - | **59% faster** |
| **Total** | | | **1,012** | **48% faster** | **69% faster** |

**Message sizes:**
- Detection Protobuf: ~37KB (63% smaller than JSON)
  - Localhost MQTT: 87μs
  - LAN MQTT: 135μs
- Regulated Protobuf: ~178KB (29% smaller than JSON)
  - Localhost MQTT: 228μs
  - LAN MQTT: 459μs

## Key Findings

1. **C++ is 73-480% faster** than Python for serialization/deserialization
2. **Protobuf is 253-480% faster** than JSON for serialization and produces 29-63% smaller messages
3. **Localhost deployment:**
   - JSON-only migration: 6% faster
   - Protobuf migration: 87% faster
4. **LAN deployment (1Gb Ethernet):**
   - JSON-only migration: **14% slower** - network overhead on 250KB regulated message (625μs) overwhelms CPU gains
   - Protobuf migration: 48% faster - smaller payloads (178KB) reduce network bottleneck
5. **Critical finding:** Architecture split with JSON degrades performance on LAN; Protobuf essential for network deployments

## MQTT Overhead Model

**Localhost (loopback):** 50μs base + 1μs/KB (~1GB/s effective throughput)  
**LAN (1Gb Ethernet):** 50μs base + 2.3μs/KB (~430MB/s effective throughput with TCP/IP overhead)

**⚠️ Important:** This is a theoretical estimate. Actual MQTT overhead depends on broker implementation, system call overhead, and message processing. Real measurements may show significantly different latency.
