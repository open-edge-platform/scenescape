#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Mock remote projection service for tracker service tests.

Implements scenescape.projection.v1.ProjectionService from the contract mounted at
/protos/projection/v1/projection.proto. Each detection gets a deterministic measurement derived
from its pixel box: centre (x / 20, y / 20, HEIGHT_M / 2), size 0.5 x 0.5 x HEIGHT_M and a
diagonal noise covariance R.

Environment:
  MOCK_PROJECTION_STATUS    gRPC status name returned for every call (for example UNAVAILABLE);
                            empty for successful replies.
  MOCK_PROJECTION_DELAY_MS  Delay before each reply, in milliseconds.
"""

import os
import sys
import time
from concurrent import futures

import grpc

sys.path.insert(0, "/protos")
protos, services = grpc.protos_and_services("projection/v1/projection.proto")

PORT = 50051
HEIGHT_M = 1.7
NOISE_DIAGONAL = [0.01, 0.01, 0.04, 0.2, 0.2, 0.2, 0.2]
NOISE_COVARIANCE = [NOISE_DIAGONAL[i // 7] if i // 7 == i % 7 else 0.0 for i in range(49)]

STATUS = os.environ.get("MOCK_PROJECTION_STATUS", "")
DELAY_S = int(os.environ.get("MOCK_PROJECTION_DELAY_MS", "0") or 0) / 1000.0


class MockProjectionService(services.ProjectionServiceServicer):

  def ProjectDetections(self, request, context):
    categories = sorted({detection.category for detection in request.detections})
    print(f"request scene={request.scene_id} camera={request.camera_id} "
          f"mode={protos.ConditioningMode.Name(request.mode)} "
          f"detections={len(request.detections)} categories={','.join(categories)}", flush=True)
    if DELAY_S > 0:
      time.sleep(DELAY_S)
    if STATUS:
      context.abort(getattr(grpc.StatusCode, STATUS), "mock projection failure")

    response = protos.ProjectDetectionsResponse(
        scene_id=request.scene_id, camera_id=request.camera_id, timestamp=request.timestamp,
        mode=protos.CONDITIONING_MODE_FRUSTUM_ONLY)
    for detection in request.detections:
      box = detection.bounding_box_px
      measurement = response.measurements.add(
          detection_id=detection.detection_id, status=protos.MEASUREMENT_STATUS_OK,
          depth_source=protos.DEPTH_SOURCE_FRUSTUM)
      measurement.measurement.mean.extend(
          [box.x / 20.0, box.y / 20.0, HEIGHT_M / 2.0, 0.5, 0.5, HEIGHT_M, 0.0])
      measurement.measurement.noise_covariance.extend(NOISE_COVARIANCE)
      measurement.measurement.z_measured = True
    return response


def main():
  server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
  services.add_ProjectionServiceServicer_to_server(MockProjectionService(), server)
  server.add_insecure_port(f"[::]:{PORT}")
  server.start()
  print(f"Mock projection service listening on {PORT} (status={STATUS or 'OK'}, "
        f"delay={DELAY_S * 1000:.0f}ms)", flush=True)
  server.wait_for_termination()


if __name__ == "__main__":
  main()
