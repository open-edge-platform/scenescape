# Copyright (C) 2022-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.
from http import HTTPStatus

testCases = {
  'Camera': {
    'scene': True,

    'create': [({'name': 'cam_1', 'intrinsics': {'fx': 905, 'fy': 905, 'cx': 640, 'cy': 360},
                 'translation': [3.0, 4.0, 1.0], 'rotation': [130.0, 10.0, 20.0],
                 'scale': [1.0, 1.0, 1.0], 'transform_type': 'euler'}, HTTPStatus.CREATED),
               ({'name': 'cam_2'}, HTTPStatus.CREATED, True)],

    'update': [({'name': 'cam_update_1'}, HTTPStatus.OK),
               ({'name': 'cam_update_2', 'uid': None}, HTTPStatus.NOT_FOUND)],

    'getAll':  [({'name': 'cam_update_1'}, HTTPStatus.OK),
                ({}, HTTPStatus.OK)]
  },
  'Sensor': {
    'scene': True,

    'create': [({'name': 'sensor_1', 'sensor_id': 'sensor_1', 'area': 'poly',
                 'points': ((-0.5, 0.5),
                            (0.5, 0.5), (0.5, -0.5), (-0.5, -0.5)), 'center': (3.0, 5.0)},
                HTTPStatus.CREATED),
               ({'area': 'square'}, HTTPStatus.BAD_REQUEST)],

    'update': [({'name': 'sensor_update_1', 'sensor_id': 'sensor_update_1', 'area': 'poly',
                 'points': ((-0.8, 0.5), (0.5, 0.8), (0.5, -0.8), (-0.5, -0.8))},
                HTTPStatus.OK),
               ({'name': 'sensor_update_2', 'area': 'poly', 'uid': None,
                 'points': ((-0.6, 0.6), (0.5, 0.5), (0.8, -0.8), (-0.5, -0.5))},
                HTTPStatus.NOT_FOUND)],

    'getAll':  [({'name': 'sensor_update_1'}, HTTPStatus.OK),
                ({}, HTTPStatus.OK)],
  },
  'Region': {
    'scene': True,

    'create': [({'name': 'region_1',
                 'points': ((1.0, 2.0), (3.0, 4.0), (0.5, 0.5), (0.6, 0.6))},
                HTTPStatus.CREATED),
               ({'name': 'region_1'}, HTTPStatus.CREATED),
               ({'name': 'region_2', 'points': None}, HTTPStatus.BAD_REQUEST)],

    'update': [({'name': 'region_update_1',
                 'points': ((2.0, 1.0), (4.0, 3.0), (0.7, 0.7), (0.8, 0.8))}, HTTPStatus.OK),
               ({'name': 'region_update_2', 'uid': None}, HTTPStatus.NOT_FOUND)],

    'getAll':  [({'name': 'region_update_1'}, HTTPStatus.OK),
                ({}, HTTPStatus.OK)],
  },
  'Tripwire': {
    'scene': True,

    'create': [({'name': 'trip_1', 'points': ((1.0, 2), (3.0, 4.0))}, HTTPStatus.CREATED),
               ({'name': 'trip_1'}, HTTPStatus.CREATED),
               ({'name': 'trip_2', 'points': None}, HTTPStatus.BAD_REQUEST)],

    'update': [({'name': 'trip_update_1', 'points': ((4.0, 3.0), (2.0, 1.0))}, HTTPStatus.OK),
               ({'name': 'trip_update_2', 'uid': None, 'points': []}, HTTPStatus.NOT_FOUND)],

    'getAll':  [({'name': 'trip_update_1'}, HTTPStatus.OK),
                ({}, HTTPStatus.OK)],

    },
    'Asset': {
    'scene': True,

    'create': [({'name': 'Person'}, HTTPStatus.CREATED),
               ({'name': 'Nurse', 'tracking_radius': 2.0}, HTTPStatus.CREATED)],

    'update': [({'name': 'Person_update_1'}, HTTPStatus.OK),
               ({'name': 'Person_update_2', 'uid': None, 'points': []}, HTTPStatus.NOT_FOUND)],

    'getAll':  [({'name': 'Person_update_1'}, HTTPStatus.OK),
                ({}, HTTPStatus.OK)],

    },

  'Scene': {
    'scene': False,

    'create': [({'name': 'scene_1'}, HTTPStatus.CREATED),
               ({'name': 'scene_1'}, HTTPStatus.BAD_REQUEST)],

    'update': [({'name': 'scene_update_1'}, HTTPStatus.OK),
               ({'name': 'scene_update_2', 'uid': None}, HTTPStatus.NOT_FOUND)],

    'getAll':  [({'name': 'scene_update_1'}, HTTPStatus.OK),
                ({}, HTTPStatus.OK)]
  },
  'User': {
    'scene': False,

    'create': [({'name': 'user_1', 'username': 'user_1', 'password': 'password_1',
                 'first_name': 'first', 'last_name': 'last', 'email': 'test@example.com'}, HTTPStatus.CREATED),
               ({'name': 'user_1', 'username': 'user_1', 'password': 'password_1',
                 'first_name': 'first', 'last_name': 'last', 'email': 'test@example.com'}, HTTPStatus.BAD_REQUEST)],

    'update': [({'name': 'user_update_1', 'username': 'user_update_success_1',
                 'first_name': 'first', 'last_name': 'last', 'email': 'test@example.com'}, HTTPStatus.OK),
               ({'name': 'user_update_2'}, HTTPStatus.NOT_FOUND)],

    'getAll': [({'username': 'user_1'}, HTTPStatus.OK),
               ({}, HTTPStatus.OK)]
  },
  'CalibrationMarker': {
      'scene': True,
      'create': [({'marker_id': 'marker_1', 'apriltag_id':'101', 'dims':[5.880603313446045,2.8565566539764404,0]}, HTTPStatus.CREATED),
                 ({'marker_id': 'marker_1', 'apriltag_id':'101', 'dims':[5.880603313446045,2.8565566539764404,0]}, HTTPStatus.BAD_REQUEST)],

      'update': [({'marker_id': 'marker_2', 'apriltag_id':'102', 'dims':[5.880603313446045,2.8565566539764404,0]}, HTTPStatus.OK),
                 ({'marker_id': 'marker_3', 'apriltag_id':'103', 'dims':[5.880603313446045,2.8565566539764404,0]}, HTTPStatus.NOT_FOUND)],

      'getAll': [({'scene': 'marker_2'}, HTTPStatus.OK),
                 ({}, HTTPStatus.OK)],
  }
}
