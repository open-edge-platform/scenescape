# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import socket
import threading
import uuid
import asyncio

from django.contrib.auth.models import User
from django.db import IntegrityError, OperationalError, connection
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework import authentication, permissions
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework import status
from rest_framework import generics
from rest_framework.authtoken.views import ObtainAuthToken

from manager.models import Scene, Cam, SingletonSensor, Region, Tripwire, Asset3D, ChildScene, CalibrationMarker, DatabaseStatus, PubSubACL
from manager.serializers import *
from manager.scene_import import ImportScene
from scene_common.timestamp import get_epoch_time, get_iso_time
from scene_common.mqtt import PubSub
from scene_common.options import *
from scene_common import log

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, inline_serializer
from drf_spectacular.types import OpenApiTypes
from manager.serializers import (
    SceneSerializer, CamSerializer, RegionSerializer,
    TripwireSerializer, SingletonSerializer, UserSerializer,
    Asset3DSerializer, ChildSceneSerializer, CalibrationMarkerSerializer
)

from drf_spectacular.openapi import AutoSchema

THING_TYPE_SERIALIZER_MAP = {
    'scene': SceneSerializer,
    'camera': CamSerializer,
    'sensor': SingletonSerializer,
    'region': RegionSerializer,
    'tripwire': TripwireSerializer,
    'user': UserSerializer,
    'asset': Asset3DSerializer,
    'child': ChildSceneSerializer,
    'calibrationmarker': CalibrationMarkerSerializer,
}

class PathPrefixedAutoSchema(AutoSchema):
    def get_operation_id(self):
        path = self.path.replace('/api/v1/', '').replace('{uid}', 'detail').replace('/', '_')
        method = self.method.lower()
        action = {'get': 'retrieve', 'post': 'create', 'put': 'update', 'delete': 'destroy'}.get(method, method)
        return f"{path}_{action}"

    def _get_serializer(self):
        # Extract thing_type from path: /api/v1/cameras -> 'camera', /api/v1/scene/{uid} -> 'scene'
        parts = [p for p in self.path.strip('/').split('/') if p and p != '{uid}']
        thing_type = parts[-1].rstrip('s') if parts else None  # strip plural 's'
        # Handle irregulars
        if thing_type == 'calibrationmarker':
            pass  # already correct
        elif thing_type == 'scene' and 'child' in self.path:
            thing_type = 'child'
        serializer_class = THING_TYPE_SERIALIZER_MAP.get(thing_type)
        return serializer_class() if serializer_class else super()._get_serializer()

    def get_path_fields(self):
        fields = super().get_path_fields()
        return [f for f in fields if f.name != 'thing_type']

    def get_operation(self, path, path_regex, path_prefix, method, registry):
      # Get the last path segment without {uid}
      parts = [p for p in path.strip('/').split('/') if p and p != '{uid}']
      last_segment = parts[-1] if parts else ''

      # ManageThing routes are singular (scene, camera, sensor...)
      # ListThings routes are plural (scenes, cameras, sensors...)
      is_singular = not last_segment.endswith('s') or last_segment == 'calibrationmarker'

      if '{uid}' in path and method == 'POST':
          return None
      if '{uid}' not in path and is_singular and method in ('GET', 'PUT', 'DELETE'):
          return None
      return super().get_operation(path, path_regex, path_prefix, method, registry)

    def get_request_serializer(self):
      parts = [p for p in self.path.strip('/').split('/') if p and p != '{uid}']
      thing_type = parts[-1] if parts else None
      # strip plural s for list endpoints
      if thing_type and thing_type.endswith('s') and thing_type != 'calibrationmarkers':
          thing_type = thing_type[:-1]
      serializer_class = THING_TYPE_SERIALIZER_MAP.get(thing_type)
      return serializer_class() if serializer_class else super().get_request_serializer()

class IsAdminOrReadOnly(permissions.BasePermission):
  def has_permission(self, request, view):
    if request.method in permissions.SAFE_METHODS:
      return request.user.is_authenticated
    return request.user.is_superuser


