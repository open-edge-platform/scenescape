# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Rich console output and test reporting utilities."""

from rich.console import Console
from rich.table import Table
from typing import Dict, Any, Optional


# Shared console instance for consistent output
console = Console()


class LoadTestReporter:
    """Test result reporting with rich formatting."""
    
    def __init__(self, test_name: str = "Service Test"):
        self.test_name = test_name
    
    def section(self, title: str, style: str = "bold blue") -> None:
        """Print a section header."""
        console.print(f"\n[{style}]{'=' * 60}[/{style}]")
        console.print(f"[{style}]{title}[/{style}]")
        console.print(f"[{style}]{'=' * 60}[/{style}]")
    
    def print_config(self, config: Dict[str, Any]) -> None:
        """Print test configuration as a table."""
        table = Table(title="Test Configuration", show_header=True, header_style="bold cyan")
        table.add_column("Parameter", style="dim")
        table.add_column("Value")
        
        for key, value in config.items():
            table.add_row(key, str(value))
        
        console.print(table)
    
    def print_metrics_summary(
        self,
        received_messages: int,
        expected_messages: int,
        dropped_messages: int = 0,
        reliable_tracks: Optional[int] = None,
        total_tracks: Optional[int] = None,
        mqtt_handler: Optional[Dict[str, Any]] = None,
        tracking_duration: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Print comprehensive metrics summary as a table."""
        table = Table(title="Metrics Summary", show_header=True, header_style="bold green")
        table.add_column("Metric", style="dim")
        table.add_column("Value")
        table.add_column("Status")
        
        # Message counts
        msg_status = "✅" if received_messages >= expected_messages else "⚠️"
        table.add_row(
            "Messages Received",
            f"{received_messages:,} / {expected_messages:,} expected",
            msg_status
        )
        
        drop_status = "✅" if dropped_messages == 0 else "⚠️"
        table.add_row(
            "Dropped Messages",
            f"{dropped_messages:,}",
            drop_status
        )
        
        # Track counts
        if reliable_tracks is not None:
            track_status = "✅" if reliable_tracks > 0 else "⚠️"
            track_value = f"{reliable_tracks:,}"
            if total_tracks is not None:
                unreliable = total_tracks - reliable_tracks
                track_value = f"{reliable_tracks:,} reliable, {unreliable:,} unreliable"
            table.add_row("Active Tracks", track_value, track_status)
        
        # MQTT Handler Duration
        if mqtt_handler:
            p95 = mqtt_handler.get("p95", 0)
            avg = mqtt_handler.get("avg", 0)
            latency_status = "✅" if p95 < 100 else "⚠️"
            table.add_row(
                "MQTT Handler Duration",
                f"p95={p95:.2f}ms, avg={avg:.2f}ms",
                latency_status
            )
        
        # Tracking Duration
        if tracking_duration:
            p95 = tracking_duration.get("p95", 0)
            avg = tracking_duration.get("avg", 0)
            latency_status = "✅" if p95 < 100 else "⚠️"
            table.add_row(
                "Tracking Duration",
                f"p95={p95:.2f}ms, avg={avg:.2f}ms",
                latency_status
            )
        
        console.print(table)
