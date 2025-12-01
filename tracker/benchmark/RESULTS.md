# Benchmark Results

Performance comparison of JSON, Protocol Buffers, and FlatBuffers for serializing/deserializing tracker messages with 1000 objects.

## Test Environment

**Hardware:**
- CPU: Intel Core Ultra 9 285H (16 cores @ 5.4 GHz max)
- RAM: 64 GB
- OS: Ubuntu 24.04.3 LTS (Linux 6.14.0-35-generic)
- Compiler: g++ with -O3 -march=x86-64-v3

## Libraries

**C++:**
- JSON: RapidJSON (serialize) + simdjson (deserialize)
- Protobuf: libprotobuf (Protocol Buffers v3)
- FlatBuffers: libflatbuffers
- Benchmark: Google Benchmark

**Python:**
- JSON: orjson
- Protobuf: protobuf (official Python bindings)
- FlatBuffers: flatbuffers (official Python bindings)
- Benchmark: pytest-benchmark

## C++ Results

### JSON Library Comparison

**Detection Message (1000 objects):**

| Library    | Operation   | Time (μs) | Speedup |
|------------|-------------|-----------|---------|
| RapidJSON  | Serialize   | 305       | -       |
| RapidJSON  | Deserialize | 359       | -       |
| simdjson   | Deserialize | 111       | 3.2x    |

**Regulated Message (1000 objects):**

| Library    | Operation   | Time (μs) | Speedup |
|------------|-------------|-----------|---------|
| RapidJSON  | Serialize   | 802       | -       |
| RapidJSON  | Deserialize | 767       | -       |
| simdjson   | Deserialize | 235       | 3.3x    |

### Detection Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------|
| JSON        | Serialize   | 305       | 1.0x    |
| JSON        | Deserialize | 111       | 1.0x    |
| Protobuf    | Serialize   | 22        | 14x     |
| Protobuf    | Deserialize | 115       | 0.96x   |
| FlatBuffers | Serialize   | 184       | 1.7x    |
| FlatBuffers | Deserialize | 0.0005    | 222,000x |

### Regulated Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------|
| JSON        | Serialize   | 802       | 1.0x    |
| JSON        | Deserialize | 235       | 1.0x    |
| Protobuf    | Serialize   | 112       | 7.2x    |
| Protobuf    | Deserialize | 473       | 0.50x   |
| FlatBuffers | Serialize   | 227       | 3.5x    |
| FlatBuffers | Deserialize | 0.0006    | 392,000x |

## Python Results

### Detection Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------|
| JSON        | Serialize   | 152       | 1.0x    |
| JSON        | Deserialize | 416       | 1.0x    |
| Protobuf    | Serialize   | 43        | 3.5x    |
| Protobuf    | Deserialize | 46        | 9.0x    |
| FlatBuffers | Serialize   | 15,009    | 0.01x   |
| FlatBuffers | Deserialize | 0.31      | 1,342x  |

### Regulated Message (1000 objects)

| Format      | Operation   | Time (μs) | vs JSON |
|-------------|-------------|-----------|---------|
| JSON        | Serialize   | 650       | 1.0x    |
| JSON        | Deserialize | 1,163     | 1.0x    |
| Protobuf    | Serialize   | 123       | 5.3x    |
| Protobuf    | Deserialize | 148       | 7.9x    |
| FlatBuffers | Serialize   | N/A       | -       |
| FlatBuffers | Deserialize | N/A       | -       |