def get_class_and_serializer(thing_type):
  if thing_type in ("scene", "scenes"):
    return Scene, SceneSerializer, 'pk'
  elif thing_type in ("camera", "cameras"):
    return Cam, CamSerializer, 'sensor_id'
  elif thing_type in ("sensor", "sensors"):
    return SingletonSensor, SingletonSerializer, 'sensor_id'
  elif thing_type in ("region", "regions"):
    return Region, RegionSerializer, 'uuid'
  elif thing_type in ("tripwire", "tripwires"):
    return Tripwire, TripwireSerializer, 'uuid'
  elif thing_type in ("user", "users"):
    return User, UserSerializer, 'username'
  elif thing_type in ("asset", "assets"):
    return Asset3D, Asset3DSerializer, 'pk'
  elif thing_type in ("child"):
    return ChildScene, ChildSceneSerializer, 'child_id'
  elif thing_type in ("calibrationmarker", "calibrationmarkers"):
    return CalibrationMarker, CalibrationMarkerSerializer, 'marker_id'
  return None, None, None


class ListThings(generics.ListCreateAPIView):
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [permissions.IsAuthenticated]
  schema = PathPrefixedAutoSchema()
  http_method_names = ['get', 'head', 'options']

  def _get_thing_type(self):
    # path() passes thing_type as a kwarg; old regex used self.args[0]
    return self.kwargs.get('thing_type') or (self.args[0] if self.args else None)
 
  def get_queryset(self):
    thing_class, _, _ = get_class_and_serializer(self._get_thing_type())
    queryset = thing_class.objects.all()
    query_params = self.request.query_params
    if query_params:
      keys = query_params.keys()
      bad_keys = [x for x in keys if x not in ('name', 'parent', 'scene', 'username', 'id')]
      if bad_keys:
        log.warning(f"Invalid key(s) in query params: {bad_keys}")
        return []
 
      filter_params = {}
      for key in keys:
        filter_params[key] = query_params.get(key)
      if 'parent' in filter_params:
        uid = filter_params['parent']
        filter_params['parent__pk'] = uid
        filter_params.pop('parent')
      queryset = queryset.filter(**filter_params)
    return queryset

  def get_serializer_class(self):
    thing_type = self._get_thing_type()
    if thing_type is None:
        return SceneSerializer  # fallback for spectacular introspection
    _, thing_serializer, _ = get_class_and_serializer(thing_type)
    return thing_serializer

