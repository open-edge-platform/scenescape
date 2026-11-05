# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Small command-line client for the Observation Processor gRPC service."""

import argparse
import sys

import grpc
from google.protobuf import text_format

from observation_processor.grpc_api import observation_processor_pb2 as pb
from observation_processor.grpc_api import observation_processor_pb2_grpc

MODES = {
  "auto": pb.CONDITIONING_MODE_AUTO,
  "full": pb.CONDITIONING_MODE_FULL,
  "frustum-only": pb.CONDITIONING_MODE_FRUSTUM_ONLY,
}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--target", default="localhost:50052")
  parser.add_argument("--scene-id", required=True)
  parser.add_argument("--camera-id", required=True)
  parser.add_argument("--category", default="person")
  parser.add_argument("--detection-id", default="example-detection")
  parser.add_argument("--box", nargs=4, type=float, metavar=("X", "Y", "WIDTH", "HEIGHT"),
                      required=True)
  parser.add_argument("--mode", choices=MODES, default="auto")
  parser.add_argument("--include-diagnostics", action="store_true")
  parser.add_argument("--timeout", type=float, default=10.0)
  args = parser.parse_args()

  request = pb.ProcessDetectionsRequest(
    scene_id=args.scene_id,
    camera_id=args.camera_id,
    mode=MODES[args.mode],
    include_diagnostics=args.include_diagnostics,
  )
  request.timestamp.GetCurrentTime()
  request.detections.add(
    detection_id=args.detection_id,
    category=args.category,
    bounding_box_px=pb.BoundingBoxPx(
      x=args.box[0], y=args.box[1], width=args.box[2], height=args.box[3]),
  )

  try:
    with grpc.insecure_channel(args.target) as channel:
      response = observation_processor_pb2_grpc.ObservationProcessorServiceStub(
        channel).ProcessDetections(
        request, timeout=args.timeout)
  except grpc.RpcError as exc:
    print(f"gRPC request failed: {exc.code().name}: {exc.details()}", file=sys.stderr)
    return 1

  print(text_format.MessageToString(response))
  return 0


if __name__ == "__main__":
  sys.exit(main())