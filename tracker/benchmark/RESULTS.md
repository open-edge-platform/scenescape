# Benchmark Results

Performance comparison of **JSON, Protocol Buffers, and FlatBuffers** for serializing/deserializing tracker messages with **1000 objects**.

**What we're benchmarking:**
- **Detection Messages:** Real-time object detection data (person category, bounding boxes, confidence scores)
- **Regulated Messages:** 3D scene tracking data (position, velocity, rotation, camera bounds, visibility)
- **Formats tested:** JSON (RapidJSON/simdjson/orjson), Protocol Buffers, FlatBuffers
- **Languages:** C++ and Python implementations

## Summary

**Best Performance by Language:**

**C++:**
- **Serialize:** Protobuf (7-14x faster than JSON)
- **Deserialize:** FlatBuffers (zero-copy, 0.5ns) or simdjson (3.2x faster than RapidJSON)

**Python:**
- **Serialize:** Protobuf (3-5x faster than JSON)
- **Deserialize:** Protobuf (8x faster than JSON)

**General Recommendation:**
- **Protobuf** for production (best cross-language performance)
- **JSON** for debugging/logging (human-readable)
- Avoid FlatBuffers in Python (serialization 102x slower than JSON)

## Test Hardware

- **CPU:** Intel Core Ultra 9 285H (16 cores @ 5.4 GHz max)
- **RAM:** 64 GB
- **OS:** Ubuntu 24.04.3 LTS (Linux 6.14.0-35-generic)
- **Compiler:** g++ with -O3 -march=x86-64-v3 (enables AVX2, BMI2, FMA)

## Libraries Used

**C++:**
- JSON: [RapidJSON](https://github.com/Tencent/rapidjson) (serialize) + [simdjson](https://github.com/simdjson/simdjson) (deserialize)
- Protobuf: [libprotobuf](https://github.com/protocolbuffers/protobuf) (Protocol Buffers v3)
- FlatBuffers: [libflatbuffers](https://github.com/google/flatbuffers)
- Benchmark: [Google Benchmark](https://github.com/google/benchmark)

**Python:**
- JSON: [orjson](https://github.com/ijl/orjson) (fastest Python JSON library)
- Protobuf: [protobuf](https://pypi.org/project/protobuf/) (official Python bindings)
- FlatBuffers: [flatbuffers](https://pypi.org/project/flatbuffers/) (official Python bindings)
- Benchmark: [pytest-benchmark](https://github.com/ionelmc/pytest-benchmark)

## C++ Results (Google Benchmark)

### JSON Library Comparison

**Detection Message (1000 objects):**

| Library    | Operation   | Time (μs) | Speedup |
|------------|-------------|-----------|---------|
| RapidJSON  | Serialize   | 307       | -       |
| RapidJSON  | Deserialize | 351       | -       |
| simdjson   | Deserialize | 111       | **3.2x faster** |

**Regulated Message (1000 objects):**

| Library    | Operation   | Time (μs) | Speedup |
|------------|-------------|-----------|---------|
| RapidJSON  | Serialize   | 832       | -       |
| RapidJSON  | Deserialize | 739       | -       |
| simdjson   | Deserialize | 234       | **3.2x faster** |

### Detection Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------|
| JSON        | Serialize   | 303       | 1.0x    |
| JSON        | Deserialize | 109       | 1.0x    |
| Protobuf    | Serialize   | 22        | **14x faster** |
| Protobuf    | Deserialize | 113       | 1.0x    |
| FlatBuffers | Serialize   | 188       | 1.6x faster |
| FlatBuffers | Deserialize | 0.0005    | **200,000x faster** |

### Regulated Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------|
| JSON        | Serialize   | 772       | 1.0x    |
| JSON        | Deserialize | 231       | 1.0x    |
| Protobuf    | Serialize   | 112       | **7x faster** |
| Protobuf    | Deserialize | 427       | 1.8x slower |
| FlatBuffers | Serialize   | 196       | **4x faster** |
| FlatBuffers | Deserialize | 0.0005    | **460,000x faster** |

## Python Results (pytest-benchmark)

### Detection Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------|
| JSON        | Serialize   | 148       | 1.0x    |
| JSON        | Deserialize | 408       | 1.0x    |
| Protobuf    | Serialize   | 43        | **3.4x faster** |
| Protobuf    | Deserialize | 48        | **8.5x faster** |
| FlatBuffers | Serialize   | 15,074    | 102x slower |
| FlatBuffers | Deserialize | 0.31      | **1,300x faster** |

### Regulated Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------|
| JSON        | Serialize   | 615       | 1.0x    |
| JSON        | Deserialize | 1,126     | 1.0x    |
| Protobuf    | Serialize   | 125       | **4.9x faster** |
| Protobuf    | Deserialize | 144       | **7.8x faster** |
| FlatBuffers | Serialize   | N/A       | (skipped) |
| FlatBuffers | Deserialize | N/A       | (skipped) |

## Key Findings

1. **Protobuf dominates for serialization** in both C++ and Python:
   - C++: 7-14x faster than JSON
   - Python: 3.4-4.9x faster than JSON

2. **FlatBuffers excels at deserialization** with zero-copy access:
   - Constant ~0.5ns regardless of message size
   - Ideal for read-heavy workloads

3. **Python FlatBuffers serialization is slow** (102x slower than JSON):
   - Python API overhead negates C++ benefits
   - Not recommended for Python serialization

4. **JSON performance varies by implementation**:
   - C++ uses RapidJSON (serialize) + simdjson (deserialize)
   - Python uses orjson (fastest JSON library)

5. **Why two different JSON libraries in C++?**
   - **simdjson is 3.2x faster** than RapidJSON for deserialization (Detection: 111μs vs 351μs)
   - **simdjson is 3.2x faster** for complex messages (Regulated: 234μs vs 739μs)
   - simdjson is parse-only (cannot serialize), so RapidJSON handles serialization
   - Using the best tool for each job maximizes performance

