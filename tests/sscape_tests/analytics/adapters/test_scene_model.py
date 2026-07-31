# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from analytics.adapters.scene_model import AnalyticsScene
from analytics.state import AnalyticsStateStore
from scene_common.geometry import Point, Region


def _scene():
  return AnalyticsScene("test-scene", None)


class TestAnalyticsSceneInit:

  def test_sets_basic_defaults(self):
    scene = _scene()

    assert scene.name == "test-scene"
    assert scene.use_tracker is False
    assert scene.persist_attributes == {}
    assert scene.regulated_rate == 30
    assert scene.external_update_rate == 30
    assert isinstance(scene.analytics_state, AnalyticsStateStore)

  def test_inherits_empty_collections_from_scene_model(self):
    scene = _scene()

    assert scene.regions == {}
    assert scene.tripwires == {}
    assert scene.sensors == {}
    assert scene.cameras == {}


class TestHydrateFromSceneData:

  def test_minimal_scene_data_sets_name_and_defaults(self):
    scene = _scene()

    scene._hydrateFromSceneData({'name': 'hydrated'})

    assert scene.name == 'hydrated'
    assert scene.parent is None
    assert scene.cameraPose is None
    assert scene.retrack is True
    assert scene.persist_attributes == {}

  def test_transform_present_builds_camera_pose(self):
    scene = _scene()
    transform = {'translation': [1, 2, 3]}

    with patch('analytics.adapters.scene_model.CameraPose') as mock_pose:
      mock_pose.return_value = 'pose-instance'
      scene._hydrateFromSceneData({'name': 's', 'transform': transform})

    mock_pose.assert_called_once_with(transform, None)
    assert scene.cameraPose == 'pose-instance'

  def test_children_names_extracted(self):
    scene = _scene()

    scene._hydrateFromSceneData({
      'name': 's', 'children': [{'name': 'child-a'}, {'name': 'child-b'}],
    })

    assert scene.children == ['child-a', 'child-b']

  def test_optional_scalar_fields_applied_when_present(self):
    scene = _scene()

    scene._hydrateFromSceneData({
      'name': 's', 'scale': 2.5, 'regulated_rate': 10, 'external_update_rate': 15,
    })

    assert scene.scale == 2.5
    assert scene.regulated_rate == 10
    assert scene.external_update_rate == 15

  def test_optional_scalar_fields_untouched_when_absent(self):
    scene = _scene()

    scene._hydrateFromSceneData({'name': 's'})

    assert scene.regulated_rate == 30
    assert scene.external_update_rate == 30

  def test_delegates_to_camera_region_tripwire_updaters(self):
    scene = _scene()
    scene.updateCameras = MagicMock()
    scene._updateRegions = MagicMock()
    scene._updateTripwires = MagicMock()
    cameras = [{'uid': 'cam1'}]
    regions = [{'uid': 'r1'}]
    tripwires = [{'uid': 'tw1'}]
    sensors = [{'uid': 'sen1'}]

    scene._hydrateFromSceneData({
      'name': 's', 'cameras': cameras, 'regions': regions,
      'tripwires': tripwires, 'sensors': sensors,
    })

    scene.updateCameras.assert_called_once_with(cameras)
    scene._updateTripwires.assert_called_once_with(tripwires)
    assert scene._updateRegions.call_args_list[0].args == (scene.regions, regions)
    assert scene._updateRegions.call_args_list[1].args == (scene.sensors, sensors)


class TestUpdateCameras:

  def test_adds_new_camera(self):
    scene = _scene()
    stub_camera = SimpleNamespace(cameraID='cam1')

    with patch('analytics.adapters.scene_model.Camera', return_value=stub_camera) as mock_camera:
      scene.updateCameras([{'uid': 'cam1', 'resolution': (640, 480)}])

    mock_camera.assert_called_once_with('cam1', {'uid': 'cam1', 'resolution': (640, 480)},
                                         resolution=(640, 480))
    assert scene.cameras['cam1'] is stub_camera

  def test_removes_deleted_camera(self):
    scene = _scene()
    with patch('analytics.adapters.scene_model.Camera', return_value=SimpleNamespace(cameraID='cam1')):
      scene.updateCameras([{'uid': 'cam1', 'resolution': (640, 480)}])

    scene.updateCameras([])

    assert scene.cameras == {}


