# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from collections import OrderedDict

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from scipy.spatial.transform import Rotation

from manager.models import Asset3D, Cam, ChildScene, Region, RegionPoint, Scene, \
  SingletonAreaPoint, SingletonSensor, Tripwire, TripwirePoint, PubSubACL, \
  RegionOccupancyThreshold, SingletonScalarThreshold, CalibrationMarker
from scene_common.options import *
from scene_common.timestamp import DATETIME_FORMAT
from scene_common.transform import CameraPose, CameraIntrinsics

class CustomAuthTokenSerializer(serializers.Serializer):
  username = serializers.CharField(max_length=150)
  password = serializers.CharField(max_length=150)

  def validate(self, data):
    username = data.get('username')
    password = data.get('password')

    if len(username) > 150 or len(password) > 150:
      raise serializers.ValidationError("Username/Password must be 150 characters or fewer.")
    else:
      user = authenticate(request=self.context.get('request'), username=username, password=password)
      if user:
        token, _ = Token.objects.get_or_create(user=user)
        data['user'] = user
        data['token'] = token.key
        return data
      else:
        raise serializers.ValidationError("Incorrect Username/Password. ")
    return

class NonNullSerializer(serializers.ModelSerializer):
  def to_representation(self, instance):
    result = super().to_representation(instance)
    return OrderedDict([(key, result[key]) for key in result
                        if (result[key] is not None and
                            not isinstance(result[key], list)
                            and not isinstance(result[key], tuple)) or result[key]])

class CenterSerializerField(serializers.DictField):
  def to_representation(self, obj):
    if hasattr(obj, 'map_x') and hasattr(obj, 'map_y') \
       and obj.map_x is not None and obj.map_y is not None:
      return [obj.map_x, obj.map_y]
    return None

  def to_internal_value(self, data):
    return {'center': data}

class PointsSerializerField(serializers.DictField):
  def to_representation(self, obj):
    points = []
    for point in obj.all().order_by('sequence'):
      points.append((point.x, point.y))
    return points

  def to_internal_value(self, data):
    return data

  @staticmethod
  def link_points(instance, points):
    instance.points.all().delete()
    for idx, point in enumerate(points):
      if isinstance(instance, Tripwire):
        TripwirePoint.objects.create(tripwire=instance, sequence=idx+1,
                                        x=point[0], y=point[1])
      elif isinstance(instance, Region):
        RegionPoint.objects.create(region=instance, sequence=idx+1,
                                        x=point[0], y=point[1])
      else:
        SingletonAreaPoint.objects.create(singleton=instance, sequence=idx+1,
                                        x=point[0], y=point[1])
    return

class ResolutionSerializerField(serializers.DictField):
  def to_representation(self, obj):
    if hasattr(obj, 'width') and hasattr(obj, 'height') \
       and obj.width is not None and obj.height is not None:
      return [obj.width, obj.height]
    return None

  def to_internal_value(self, data):
    if isinstance(data, (list, tuple)):
      return {'width': data[0], 'height': data[1]}
    return None