class SceneImportAPIView(APIView):
  @extend_schema(exclude=True)
  def post(self, request, *args, **kwargs):
    if "zipFile" not in request.FILES:
      return Response({"error": "zipFile is required"}, status=status.HTTP_400_BAD_REQUEST)

    zip_file = request.FILES["zipFile"]
    scene_import_instance = SceneImport.objects.create(zipFile=zip_file)

    zip_path = scene_import_instance.zipFile.path

    if not os.path.exists(zip_path):
      return Response({"error": f"Uploaded file not found at {zip_path}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    user_token = request.auth.key if hasattr(request.auth, "key") else str(request.auth)
    scene = ImportScene(zip_path, user_token)
    coroutine = scene.loadScene()
    errors = asyncio.run(coroutine)
    return Response(errors, status=status.HTTP_201_CREATED)

class ManageThing(APIView):
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]
  schema = PathPrefixedAutoSchema()

  def validateUnknownParams(self, request, allowed_query_params=None):
    allowed_query_params = allowed_query_params or set()
    incoming_params = set(request.query_params.keys())
    unknown_params = incoming_params - allowed_query_params

    if unknown_params:
      raise ValidationError({param: ["Unknown query parameter."] for param in unknown_params})
    return

  def _parse_uid(self, uid, thing_type):
    """
    Parse and convert a UID string to its appropriate type based on the thing_type.

    @param uid        The UID string to be parsed and converted
    @param thing_type The type of object determining how the UID should be interpreted
    """
    _, _, uid_field = get_class_and_serializer(thing_type)

    if uid_field in ['sensor_id', 'username', 'marker_id']:
      return uid

    if uid_field == 'pk' and thing_type not in ['scene']:
      if uid.isdigit():
        return int(uid)
      return None

    if uid_field in ['uuid'] or thing_type in ['region', 'tripwire', 'child', 'scene']:
      try:
        return uuid.UUID(uid, version=4)
      except ValueError:
        raise ValidationError({"uid": "Invalid UUID format"})

    return uid

  @extend_schema(
        summary='Retrieve a thing by type and UID',
        parameters=[
            OpenApiParameter('uid', OpenApiTypes.STR, OpenApiParameter.PATH, required=False),
        ],
        responses={
            200: OpenApiResponse(description='Success'),
            400: OpenApiResponse(description='Bad request - UID required or invalid format'),
            404: OpenApiResponse(description='Not found'),
        },)
  def get(self, request, thing_type, uid=None):
    thing_class, thing_serializer, uid_field = get_class_and_serializer(thing_type)

    self.validateUnknownParams(request)

    if uid is None:
      return Response(
          {"error": "UID is required"},
          status=status.HTTP_400_BAD_REQUEST
      )

    try:
      uid = self._parse_uid(uid, thing_type)
    except ValidationError as e:
      return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

    try:
      thing = thing_class.objects.get(**{uid_field: uid})
    except thing_class.DoesNotExist:
      return Response(status=status.HTTP_404_NOT_FOUND)

    serializer = thing_serializer(thing)
    return Response(serializer.data)

  @extend_schema(
      summary='Create a new thing',
      parameters=[],
      responses={
        201: OpenApiResponse(description='Created'),
        400: OpenApiResponse(description='Validation error'),}
  )
  def post(self, request, thing_type, uid=None):
    thing_class, thing_serializer, uid_field = get_class_and_serializer(thing_type)

    self.validateUnknownParams(request)

    thing = None

    if uid is not None:
      try:
        uid = self._parse_uid(uid, thing_type)
      except ValidationError as e:
        return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

      thing = thing_class.objects.filter(**{uid_field: uid}).first()

      if thing is None:
        return Response(status=status.HTTP_404_NOT_FOUND)

    serializer = thing_serializer(
        thing,
        data=request.data,
        partial=True
    ) if thing else thing_serializer(data=request.data, partial=True)

    if not serializer.is_valid():
      raise ValidationError(serializer.errors)

    try:
      serializer.save()
    except IntegrityError as e:
      raise ValidationError(str(e))

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED if thing is None else status.HTTP_200_OK
    )

  @extend_schema(
        summary='Update a thing by UID',
        parameters=[
            OpenApiParameter('uid', OpenApiTypes.STR, OpenApiParameter.PATH),
        ],
        responses={
            200: OpenApiResponse(description='Updated'),
            400: OpenApiResponse(description='Validation error or UID required'),
            404: OpenApiResponse(description='Not found'),
        }
  )
  def put(self, request, thing_type, uid=None):
    self.validateUnknownParams(request)
    if uid is None:
      return Response(
        {"error": "UID is required"},
        status=status.HTTP_400_BAD_REQUEST
      )
    return self.post(request, thing_type, uid)

  @extend_schema(
        summary='Delete a thing by UID',
        parameters=[
            OpenApiParameter('uid', OpenApiTypes.STR, OpenApiParameter.PATH),
        ],
        responses={
            200: OpenApiResponse(description='Deleted'),
            400: OpenApiResponse(description='UID required or invalid format'),
            404: OpenApiResponse(description='Not found'),
        }
  )
  def delete(self, request, thing_type, uid=None):
    thing_class, _, uid_field = get_class_and_serializer(thing_type)

    self.validateUnknownParams(request)

    if uid is None:
      return Response(
          {"error": "UID is required"},
          status=status.HTTP_400_BAD_REQUEST
      )

    try:
      uid = self._parse_uid(uid, thing_type)
    except ValidationError as e:
      return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

    obj = thing_class.objects.filter(**{uid_field: uid}).first()

    if not obj:
      return Response(status=status.HTTP_404_NOT_FOUND)

    obj.delete()

    log.info("DELETED", thing_type, {uid_field: uid})

    return Response({uid_field: uid}, status=status.HTTP_200_OK)


