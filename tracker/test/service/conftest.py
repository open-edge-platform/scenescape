#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration for tracker service tests.

Provides fixtures for:
- Docker Compose orchestration with unique project names
- Conditional cleanup based on test results
"""

import os
import sys
import uuid
import pytest
import waiting
from python_on_whales import DockerClient


def wait_for_container(docker, container, description, check_health=False, timeout=30):
    """Wait for container to be ready."""
    print(f"⏳ Waiting for {description}...")
    
    def is_ready():
        try:
            c = docker.container.inspect(container.id)
            if check_health:
                return c.state.health and c.state.health.status == "healthy"
            return c.state.running
        except:
            return False
    
    try:
        waiting.wait(is_ready, timeout_seconds=timeout, sleep_seconds=1,
                     waiting_for=f"{description} to be ready")
        print(f"✅ {description.capitalize()} ready")
    except waiting.exceptions.TimeoutExpired:
        logs = docker.container.logs(container)
        print(f"\n❌ {description.capitalize()} logs:")
        print(logs)
        pytest.fail(f"{description.capitalize()} failed to start within {timeout}s")


@pytest.fixture(scope="function")
def tracker_service(request):
    """
    Fixture that starts tracker service with broker and OTEL collector.
    
    Yields:
        dict: Contains 'project_name', 'containers', 'compose_file'
    
    Environment variables:
        PRESERVE_ON_FAILURE: Keep containers on test failure (default: "1")
        KEEP_CONTAINERS: Always keep containers (default: "0")
    """
    project_name = f"tracker-test-{uuid.uuid4().hex[:8]}"
    docker = DockerClient(compose_files=["docker-compose.test.yml"], 
                         compose_project_name=project_name,
                         compose_project_directory=os.path.dirname(__file__))
    
    # Determine cleanup strategy
    preserve_on_failure = os.environ.get("PRESERVE_ON_FAILURE", "1") == "1"
    always_preserve = os.environ.get("KEEP_CONTAINERS", "0") == "1"
    
    try:
        # Start services
        print(f"\n🚀 Starting test environment: {project_name}")
        docker.compose.up(detach=True)
        
        # Get all containers
        containers = docker.compose.ps()
        broker_container = containers[0]
        otel_container = containers[1]
        tracker_container = containers[2]
        
        # Wait for services to be ready
        wait_for_container(docker, broker_container, "broker")
        wait_for_container(docker, otel_container, "OTEL collector")
        wait_for_container(docker, tracker_container, "tracker", check_health=True)
        
        # Yield test context
        context = {
            "project_name": project_name,
            "containers": docker.compose.ps(),
            "docker": docker,
        }
        
        yield context
        
    except Exception as e:
        print(f"\n❌ Setup failed: {e}", file=sys.stderr)
        # Always show logs on setup failure
        try:
            containers = docker.compose.ps()
            for container in containers:
                print(f"\n📋 Logs for {container.name}:")
                print(docker.logs(container))
        except:
            pass
        raise
    
    finally:
        # Determine if we should cleanup
        test_failed = hasattr(request.node, 'rep_call') and request.node.rep_call.failed
        should_cleanup = not always_preserve and not (test_failed and preserve_on_failure)
        
        if should_cleanup:
            print(f"\n🧹 Cleaning up test environment: {project_name}")
            try:
                docker.compose.down(remove_orphans=True)
            except Exception as e:
                print(f"⚠️  Cleanup failed: {e}", file=sys.stderr)
        else:
            reason = "always keep" if always_preserve else "test failed"
            print(f"\n🔍 Containers preserved ({reason}): {project_name}")
            print(f"   View logs: docker compose -p {project_name} logs")
            print(f"   Cleanup: docker compose -p {project_name} down -v")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture test result for conditional cleanup."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