class RegionOccupancyThresholdSerializer(serializers.ModelSerializer):
  sectors = serializers.JSONField()
  range_max = serializers.IntegerField()

  @staticmethod
  def validateColorRanges(value):
    if not isinstance(value, dict):
      raise serializers.ValidationError("Invalid JSON format")
    if 'sectors' not in value:
      raise serializers.ValidationError("Missing sectors field")
    if 'range_max' not in value:
      raise serializers.ValidationError("Missing range_max field")
    if not isinstance(value['sectors'], list):
      raise serializers.ValidationError("Invalid sectors value")
    for sector in value['sectors']:
      if not isinstance(sector, dict):
        raise serializers.ValidationError("Invalid sector value")
      if 'color' not in sector:
        raise serializers.ValidationError("Missing color field")
      elif sector['color'] not in ['green', 'yellow', 'red']:
        raise serializers.ValidationError("Invalid color value")
      if 'color_min' not in sector:
        raise serializers.ValidationError("Missing color_min field")
    return value

  def create_update(self, validated_data, instance=None):
    is_update = instance is not None
    if not is_update:
      instance = super().create(validated_data)
    else:
      super().update(instance, validated_data)
    return instance

  def create(self, validated_data):
    return self.create_update(validated_data)

  def update(self, instance, validated_data):
    return self.create_update(validated_data, instance)

  @staticmethod
  def linkRegionOccupancyThreshold(instance, color_range):
    if hasattr(instance, 'roi_occupancy_threshold'):
      instance.roi_occupancy_threshold.delete()
    RegionOccupancyThreshold.objects.create(region=instance, sectors=color_range['sectors'],
                                              range_max=color_range['range_max'])
    return

  class Meta:
    model = RegionOccupancyThreshold
    fields = ['sectors', 'range_max']

class SingletonScalarThresholdSerializer(RegionOccupancyThresholdSerializer):

  class Meta:
    model = SingletonScalarThreshold
    fields = ['sectors', 'range_max']

  @staticmethod
  def linkSingletonScalarThreshold(instance, color_range):
    if hasattr(instance, 'singleton_scalar_threshold'):
      instance.singleton_scalar_threshold.delete()
    SingletonScalarThreshold.objects.create(singleton=instance, sectors=color_range['sectors'],
                                              range_max=color_range['range_max'])
    return

class SingletonSerializer(NonNullSerializer):
  uid = serializers.CharField(source="sensor_id", read_only=True)
  scene = serializers.CharField(source='scene.pk', allow_null=True)
  center = CenterSerializerField(source='*')
  points = PointsSerializerField()
  translation = serializers.SerializerMethodField('get_translation')
  color_ranges = SingletonScalarThresholdSerializer(source='singleton_scalar_threshold')

  def get_translation(self, obj):
    return [obj.map_x, obj.map_y, 0.0]

  def validate(self, data):
    area = data.get('area')
    if area not in [x[0] for x in AREA_CHOICES]:
      raise serializers.ValidationError({"area": "invalid area: \"" + str(area) + "\""})
    required = None
    if area == "circle":
      required = ['radius', 'center']
    elif area == "poly":
      required = ['points']
    if required:
      for field in required:
        val = data.get(field)
        if val is None:
          raise serializers.ValidationError({field: "required"})
    if 'color_ranges' in data:
      SingletonScalarThresholdSerializer.validateColorRanges(data['color_ranges'])
    return data

  def create_update(self, validated_data, instance=None):
    is_update = instance is not None

    scene_uid = validated_data.pop('scene', None)
    if scene_uid is not None:
      validated_data['scene_id'] = scene_uid['pk']
    center = validated_data.pop('center', None)
    if center is not None:
      validated_data['map_x'] = center[0]
      validated_data['map_y'] = center[1]
    validated_data['type'] = "generic"
    points = validated_data.pop('points', None)
    color_ranges = validated_data.pop('singleton_scalar_threshold', None)

    if not is_update:
      sensor_id = validated_data.get('sensor_id', None)
      if sensor_id is None:
        sensor_id = validated_data.get('name')
        sensor_id.replace(" ", "_")
        validated_data['sensor_id'] = sensor_id
      instance = super().create(validated_data)
    else:
      super().update(instance, validated_data)

    if points:
      PointsSerializerField.link_points(instance, points)

    if color_ranges:
      SingletonScalarThresholdSerializer.linkSingletonScalarThreshold(instance, color_ranges)

    # notify that DB has been updated
    instance.notifydbupdate()
    return instance

  def create(self, validated_data):
    return self.create_update(validated_data)

  def update(self, instance, validated_data):
    return self.create_update(validated_data, instance)

  class Meta:
    model = SingletonSensor
    fields = ['uid', 'scene', 'sensor_id', 'name', 'area', 'points', 'radius', 'center',
              'translation', 'singleton_type', 'color_ranges']

