# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Camera source handling in the DL Streamer pipeline generator."""

import pytest

from manager.ppl_generator import PipelineGenerationValueError
from manager.ppl_generator.pipeline_generator import PipelineGenerator

MODEL_CONFIG = {
  'retail': {
    'type': 'detect',
    'params': {'model': 'omz/retail/retail.xml'},
  }
}


def _generate(command, cv_subsystem='AUTO'):
  settings = {'command': command, 'camerachain': 'retail', 'cv_subsystem': cv_subsystem}
  return PipelineGenerator(settings, MODEL_CONFIG).generate()


@pytest.mark.parametrize('cv_subsystem', ['AUTO', 'GPU', 'CPU'])
@pytest.mark.parametrize('device', ['/dev/video0', '/dev/video10', '/dev/v4l/by-id/usb-cam-video-index0'])
def test_v4l2_source_converts_raw_video(device, cv_subsystem):
  """Raw V4L2 video is converted, not routed through a decodebin."""
  pipeline = _generate(device, cv_subsystem)
  assert pipeline.startswith(f'v4l2src device={device} name=source ! videoconvert ! ')
  assert 'decodebin' not in pipeline
  assert ('video/x-raw,format=BGR' in pipeline) == (cv_subsystem == 'CPU')


@pytest.mark.parametrize('command, expected_source', [
  ('rtsp://camera:554/stream', 'rtspsrc location=rtsp://camera:554/stream latency=200 name=source'),
  ('http://camera/mjpeg', 'souphttpsrc location=http://camera/mjpeg name=source ! multipartdemux'),
  ('https://camera/mjpeg', 'souphttpsrc location=https://camera/mjpeg name=source ! multipartdemux'),
])
def test_network_sources_use_decodebin3(command, expected_source):
  """Compressed network streams still go through decodebin3."""
  pipeline = _generate(command)
  assert pipeline.startswith(f'{expected_source} ! decodebin3 ! ')


@pytest.mark.parametrize('command', [
  '', 'ftp://camera/stream', '/dev/sda', '/dev/video0/../sda', 'camera.ts',
])
def test_unsupported_sources_rejected(command):
  with pytest.raises(PipelineGenerationValueError):
    _generate(command)
