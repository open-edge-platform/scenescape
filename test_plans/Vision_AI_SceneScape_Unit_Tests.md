# Vision_AI/SceneScape/Unit Tests: Test Suite

## Test suite requirements mapping

- FAREQ-328: When ingesting data with longitude, latitude, altitude (LLA) and no cartesian location, the system must convert LLA into earth-centered earth-fixed (ECEF).
- FAREQ-368: The system must provide a method of synchronizing the timestamps between multiple instances of the pipeline to better than 1 ms on the same or different computers.
- FAREQ-387: The system must provide a method of publishing undecorated frames.
- FAREQ-91: The system shall enable scene controller performance profiling.
- ITEP-66616: 6.4.7 Camera Calibration Microservice
- SAIL-1538: Enable Markerless Auto Camera Calibration
- SAIL-1804: [Auto Camera Calibration] Validation and Test Plan
- SAIL-1914: Geospatial output/input without UI​
- SAIL-2407: Out of the box demo improvements
- SAIL-36: Plan/enable baseline validation and performance optimal configurations for standard deployments

## Test suite setup

### Hardware Requirements

## Vision_AI/SceneScape/Unit Tests/01: Unit Tests for scenescape.py

**Affected Versions:** 2023.4, 2024.1, 2022.4, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

-

### Test requirements mapping

-

### Test priority

- P3

### Prerequisites

-

### Test steps

1.

## Vision_AI/SceneScape/Unit Tests/02: Unit Tests for sscape/geometry.py

**Affected Versions:** 2023.4, 2024.1, 2022.4, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- Unit Tests for sscape/geometry.py

### Test requirements mapping

- FAREQ-328: When ingesting data with longitude, latitude, altitude (LLA) and no cartesian location, the system must convert LLA into earth-centered earth-fixed (ECEF).
- SAIL-1914: Geospatial output/input without UI​

### Test priority

- P3

### Prerequisites

-

### Test steps

1.

## Vision_AI/SceneScape/Unit Tests/03: unit tests for schema files

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2024.2

### Test summary

- unit tests for schema validation

### Test requirements mapping

- SAIL-36: Plan/enable baseline validation and performance optimal configurations for standard deployments
- FAREQ-91: The system shall enable scene controller performance profiling.

### Test priority

- P3

### Prerequisites

-

### Test steps

1.

## Vision_AI/SceneScape/Unit Tests/04: Unit Test cases for auto-camera-calibration module

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2023.2, 2024.2

### Test summary

- Unit test cases for the functionality of auto camera calibration for atag detector and camera calibration.

### Test requirements mapping

- SAIL-1804: [Auto Camera Calibration] Validation and Test Plan
- SAIL-1538: Enable Markerless Auto Camera Calibration
- FAREQ-387: The system must provide a method of publishing undecorated frames.
- ITEP-66616: 6.4.7 Camera Calibration Microservice

### Test priority

- P3

### Prerequisites

-

### Test steps

1.

## Vision_AI/SceneScape/Unit Tests/05: View Unit Tests

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2023.2, 2024.2

### Test summary

- This is a placeholder to represent to views unit tests for traceability.

re: views-unit -&gt; tests\sscape_tests\views\conftest.py

### Test requirements mapping

-

### Test priority

- P3

### Prerequisites

-

### Test steps

1.

## Vision_AI/SceneScape/Unit Tests/06: Timestamp Unit Tests

**Affected Versions:** 2023.4, 2024.1, 2023.3, 2023.2, 2024.2

### Test summary

- This is a placeholder to represent to timestamp unit tests for traceability.

### Test requirements mapping

- FAREQ-368: The system must provide a method of synchronizing the timestamps between multiple instances of the pipeline to better than 1 ms on the same or different computers.

### Test priority

- P3

### Prerequisites

-

### Test steps

1.

## Vision_AI/SceneScape/Unit Tests/07: Unit tests for markerless calibration code

**Affected Versions:** 2023.4, 2024.1, 2024.2

### Test summary

-

### Test requirements mapping

- SAIL-1804: [Auto Camera Calibration] Validation and Test Plan
- SAIL-2407: Out of the box demo improvements
- SAIL-1538: Enable Markerless Auto Camera Calibration

### Test priority

- P3

### Prerequisites

-

### Test steps

1.

## Vision_AI/SceneScape/Unit Tests/08: Transform unit test

**Affected Versions:**

### Test summary

-

### Test requirements mapping

-

### Test priority

- P3

### Prerequisites

-

### Test steps

1. make -C tests transform-unit

## Vision_AI/SceneScape/Unit Tests/09: Geospatial unit test

**Affected Versions:**

### Test summary

-

### Test requirements mapping

-

### Test priority

- P3

### Prerequisites

-

### Test steps

1. make -C tests geospatial-unit
