# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Docker Compose infrastructure management for tests."""

import os
import pytest
import requests
from tenacity import retry, stop_after_delay, wait_fixed, retry_if_exception_type
from python_on_whales import DockerClient

from .reporting import console


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
    compose_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    compose_files = [
        os.path.join(compose_dir, "compose.yml"),
        os.path.join(compose_dir, "test", "compose.override.yml")
    ]
    
    # Create clients - one with all profiles for cleanup, separate ones for startup
    docker_all = DockerClient(compose_files=compose_files, compose_profiles=["infra", "tracker"])
    docker_infra = DockerClient(compose_files=compose_files, compose_profiles=["infra"])
    docker_tracker = DockerClient(compose_files=compose_files, compose_profiles=["tracker"])
    
    console.print("\n[bold]=== Docker Compose Setup ===[/bold]")
    
    # Cleanup any previous state - use client with all profiles
    console.print("Cleaning up any previous state...")
    docker_all.compose.down(volumes=True, remove_orphans=True)
    
    # Start infrastructure services first (infra profile: MQTT, OTEL, Jaeger)
    console.print("Starting infrastructure services (MQTT, OTEL, Jaeger)...")
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
    
    yield docker_all
    
    # Cleanup after tests - skip if KEEP_CONTAINERS is set or tests failed
    keep_containers = os.getenv("KEEP_CONTAINERS", "").lower() in ("1", "true", "yes")
    
    if keep_containers:
        console.print("\n[bold]=== Keeping Containers Running (KEEP_CONTAINERS=1) ===[/bold]")
        console.print("Metrics endpoint: http://localhost:8889/metrics")
        console.print("To stop: docker compose -f compose.yml -f test/compose.override.yml --profile infra --profile tracker down -v")
        return
    
    if request.session.testsfailed > 0 and not os.getenv("CLEANUP_ON_FAILURE"):
        console.print("\n[bold]=== Keeping Containers Running (Tests Failed) ===[/bold]")
        console.print("Metrics endpoint: http://localhost:8889/metrics")
        console.print("To stop: docker compose -f compose.yml -f test/compose.override.yml --profile infra --profile tracker down -v")
        console.print("To cleanup on failure, run: CLEANUP_ON_FAILURE=1 pytest ...")
        return
    
    console.print("\n[bold]=== Docker Compose Teardown ===[/bold]")
    console.print("Stopping and removing containers, volumes, and networks...")
    docker_all.compose.down(volumes=True, remove_orphans=True)
    console.print("[green]✓ Cleanup complete[/green]")