class CamSerializer(NonNullSerializer):
  uid = serializers.CharField(source="sensor_id", read_only=True)
  intrinsics = serializers.SerializerMethodField('get_intrinsics')
  distortion = serializers.SerializerMethodField('get_distortion')
  translation = serializers.SerializerMethodField('get_translation')
  rotation = serializers.SerializerMethodField('get_rotation')
  scale = serializers.SerializerMethodField('get_scale')
  resolution = ResolutionSerializerField(source='cam')
  scene = serializers.CharField(source="scene.pk", allow_null=True)

  def create_update(self, validated_data, instance=None):
    is_update = instance is not None
    scene_uid = validated_data.pop('scene', None)
    if scene_uid is not None:
      validated_data['scene_id'] = scene_uid['pk']

    validated_data['type'] = "camera"

    self.map_intrinsics_fields(validated_data)
    self.map_distortion_fields(validated_data)
    self.map_transform_fields(validated_data)

    if not is_update:
      sensor_id = validated_data.get('sensor_id', None)
      if sensor_id is None:
        sensor_id = self.initial_data.get('name')
        if sensor_id is not None:
          sensor_id.replace(" ", "_")
        validated_data['sensor_id'] = sensor_id
      instance = super().create(validated_data)
    else:
      super().update(instance, validated_data)

    self.create_camera_instance(instance)
    return instance

  def create(self, validated_data):
    return self.create_update(validated_data)

  def update(self, instance, validated_data):
    return self.create_update(validated_data, instance)

  def map_intrinsics_fields(self, validated_data):
    intrinsics = self.initial_data.get('intrinsics', None)
    if not intrinsics:
      return

    try:
      array = CameraIntrinsics.intrinsicsDictToList(intrinsics)
    except ValueError:
      raise serializers.ValidationError({"intrinsics": "invalid intrinsics: \""
                                         + str(intrinsics) + "\""})

    extended_data = {'intrinsics_' + key: None for key in CameraIntrinsics.INTRINSICS_KEYS}
    for key, val in zip(CameraIntrinsics.INTRINSICS_KEYS, array):
      extended_data['intrinsics_' + key] = val
    validated_data.update(extended_data)

    return

  def map_distortion_fields(self, validated_data):
    distortion = self.initial_data.get('distortion', None)
    if not distortion:
      return

    try:
      array = CameraIntrinsics.distortionDictToList(distortion)
    except ValueError:
      raise serializers.ValidationError({"distortion": "invalid distortion: \""
                                         + str(distortion) + "\""})

    extended_data = {'distortion_' + key: None for key in CameraIntrinsics.DISTORTION_KEYS}
    for key, val in zip(CameraIntrinsics.DISTORTION_KEYS, array):
      extended_data['distortion_' + key] = val
    validated_data.update(extended_data)

    return

  def map_transform_fields(self, validated_data):
    transform_type = self.initial_data.get("transform_type", None)
    extended_data = {}

    if transform_type in (EULER, QUATERNION) \
       and all(key in self.initial_data for key in ('translation', 'rotation', 'scale')):
      # Convert quaternion to euler
      if transform_type == QUATERNION:
        self.initial_data['rotation'] = Rotation.from_quat(
          self.initial_data['rotation']
        ).as_euler('XYZ', degrees=True).tolist()
        transform_type = EULER
      extended_data['transforms'] = (
        self.initial_data['translation'] +
        self.initial_data['rotation'] +
        self.initial_data['scale']
      )

    elif transform_type == POINT_CORRESPONDENCE:
      extended_data['transforms'] = self.initial_data.get('transforms', None)

    if extended_data:
      extended_data.update({
        'type': "camera",
        'transform_type': transform_type,
      })
      validated_data.update(extended_data)
    return

  def create_camera_instance(self, instance):
    if instance.cam.transforms is None:
      return

    if instance.sensor_id in instance.scene.scenescapeScene.cameras:
      instance.scene.scenescapeScene.cameras.pop(instance.sensor_id)

    instance.scene.scenescapeSceneUpdateSensors(instance.scene.scenescapeScene)
    return

  def get_intrinsics(self, obj):
    cam = obj.cam
    if cam.intrinsics_fx != None and cam.intrinsics_fy != None \
       and cam.intrinsics_cx != None and cam.intrinsics_cy != None:
      return {
        'fx': cam.intrinsics_fx,
        'fy': cam.intrinsics_fy,
        'cx': cam.intrinsics_cx,
        'cy': cam.intrinsics_cy,
      }
    elif cam.intrinsics_fx != None and cam.intrinsics_fy != None:
      return {
        'hfov': cam.intrinsics_fx,
        'vfov': cam.intrinsics_fy,
      }
    elif cam.intrinsics_fx != None:
      return {
        'fov': cam.intrinsics_fx,
      }
    return None

  def get_distortion(self, obj):
    cam = obj.cam
    distortion = {}
    for key in CameraIntrinsics.DISTORTION_KEYS:
      ext_key = 'distortion_' + key
      val = getattr(cam, ext_key, None)
      if val is None:
        break
      distortion[key] = val
    if not distortion:
      distortion = None
    return distortion

  def get_translation(self, obj):
    if not obj.scene:
      return None

    self.create_camera_instance(obj)

    camera = obj.scene.scenescapeScene.cameraWithID(obj.sensor_id)
    return camera.pose.translation.asNumpyCartesian.tolist() if camera \
      and hasattr(camera, 'pose') else None

  def get_rotation(self, obj):
    if not obj.scene:
      return None

    self.create_camera_instance(obj)

    camera = obj.scene.scenescapeScene.cameraWithID(obj.sensor_id)
    return getattr(camera.pose, 'euler_rotation', None) \
      if camera and hasattr(camera, 'pose') else None

  def get_scale(self, obj):
    if not obj.scene:
      return None
    camera = obj.scene.scenescapeScene.cameraWithID(obj.sensor_id)
    return camera.pose.scale if camera and hasattr(camera, 'pose') else None

  class Meta:
    model = Cam
    fields = ['uid', 'name', 'intrinsics', 'distortion', 'translation', 'rotation', 'scale',
              'resolution', 'scene', 'command', 'camerachain', 'threshold', 'aspect', 'cv_subsystem']

