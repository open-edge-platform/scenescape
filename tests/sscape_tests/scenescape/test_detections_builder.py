# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from controller.detections_builder import buildDetectionsDict, buildDetectionsList, prepareObjDict
from controller.scene import TripwireEvent
from controller.moving_object import ChainData
from scene_common.geometry import Point
from scene_common.timestamp import get_iso_time


def _build_object(*, velocity=None, include_sensor_payload=True):
  chain_data = ChainData(
    regions={'region-a': {'entered': '2026-03-31T10:00:00Z'}},
    publishedLocations=[],
    persist={'asset_tag': 'forklift-7'},
  )

  if include_sensor_payload:
    chain_data.env_sensor_state['temp-1'] = {'readings': [('2026-03-31T10:00:00Z', 21.5)]}
    chain_data.attr_sensor_events['badge-1'] = [('2026-03-31T10:00:00Z', 'authorized')]

  return SimpleNamespace(
    category='person',
    gid='object-1',
    sceneLoc=Point(1.0, 2.0, 3.0),
    velocity=velocity,
    info={'source': 'camera-1', 'bb_meters': {'width': 1.2, 'height': 2.3}},
    size={'width': 1.2, 'height': 2.3, 'length': 0.7},
    rotation={'yaw': 90.0},
    metadata={'age': 'adult', 'reid': 'discard-me'},
    reid={'embedding_vector': np.array([0.1, 0.2], dtype=np.float32), 'model_name': 'reid-model'},
    visibility={'cam-1': True},
    vectors=[SimpleNamespace(camera=SimpleNamespace(cameraID='cam-1'))],
    boundingBoxPixels=SimpleNamespace(asDict={'x': 10, 'y': 20, 'width': 30, 'height': 40}),
    chain_data=chain_data,
    confidence=0.97,
    similarity=0.88,
    first_seen=1711886400,
    asset_scale=1.25
  )


class TestDetectionsBuilder:
  def test_build_detections_list_returns_empty_for_no_objects(self):
    scene = SimpleNamespace(output_lla=False)

    detections = buildDetectionsList([], scene)

    assert detections == []

  def test_build_detections_dict_returns_empty_for_no_objects(self):
    scene = SimpleNamespace(output_lla=False)

    detections = buildDetectionsDict([], scene)

    assert detections == {}

  def test_build_detections_list_serializes_metadata_sensors_and_visibility(self):
    obj = _build_object(velocity=Point(4.0, 5.0))
    scene = SimpleNamespace(output_lla=False)

    detections = buildDetectionsList([obj], scene, update_visibility=True, include_sensors=True)

    assert len(detections) == 1

    detection = detections[0]
    assert detection['id'] == 'object-1'
    assert detection['type'] == 'person'
    assert detection['translation'] == [1.0, 2.0, 3.0]
    assert detection['velocity'] == [4.0, 5.0]
    assert detection['rotation'] == {'yaw': 90.0}
    assert detection['metadata']['age'] == 'adult'
    assert np.allclose(detection['metadata']['reid']['embedding_vector'], [0.1, 0.2])
    assert detection['metadata']['reid']['model_name'] == 'reid-model'
    assert detection['sensors']['temp-1']['values'][0][1] == 21.5
    assert detection['sensors']['badge-1']['values'][0][1] == 'authorized'
    assert detection['regions'] == {'region-a': {'entered': '2026-03-31T10:00:00Z'}}
    assert detection['camera_bounds'] == {
      'cam-1': {'x': 10, 'y': 20, 'width': 30, 'height': 40, 'projected': False}
    }
    assert detection['persistent_data'] == {'asset_tag': 'forklift-7'}
    assert detection['first_seen'] == get_iso_time(obj.first_seen)

  def test_build_detections_list_omits_sensor_data_when_disabled(self):
    obj = _build_object(velocity=Point(4.0, 5.0))
    scene = SimpleNamespace(output_lla=False)

    detections = buildDetectionsList([obj], scene, include_sensors=False)

    assert len(detections) == 1
    assert 'sensors' not in detections[0]
    assert detections[0]['regions'] == {'region-a': {'entered': '2026-03-31T10:00:00Z'}}

  def test_build_detections_list_does_not_leak_sensors_between_calls(self):
    obj = _build_object(velocity=Point(4.0, 5.0))
    scene = SimpleNamespace(output_lla=False)

    with_sensors = buildDetectionsList([obj], scene, include_sensors=True)
    without_sensors = buildDetectionsList([obj], scene, include_sensors=False)

    assert 'sensors' in with_sensors[0]
    assert 'sensors' not in without_sensors[0]

  def test_build_detections_dict_handles_tripwire_and_defaults_missing_velocity(self):
    obj = _build_object(velocity=None, include_sensor_payload=False)
    scene = SimpleNamespace(output_lla=False)
    event = TripwireEvent(obj, 'entering')

    detections = buildDetectionsDict([event], scene)

    assert list(detections.keys()) == ['object-1']
    detection = detections['object-1']
    assert detection['velocity'] == [0, 0]
    assert detection['direction'] == 'entering'
    assert 'sensors' not in detection

  def test_prepare_obj_dict_omits_reid_metadata_when_embedding_is_none(self):
    obj = _build_object(velocity=Point(4.0, 5.0), include_sensor_payload=False)
    obj.reid = {'embedding_vector': None, 'model_name': 'ignored-model'}

    detection = prepareObjDict(SimpleNamespace(output_lla=False), obj, update_visibility=False)

    assert 'reid' not in detection['metadata']

  def test_prepare_obj_dict_handles_chain_data_without_sensor_fields(self):
    obj = _build_object(velocity=Point(4.0, 5.0), include_sensor_payload=False)
    obj.chain_data = ChainData(regions=[], persist={}, publishedLocations=[])

    detection = prepareObjDict(SimpleNamespace(output_lla=False), obj, update_visibility=False, include_sensors=True)

    assert 'sensors' not in detection

  def test_prepare_obj_dict_raises_with_missing_gid(self):
    obj = _build_object(velocity=Point(4.0, 5.0), include_sensor_payload=False)
    del obj.gid

    with pytest.raises(AttributeError):
      prepareObjDict(SimpleNamespace(output_lla=False), obj, update_visibility=False)

  def test_prepare_obj_dict_raises_with_missing_chain_data(self):
    obj = _build_object(velocity=Point(4.0, 5.0), include_sensor_payload=False)
    del obj.chain_data

    with pytest.raises(AttributeError):
      prepareObjDict(SimpleNamespace(output_lla=False), obj, update_visibility=False)

  @patch('controller.detections_builder.calculateHeading')
  @patch('controller.detections_builder.convertXYZToLLA')
  def test_prepare_obj_dict_adds_lla_output_when_enabled(self, mock_convert_xyz_to_lla, mock_calculate_heading):
    obj = _build_object(velocity=Point(4.0, 5.0, 6.0), include_sensor_payload=False)
    scene = SimpleNamespace(output_lla=True, trs_xyz_to_lla='trs-transform')
    mock_convert_xyz_to_lla.return_value = np.array([45.0, -122.0, 12.0])
    mock_calculate_heading.return_value = np.array([180.0])

    detection = prepareObjDict(scene, obj, update_visibility=False)

    assert detection['lat_long_alt'] == [45.0, -122.0, 12.0]
    assert detection['heading'] == [180.0]
    mock_convert_xyz_to_lla.assert_called_once_with('trs-transform', [1.0, 2.0, 3.0])
    mock_calculate_heading.assert_called_once_with('trs-transform', [1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
