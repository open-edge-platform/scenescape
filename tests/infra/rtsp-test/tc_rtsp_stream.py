#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from argparse import ArgumentParser
import cv2
import tests.common_test_utils as common

TEST_NAME = "NEX-T10424"
EXPECTED_FRAME_COUNT = 90

def stream_url(request):
  return request.config.getoption('--url')

def test_main(record_xml_attribute, request):
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)

  exit_code = -1
  frame_count = 0

  rtsp_link = stream_url(request)
  src = "rtspsrc location=%s protocols=tcp ! rtph264depay ! avdec_h264 ! videoconvert ! appsink max-buffers=1 drop=true" % rtsp_link

  cap = cv2.VideoCapture(src)

  while frame_count < EXPECTED_FRAME_COUNT:
    cap_read_success, frame = cap.read()
    if cap_read_success and frame is not None:
      frame_count += 1
    else:
      break

  cap.release()

  print("Received " + str(frame_count) + " frames from RTSP")
  if frame_count == EXPECTED_FRAME_COUNT:
    exit_code = 0

  common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