class RegionSerializer(NonNullSerializer):
  uid = serializers.SerializerMethodField('get_uuid')
  points = PointsSerializerField()
  scene = serializers.CharField(source='scene.pk')
  color_ranges = RegionOccupancyThresholdSerializer(source='roi_occupancy_threshold')

  def create_update(self, validated_data, instance=None):
    is_update = instance is not None

    scene_uid = validated_data.pop('scene', None)
    if scene_uid is not None:
      validated_data['scene_id'] = scene_uid['pk']
    points = validated_data.pop('points', None)
    color_ranges = validated_data.pop('roi_occupancy_threshold', None)

    if color_ranges:
      RegionOccupancyThresholdSerializer.validateColorRanges(color_ranges)

    if not is_update:
      instance = super().create(validated_data)
    else:
      super().update(instance, validated_data)

    if points:
      PointsSerializerField.link_points(instance, points)

    if color_ranges:
      RegionOccupancyThresholdSerializer.linkRegionOccupancyThreshold(instance, color_ranges)

    # notify that DB has been updated
    instance.notifydbupdate()
    return instance

  def create(self, validated_data):
    return self.create_update(validated_data)

  def update(self, instance, validated_data):
    return self.create_update(validated_data, instance)

  def get_uuid(self, obj):
    return str(obj.uuid)

  class Meta:
    model = Region
    fields = ['uid', 'name', 'points', 'scene', 'color_ranges']

