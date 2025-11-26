# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import re
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

  def get_queryset(self):
    thing_class, _, _ = get_class_and_serializer(self.args[0])
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
        value = query_params.get(key)

        if key in ('parent', 'scene', 'id'):
          if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|^\d+$', value):
            log.warning(f"Invalid {key} format: {value}")
            return []
        elif key in ('name', 'username'):
          if not re.match(r'^[a-zA-Z0-9._\- ]{1,150}$', value):
            log.warning(f"Invalid {key} format: {value}")
            return []

        filter_params[key] = value

      if 'parent' in filter_params:
        uid = filter_params['parent']
        filter_params['parent__pk'] = uid
        filter_params.pop('parent')
      queryset = queryset.filter(**filter_params)
    return queryset

  def get_serializer_class(self):
    _, thing_serializer, _ = get_class_and_serializer(self.args[0])
    return thing_serializer

class SceneImportAPIView(APIView):
  def post(self, request, *args, **kwargs):
    if "zipFile" not in request.FILES:
      return Response({"error": "zipFile is required"}, status=status.HTTP_400_BAD_REQUEST)

    zip_file = request.FILES["zipFile"]

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB in bytes
    if zip_file.size > MAX_FILE_SIZE:
      return Response(
        {"error": f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024 * 1024)}MB"},
        status=status.HTTP_400_BAD_REQUEST
      )

    if not zip_file.name.lower().endswith('.zip'):
      return Response(
        {"error": "File must be a ZIP archive"},
        status=status.HTTP_400_BAD_REQUEST
      )

    if not re.match(r'^[a-zA-Z0-9._\-]+\.zip$', zip_file.name.lower()):
      return Response(
        {"error": "Invalid filename. Use only alphanumeric characters, dots, hyphens, and underscores"},
        status=status.HTTP_400_BAD_REQUEST
      )

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

  def _check_query_string_injection(self, request, uid):
    """
    Check if the request path contains query string injection attempts.
    Returns True if injection detected, False otherwise.
    """
    if uid and '?' in request.get_full_path():
      return True
    return False

  def _validate_json_depth(self, data, max_depth=5, current_depth=0):
    """
    Recursively validate JSON depth to prevent deep nesting attacks.
    Returns True if valid, raises ValidationError if too deep.
    """
    if current_depth > max_depth:
      raise ValidationError({'detail': f'JSON nesting depth exceeds maximum of {max_depth}'})

    if isinstance(data, dict):
      for value in data.values():
        self._validate_json_depth(value, max_depth, current_depth + 1)
    elif isinstance(data, list):
      for item in data:
        self._validate_json_depth(item, max_depth, current_depth + 1)
    return True

  def isValidQueryParameter(self, uid, thing_type):
    _, thing_serializer, uid_field = get_class_and_serializer(thing_type)

    if uid_field == 'pk' and thing_type != 'scene':
      # Primary keys: only digits allowed
      if not uid.isdigit():
        return False
      return True
    elif (uid_field == 'uuid' and thing_type in ['region', 'tripwire']) or (uid_field == 'pk' and thing_type == 'scene') or (uid_field == 'child_id' and thing_type == 'child'):
      # UUIDs: only lowercase hex digits and hyphens in proper UUID format
      if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', uid):
        return False
      try:
        val = uuid.UUID(uid, version=4)
        if str(val) != uid:
          return False
        return True
      except ValueError:
        return False
    elif uid_field == 'sensor_id' or uid_field == 'marker_id':
      # Sensor/Marker IDs: alphanumeric, underscores, hyphens only
      if not re.match(r'^[a-zA-Z0-9_-]+$', uid):
        return False
      return True
    elif uid_field == 'username':
      # Usernames: alphanumeric, underscores, hyphens, dots only
      if not re.match(r'^[a-zA-Z0-9._-]+$', uid):
        return False
      return True
    return False

  def get(self, request, thing_type, uid=None):
    if self._check_query_string_injection(request, uid):
      return Response(status=status.HTTP_404_NOT_FOUND)

    thing_class, thing_serializer, uid_field = get_class_and_serializer(thing_type)
    if uid is None:
      raise ValidationError(thing_serializer.errors)
    elif not self.isValidQueryParameter(uid, thing_type):
      return Response(status=status.HTTP_404_NOT_FOUND)
    try:
      thing = thing_class.objects.get(**{uid_field: uid})
    except thing_class.DoesNotExist:
      return Response(status=status.HTTP_404_NOT_FOUND)
    serializer = thing_serializer(thing)
    return Response(serializer.data)

  def post(self, request, thing_type, uid=None):
    if self._check_query_string_injection(request, uid):
      return Response(status=status.HTTP_404_NOT_FOUND)
    if not isinstance(request.data, dict):
      raise ValidationError({'detail': 'Request body must be a JSON object'})
    if len(request.data) > 100:
      raise ValidationError({'detail': 'Request body exceeds maximum of 100 keys'})
    self._validate_json_depth(request.data, max_depth=5)

    thing_class, thing_serializer, uid_field = get_class_and_serializer(thing_type)
    thing = None
    if uid is not None:
      if not self.isValidQueryParameter(uid, thing_type):
        return Response(status=status.HTTP_404_NOT_FOUND)
      try:
        thing = thing_class.objects.get(**{uid_field: uid})
      except thing_class.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

      if 'uid' in request.data and request.data['uid'] != uid:
        raise ValidationError({
          'uid': f'UID in request body does not match UID in URL path. Expected: {uid}, Got: {request.data["uid"]}'
        })

    if thing:
      serializer = thing_serializer(thing, data=request.data, partial=True)
    else:
      serializer = thing_serializer(data=request.data, partial=True)
    if not serializer.is_valid():
      raise ValidationError(serializer.errors)
    try:
      serializer.save()
    except IntegrityError as e:
      raise ValidationError(str(e))
    return Response(serializer.data,
                    status=status.HTTP_201_CREATED if not thing else status.HTTP_200_OK)

  def put(self, request, thing_type, uid=None):
    if self._check_query_string_injection(request, uid):
      return Response(status=status.HTTP_404_NOT_FOUND)

    _, thing_serializer, _ = get_class_and_serializer(thing_type)
    if uid is None:
      raise ValidationError(thing_serializer.errors)
    return self.post(request, thing_type, uid)

  def delete(self, request, thing_type, uid=None):
    if self._check_query_string_injection(request, uid):
      return Response(status=status.HTTP_404_NOT_FOUND)

    thing_class, thing_serializer, uid_field = get_class_and_serializer(thing_type)
    if uid is None:
      raise ValidationError(thing_serializer.errors)
    elif not self.isValidQueryParameter(uid, thing_type):
      return Response(status=status.HTTP_404_NOT_FOUND)
    thing = thing_class.objects.filter(**{uid_field: uid})
    if not thing:
      return Response(status=status.HTTP_404_NOT_FOUND)
    thing[0].delete() # thing is always a list of single element
    data = {uid_field: uid}
    log.info("DELETED", thing_type, data)
    return Response(data, status=status.HTTP_200_OK)


