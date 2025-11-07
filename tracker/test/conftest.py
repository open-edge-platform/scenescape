# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import subprocess
import os
import requests
from tenacity import retry, stop_after_delay, wait_fixed, retry_if_exception_type


@pytest.fixture(scope="session")
def test_config():
    """Test configuration from environment variables with defaults."""
    return {
        "mqtt_host": os.getenv("MQTT_HOST", "tcp://localhost"),
        "mqtt_port": os.getenv("MQTT_PORT", "1883"),
        "camera_id_prefix": os.getenv("CAMERA_ID_PREFIX", "dummy_cam"),
        "camera_count": int(os.getenv("CAMERA_COUNT", "1")),
        "camera_fps": int(os.getenv("CAMERA_FPS", "1")),
        "object_count": int(os.getenv("OBJECT_COUNT", "5")),
        "test_duration": os.getenv("TEST_DURATION", "1m"),
        "metrics_endpoint": os.getenv("METRICS_ENDPOINT", "http://localhost:8889/metrics"),
        "export_interval": int(os.getenv("EXPORT_INTERVAL", "10")),
        # Buffer added to export_interval when waiting for metrics to account for
        # processing delays, network latency, batch export timing variations, and
        # worst-case export cycle alignment (metrics may be buffered until next interval)
        "metrics_timeout_buffer": int(os.getenv("METRICS_TIMEOUT_BUFFER", "15")),
        # Processing budget in milliseconds (MQTT handler + tracking) per message
        # Based on 15 FPS requirement: 1000ms / 15 = 66.67ms budget per message
        "processing_budget_ms": float(os.getenv("PROCESSING_BUDGET_MS", "66.0")),
    }


@retry(
    stop=stop_after_delay(30),
    wait=wait_fixed(1),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    reraise=True
)
def check_http_service(url):
    """Check if HTTP service is responsive (with automatic retry)."""
    response = requests.get(url, timeout=2)
    if response.status_code != 200:
        raise requests.ConnectionError(f"Service returned {response.status_code}")


@retry(
    stop=stop_after_delay(30),
    wait=wait_fixed(1),
    reraise=True
)
def check_docker_service(service_name, compose_dir):
    """Check if docker service is running (with automatic retry)."""
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "json", service_name],
        cwd=compose_dir,
        capture_output=True,
        text=True
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(f"Service {service_name} not found")
    if '"State":"running"' not in result.stdout and '"Status":"running"' not in result.stdout:
        raise RuntimeError(f"Service {service_name} not running yet")


@pytest.fixture(scope="session")
def docker_compose(request):
    """Manage docker compose lifecycle for the test session."""
    compose_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    print("\n=== Docker Compose Setup ===")
    
    # Cleanup any previous state
    print("Cleaning up any previous state...")
    subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "-f", "test/compose.override.yml", "--profile", "tracker", "down", "-v", "--remove-orphans"],
        cwd=compose_dir,
        capture_output=True
    )
    
    # Start infrastructure services first (without tracker profile)
    print("Starting infrastructure services (MQTT, OTEL, Jaeger)...")
    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=compose_dir,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        pytest.fail(f"Failed to start infrastructure services: {result.stderr}")
    
    print("✓ Infrastructure services started")
    
    # Start tracker service with test config override
    print("Starting tracker service (with test config override)...")
    result = subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "-f", "test/compose.override.yml", "--profile", "tracker", "up", "-d"],
        cwd=compose_dir,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        pytest.fail(f"Failed to start docker compose: {result.stderr}")
    
    print("✓ Services started successfully")
    
    # Wait for services to be ready using tenacity retry decorators
    print("Waiting for services to be ready...")
    
    try:
        check_docker_service("mqtt-broker", compose_dir)
        print("  ✓ MQTT broker is running")
        
        check_docker_service("otel-collector", compose_dir)
        print("  ✓ OTEL collector is running")
        
        check_http_service("http://localhost:8889/metrics")
        print("  ✓ OTEL collector metrics endpoint is ready")
        
        check_docker_service("tracker", compose_dir)
        print("  ✓ Tracker service is running")
        
    except Exception as e:
        pytest.fail(f"Service readiness check failed: {e}")
    
    print("✓ All services ready")
    
    yield
    
    # Cleanup after tests - skip if KEEP_CONTAINERS is set or tests failed
    keep_containers = os.getenv("KEEP_CONTAINERS", "").lower() in ("1", "true", "yes")
    
    if keep_containers:
        print("\n=== Keeping Containers Running (KEEP_CONTAINERS=1) ===")
        print("Metrics endpoint: http://localhost:8889/metrics")
        print("To stop: docker compose -f compose.yml -f test/compose.override.yml --profile tracker down -v")
        return
    
    if request.session.testsfailed > 0:
        print("\n=== Keeping Containers Running (Tests Failed) ===")
        print("Metrics endpoint: http://localhost:8889/metrics")
        print("To stop: docker compose -f compose.yml -f test/compose.override.yml --profile tracker down -v")
        print("To cleanup on failure, run: CLEANUP_ON_FAILURE=1 pytest ...")
        if not os.getenv("CLEANUP_ON_FAILURE"):
            return
    
    print("\n=== Docker Compose Teardown ===")
    print("Stopping and removing containers, volumes, and networks...")
    subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "-f", "test/compose.override.yml", "--profile", "tracker", "down", "-v", "--remove-orphans"],
        cwd=compose_dir,
        capture_output=True
    )
    print("✓ Cleanup complete")
