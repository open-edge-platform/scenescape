# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Service tests for Tracker Service.

Tests the tracker in isolation with mocked dependencies (MQTT broker, OTEL collector).
Designed for:
- CI: Run on every PR with small load (default config)
- Benchmarking: Run with large load on dedicated hardware (env var overrides)

Usage:
    # CI mode (default - small load)
    make load-test

    # Benchmark mode (large load)
    CAMERA_COUNT=16 CAMERA_FPS=30 TEST_DURATION=5m make load-test
"""

import pytest
import pytimeparse2
import warnings

from .config import test_config
from .infrastructure import docker_compose
from .metrics import PrometheusMetrics
from .k6_runner import run_k6_test
from .reporting import console, LoadTestReporter


class ServiceTestWarning(UserWarning):
    """Warning for non-critical service test issues."""
    pass


@pytest.fixture(scope="module")
def load_test_results(docker_compose, test_config):
    """
    Run load test and collect metrics once per module.
    Individual tests assert on the collected metrics.
    """
    reporter = LoadTestReporter("Tracker Service Test")
    reporter.section("Test Configuration")
    reporter.print_config(test_config)
    
    # Calculate expected messages
    duration_seconds = pytimeparse2.parse(test_config["test_duration"])
    expected_messages = (
        test_config["camera_count"] 
        * test_config["camera_fps"] 
        * duration_seconds
    )
    console.print(f"\n[cyan]Expected messages: {expected_messages:,}[/cyan]")
    
    # Initialize metrics client
    metrics = PrometheusMetrics(test_config["metrics_endpoint"])
    
    # Run K6 load test
    reporter.section("Running K6 Load Test")
    k6_result = run_k6_test(test_config)
    
    if not k6_result.success:
        console.print("[red]K6 test failed[/red]")
        pytest.fail("K6 load test failed")
    
    actual_sent = k6_result.iterations or expected_messages
    console.print(f"[green]✓ K6 sent {actual_sent:,} messages (expected ~{expected_messages:,})[/green]")
    
    # Wait for metrics endpoint to have data
    metrics_timeout = test_config["export_interval"] + test_config["metrics_timeout_buffer"]
    reporter.section(f"Waiting for Metrics (timeout: {metrics_timeout}s)")
    console.print("  Waiting for first metrics export...")
    metrics.wait_for_endpoint(timeout=metrics_timeout, interval=1)
    console.print("[green]✓ Metrics endpoint has data[/green]")
    
    # Wait for counter to reach expected value
    received = metrics.wait_for_counter(
        name="mqtt_messages_received_total",
        min_value=actual_sent,
        timeout=metrics_timeout,
        interval=1,
    )
    console.print(f"[green]✓ Metrics collected ({received:,} messages received)[/green]")
    
    # Collect all metrics
    reliable_tracks, total_tracks = metrics.get_track_counts()
    
    results = {
        "config": test_config,
        "expected_messages": expected_messages,
        "actual_sent": actual_sent,
        "received_messages": received,
        "dropped_messages": metrics.get_dropped_messages(),
        "reliable_tracks": reliable_tracks,
        "total_tracks": total_tracks,
        "mqtt_handler": metrics.get_histogram_stats("scenescape_tracker_mqtt_handler_duration_milliseconds"),
        "tracking_duration": metrics.get_histogram_stats("scenescape_tracker_tracking_duration_milliseconds"),
    }
    
    # Print summary
    reporter.section("Metrics Summary")
    reporter.print_metrics_summary(
        received_messages=received,
        expected_messages=actual_sent,
        dropped_messages=results["dropped_messages"],
        reliable_tracks=reliable_tracks,
        total_tracks=total_tracks,
        mqtt_handler=results["mqtt_handler"],
        tracking_duration=results["tracking_duration"],
    )
    
    return results


class TestTrackerService:
    """Service tests for tracker - validates metrics after load test."""

    def test_message_count(self, load_test_results):
        """Verify all sent messages were received by the tracker."""
        received = load_test_results["received_messages"]
        expected = load_test_results["actual_sent"]
        
        assert received >= expected, \
            f"Message loss: expected {expected:,}, got {received:,} (lost {expected - received:,})"

    def test_dropped_messages(self, load_test_results):
        """Check for dropped messages (warns but doesn't fail)."""
        dropped = load_test_results["dropped_messages"]
        
        if dropped > 0:
            warnings.warn(f"Dropped {dropped:,} messages due to backpressure", ServiceTestWarning, stacklevel=2)

    def test_active_tracks(self, load_test_results):
        """Verify tracker is producing tracks."""
        reliable = load_test_results["reliable_tracks"]
        
        assert reliable is not None, "Track metrics not found"
        assert reliable > 0, f"No reliable tracks detected (got {reliable})"

    def test_mqtt_handler_latency(self, load_test_results):
        """Verify MQTT handler p95 latency is within processing budget (warns only)."""
        histogram = load_test_results["mqtt_handler"]
        budget_ms = load_test_results["config"]["processing_budget_ms"]
        
        assert histogram is not None, "MQTT handler histogram metric not found"
        
        p95 = histogram["p95"]
        if p95 >= budget_ms:
            warnings.warn(f"MQTT handler p95={p95:.2f}ms exceeds budget={budget_ms}ms", ServiceTestWarning, stacklevel=2)

    def test_tracking_latency(self, load_test_results):
        """Verify tracking p95 latency is within processing budget (warns only)."""
        histogram = load_test_results["tracking_duration"]
        budget_ms = load_test_results["config"]["processing_budget_ms"]
        
        assert histogram is not None, "Tracking duration histogram metric not found"
        
        p95 = histogram["p95"]
        if p95 >= budget_ms:
            warnings.warn(f"Tracking p95={p95:.2f}ms exceeds budget={budget_ms}ms", ServiceTestWarning, stacklevel=2)