class TestUpdateRegions:

  def test_adds_new_region(self, make_region):
    scene = _scene()

    scene._updateRegions(scene.regions, [{'uid': 'r1', 'name': 'R1', 'points': [
      [0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0],
    ]}])

    assert isinstance(scene.regions['r1'], Region)
    assert scene.regions['r1'].name == 'R1'

  def test_update_existing_region_preserves_cached_value_fields(self):
    scene = _scene()
    region_data = {'uid': 'r1', 'name': 'R1', 'points': [
      [0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0],
    ]}
    scene._updateRegions(scene.regions, [region_data])
    scene.regions['r1'].value = 21.5
    scene.regions['r1'].lastValue = 20.0
    scene.regions['r1'].lastWhen = 5.0

    scene._updateRegions(scene.regions, [region_data])

    assert scene.regions['r1'].value == 21.5
    assert scene.regions['r1'].lastValue == 20.0
    assert scene.regions['r1'].lastWhen == 5.0

  def test_deleted_region_removed_and_state_cleared(self):
    scene = _scene()
    region_data = {'uid': 'r1', 'name': 'R1', 'points': [
      [0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0],
    ]}
    scene._updateRegions(scene.regions, [region_data])
    scene.analytics_state.remove_region = MagicMock()

    scene._updateRegions(scene.regions, [])

    assert 'r1' not in scene.regions
    scene.analytics_state.remove_region.assert_called_once_with('r1')


class TestUpdateTripwires:

  def test_adds_new_tripwire(self):
    scene = _scene()

    scene._updateTripwires([{'uid': 'tw1', 'name': 'TW1', 'points': [[0.0, 0.0], [10.0, 0.0]]}])

    assert 'tw1' in scene.tripwires

  def test_deleted_tripwire_removed_and_state_cleared(self):
    scene = _scene()
    scene._updateTripwires([{'uid': 'tw1', 'name': 'TW1', 'points': [[0.0, 0.0], [10.0, 0.0]]}])
    scene.analytics_state.remove_tripwire = MagicMock()

    scene._updateTripwires([])

    assert 'tw1' not in scene.tripwires
    scene.analytics_state.remove_tripwire.assert_called_once_with('tw1')


class TestSyncAndTrackedObjects:

  def test_sync_analytics_objects_calls_ingestion_ingest(self):
    scene = _scene()
    scene._ingestion = MagicMock()

    scene.syncAnalyticsObjects('person', ['obj-a'])

    scene._ingestion.ingest.assert_called_once_with('person', ['obj-a'], scene.sensors)

  def test_update_tracked_objects_delegates_to_sync(self):
    scene = _scene()
    scene.syncAnalyticsObjects = MagicMock()

    scene.updateTrackedObjects('person', ['obj-a'])

    scene.syncAnalyticsObjects.assert_called_once_with('person', ['obj-a'])

  def test_get_tracked_objects_delegates_to_ingestion(self):
    scene = _scene()
    scene._ingestion = MagicMock()
    scene._ingestion.get_objects.return_value = ['obj-a']

    result = scene.getTrackedObjects('person')

    scene._ingestion.get_objects.assert_called_once_with('person')
    assert result == ['obj-a']