class CustomAuthToken(ObtainAuthToken):
  serializer_class = CustomAuthTokenSerializer

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

  def get(self, request, thing_type):
    pubsub = self.openPubSub()
    query = request.data
    if not query:
      query = request.query_params

    camera = query.get('camera', None)
    if camera is None:
      raise ValidationError({'camera': "Must provide camera ID"})

    # Validate camera ID format (alphanumeric, hyphens, underscores)
    if not re.match(r'^[a-zA-Z0-9_-]{1,100}$', camera):
      raise ValidationError({'camera': "Invalid camera ID format"})

    # Validate thing_type against whitelist and dispatch
    if thing_type == "frame":
      return self.getFrame(camera, query, pubsub)
    elif thing_type == "video":
      return self.getVideo(camera, query, pubsub)
    else:
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
  def post(self, request):
    username = request.data.get('username')
    currentTopic = request.data.get('topic')
    requestedAccess = request.data.get('acc')

    if not username or not currentTopic or requestedAccess is None:
      log.warning('Missing required parameters')
      return Response(
        {'detail': 'Missing required parameters.'},
        status=status.HTTP_400_BAD_REQUEST
      )

    # Validate username format (alphanumeric, dots, underscores, hyphens)
    if not re.match(r'^[a-zA-Z0-9._-]{1,150}$', username):
      log.warning(f'Invalid username format: {username}')
      return Response(
        {'detail': 'Invalid username format.'},
        status=status.HTTP_400_BAD_REQUEST
      )

    # Validate topic format and length
    if len(currentTopic) > 500 or not re.match(r'^[a-zA-Z0-9/_\-+#]+$', currentTopic):
      log.warning(f'Invalid topic format: {currentTopic}')
      return Response(
        {'detail': 'Invalid topic format.'},
        status=status.HTTP_400_BAD_REQUEST
      )

    # Validate access level is a valid integer
    try:
      requestedAccess = int(requestedAccess)
      # Validate it's within expected range (assuming 1-4 based on READ_ONLY, CAN_SUBSCRIBE, WRITE_ONLY, READ_AND_WRITE)
      if requestedAccess not in [1, 2, 3, 4]:
        raise ValueError
    except (ValueError, TypeError):
      log.warning(f'Invalid access level: {requestedAccess}')
      return Response(
        {'detail': 'Invalid access level.'},
        status=status.HTTP_400_BAD_REQUEST
      )

    try:
      user = User.objects.get(username=username)
    except User.DoesNotExist:
      log.warning(f'User not found: {username}')
      return Response({'result': 'deny'}, status=status.HTTP_403_FORBIDDEN)

    user_acls = PubSubACL.objects.filter(user=user)

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
