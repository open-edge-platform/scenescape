# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""K6 load test runner."""

import os
import json
import subprocess
from dataclasses import dataclass
from typing import Optional

from .reporting import console


@dataclass
class K6Result:
    """Result from a K6 load test run."""
    returncode: int
    iterations: Optional[int] = None
    
    @property
    def success(self) -> bool:
        return self.returncode == 0


def run_k6_test(config: dict, script_dir: Optional[str] = None) -> K6Result:
    """
    Run K6 load test with configured parameters.
    
    Args:
        config: Test configuration dict with mqtt_host, camera_count, etc.
        script_dir: Directory containing generate-detections.js (defaults to test/)
    
    Returns:
        K6Result with returncode and iterations count
    """
    if script_dir is None:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    k6_script = os.path.join(script_dir, "generate-detections.js")
    summary_file = os.path.join(script_dir, "k6-summary.json")
    
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
    iterations = None
    try:
        with open(summary_file, 'r') as f:
            summary = json.load(f)
            iterations = int(summary['metrics']['iterations']['count'])
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        console.print(f"[yellow]Warning: Could not parse K6 summary: {e}[/yellow]")
    
    return K6Result(returncode=result.returncode, iterations=iterations)
