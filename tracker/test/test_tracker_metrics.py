# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import subprocess
import os
import json
import requests
from tenacity import retry, stop_after_delay, wait_fixed, retry_if_result
from prometheus_client.parser import text_string_to_metric_families
from pytimeparse2 import parse as parse_duration
from rich.console import Console
from rich.table import Table

console = Console()


class TestTrackerMetrics:
    """Test tracker service metrics collection and verification."""
    
    def test_tracker_metrics(self, docker_compose, test_config):
        """
        Test that tracker correctly records metrics.
        
        This test:
        1. Runs K6 load test to generate MQTT messages
        2. Waits for metrics to be exported
        3. Queries Prometheus endpoint
        4. Verifies mqtt_messages_received_total counter matches sent messages
        5. Verifies mqtt_handler_duration and tracking_duration histograms
        6. Checks for dropped messages and warns if any detected
        """
        # Calculate expected messages
        duration_seconds = parse_duration(test_config["test_duration"])
        expected_messages = (
            test_config["camera_count"] * 
            test_config["camera_fps"] * 
            duration_seconds
        )
        
        console.print(f"\n[bold]=== Test Configuration ===[/bold]")
        console.print(f"Cameras: {test_config['camera_count']}")
        console.print(f"FPS: {test_config['camera_fps']}")
        console.print(f"Objects per message: {test_config['object_count']}")
        console.print(f"Duration: {test_config['test_duration']} ({duration_seconds}s)")
        console.print(f"Expected messages: {expected_messages}")
        
        # Run K6 load test
        console.print("\n[bold]=== Running K6 Load Test ===[/bold]")
        k6_result, k6_metrics = self._run_k6_test(test_config)
        assert k6_result == 0, "K6 load test failed"
        
        # Use actual messages sent by K6 (accounting for timing variations)
        actual_sent = k6_metrics.get("iterations", expected_messages)
        console.print(f"K6 sent {actual_sent} messages (expected ~{expected_messages})")
        
        # Wait for metrics to appear (cold start handling)
        # First wait for metrics endpoint to return ANY data
        metrics_timeout = test_config["export_interval"] + test_config["metrics_timeout_buffer"]
        console.print(f"\n[bold]=== Waiting for metrics (timeout: {metrics_timeout}s) ===[/bold]")
        console.print("  Waiting for first metrics export...")
        self._wait_for_metrics_endpoint(test_config["metrics_endpoint"], timeout=metrics_timeout)
        
        # Now wait for the specific counter value
        actual_messages = self._wait_for_metric_value(
            test_config["metrics_endpoint"],
            "mqtt_messages_received_total",
            actual_sent,
            timeout=metrics_timeout
        )
        
        assert actual_messages == actual_sent, \
            f"Message counter mismatch: expected {actual_sent}, got {actual_messages} (diff: {actual_messages - actual_sent})"
        
        console.print("[green]✓ Message counter verification PASSED[/green]")
        
        # Get all metrics for analysis
        console.print("\n[bold]=== Fetching Metrics ===[/bold]")
        response = requests.get(test_config["metrics_endpoint"], timeout=5)
        response.raise_for_status()
        
        # Parse metrics once for all subsequent checks
        metrics = self._parse_metrics(response.text)
        
        # Check for dropped messages
        dropped_count, dropped_by_reason = self._check_dropped_messages(metrics)
        
        # Verify MQTT handler duration histogram
        console.print("\n[bold]=== Verifying MQTT Handler Duration Histogram ===[/bold]")
        handler_stats = self._verify_histogram(
            metrics,
            "scenescape_tracker_mqtt_handler_duration_milliseconds",
            "MQTT handler duration"
        )
        
        # Verify tracking duration histogram
        console.print("\n[bold]=== Verifying Tracking Duration Histogram ===[/bold]")
        tracking_stats = self._verify_histogram(
            metrics,
            "scenescape_tracker_tracking_duration_milliseconds",
            "Tracking duration"
        )
        
        # Verify active tracks gauges
        console.print("\n[bold]=== Verifying Active Tracks ===[/bold]")
        reliable_tracks, total_tracks = self._check_active_tracks(metrics)
        
        # Calculate total processing time and check budget
        processing_budget_ms = test_config["processing_budget_ms"]
        total_processing_ms = 0.0
        total_p95_ms = None
        if handler_stats and tracking_stats:
            total_processing_ms = handler_stats['avg'] + tracking_stats['avg']
            # Calculate total p95 if both are available
            if handler_stats.get('p95') is not None and tracking_stats.get('p95') is not None:
                total_p95_ms = handler_stats['p95'] + tracking_stats['p95']
        
        # Print summary using rich table
        console.print("\n[bold]=== Test Summary ===[/bold]")
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="dim")
        table.add_column("Value", justify="right")
        
        table.add_row("Cameras", str(test_config['camera_count']))
        table.add_row("FPS", str(test_config['camera_fps']))
        table.add_row("Objects per message", str(test_config['object_count']))
        table.add_row("Duration", test_config['test_duration'])
        table.add_row("Messages sent", str(actual_sent))
        table.add_row("Messages received", str(actual_messages))
        table.add_row("Messages dropped", str(dropped_count))
        
        if reliable_tracks is not None:
            table.add_row("Reliable tracks", str(reliable_tracks))
        if total_tracks is not None:
            unreliable = total_tracks - reliable_tracks if reliable_tracks else total_tracks
            table.add_row("Total tracks", f"{total_tracks} ({unreliable} unreliable)")
        
        if handler_stats:
            table.add_row("MQTT handler avg", f"{handler_stats['avg']:.2f} ms")
            if handler_stats.get('p95'):
                table.add_row("MQTT handler p95", f"{handler_stats['p95']:.2f} ms")
        
        if tracking_stats:
            table.add_row("Tracking avg", f"{tracking_stats['avg']:.2f} ms")
            if tracking_stats.get('p95'):
                table.add_row("Tracking p95", f"{tracking_stats['p95']:.2f} ms")
        
        if total_p95_ms is not None:
            table.add_row("Total processing p95", f"{total_p95_ms:.2f} ms")
        elif total_processing_ms > 0:
            table.add_row("Total processing avg", f"{total_processing_ms:.2f} ms")
        table.add_row("Processing budget", f"{processing_budget_ms:.2f} ms")
        
        console.print(table)
        
        # Check budget based on p95 (preferred) or average
        processing_metric = total_p95_ms if total_p95_ms is not None else total_processing_ms
        metric_name = "p95" if total_p95_ms is not None else "avg"
        
        if processing_metric <= processing_budget_ms:
            headroom = processing_budget_ms - processing_metric
            console.print(f"[green]✓ {metric_name} within budget ({headroom:.2f} ms headroom)[/green]")
        
        # Warnings
        if dropped_count > 0:
            reasons_str = ", ".join([f"{count} {reason}" for reason, count in dropped_by_reason.items()])
            console.print(f"\n[yellow]⚠️  WARNING: {dropped_count} messages were dropped during the test! ({reasons_str})[/yellow]")
            console.print("    This may indicate the tracker is overloaded or falling behind.")
        
        # Check if track count matches expected object count
        expected_objects = test_config['object_count']
        if reliable_tracks is not None and reliable_tracks != expected_objects:
            diff = abs(reliable_tracks - expected_objects)
            if reliable_tracks < expected_objects:
                console.print(f"\n[yellow]⚠️  WARNING: Fewer tracks than objects! Reliable tracks: {reliable_tracks}, Expected: {expected_objects} (missing {diff})[/yellow]")
                console.print("    The tracker may be losing objects or failing to initialize tracks.")
            else:
                console.print(f"\n[yellow]⚠️  WARNING: More tracks than objects! Reliable tracks: {reliable_tracks}, Expected: {expected_objects} (extra {diff})[/yellow]")
                console.print("    The tracker may be creating duplicate tracks or not cleaning up old tracks.")
        
        if processing_metric > processing_budget_ms:
            overage = processing_metric - processing_budget_ms
            console.print(f"\n[yellow]⚠️  WARNING: Processing time ({metric_name}) exceeds budget by {overage:.2f} ms![/yellow]")
            console.print(f"    Total processing {metric_name}: {processing_metric:.2f} ms > Budget: {processing_budget_ms:.2f} ms")
            console.print("    Consider optimizing the tracking algorithm or reducing load.")
        
        console.print("\n[green]✓ All metrics verified successfully[/green]")
    
    def _parse_metrics(self, metrics_text):
        """Parse Prometheus text format into a dict keyed by metric name."""
        metrics = {}
        for family in text_string_to_metric_families(metrics_text):
            metrics[family.name] = family
        return metrics
    
    def _run_k6_test(self, config):
        """Run K6 load test with configured parameters and return metrics."""
        test_dir = os.path.dirname(os.path.abspath(__file__))
        k6_script = os.path.join(test_dir, "generate-detections.js")
        summary_file = os.path.join(test_dir, "k6-summary.json")
        
        env = os.environ.copy()
        env.update({
            "MQTT_HOST": config["mqtt_host"],
            "MQTT_PORT": str(config["mqtt_port"]),
            "CAMERA_ID_PREFIX": config["camera_id_prefix"],
            "CAMERA_COUNT": str(config["camera_count"]),
            "CAMERA_FPS": str(config["camera_fps"]),
            "OBJECT_COUNT": str(config["object_count"]),
            "DEFAULT_TEST_DURATION": config["test_duration"],
        })
        
        # Run K6 with streaming output and JSON summary export
        result = subprocess.run(
            ["k6", "run", f"--summary-export={summary_file}", k6_script],
            env=env,
            capture_output=False
        )
        
        # Parse iteration count from JSON summary
        metrics = {}
        try:
            with open(summary_file, 'r') as f:
                summary = json.load(f)
                metrics['iterations'] = int(summary['metrics']['iterations']['count'])
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            console.print(f"[yellow]Warning: Could not parse K6 summary: {e}[/yellow]")
        
        return result.returncode, metrics
    
    def _wait_for_metrics_endpoint(self, endpoint, timeout=30):
        """Wait for Prometheus endpoint to return any metrics (not empty response)."""
        @retry(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(1),
            retry=retry_if_result(lambda x: not x),  # Retry if False (no metrics)
            reraise=True
        )
        def check_endpoint():
            try:
                response = requests.get(endpoint, timeout=5)
                response.raise_for_status()
                # Check if response has any non-comment content
                has_metrics = any(
                    line.strip() and not line.startswith('#') 
                    for line in response.text.split('\n')
                )
                if not has_metrics:
                    console.print("\r  Metrics endpoint responding but no data yet...", end='')
                return has_metrics
            except requests.RequestException:
                console.print("\r  Waiting for metrics endpoint to be available...", end='')
                return False
        
        try:
            result = check_endpoint()
            console.print("\n  [green]✓ Metrics endpoint has data[/green]")
            return result
        except Exception as e:
            console.print()
            pytest.fail(f"Metrics endpoint did not return data within {timeout}s: {e}")
    
    def _get_metric_value(self, endpoint, metric_name):
        """Query Prometheus endpoint and extract metric value."""
        try:
            response = requests.get(endpoint, timeout=5)
            response.raise_for_status()
        except requests.RequestException:
            return None
        
        metrics = self._parse_metrics(response.text)
        
        # prometheus_client parser strips _total suffix from counter family names
        # Try both the original name and without _total suffix
        family_name = metric_name
        if metric_name not in metrics and metric_name.endswith("_total"):
            family_name = metric_name[:-6]  # Remove "_total"
        
        if family_name not in metrics:
            return None
        
        # Return the first sample's value (counters typically have one sample)
        samples = list(metrics[family_name].samples)
        if samples:
            return int(samples[0].value)
        return None
    
    def _wait_for_metric_value(self, endpoint, metric_name, expected_value, timeout=30):
        """Wait for metric to reach expected value (with retry)."""
        @retry(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(1),
            retry=retry_if_result(lambda x: x != expected_value),
            reraise=True
        )
        def check_metric():
            value = self._get_metric_value(endpoint, metric_name)
            if value is None:
                # Try to get available metrics for better error message
                try:
                    response = requests.get(endpoint, timeout=5)
                    available_metrics = [
                        line.split()[0] 
                        for line in response.text.split('\n') 
                        if line and not line.startswith('#') and '{' in line
                    ]
                    raise RuntimeError(
                        f"Metric {metric_name} not found. "
                        f"Available metrics: {', '.join(set(available_metrics[:10]))}"
                    )
                except requests.RequestException:
                    raise RuntimeError(f"Metric {metric_name} not found (endpoint unreachable)")
            console.print(f"\r  Current {metric_name}: {value} (waiting for {expected_value})", end='')
            return value
        
        try:
            result = check_metric()
            console.print()  # Newline after successful completion
            return result
        except Exception as e:
            console.print()  # Newline on error
            # On timeout, return the last value we got for better error messages
            final_value = self._get_metric_value(endpoint, metric_name)
            if final_value is not None:
                return final_value
            pytest.fail(f"Failed to get metric {metric_name}: {e}")
    
    def _check_dropped_messages(self, metrics):
        """Check for dropped messages metric and return count and reasons."""
        dropped_by_reason = {}
        total_dropped = 0
        
        metric_name = "scenescape_controller_mqtt_messages_dropped"
        if metric_name in metrics:
            for sample in metrics[metric_name].samples:
                if sample.name.endswith("_total"):
                    count = int(sample.value)
                    if count > 0:
                        reason = sample.labels.get("reason", "unknown")
                        dropped_by_reason[reason] = count
                        total_dropped += count
        
        if total_dropped > 0:
            for reason, count in dropped_by_reason.items():
                reason_desc = {
                    "fell_behind": "buffer full/fell behind",
                    "tracker_busy": "tracker processing busy",
                    "missing_category": "missing object category"
                }.get(reason, reason)
                console.print(f"  Found {count} dropped messages (type: {reason_desc})")
        else:
            console.print("  No dropped messages detected")
        
        return total_dropped, dropped_by_reason
    
    def _check_active_tracks(self, metrics):
        """Check for active tracks gauges and return counts."""
        reliable_tracks = None
        total_tracks = None
        
        if "scenescape_tracker_reliable_tracks" in metrics:
            samples = list(metrics["scenescape_tracker_reliable_tracks"].samples)
            if samples:
                reliable_tracks = int(samples[0].value)
        
        if "scenescape_tracker_total_tracks" in metrics:
            samples = list(metrics["scenescape_tracker_total_tracks"].samples)
            if samples:
                total_tracks = int(samples[0].value)
        
        if reliable_tracks is not None:
            console.print(f"  Found {reliable_tracks} reliable tracks")
            if total_tracks is not None:
                unreliable = total_tracks - reliable_tracks
                console.print(f"  Found {total_tracks} total tracks ({unreliable} unreliable)")
                if reliable_tracks == 0 and total_tracks == 0:
                    console.print(f"  [yellow]⚠️  Warning: No tracks detected - tracker may not be working correctly[/yellow]")
        else:
            console.print(f"  [yellow]⚠️  Warning: Track metrics not found[/yellow]")
        
        return reliable_tracks, total_tracks
    
    def _verify_histogram(self, metrics, metric_name, description):
        """Verify histogram metric exists and return statistics including p95."""
        assert metric_name in metrics, f"{description} metric not found"
        
        metric = metrics[metric_name]
        samples = list(metric.samples)
        
        sum_value = None
        count_value = None
        buckets = []  # List of (le_value, cumulative_count)
        
        for sample in samples:
            if sample.name.endswith("_sum"):
                sum_value = sample.value
            elif sample.name.endswith("_count"):
                count_value = int(sample.value)
            elif sample.name.endswith("_bucket"):
                le_value = sample.labels.get("le", "+Inf")
                buckets.append((le_value, int(sample.value)))
        
        # Display sample metrics (first 5)
        for sample in samples[:5]:
            labels_str = ",".join(f'{k}="{v}"' for k, v in sample.labels.items())
            console.print(f"  {sample.name}{{{labels_str}}} {sample.value}")
        if len(samples) > 5:
            console.print(f"  ... and {len(samples) - 5} more data points")
        
        # Calculate p95 from buckets
        p95_value = None
        if count_value and count_value > 0 and buckets:
            p95_threshold = count_value * 0.95
            for le_value, cumulative_count in buckets:
                if cumulative_count >= p95_threshold:
                    # Handle +Inf bucket
                    if le_value == "+Inf":
                        p95_value = None  # Can't determine exact value
                    else:
                        p95_value = float(le_value)
                    break
        
        # Calculate and display statistics
        stats = None
        if sum_value is not None and count_value is not None and count_value > 0:
            avg_duration = sum_value / count_value
            stats = {'sum': sum_value, 'count': count_value, 'avg': avg_duration, 'p95': p95_value}
            console.print(f"  Total observations: {count_value}")
            console.print(f"  Total duration: {sum_value:.2f} ms")
            console.print(f"  Average duration: {avg_duration:.2f} ms")
            if p95_value is not None:
                console.print(f"  p95 latency: {p95_value:.2f} ms")
        
        console.print(f"[green]✓ {description} histogram verified ({len(samples)} data points)[/green]")
        return stats
