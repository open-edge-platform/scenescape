# MQTT Payload Encoding Performance Analysis

Performance comparison of current vs proposed SceneScape pipeline architecture.

**Current:** DL Streamer → Controller (Python monolith)  
**Proposed:** DL Streamer (Python) → Tracker (C++) → Analytics (Python)

## Summary

Migrating to Protobuf + C++ Tracker reduces serialization time from **1,171μs** to **412μs** per frame (**2.8x faster**).

## Current Architecture

**Technology:**
- Language: Python
- Encoding: JSON
- Process: Single (Controller = Tracker + Analytics)

**Performance (1000 objects/frame):**

| Stage | Message | Operation | Time (μs) |
|-------|---------|-----------|-----------|
| DLS | Detection | Serialize | 148 |
| Controller | Detection | Deserialize | 408 |
| Controller | Regulated | Serialize | 615 |
| **Total** | | | **1,171** |

*Regulated message stays in-process, no deserialization needed*

## Proposed Architecture

**Technology:**
- Language: Python (DLS, Analytics), C++ (Tracker)
- Encoding: Protobuf
- Process: Split (Tracker and Analytics separate)

**Performance (1000 objects/frame):**

| Stage | Message | Operation | Time (μs) | Speedup |
|-------|---------|-----------|-----------|---------|
| DLS | Detection | Serialize | 43 | 3.4x |
| Tracker | Detection | Deserialize | 113 | 3.6x |
| Tracker | Regulated | Serialize | 112 | 5.5x |
| Analytics | Regulated | Deserialize | 144 | - |
| **Total** | | | **412** | **2.8x** |
