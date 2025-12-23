# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import os
import requests
from tenacity import retry, stop_after_delay, wait_fixed, retry_if_exception_type
from python_on_whales import DockerClient
from rich.console import Console

console = Console()


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


@pytest.fixture(scope="session")
def docker_compose(request):
    """Manage docker compose lifecycle for the test session."""
    compose_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    compose_files = [
        os.path.join(compose_dir, "compose.yml"),
        os.path.join(compose_dir, "test", "compose.override.yml")
    ]
    
    # Create client for cleanup (no profiles needed for down)
    docker = DockerClient(compose_files=compose_files)
    
    console.print("\n[bold]=== Docker Compose Setup ===[/bold]")
    
    # Cleanup any previous state
    console.print("Cleaning up any previous state...")
    docker.compose.down(volumes=True, remove_orphans=True)
    
    # Start infrastructure services first (infra profile: MQTT, OTEL, Jaeger)
    console.print("Starting infrastructure services (MQTT, OTEL, Jaeger)...")
    docker_infra = DockerClient(compose_files=compose_files, compose_profiles=["infra"])
    docker_infra.compose.up(detach=True, wait=True)
    console.print("[green]✓ Infrastructure services started[/green]")
    
    # Start tracker service with test config override
    console.print("Starting tracker service (with test config override)...")
    docker_tracker = DockerClient(compose_files=compose_files, compose_profiles=["tracker"])
    docker_tracker.compose.up(detach=True, wait=True)
    console.print("[green]✓ Services started successfully[/green]")
    
    # Wait for HTTP endpoints to be ready
    console.print("Waiting for services to be ready...")
    
    try:
        check_http_service("http://localhost:8889/metrics")
        console.print("  [green]✓ OTEL collector metrics endpoint is ready[/green]")
        
    except Exception as e:
        pytest.fail(f"Service readiness check failed: {e}")
    
    console.print("[green]✓ All services ready[/green]")
    
    yield docker
    
    # Cleanup after tests - skip if KEEP_CONTAINERS is set or tests failed
    keep_containers = os.getenv("KEEP_CONTAINERS", "").lower() in ("1", "true", "yes")
    
    if keep_containers:
        console.print("\n[bold]=== Keeping Containers Running (KEEP_CONTAINERS=1) ===[/bold]")
        console.print("Metrics endpoint: http://localhost:8889/metrics")
        console.print("To stop: docker compose -f compose.yml -f test/compose.override.yml --profile tracker down -v")
        return
    
    if request.session.testsfailed > 0 and not os.getenv("CLEANUP_ON_FAILURE"):
        console.print("\n[bold]=== Keeping Containers Running (Tests Failed) ===[/bold]")
        console.print("Metrics endpoint: http://localhost:8889/metrics")
        console.print("To stop: docker compose -f compose.yml -f test/compose.override.yml --profile tracker down -v")
        console.print("To cleanup on failure, run: CLEANUP_ON_FAILURE=1 pytest ...")
        return
    
    console.print("\n[bold]=== Docker Compose Teardown ===[/bold]")
    console.print("Stopping and removing containers, volumes, and networks...")
    docker.compose.down(volumes=True, remove_orphans=True)
    console.print("[green]✓ Cleanup complete[/green]")
