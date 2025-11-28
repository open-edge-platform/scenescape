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
|------------|-------------|-----------|---------||
| RapidJSON  | Serialize   | 305       | -       |
| RapidJSON  | Deserialize | 359       | -       |
| simdjson   | Deserialize | 111       | **3.2x faster** |

**Regulated Message (1000 objects):**

| Library    | Operation   | Time (μs) | Speedup |
|------------|-------------|-----------|---------||
| RapidJSON  | Serialize   | 802       | -       |
| RapidJSON  | Deserialize | 767       | -       |
| simdjson   | Deserialize | 235       | **3.3x faster** |

### Detection Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------||
| JSON        | Serialize   | 305       | 1.0x    |
| JSON        | Deserialize | 111       | 1.0x    |
| Protobuf    | Serialize   | 22        | **14x faster** |
| Protobuf    | Deserialize | 115       | 0.96x slower |
| FlatBuffers | Serialize   | 184       | 1.7x faster |
| FlatBuffers | Deserialize | 0.0005    | **200,000x faster** |

### Regulated Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------||
| JSON        | Serialize   | 802       | 1.0x    |
| JSON        | Deserialize | 235       | 1.0x    |
| Protobuf    | Serialize   | 112       | **7.2x faster** |
| Protobuf    | Deserialize | 473       | 2.0x slower |
| FlatBuffers | Serialize   | 227       | **3.5x faster** |
| FlatBuffers | Deserialize | 0.0006    | **390,000x faster** |

## Python Results (pytest-benchmark)

### Detection Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------||
| JSON        | Serialize   | 152       | 1.0x    |
| JSON        | Deserialize | 416       | 1.0x    |
| Protobuf    | Serialize   | 43        | **3.5x faster** |
| Protobuf    | Deserialize | 46        | **9.0x faster** |
| FlatBuffers | Serialize   | 15,009    | 99x slower |
| FlatBuffers | Deserialize | 0.31      | **1,340x faster** |

### Regulated Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------||
| JSON        | Serialize   | 650       | 1.0x    |
| JSON        | Deserialize | 1,163     | 1.0x    |
| Protobuf    | Serialize   | 123       | **5.3x faster** |
| Protobuf    | Deserialize | 148       | **7.9x faster** |
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
   - **simdjson is 3.2x faster** than RapidJSON for deserialization (Detection: 111μs vs 359μs)
   - **simdjson is 3.3x faster** for complex messages (Regulated: 235μs vs 767μs)
   - simdjson is parse-only (cannot serialize), so RapidJSON handles serialization
   - Using the best tool for each job maximizes performance

