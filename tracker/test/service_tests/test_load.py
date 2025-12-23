# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Load test for tracker service with metrics validation."""

import pytest
import pytimeparse2

from .config import test_config
from .infrastructure import docker_compose
from .metrics import PrometheusMetrics
from .k6_runner import run_k6_test
from .reporting import console, LoadTestReporter


class TestTrackerMetrics:
    """Test class for tracker service load testing with metrics validation."""

    def test_tracker_metrics(self, docker_compose, test_config):
        """
        End-to-end load test that:
        1. Starts infrastructure via Docker Compose
        2. Runs K6 load test generating MQTT messages
        3. Validates received message count via Prometheus metrics
        4. Checks active tracks and processing latency histogram
        """
        reporter = LoadTestReporter("Tracker Load Test")
        reporter.section("Starting Load Test")
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
        
        # Run K6 load test FIRST (generates MQTT traffic that creates metrics)
        reporter.section("Running K6 Load Test")
        k6_result = run_k6_test(test_config)
        
        if not k6_result.success:
            console.print("[red]K6 test failed[/red]")
            pytest.fail("K6 load test failed")
        
        actual_sent = k6_result.iterations or expected_messages
        console.print(f"[green]✓ K6 sent {actual_sent:,} messages (expected ~{expected_messages:,})[/green]")
        
        # Now wait for metrics endpoint to have data (after k6 has generated traffic)
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
        
        # Verify message count matches
        assert received == actual_sent, \
            f"Message counter mismatch: expected {actual_sent}, got {received} (diff: {received - actual_sent})"
        
        console.print(f"[green]✓ Message counter verification PASSED ({received:,} messages)[/green]")
        
        # Collect all metrics for summary
        dropped = metrics.get_dropped_messages()
        if dropped > 0:
            reporter.add_warning(f"Dropped {dropped:,} messages")
        
        reliable_tracks, total_tracks = metrics.get_track_counts()
        
        mqtt_handler = metrics.get_histogram_stats("scenescape_tracker_mqtt_handler_duration_milliseconds")
        tracking_duration = metrics.get_histogram_stats("scenescape_tracker_tracking_duration_milliseconds")
        
        if mqtt_handler and mqtt_handler["p95"] > 100:
            reporter.add_warning(f"MQTT handler P95 latency is {mqtt_handler['p95']:.2f}ms (>100ms)")
        if tracking_duration and tracking_duration["p95"] > 100:
            reporter.add_warning(f"Tracking P95 latency is {tracking_duration['p95']:.2f}ms (>100ms)")
        
        # Print summary
        reporter.section("Test Summary")
        reporter.print_metrics_summary(
            received_messages=received,
            expected_messages=actual_sent,
            dropped_messages=dropped,
            reliable_tracks=reliable_tracks,
            total_tracks=total_tracks,
            mqtt_handler=mqtt_handler,
            tracking_duration=tracking_duration,
        )
        
        reporter.print_warnings()
        reporter.print_result(
            success=True,
            message=f"Processed {received:,} messages with {reliable_tracks or 0} reliable tracks"
        )
