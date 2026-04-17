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
from scene_common.timestamp import get_epoch_time, get_iso_time


def _build_object(*, velocity=None, include_sensor_payload=True):
  chain_data = ChainData(
    regions={'region-a': {'entered': '2026-03-31T10:00:00.000Z'}},
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


def _build_object_with_regions(gid, regions, *, velocity=None):
  obj = _build_object(velocity=velocity, include_sensor_payload=False)
  obj.gid = gid
  obj.chain_data.regions = regions
  return obj


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
    assert detection['regions'] == {'region-a': {'entered': '2026-03-31T10:00:00.000Z'}}
    assert detection['camera_bounds'] == {
      'cam-1': {'x': 10, 'y': 20, 'width': 30, 'height': 40, 'projected': False}
    }
    assert detection['persistent_data'] == {'asset_tag': 'forklift-7'}
    assert detection['first_seen'] == get_iso_time(obj.first_seen)

  def test_build_detections_list_adds_region_dwell_when_requested(self):
    obj = _build_object(velocity=Point(4.0, 5.0))
    scene = SimpleNamespace(output_lla=False)

    detections = buildDetectionsList(
      [obj], scene, include_sensors=True,
      include_region_dwell=True, current_time=get_epoch_time('2026-03-31T10:00:05.000Z'))

    assert detections[0]['regions']['region-a']['entered'] == '2026-03-31T10:00:00.000Z'
    assert detections[0]['regions']['region-a']['dwell'] == pytest.approx(5.0)

  @patch('controller.detections_builder.get_epoch_time', return_value=10.0)
  def test_build_detections_list_reuses_cached_entered_epoch(self, mock_get_epoch_time):
    scene = SimpleNamespace(output_lla=False)
    obj = _build_object_with_regions(
      'object-1', {'region-a': {'entered': '2026-03-31T10:00:00.000Z'}}, velocity=Point(1.0, 0.0))

    first = buildDetectionsList([obj], scene, include_region_dwell=True, current_time=15.0)
    second = buildDetectionsList([obj], scene, include_region_dwell=True, current_time=16.0)

    assert first[0]['regions']['region-a']['dwell'] == pytest.approx(5.0)
    assert second[0]['regions']['region-a']['dwell'] == pytest.approx(6.0)
    assert mock_get_epoch_time.call_count == 1

  def test_build_detections_list_dwell_requires_entered_timestamp(self):
    scene = SimpleNamespace(output_lla=False)
    obj = _build_object_with_regions(
      'object-1', {'region-a': {'entered_epoch': 20.0}}, velocity=Point(1.0, 0.0))

    detections = buildDetectionsList([obj], scene, include_region_dwell=True, current_time=25.0)

    assert 'dwell' not in detections[0]['regions']['region-a']

  def test_build_detections_list_adds_region_dwell_for_multiple_objects_multiple_regions(self):
    scene = SimpleNamespace(output_lla=False)
    obj_1 = _build_object_with_regions(
      'object-1',
      {
        'region-a': {'entered': '2026-03-31T10:00:00.000Z'},
        'region-b': {'entered': '2026-03-31T10:00:06.000Z'},
      },
      velocity=Point(2.0, 0.0),
    )
    obj_2 = _build_object_with_regions(
      'object-2',
      {
        'region-a': {'entered': '2026-03-31T10:00:02.000Z'},
        'region-c': {'entered': '2026-03-31T10:00:08.000Z'},
      },
      velocity=Point(0.0, 2.0),
    )

    detections = buildDetectionsList(
      [obj_1, obj_2], scene, include_region_dwell=True,
      current_time=get_epoch_time('2026-03-31T10:00:12.000Z'))

    detections_by_id = {detection['id']: detection for detection in detections}
    assert detections_by_id['object-1']['regions']['region-a']['dwell'] == pytest.approx(12.0)
    assert detections_by_id['object-1']['regions']['region-b']['dwell'] == pytest.approx(6.0)
    assert detections_by_id['object-2']['regions']['region-a']['dwell'] == pytest.approx(10.0)
    assert detections_by_id['object-2']['regions']['region-c']['dwell'] == pytest.approx(4.0)

  def test_build_detections_list_omits_sensor_data_when_disabled(self):
    obj = _build_object(velocity=Point(4.0, 5.0))
    scene = SimpleNamespace(output_lla=False)

    detections = buildDetectionsList([obj], scene, include_sensors=False)

    assert len(detections) == 1
    assert 'sensors' not in detections[0]
    assert detections[0]['regions'] == {'region-a': {'entered': '2026-03-31T10:00:00.000Z'}}

  def test_build_detections_list_does_not_leak_sensors_between_calls(self):
    obj = _build_object(velocity=Point(4.0, 5.0))
    scene = SimpleNamespace(output_lla=False)

    with_sensors = buildDetectionsList([obj], scene, include_sensors=True)
    without_sensors = buildDetectionsList([obj], scene, include_sensors=False)

    assert 'sensors' in with_sensors[0]
    assert 'sensors' not in without_sensors[0]
    assert 'dwell' not in with_sensors[0]['regions']['region-a']
    assert 'dwell' not in without_sensors[0]['regions']['region-a']

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

  def test_region_dwell_increases_while_object_in_region(self):
    """Functional test verifying dwell time updates continuously while object remains in region."""
    scene = SimpleNamespace(output_lla=False)
    entry_time_str = '2026-03-31T10:00:00.000Z'
    entry_epoch = get_epoch_time(entry_time_str)

    obj = _build_object_with_regions(
      'object-1',
      {'region-a': {'entered': entry_time_str}},
      velocity=Point(1.0, 0.0),
    )

    # Query dwell at multiple time points while object is in the region
    query_time_1 = entry_epoch + 2.0  # 2 seconds after entering
    query_time_2 = entry_epoch + 5.0  # 5 seconds after entering
    query_time_3 = entry_epoch + 8.5  # 8.5 seconds after entering

    dwell_at_t1 = buildDetectionsList(
      [obj], scene, include_region_dwell=True, current_time=query_time_1)[0]['regions']['region-a']['dwell']
    dwell_at_t2 = buildDetectionsList(
      [obj], scene, include_region_dwell=True, current_time=query_time_2)[0]['regions']['region-a']['dwell']
    dwell_at_t3 = buildDetectionsList(
      [obj], scene, include_region_dwell=True, current_time=query_time_3)[0]['regions']['region-a']['dwell']

    # Verify dwell increases consistently
    assert dwell_at_t1 == pytest.approx(2.0)
    assert dwell_at_t2 == pytest.approx(5.0)
    assert dwell_at_t3 == pytest.approx(8.5)

    # Verify dwell differences match time intervals
    assert (dwell_at_t2 - dwell_at_t1) == pytest.approx(3.0)  # 5.0 - 2.0 = 3.0 second interval
    assert (dwell_at_t3 - dwell_at_t2) == pytest.approx(3.5)  # 8.5 - 5.0 = 3.5 second interval
    assert (dwell_at_t3 - dwell_at_t1) == pytest.approx(6.5)  # 8.5 - 2.0 = 6.5 second interval
