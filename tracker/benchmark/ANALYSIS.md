# MQTT Payload Encoding Performance Analysis

Performance comparison of current vs proposed SceneScape pipeline architecture.

**Current:** DL Streamer → Controller (Python monolith)  
**Proposed:** DL Streamer (Python) → Tracker (C++) → Analytics (Python)

## Summary

- **Architecture change only (keeping JSON):** 1,218μs → 766μs per frame (**1.6x faster**)
- **Full migration (C++ Tracker + Protobuf):** 1,218μs → 418μs per frame (**2.9x faster**)

## Current Architecture

**Technology:**
- Language: Python
- Encoding: JSON
- Process: Single (Controller = Tracker + Analytics)

**Performance (1000 objects/frame):**

| Stage | Message | Operation | Time (μs) |
|-------|---------|-----------|-----------||
| DLS | Detection | Serialize | 152 |
| Controller | Detection | Deserialize | 416 |
| Controller | Regulated | Serialize | 650 |
| **Total** | | | **1,218** |

*Regulated message stays in-process, no deserialization needed*

## Proposed Architecture Option 1: C++ Tracker with JSON (No Encoding Change)

**Technology:**
- Language: Python (DLS, Analytics), C++ (Tracker)
- Encoding: **JSON** (same as current)
- Process: Split (Tracker and Analytics separate)

**Performance (1000 objects/frame):**

| Stage | Message | Operation | Time (μs) | Speedup vs Current |
|-------|---------|-----------|-----------|-------------------|
| DLS | Detection | Serialize | 152 | 1.0x |
| Tracker | Detection | Deserialize | 111 | **3.7x faster** |
| Tracker | Regulated | Serialize | 305 | **2.1x faster** |
| Analytics | Regulated | Deserialize | 235 | - |
| **Total** | | | **803** | **1.5x faster** |

**Key Insight:** C++ Tracker alone (without changing encoding) provides **1.5x speedup** due to:
- simdjson deserialization: 111μs vs 416μs Python (3.7x faster)
- RapidJSON serialization: 305μs vs 650μs Python (2.1x faster)

## Proposed Architecture Option 2: C++ Tracker with Protobuf

**Technology:**
- Language: Python (DLS, Analytics), C++ (Tracker)
- Encoding: **Protocol Buffers**
- Process: Split (Tracker and Analytics separate)

**Performance (1000 objects/frame):**

| Stage | Message | Operation | Time (μs) | Speedup vs Current | Speedup vs JSON |
|-------|---------|-----------|-----------|-------------------|-----------------|
| DLS | Detection | Serialize | 43 | **3.5x faster** | **3.5x faster** |
| Tracker | Detection | Deserialize | 115 | **3.6x faster** | 0.97x slower |
| Tracker | Regulated | Serialize | 112 | **5.8x faster** | **2.7x faster** |
| Analytics | Regulated | Deserialize | 148 | - | **1.6x faster** |
| **Total** | | | **418** | **2.9x faster** | **1.9x faster** |

**Key Insight:** Adding Protobuf on top of C++ Tracker provides another **1.9x speedup** (803μs → 418μs)

## Migration Path Recommendation

**Phased Approach:**
1. **Phase 1:** Deploy C++ Tracker with JSON (452μs saved, 37% improvement, lower risk)
2. **Phase 2:** Switch to Protobuf after validation (385μs additional savings, 48% more improvement)

**Benefits of phased approach:**
- Minimizes risk by keeping JSON human-readable during initial migration
- Captures 37% of total performance gain immediately
- Allows validation of C++ Tracker behavior before encoding changes
- Easier debugging and troubleshooting during migration
