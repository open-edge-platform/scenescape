#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Basic service test for tracker skeleton.

Validates:
- Tracker service starts successfully
- Service stays running for at least 5 seconds
- MQTT broker is running
"""

import time
from python_on_whales import DockerClient


def test_tracker_service_starts_and_runs(tracker_service):
    """
    Test that tracker service starts and stays running.
    
    Verification:
    1. Service starts successfully and healthcheck passes (verified by fixture)
    2. Service remains healthy for 5 seconds
    3. Broker remains running
    """
    docker = DockerClient()
    context = tracker_service
    
    # Get tracker and broker containers  
    tracker_container = None
    broker_container = None
    for container in context["containers"]:
        if "-tracker-" in container.name:
            tracker_container = container
        elif "-broker-" in container.name:
            broker_container = container
    
    assert tracker_container is not None, "Tracker container not found"
    assert broker_container is not None, "Broker container not found"
    
    # Wait 5 seconds to verify service stability
    print("\n⏳ Waiting 5 seconds to verify service stability...")
    time.sleep(5)
    
    # Verify tracker is still healthy
    tracker_container = docker.container.inspect(tracker_container.id)
    assert tracker_container.state.running, \
        f"Tracker container stopped unexpectedly: {tracker_container.state.status}"
    
    health = tracker_container.state.health
    assert health and health.status == "healthy", \
        f"Tracker healthcheck failed: {health.status if health else 'no healthcheck'}"
    
    # Verify broker is still running
    broker_container = docker.container.inspect(broker_container.id)
    assert broker_container.state.running, \
        f"Broker container stopped unexpectedly: {broker_container.state.status}"
    
    print(f"\n✅ Test passed: Tracker service is healthy and stable")
