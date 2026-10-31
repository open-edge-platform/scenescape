# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""External Cartesian observations retain geometry, identity, and reporting provenance."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from analytics.event_serializer import serialize_for_event
from controller.external_source import ExternalSourcePoseCache, IdentityClaimRegistry
from controller.ilabs_tracking import IntelLabsTracking
from controller.scene import Scene
from controller.scene_controller import SceneController
from controller.tracking import Tracking
from scene_common.detections_builder import buildDetectionsList
from scene_common.ingestion import SceneDataIngestion
from scene_common.transform import CameraPose


def _scene(uid):
  scene = Scene.__new__(Scene)
  scene.uid = uid
  scene.output_lla = False
  scene.persist_attributes = {}
  scene.tracker = SimpleNamespace(createObject=Tracking.createObject)
  scene.cameras = {}
  scene.finishProcessing = MagicMock()
  return scene


def _controller():
  controller = SceneController.__new__(SceneController)
  controller.external_source_pose_cache = ExternalSourcePoseCache()
  controller.identity_claim_registry = IdentityClaimRegistry()
  controller.trusted_positioning_sources = {'drone-1', 'drone-2'}
  controller.source_state_publisher = MagicMock()
  return controller


def _message():
  return {
    'source_id': 'drone-1', 'track': False,
    'pose': {
      'reference_frame': 'scene', 'translation': [10, 20, 5],
      'rotation': Rotation.from_euler('z', 90, degrees=True).as_quat().tolist(),
    },
    'objects': [{
      'id': 'tag-1', 'category': 'unknown', 'translation': [2, 0, 1],
      'rotation': Rotation.from_euler('x', 30, degrees=True).as_quat().tolist(),
      'source_id': 'untrusted-object-claim',
      'metadata': {'label': {'label': 'target'}, 'reid': {'embedding_vector': [0.1, 0.2]}},
    }],
  }


def _object(scene):
  assert scene.finishProcessing.call_args.args[2] == []
  return scene.finishProcessing.call_args.args[3][0]


@pytest.mark.parametrize('track', [False, True])
def test_body_transform_applied_once_and_mount_does_not_move_objects(track):
  controller, scene, message = _controller(), _scene('scene-1'), _message()
  message['track'] = track
  original = deepcopy(message)
  controller._handleExternalSourceObject(scene, message, 'unknown', 100)
  obj = scene.finishProcessing.call_args.args[2 if track else 3][0]
  np.testing.assert_allclose(obj.sceneLoc.asNumpyCartesian, [10, 22, 6], atol=1e-10)
  expected = Rotation.from_quat(message['pose']['rotation']) * Rotation.from_quat(
    message['objects'][0]['rotation'])
  np.testing.assert_allclose(Rotation.from_quat(obj.rotation).as_matrix(),
                             expected.as_matrix(), atol=1e-10)
  assert obj.info['source_id'] == 'drone-1'
  assert message == original


def test_pixel_routing_assigns_provenance_without_sharing_input_metadata():
  controller = _controller()
  observation = {
    'id': 'pixel-1', 'category': 'person', 'source_id': 'spoofed',
    'bounding_box_px': {'x': 1, 'y': 2, 'width': 3, 'height': 4},
    'metadata': {'label': {'label': 'original'}},
  }
  original = deepcopy(observation)
  routed = controller._routeExternalObject(
    0, observation, source_id='drone-1', scene_uid='scene-1',
    detection_type='person', source_track=False, tracked_id_counts={}, msg_when=100)
  assert routed['source_id'] == 'drone-1'
  routed['metadata']['label']['label'] = 'modified'
  routed['bounding_box_px']['x'] = 99
  assert observation == original


def test_same_message_can_be_transformed_for_two_scenes_without_mutation():
  scene_a, scene_b = _scene('a'), _scene('b')
  message = _message()
  original = deepcopy(message)
  source = SimpleNamespace(uid='drone-1', name='drone-1', retrack=False)
  pose_a = CameraPose(dict(message['pose'], scale=[1, 1, 1]), None)
  pose_b = CameraPose({'translation': [-10, 0, 0], 'rotation': [0, 0, 0, 1],
                       'scale': [1, 1, 1]}, None)
  _, objects_a = scene_a.createMovingObjectsForSceneData(message, source, pose_a, 'unknown', 100)
  _, objects_b = scene_b.createMovingObjectsForSceneData(message, source, pose_b, 'unknown', 100)
  np.testing.assert_allclose(objects_a[0].sceneLoc.asNumpyCartesian, [10, 22, 6], atol=1e-10)
  np.testing.assert_allclose(objects_b[0].sceneLoc.asNumpyCartesian, [-8, 0, 1], atol=1e-10)
  assert 'reid' in message['objects'][0]['metadata']
  objects_a[0].metadata['label']['label'] = 'changed'
  assert objects_b[0].metadata['label']['label'] == 'target'
  assert message == original


def test_source_identity_and_provenance_survive_merge_and_analytics_output():
  controller, scene, message = _controller(), _scene('scene-1'), _message()
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.already_tracked_objects = []
  for when in (100, 101):
    controller._handleExternalSourceObject(scene, message, 'unknown', when)
    tracker.already_tracked_objects = tracker.mergeAlreadyTrackedObjects([_object(scene)])
  obj = tracker.already_tracked_objects[0]
  assert obj.gid == 'tag-1'
  assert obj.frameCount == 2
  scene._updateVisible([obj])
  output = buildDetectionsList([obj], scene)
  assert output[0]['source_id'] == 'drone-1'
  assert output[0]['visibility'] == []
  ingestion = SceneDataIngestion()
  ingestion.ingest('unknown', output, {})
  analytics_obj = ingestion.get_objects('unknown')[0]
  regulated = buildDetectionsList([analytics_obj], scene)
  event = serialize_for_event(analytics_obj)
  for serialized in (regulated[0], event):
    assert serialized['id'] == 'tag-1'
    assert serialized['source_id'] == 'drone-1'
    assert serialized['visibility'] == []
    np.testing.assert_allclose(serialized['translation'], [10, 22, 6], atol=1e-10)
    np.testing.assert_allclose(serialized['rotation'], obj.rotation)
  ingestion.ingest('unknown', [dict(output[0], source_id='drone-2')], {})
  assert ingestion.get_objects('unknown')[0].info['source_id'] == 'drone-2'
  without_provenance = dict(output[0])
  del without_provenance['source_id']
  ingestion.ingest('unknown', [without_provenance], {})
  assert 'source_id' not in serialize_for_event(ingestion.get_objects('unknown')[0])


def test_collision_still_drops_second_sources_observation():
  controller, scene, message = _controller(), _scene('scene-1'), _message()
  controller._handleExternalSourceObject(scene, message, 'unknown', 100)
  scene.finishProcessing.reset_mock()
  message['source_id'] = 'drone-2'
  controller._handleExternalSourceObject(scene, message, 'unknown', 101)
  scene.finishProcessing.assert_not_called()


@pytest.mark.parametrize('track', [False, True])
def test_missing_object_rotation_is_not_invented_from_drone_attitude(track):
  controller, scene, message = _controller(), _scene('scene-1'), _message()
  message['track'] = track
  del message['objects'][0]['rotation']
  controller._handleExternalSourceObject(scene, message, 'unknown', 100)
  obj = scene.finishProcessing.call_args.args[2 if track else 3][0]
  assert obj.has_detection_rotation is False
  assert obj.rotation == [0, 0, 0, 1]
  assert obj.info['source_id'] == 'drone-1'
