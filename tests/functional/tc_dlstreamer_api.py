#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from tests.functional import FunctionalTest
import os
import requests
import json
import time

TEST_NAME = 'NEX-T12678'
HEADERS = {"Content-Type": "application/json"}

class DLStreamerPipelineTest(FunctionalTest):
    def __init__(self, testName, request, recordXMLAttribute):
        super().__init__(testName, request, recordXMLAttribute)
        self.ports = [8080, 8081]
        return

    def load_config(self, path):
        with open(path, 'r') as f:
            return json.load(f)
    
    def wait_until_ready(self, host, port, retries=10, delay=5):
        for i in range(retries):
            try:
                r = requests.get(f"http://{host}:{port}/pipelines")
                if r.status_code == 200:
                    print(f"{host}:{port} is ready")
                    return
            except requests.exceptions.RequestException:
                pass
            print(f"Waiting for {host}:{port} to become ready...")
            time.sleep(delay)
        raise TimeoutError(f"{host}:{port} did not become ready in time")

    def dlstreamer_pipeline_api(self, config_file, host, port):
        config = self.load_config(config_file)
        pipeline = config["config"]["pipelines"][0]
        name = pipeline["name"]
        version = name
        payload = pipeline["payload"]

        api_base = f"http://{host}:{port}"
        # Get running pipelines
        r = requests.get(f"{api_base}/pipelines")
        print(f"Request failed with status {r.status_code}: {r.text}")
        assert r.status_code == 200
        output = r.json()
        for item in output:
            assert item["version"] == version
            assert item["type"] == "GStreamer"

            params = item.get("params", {})
            assert isinstance(params, dict)

        # Create new pipeline
        r = requests.post(f"{api_base}/pipelines/{name}/{version}", headers=HEADERS, data=json.dumps(payload))
        assert r.status_code == 200, f"Create failed: {r.text}"
        pipeline_id = r.json()
        time.sleep(1)

        # Verify created pipeline details
        r = requests.get(f"{api_base}/pipelines/{pipeline_id}")
        assert r.status_code == 200
        instance = r.json()
        assert instance["id"] == pipeline_id
        assert instance["params"]["version"] == version or name  # Depending on implementation
        assert instance["state"] == "RUNNING"

        # Gel all pipelines status
        r = requests.get(f"{api_base}/pipelines/status")
        assert r.status_code == 200
        data = r.json()
        required_keys = {"id", "state", "avg_fps", "elapsed_time"}
        for d in data:
            assert required_keys.issubset(d), f"Missing keys in {d}"
        all_ids = [p["id"] for p in data]
        assert pipeline_id in all_ids

        # Update pipeline config only if pipeline supports it
        # Send request to an already queued pipeline. Supported only for source of type "image_ingestor".
        if name == "image_ingestor":
            update_payload = {
                "timeout": 2,
                "source": {
                    "type": "file",
                    "path": "file:///root/image-examples/example2.jpg"
                },
                "additional_meta_data": {}
            }
            r = requests.post(
                f"{api_base}/pipelines/{name}/{version}/{pipeline_id}",
                headers=HEADERS,
                json=update_payload
            )
            assert r.status_code == 200, f"Update failed: {r.text}"
            time.sleep(1)

        # Delete pipeline
        r = requests.delete(f"{api_base}/pipelines/{pipeline_id}")
        assert r.status_code == 200
        time.sleep(1)

        # Confirm deletion
        r = requests.get(f"{api_base}/pipelines/{pipeline_id}/status")
        assert r.status_code == 200
        instance = r.json()
        assert instance["state"] == "ABORTED"

        # Restart (re-create) pipeline
        r = requests.post(f"{api_base}/pipelines/{name}/{version}", headers=HEADERS, data=json.dumps(payload))
        assert r.status_code == 200
        restarted_id = r.json()
        time.sleep(1)

        r = requests.get(f"{api_base}/pipelines/{restarted_id}/status")
        instance = r.json()
        assert instance["state"] == "RUNNING"

    def runPipelineTest(self):
        self.exitCode = 1
        project = os.environ.get("PROJECT", "default")
        print("PROJECT =", os.environ.get("PROJECT"))
        config_map = [
            ("tests/config_retail_video.json", f"{project}-retail-video-1", 8080),
            ("tests/config_queuing_video.json", f"{project}-queuing-video-1", 8081)
        ]

        for config_file, host, port in config_map:
            self.wait_until_ready(host, port)
            self.dlstreamer_pipeline_api(config_file, host, port)

        self.exitCode = 0
        self.recordTestResult()
        return

def test_dlstreamer_pipeline(request, record_xml_attribute):
    test = DLStreamerPipelineTest(TEST_NAME, request, record_xml_attribute)
    test.runPipelineTest()
    assert test.exitCode == 0
    return

def main():
    return test_dlstreamer_pipeline(None, None)

if __name__ == '__main__':
    os._exit(main() or 0)

