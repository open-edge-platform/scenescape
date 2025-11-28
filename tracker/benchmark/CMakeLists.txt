cmake_minimum_required(VERSION 3.15)
project(SerializationBenchmark CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3 -march=native")

# Find packages
find_package(Protobuf REQUIRED)
find_package(Flatbuffers REQUIRED)
find_package(nlohmann_json 3.2.0 REQUIRED)

# Generate protobuf files
set(PROTO_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../data")
set(PROTO_FILE "${PROTO_DIR}/detection-message.proto")
set(PROTO_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated/proto")

file(MAKE_DIRECTORY ${PROTO_GENERATED_DIR})

execute_process(
    COMMAND protoc --cpp_out=${PROTO_GENERATED_DIR} -I${PROTO_DIR} ${PROTO_FILE}
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
)

# Generate FlatBuffers files
set(FBS_FILE "${PROTO_DIR}/detection-message.fbs")
set(FBS_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated/fbs")

file(MAKE_DIRECTORY ${FBS_GENERATED_DIR})

execute_process(
    COMMAND flatc --cpp -o ${FBS_GENERATED_DIR} ${FBS_FILE}
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
)

# Create executable
add_executable(benchmark_serialization
    benchmark_serialization.cpp
    ${PROTO_GENERATED_DIR}/detection_message.pb.cc
)

target_include_directories(benchmark_serialization PRIVATE
    ${PROTO_GENERATED_DIR}
    ${FBS_GENERATED_DIR}
    ${Protobuf_INCLUDE_DIRS}
    ${FLATBUFFERS_INCLUDE_DIRS}
)

target_link_libraries(benchmark_serialization
    ${Protobuf_LIBRARIES}
    nlohmann_json::nlohmann_json
)