class TripwireSerializer(RegionSerializer):
  class Meta:
    model = Tripwire
    fields = ['uid', 'name', 'points', 'scene']

class TransformSerializerField(serializers.DictField):
  def to_representation(self, obj):
    return obj.asDict

  def to_internal_value(self, data):
    return data

class SceneSerializer(NonNullSerializer):
  uid = serializers.SerializerMethodField('get_uid')
  cameras = serializers.SerializerMethodField('get_cameras')
  sensors = serializers.SerializerMethodField('get_sensors')
  regions = RegionSerializer(many=True)
  tripwires = TripwireSerializer(many=True)
  parent = serializers.CharField(source='parent.parent.pk')
  transform = TransformSerializerField(source='parent.cameraPose')
  mesh_translation = serializers.SerializerMethodField('get_translation')
  mesh_rotation = serializers.SerializerMethodField('get_rotation')
  mesh_scale = serializers.SerializerMethodField('get_scale')
  children = serializers.SerializerMethodField('get_children')
  map_processed = serializers.DateTimeField(format=f"{DATETIME_FORMAT}Z")

  def get_uid(self, obj):
    return obj.id

  def get_cameras(self, obj):
    queryset = [x for x in obj.sensor_set.all() if x.type == "camera"]
    return CamSerializer(queryset, many=True).data

  def get_sensors(self, obj):
    queryset = [SingletonSensor.objects.get(pk=x.id) for x in obj.sensor_set.all()
                if x.type == "generic"]
    return SingletonSerializer(queryset, many=True).data

  def get_rotation(self, obj):
    return [obj.rotation_x, obj.rotation_y, obj.rotation_z] if obj.rotation_x else [0, 0, 0]

  def get_translation(self, obj):
    return [obj.translation_x, obj.translation_y, obj.translation_z] if obj.translation_x else [0, 0, 0]

  def get_scale(self, obj):
    return [obj.scale_x, obj.scale_y, obj.scale_z] if obj.scale_x else [1, 1, 1]

  def get_children(self, obj):
    children = obj.children
    children = []

    # list of children having associated scene object
    need_to_serialize = []
    for x in obj.children.all():
      if x.child is None:
        children.append({'name':x.child_name})
      else:
        need_to_serialize.append(x.child)
    serialized_children = SceneSerializer(need_to_serialize, many=True).data
    return children + serialized_children

  @staticmethod
  def check_circular_dependency(parent_scene, child_scene):
    # Check if any of the descendants of the child scene are the parent before linking
    child_scene_children = ChildScene.objects.filter(parent=child_scene)
    for child in child_scene_children:
      stack = [child]
      while stack:
        current_child = stack.pop()
        if parent_scene == current_child.child:
          raise serializers.ValidationError(f"Cannot link \"{parent_scene}\" with "
                                            f"\"{child_scene}\" due to circular dependency")
        for child_node in ChildScene.objects.filter(parent=current_child.child):
          stack.append(child_node)
    return

  def link_parent(self, parent_uid, child_scene):
    parent_scene = Scene.objects.get(pk=parent_uid)
    self.check_circular_dependency(parent_scene, child_scene)
    child_link = ChildScene.objects.create(parent=parent_scene, child=child_scene)
    return child_link

  def update_child_transform(self, child_scene, pose_dict):
    if not pose_dict:
      return
    pose = CameraPose(pose_dict, None)
    child_scene.transform_type = EULER
    child_scene.transform1 = pose.translation.x
    child_scene.transform2 = pose.translation.y
    child_scene.transform3 = pose.translation.z
    child_scene.transform4 = pose.euler_rotation[0]
    child_scene.transform5 = pose.euler_rotation[1]
    child_scene.transform6 = pose.euler_rotation[2]
    child_scene.transform7 = pose.scale[0]
    child_scene.transform8 = pose.scale[1]
    child_scene.transform9 = pose.scale[2]
    return

  def create_update(self, validated_data, instance=None):
    is_update = instance is not None

    parent_uid = None
    transform = None
    output_lla = validated_data.get('output_lla', None)
    if output_lla:
      instance.scenescapeScene.output_lla = output_lla
    map_corners_lla = validated_data.get('map_corners_lla', None)
    if map_corners_lla:
      instance.scenescapeScene.map_corners_lla = map_corners_lla
    self.handleMeshTransform(self.initial_data, validated_data)
    child_data = validated_data.pop('parent', None)
    if child_data:
      if 'parent' in child_data:
        parent_uid = child_data['parent']['pk']
      if 'cameraPose' in child_data:
        transform = child_data['cameraPose']

    if not is_update:
      instance = super().create(validated_data)

    if parent_uid:
      self.link_parent(parent_uid, instance)
    if transform and hasattr(instance, 'parent') and instance.parent:
      self.update_child_transform(instance.parent, transform)
    if hasattr(instance, 'parent') and instance.parent:
      instance.parent.save()

    if is_update:
      super().update(instance, validated_data)
    return instance

  def create(self, validated_data):
    return self.create_update(validated_data)

  def update(self, instance, validated_data):
    return self.create_update(validated_data, instance)

  def handleMeshTransform(self, data, validated_data):
    axes = {'x': 0, 'y': 1, 'z': 2}
    types = ['translation', 'rotation', 'scale']
    for trans_type in types:
      popped_data = data.pop('mesh_' + trans_type, None)
      if popped_data:
        for axis, index in axes.items():
          validated_data[trans_type + '_' + axis] = popped_data[index]
    return

  class Meta:
    model = Scene
    fields = ['uid', 'name', 'output_lla', 'map_corners_lla', 'map', 'thumbnail', 'cameras', 'sensors', 'regions',
              'tripwires', 'parent', 'transform', 'mesh_translation', 'mesh_rotation',
              'mesh_scale', 'scale', 'children', 'regulated_rate', 'external_update_rate',
              'camera_calibration', 'apriltag_size', 'map_processed', 'polycam_data',
              'number_of_localizations', 'global_feature', 'local_feature', 'matcher',
              'minimum_number_of_matches', 'inlier_threshold']