class TestProcessSensorData:

  def _obj(self, loc):
    from scene_common.chain_data import ChainData
    return SimpleNamespace(
      sceneLoc=loc,
      chain_data=ChainData(regions={}, publishedLocations=[], persist={}),
    )

  def test_unknown_sensor_returns_false(self):
    scene = _scene()

    result = scene.processSensorData({'id': 'missing', 'value': 1}, 10.0)

    assert result is False

  def test_stale_data_discarded_when_when_not_after_lastwhen(self, make_region):
    scene = _scene()
    sensor = make_region('sen1', 'Sensor', area='scene', singleton_type='environmental')
    sensor.lastWhen = 10.0
    scene.sensors['sen1'] = sensor

    result = scene.processSensorData({'id': 'sen1', 'value': 42}, 5.0)

    assert result is True
    assert not hasattr(sensor, 'value')

  def test_environmental_sensor_updates_objects_in_range(self, make_region):
    scene = _scene()
    sensor = make_region('sen1', 'Sensor', area='scene', singleton_type='environmental')
    scene.sensors['sen1'] = sensor
    obj = self._obj(Point(1.0, 1.0, 0.0))
    scene._analytics_objects['obj-1'] = obj

    with patch('analytics.adapters.scene_model.update_environmental_sensor_readings',
               return_value=True) as mock_update:
      result = scene.processSensorData({'id': 'sen1', 'value': 21.5}, 10.0)

    assert result is True
    mock_update.assert_called_once()
    assert 'sen1' in obj.chain_data.active_sensors
    assert sensor.value == 21.5

  def test_environmental_sensor_failure_propagates_false(self, make_region):
    scene = _scene()
    sensor = make_region('sen1', 'Sensor', area='scene', singleton_type='environmental')
    scene.sensors['sen1'] = sensor
    obj = self._obj(Point(1.0, 1.0, 0.0))
    scene._analytics_objects['obj-1'] = obj

    with patch('analytics.adapters.scene_model.update_environmental_sensor_readings',
               return_value=False):
      result = scene.processSensorData({'id': 'sen1', 'value': 'bad'}, 10.0)

    assert result is False

  def test_attribute_sensor_calls_update_attribute_sensor_events(self, make_region):
    scene = _scene()
    sensor = make_region('sen1', 'Sensor', area='scene', singleton_type='attribute')
    scene.sensors['sen1'] = sensor
    obj = self._obj(Point(1.0, 1.0, 0.0))
    scene._analytics_objects['obj-1'] = obj

    with patch('analytics.adapters.scene_model.update_attribute_sensor_events') as mock_update:
      result = scene.processSensorData({'id': 'sen1', 'value': 'authorized'}, 10.0)

    assert result is True
    mock_update.assert_called_once()

  def test_non_scene_wide_sensor_filters_objects_by_point_containment(self, make_region):
    scene = _scene()
    sensor = make_region('sen1', 'Sensor', singleton_type='environmental', points=[
      [0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0],
    ])
    scene.sensors['sen1'] = sensor
    inside = self._obj(Point(5.0, 5.0, 0.0))
    outside = self._obj(Point(50.0, 50.0, 0.0))
    scene._analytics_objects['inside'] = inside
    scene._analytics_objects['outside'] = outside

    with patch('analytics.adapters.scene_model.update_environmental_sensor_readings',
               return_value=True) as mock_update:
      scene.processSensorData({'id': 'sen1', 'value': 21.5}, 10.0)

    called_objects = mock_update.call_args.args[0]
    assert inside in called_objects
    assert outside not in called_objects


class TestUpdateEvents:

  def test_uses_provided_current_objects_and_skips_publish_when_no_fn(self):
    scene = _scene()
    obj = MagicMock()

    with patch('analytics.adapters.scene_model.moving_object_to_analytics_object',
               side_effect=lambda o: o) as mock_convert, \
         patch('analytics.adapters.scene_model.process_frame') as mock_process, \
         patch('analytics.adapters.scene_model.publish_events') as mock_publish:
      scene._updateEvents('person', 10.0, curObjects=[obj])

    mock_convert.assert_called_once_with(obj)
    mock_process.assert_called_once()
    mock_publish.assert_not_called()

  def test_fetches_tracked_objects_when_none_provided(self):
    scene = _scene()
    scene.getTrackedObjects = MagicMock(return_value=['raw-obj'])

    with patch('analytics.adapters.scene_model.moving_object_to_analytics_object',
               side_effect=lambda o: o), \
         patch('analytics.adapters.scene_model.process_frame'), \
         patch('analytics.adapters.scene_model.publish_events'):
      scene._updateEvents('person', 10.0)

    scene.getTrackedObjects.assert_called_once_with('person')

  def test_publish_fn_triggers_publish_events(self):
    scene = _scene()
    publish_fn = MagicMock()

    with patch('analytics.adapters.scene_model.moving_object_to_analytics_object',
               side_effect=lambda o: o), \
         patch('analytics.adapters.scene_model.process_frame'), \
         patch('analytics.adapters.scene_model.publish_events') as mock_publish, \
         patch('analytics.adapters.scene_model.get_iso_time', return_value='iso-10'):
      scene._updateEvents('person', 10.0, curObjects=[], publish_fn=publish_fn)

    mock_publish.assert_called_once_with(scene, 'iso-10', publish_fn)


