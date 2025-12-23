# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Prometheus metrics client for fetching and parsing metrics."""

from typing import Optional
import requests
from tenacity import retry, stop_after_delay, wait_fixed, retry_if_result
from prometheus_client.parser import text_string_to_metric_families

from .reporting import console


class PrometheusMetrics:
    """Client for fetching and parsing Prometheus metrics."""
    
    def __init__(self, endpoint: str):
        """Initialize with metrics endpoint URL."""
        self.endpoint = endpoint
        self._metrics = None
    
    def fetch(self) -> dict:
        """Fetch and parse metrics from endpoint."""
        response = requests.get(self.endpoint, timeout=5)
        response.raise_for_status()
        self._metrics = self._parse(response.text)
        return self._metrics
    
    def _parse(self, metrics_text: str) -> dict:
        """Parse Prometheus text format into a dict keyed by metric name."""
        metrics = {}
        for family in text_string_to_metric_families(metrics_text):
            metrics[family.name] = family
        return metrics
    
    def get_counter_value(self, metric_name: str) -> Optional[int]:
        """Get value of a counter metric."""
        try:
            response = requests.get(self.endpoint, timeout=5)
            response.raise_for_status()
        except requests.RequestException:
            return None
        
        metrics = self._parse(response.text)
        
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
    
    def wait_for_endpoint(self, timeout: int = 30, interval: int = 1) -> bool:
        """Wait for metrics endpoint to return any metrics (not empty response)."""
        printed_waiting = [False]  # Track if we've printed waiting message
        
        @retry(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(interval),
            retry=retry_if_result(lambda x: not x),
            reraise=True
        )
        def check_endpoint():
            try:
                response = requests.get(self.endpoint, timeout=5)
                response.raise_for_status()
                has_metrics = any(
                    line.strip() and not line.startswith('#') 
                    for line in response.text.split('\n')
                )
                if not has_metrics and not printed_waiting[0]:
                    console.print("  Waiting for metrics data...")
                    printed_waiting[0] = True
                return has_metrics
            except requests.RequestException:
                if not printed_waiting[0]:
                    console.print("  Waiting for metrics endpoint...")
                    printed_waiting[0] = True
                return False
        
        result = check_endpoint()
        console.print("  [green]✓ Metrics endpoint has data[/green]")
        return result
    
    def wait_for_counter(
        self, 
        name: str = None, 
        metric_name: str = None,
        min_value: int = None, 
        expected_value: int = None,
        timeout: int = 30,
        interval: int = 1
    ) -> int:
        """Wait for counter metric to reach expected value.
        
        Args:
            name: Metric name (alias for metric_name)
            metric_name: Metric name
            min_value: Minimum value to wait for (alias for expected_value)
            expected_value: Expected value to wait for
            timeout: Maximum wait time in seconds
            interval: Check interval in seconds
        """
        # Handle parameter aliases
        metric = name or metric_name
        target = min_value if min_value is not None else expected_value
        
        if not metric:
            raise ValueError("Either 'name' or 'metric_name' must be provided")
        if target is None:
            raise ValueError("Either 'min_value' or 'expected_value' must be provided")
        
        last_value = [None]  # Use list to allow mutation in nested function
        
        @retry(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(interval),
            retry=retry_if_result(lambda x: x < target),
            reraise=True
        )
        def check_metric():
            value = self.get_counter_value(metric)
            if value is None:
                try:
                    response = requests.get(self.endpoint, timeout=5)
                    available_metrics = [
                        line.split()[0] 
                        for line in response.text.split('\n') 
                        if line and not line.startswith('#') and '{' in line
                    ]
                    raise RuntimeError(
                        f"Metric {metric} not found. "
                        f"Available metrics: {', '.join(set(available_metrics[:10]))}"
                    )
                except requests.RequestException:
                    raise RuntimeError(f"Metric {metric} not found (endpoint unreachable)")
            # Only print when value changes
            if value != last_value[0]:
                console.print(f"  Current {metric}: {value:,} (waiting for ≥{target:,})")
                last_value[0] = value
            return value
        
        result = check_metric()
        return result
    
    def get_dropped_messages(self, metrics: dict = None) -> int:
        """Check for dropped messages metric and return total count.
        
        Args:
            metrics: Pre-fetched metrics dict. If None, fetches fresh metrics.
        
        Returns:
            Total number of dropped messages.
        """
        if metrics is None:
            metrics = self.fetch()
        
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
                # Store reason info but don't print (shown in summary)
        
        return total_dropped
    
    def get_active_tracks(self, metrics: dict = None) -> Optional[int]:
        """Check for active tracks gauges and return reliable tracks count.
        
        Args:
            metrics: Pre-fetched metrics dict. If None, fetches fresh metrics.
            
        Returns:
            Number of reliable tracks, or None if metric not found.
        """
        reliable, _ = self.get_track_counts(metrics)
        return reliable
    
    def get_track_counts(self, metrics: dict = None) -> tuple[Optional[int], Optional[int]]:
        """Get track counts.
        
        Args:
            metrics: Pre-fetched metrics dict. If None, fetches fresh metrics.
            
        Returns:
            Tuple of (reliable_tracks, total_tracks), either may be None.
        """
        if metrics is None:
            metrics = self.fetch()
        
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
        
        return reliable_tracks, total_tracks
    
    def get_histogram_stats(self, metric_name: str, metrics: dict = None) -> Optional[dict]:
        """Get histogram statistics including p95.
        
        Args:
            metric_name: Name of the histogram metric.
            metrics: Pre-fetched metrics dict. If None, fetches fresh metrics.
            
        Returns:
            Dictionary with 'sum', 'count', 'avg', 'p95', 'buckets' or None if not found.
        """
        if metrics is None:
            metrics = self.fetch()
        
        if metric_name not in metrics:
            return None
        
        metric = metrics[metric_name]
        samples = list(metric.samples)
        
        sum_value = None
        count_value = None
        buckets = {}
        
        for sample in samples:
            if sample.name.endswith("_sum"):
                sum_value = sample.value
            elif sample.name.endswith("_count"):
                count_value = int(sample.value)
            elif sample.name.endswith("_bucket"):
                le_value = sample.labels.get("le", "+Inf")
                buckets[le_value] = int(sample.value)
        
        if sum_value is None or count_value is None or count_value == 0:
            return None
        
        # Calculate p95 from buckets
        p95_value = None
        if buckets:
            p95_threshold = count_value * 0.95
            sorted_buckets = sorted(
                buckets.items(), 
                key=lambda x: float(x[0]) if x[0] != "+Inf" else float('inf')
            )
            for le_value, cumulative_count in sorted_buckets:
                if cumulative_count >= p95_threshold:
                    if le_value != "+Inf":
                        p95_value = float(le_value)
                    break
        
        return {
            'sum': sum_value,
            'count': count_value,
            'avg': sum_value / count_value,
            'p95': p95_value or 0.0,
            'buckets': buckets
        }
