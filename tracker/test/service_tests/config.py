# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Test configuration loader from environment variables."""

import os
import pytest


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