class CustomAuthToken(ObtainAuthToken):
  serializer_class = CustomAuthTokenSerializer

  @extend_schema(
    summary='Obtain authentication token',
    auth=[],  # no auth required
    responses={
        200: inline_serializer(
            name='AuthTokenResponse',
            fields={'token': serializers.CharField()}
        ),
        400: OpenApiResponse(description='Invalid credentials'),
    }
  )
  def post(self, request, *args, **kwargs):
    serializer = self.serializer_class(data=request.data,
                                           context={'request': request})
    if serializer.is_valid():
      token = serializer.validated_data['token']
      return Response({'token': token}, status=status.HTTP_200_OK)
    else:
      return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DatabaseReady(APIView):
  def checkDatabase(self):
    try:
      connection.cursor()
      return True
    except OperationalError:
      return False

  @extend_schema(exclude=True)
  def get(self, request):
    db_status = DatabaseStatus.objects.first()
    if not self.checkDatabase() or not db_status or not db_status.is_ready:
      return Response({'databaseReady': False}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    user_count = User.objects.count()
    database_ready = user_count > 0
    return Response({'databaseReady': database_ready}, status=status.HTTP_200_OK)


class CameraManager(APIView):
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [permissions.IsAuthenticated]

  def openPubSub(self):
    broker = os.environ.get("BROKER")
    if broker is None:
      log.error("WHY IS THERE NO BROKER?")
      return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

    auth = os.environ.get("BROKERAUTH")
    rootcert = os.environ.get("BROKERROOTCERT")
    if rootcert is None:
      rootcert = "/run/secrets/certs/scenescape-ca.pem"
    cert = os.environ.get("BROKERCERT")

    pubsub = PubSub(auth, cert, rootcert, broker)
    try:
      pubsub.connect()
    except socket.gaierror as e:
      log.error("Unable to connect", e)
      return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

    pubsub.loopStart()
    return pubsub

  @extend_schema(
    summary='Get camera frame or video',
    parameters=[
        OpenApiParameter('camera', OpenApiTypes.STR, OpenApiParameter.QUERY, required=True,
                         description='Camera ID'),
        OpenApiParameter('timestamp', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         description='ISO timestamp (required for frame)'),
        OpenApiParameter('type', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         description='Frame type filter'),
    ],
    responses={
        200: OpenApiResponse(description='Frame data or video file'),
        404: OpenApiResponse(description='Not found'),
        503: OpenApiResponse(description='Broker unavailable'),
    },
  )
  def get(self, request, thing_type):
    pubsub = self.openPubSub()
    query = request.data
    if not query:
      query = request.query_params

    camera = query.get('camera', None)
    if camera is None:
      raise ValidationError({'camera': "Must provide camera ID"})
    # FIXME - make sure camera exists

    if thing_type == "frame":
      return self.getFrame(camera, query, pubsub)
    elif thing_type == "video":
      return self.getVideo(camera, query, pubsub)

    return Response(status=status.HTTP_404_NOT_FOUND)

  def getFrame(self, camera, params, pubsub):
    timestamp = params.get('timestamp', None)
    try:
      ts_epoch = get_epoch_time(timestamp)
    except ValueError:
      raise ValidationError({'timestamp': "Must provide valid timestamp"})

    query = {
      'channel': str(uuid.uuid4()),
      'timestamp': get_iso_time(ts_epoch),
    }
    if 'type' in params:
      ftype = params['type'].split()
      query['frame_type'] = ftype

    topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera)
    jdata = f"getimage: {json.dumps(query)}"
    channelTopic = PubSub.formatTopic(PubSub.CHANNEL, channel=query['channel'])
    self.received = None
    self.imageCondition = threading.Condition()
    pubsub.addCallback(channelTopic, self.imageReceived)
    pubsub.publish(topic, jdata, qos=2)

    self.imageCondition.acquire()
    found = self.imageCondition.wait(timeout=3)
    self.imageCondition.release()
    pubsub.removeCallback(topic)

    if found and self.received:
      return Response(self.received, status=status.HTTP_200_OK)
    return Response(status=status.HTTP_404_NOT_FOUND)

  def imageReceived(self, pubsub, userdata, message):
    self.imageCondition.acquire()
    self.received = json.loads(str(message.payload.decode("utf-8")))
    self.imageCondition.notify()
    self.imageCondition.release()
    return

  def getVideo(self, camera, params, pubsub):
    query = {
      'channel': str(uuid.uuid4()),
    }
    topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera)
    jdata = f"getvideo: {json.dumps(query)}"
    msg = pubsub.publish(topic, jdata, qos=2)

    topic = PubSub.formatTopic(PubSub.CHANNEL, channel=query['channel'])
    data = pubsub.receiveFile(topic)
    if data is not None:
      response = HttpResponse(bytes(data))
      response['Content-Disposition'] = f"attachment; filename={camera}.mp4"
      response['Content-Type'] = "application/octet-stream"
      return response

    return Response(status=status.HTTP_404_NOT_FOUND)


