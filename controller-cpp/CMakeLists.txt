cmake_minimum_required(VERSION 3.16)
project(scenescape-controller-cpp VERSION 1.0.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find required packages
find_package(PkgConfig REQUIRED)
find_package(OpenCV REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(cpprest REQUIRED)
find_package(Threads REQUIRED)

# Find paho-mqtt-cpp
find_library(PAHO_MQTT_CPP_LIB paho-mqttpp3)
if(NOT PAHO_MQTT_CPP_LIB)
    message(FATAL_ERROR "paho-mqtt-cpp library not found")
endif()

# Find paho-mqtt-c (dependency of paho-mqtt-cpp)
find_library(PAHO_MQTT_C_LIB paho-mqtt3as)
if(NOT PAHO_MQTT_C_LIB)
    message(FATAL_ERROR "paho-mqtt-c library not found")
endif()

# Include directories
include_directories(include)
include_directories(../controller/src/robot_vision/include)

# Source files
set(SOURCES
    src/main.cpp
    src/scene_controller.cpp
    src/scene.cpp
    src/cache_manager.cpp
    src/detections_builder.cpp
    src/moving_object.cpp
    src/mqtt_client.cpp
    src/rest_client.cpp
    src/timestamp.cpp
    src/geometry.cpp
)

# Create executable
add_executable(controller ${SOURCES})

# Link libraries
target_link_libraries(controller
    ${OpenCV_LIBS}
    nlohmann_json::nlohmann_json
    cpprest::cpprest
    ${PAHO_MQTT_CPP_LIB}
    ${PAHO_MQTT_C_LIB}
    Threads::Threads
)

# Link robot_vision library (using the existing Python-built version)
# We'll assume robot_vision provides a C++ interface
find_library(ROBOT_VISION_LIB robot_vision PATHS ../controller/src/robot_vision/lib)
if(ROBOT_VISION_LIB)
    target_link_libraries(controller ${ROBOT_VISION_LIB})
endif()

# Install targets
install(TARGETS controller DESTINATION bin)

# Copy configuration files
install(FILES 
    config/tracker-config.json 
    DESTINATION etc/scenescape/controller)