class PubSubACLSerializer(NonNullSerializer):
  class Meta:
    model = PubSubACL
    fields = ['topic', 'access']

class UserSerializer(NonNullSerializer):
  uid = serializers.CharField(source="pk", read_only=True)
  acls = PubSubACLSerializer(many=True, required=False)

  def create_update(self, validated_data, instance=None):
    is_update = instance is not None

    password = validated_data.pop('password', None)
    acl_data = validated_data.pop('acls', [])
    if password is not None:
      validated_data['password'] = make_password(password)

    if not is_update:
      instance = super().create(validated_data)
    else:
      super().update(instance, validated_data)

    if acl_data:
      if is_update:
        instance.acls.all().delete()
      for acl in acl_data:
        PubSubACL.objects.create(user=instance, **acl)
    return instance

  def create(self, validated_data):
    return self.create_update(validated_data)

  def update(self, instance, validated_data):
    return self.create_update(validated_data, instance)

  class Meta:
    model = User
    fields = ['uid', 'username', 'password', 'is_active', 'is_staff', 'is_superuser', 'first_name', 'last_name',
              'email', 'acls']

    extra_kwargs = {
      'password': {'write_only': True}
    }

class Asset3DSerializer(NonNullSerializer):
  uid = serializers.CharField(source='pk')

  def create_update(self, validated_data, instance=None):
    is_update = instance is not None
    if not is_update:
      instance = super().create(validated_data)
    else:
      super().update(instance, validated_data)
    return instance

  def create(self, validated_data):
    return self.create_update(validated_data)

  def update(self, instance, validated_data):
    return self.create_update(validated_data, instance)

  class Meta:
    model = Asset3D
    fields = ['uid', 'name', 'x_size', 'y_size', 'z_size', 'tracking_radius', 'shift_type', 'mark_color',
              'model_3d', 'scale', 'project_to_map', 'rotation_from_velocity']