class ACLCheck(APIView):
  @extend_schema(exclude=True)
  def post(self, request):
    username = request.data.get('username')
    currentTopic = request.data.get('topic')

    if not username or not currentTopic:
      log.warning('Missing required parameters')
      return Response(
        {'detail': 'Missing required parameters.'},
        status=status.HTTP_400_BAD_REQUEST
      )

    user = User.objects.get(username=username)
    user_acls = PubSubACL.objects.filter(user=user)
    requestedAccess = request.data['acc']
    requestedAccess = int(requestedAccess)

    # Admin users have full read/write access to the broker.
    if user.is_superuser:
      return Response({'result': 'allow', 'acc': READ_AND_WRITE}, status=status.HTTP_200_OK)

    if not user_acls.exists():
      log.warning("Access denied based on ACL restrictions.")
      return Response({'result': 'deny'}, status=status.HTTP_403_FORBIDDEN)

    matchedACL = None
    for acl in user_acls:
      templateTopic = PubSub.getTopicByTemplateName(acl.topic).template
      if PubSub.match_topic(templateTopic, currentTopic):
        matchedACL = acl

    if matchedACL:
      if matchedACL.access == requestedAccess:
        return Response({'result': 'allow', 'acc': requestedAccess}, status=status.HTTP_200_OK)
      elif matchedACL.access == READ_AND_WRITE and requestedAccess == CAN_SUBSCRIBE:
        return Response({'result': 'allow', 'acc': CAN_SUBSCRIBE}, status=status.HTTP_200_OK)
      elif matchedACL.access == READ_AND_WRITE and requestedAccess == WRITE_ONLY:
        return Response({'result': 'allow', 'acc': WRITE_ONLY}, status=status.HTTP_200_OK)
      elif matchedACL.access == READ_AND_WRITE and requestedAccess == READ_ONLY:
        return Response({'result': 'allow', 'acc': CAN_SUBSCRIBE}, status=status.HTTP_200_OK)
      elif matchedACL.access == CAN_SUBSCRIBE and requestedAccess == READ_ONLY:
        return Response({'result': 'allow', 'acc': CAN_SUBSCRIBE}, status=status.HTTP_200_OK)
      elif matchedACL.access == READ_ONLY and requestedAccess == CAN_SUBSCRIBE:
        return Response({'result': 'allow', 'acc': CAN_SUBSCRIBE}, status=status.HTTP_200_OK)
      else:
        return Response({'result': 'deny'}, status=status.HTTP_403_FORBIDDEN)
    else:
      return Response({'result': 'deny'}, status=status.HTTP_403_FORBIDDEN)