class TestIsIntersecting:

  def test_returns_false_when_compute_intersection_disabled(self, make_region):
    scene = _scene()
    region = make_region()
    region.compute_intersection = False
    obj = MagicMock()

    assert scene.isIntersecting(obj, region) is False

  def test_creates_region_mesh_when_missing(self, make_region):
    scene = _scene()
    region = make_region()
    region.compute_intersection = True
    region.mesh = None
    obj = MagicMock()
    obj.mesh.is_intersecting.return_value = True

    with patch('analytics.adapters.scene_model.createRegionMesh') as mock_create_region, \
         patch('analytics.adapters.scene_model.createObjectMesh') as mock_create_obj:
      result = scene.isIntersecting(obj, region)

    mock_create_region.assert_called_once_with(region)
    mock_create_obj.assert_called_once_with(obj)
    assert result is True

  def test_object_mesh_value_error_returns_false(self, make_region):
    scene = _scene()
    region = make_region()
    region.compute_intersection = True
    region.mesh = 'existing-mesh'
    obj = MagicMock()

    with patch('analytics.adapters.scene_model.createObjectMesh', side_effect=ValueError("bad")):
      result = scene.isIntersecting(obj, region)

    assert result is False


class TestUpdateVisible:

  def test_object_visible_in_camera_added_to_visibility(self):
    scene = _scene()
    camera = SimpleNamespace(
      cameraID='cam1',
      pose=SimpleNamespace(regionOfView=SimpleNamespace(isPointWithin=lambda pt: True)),
    )
    scene.cameras['cam1'] = camera
    obj = SimpleNamespace(sceneLoc=Point(1.0, 1.0, 0.0))

    scene._updateVisible([obj])

    assert obj.visibility == ['cam1']

  def test_object_not_visible_excluded(self):
    scene = _scene()
    camera = SimpleNamespace(
      cameraID='cam1',
      pose=SimpleNamespace(regionOfView=SimpleNamespace(isPointWithin=lambda pt: False)),
    )
    scene.cameras['cam1'] = camera
    obj = SimpleNamespace(sceneLoc=Point(1.0, 1.0, 0.0))

    scene._updateVisible([obj])

    assert obj.visibility == []

  def test_camera_without_pose_is_skipped(self):
    scene = _scene()
    scene.cameras['cam1'] = SimpleNamespace(cameraID='cam1')
    obj = SimpleNamespace(sceneLoc=Point(1.0, 1.0, 0.0))

    scene._updateVisible([obj])  # must not raise

    assert obj.visibility == []

  def test_producer_visibility_is_passed_through(self):
    scene = _scene()
    camera = SimpleNamespace(
      cameraID='cam1',
      pose=SimpleNamespace(regionOfView=SimpleNamespace(isPointWithin=lambda pt: True)),
    )
    scene.cameras['cam1'] = camera
    obj = SimpleNamespace(sceneLoc=Point(1.0, 1.0, 0.0), visibility=['producer-cam'])

    scene._updateVisible([obj])

    assert obj.visibility == ['producer-cam']

  def test_empty_producer_visibility_triggers_fov_fill(self):
    """Empty list is indistinguishable from omitted (ingestion default)."""
    scene = _scene()
    camera = SimpleNamespace(
      cameraID='cam1',
      pose=SimpleNamespace(regionOfView=SimpleNamespace(isPointWithin=lambda pt: True)),
    )
    scene.cameras['cam1'] = camera
    obj = SimpleNamespace(sceneLoc=Point(1.0, 1.0, 0.0), visibility=[])

    scene._updateVisible([obj])

    assert obj.visibility == ['cam1']


class TestDeserialize:

  def test_deserialize_builds_scene_with_uid_and_mesh_fields(self):
    data = {
      'name': 'deserialized-scene',
      'uid': 'scene-uid-1',
      'map': None,
      'scale': None,
      'mesh_translation': [1.0, 2.0, 3.0],
      'mesh_rotation': [0.0, 0.0, 0.0],
    }

    scene = AnalyticsScene.deserialize(data)

    assert scene.uid == 'scene-uid-1'
    assert scene.name == 'deserialized-scene'
    assert scene.mesh_translation == [1.0, 2.0, 3.0]
    assert scene.mesh_rotation == [0.0, 0.0, 0.0]