class ChildSceneSerializer(NonNullSerializer):
  name = serializers.SerializerMethodField('getChildName')
  uid = serializers.CharField(source='pk', read_only=True)
  transform = TransformSerializerField(source="cameraPose")

  def getChildName(self, obj):
    return obj.child.name if obj.child else obj.child_name

  def validate(self, data):
    child_type = data.get('child_type')
    parent = data.get('parent')
    child = data.get('child', None)
    remote_child_id = data.get('remote_child_id', None)

    required = []
    if child_type == 'remote':
      required = ['remote_child_id', 'child_name', 'host_name', 'mqtt_username', 'mqtt_password']
    elif child_type == 'local':
      required = ['child']

    missing = [field for field in required if not data.get(field)]
    if missing:
      raise serializers.ValidationError({field: "required" for field in missing})

    if child_type == 'remote' and remote_child_id and parent:
      if remote_child_id == parent:
        raise serializers.ValidationError({'remote_child_id': 'remote_child_id cannot be the same as parent.'})
      query_child = ChildScene.objects.filter(remote_child_id=remote_child_id, parent=parent)
      if self.instance:
        query_child = query_child.exclude(pk=self.instance.pk)
      if query_child.exists():
        raise serializers.ValidationError({'remote_child_id': f"{remote_child_id} already exists for this parent."})

    if child_type == 'local' and child and parent:
      if child == parent:
        raise serializers.ValidationError({'child': 'child cannot be the same as parent.'})
      query_child = ChildScene.objects.filter(child=child, parent=parent)
      if self.instance:
        query_child = query_child.exclude(pk=self.instance.pk)
      if query_child.exists():
        raise serializers.ValidationError({'child': f"{child} already exists for this parent."})

    return data

  def create_update(self, validated_data, instance=None):
    is_update = instance is not None
    parent_scene = validated_data.get('parent')
    child_type = validated_data.get('child_type')

    if is_update and instance.child_type != child_type:
      if child_type == "remote":
        validated_data['child'] = None
      else:
        validated_data['child_name'] = None
        validated_data['host_name'] = None
        validated_data['mqtt_username'] = None
        validated_data['mqtt_password'] = None
        if instance.child:
          SceneSerializer.check_circular_dependency(parent_scene, instance.child)
      return super().update(instance, validated_data)

    if child_type == "local" and validated_data.get('child'):
      SceneSerializer.check_circular_dependency(parent_scene, validated_data['child'])

    return super().create(validated_data)

  def create(self, validated_data):
    return self.create_update(validated_data)

  def update(self, instance, validated_data):
    return self.create_update(validated_data, instance)

  class Meta:
    model = ChildScene
    fields = ['uid', 'child_type', 'transform', 'name', 'remote_child_id', \
          'child', 'parent', 'host_name', 'child_name', \
          'mqtt_username', 'mqtt_password', 'retrack', 'transform_type', \
          'transform1', 'transform2', 'transform3', 'transform4', \
          'transform5', 'transform6', 'transform7', 'transform8', \
          'transform9', 'transform10', 'transform11', 'transform12', \
          'transform13', 'transform14', 'transform15', 'transform16']
    validators = []

class CalibrationMarkerSerializer(NonNullSerializer):

  def create_update(self, validated_data, instance=None):
    is_update = instance is not None
    if not is_update:
      instance = super().create(validated_data)
    else:
      super().update(instance, validated_data)
    return instance

  def create(self, validated_data):
    return self.create_update(validated_data)

  def update(self, instance, validated_data):
    return self.create_update(validated_data, instance)

  class Meta:
    model = CalibrationMarker
    fields = ['marker_id', 'apriltag_id', 'dims', 'scene']
