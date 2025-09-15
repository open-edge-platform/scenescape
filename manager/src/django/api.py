# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import socket
import threading
import uuid

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
        log.warn(f"Invalid key(s) in query params: {bad_keys}")
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
    _, thing_serializer, _ = get_class_and_serializer(self.args[0])
    return thing_serializer

class SceneImportAPIView(APIView):
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

  def isValidQueryParameter(self, uid, thing_type):
    _, thing_serializer, uid_field = get_class_and_serializer(thing_type)
    if uid_field == 'pk' and thing_type != 'scene' and uid.isdigit():
      return True
    elif (uid_field == 'uuid' and thing_type in ['region', 'tripwire']) or (uid_field == 'pk' and thing_type == 'scene') or (uid_field == 'child_id' and thing_type == 'child'):
      try:
        val = uuid.UUID(uid, version=4)
        return True
      except ValueError:
        raise ValidationError(thing_serializer.errors)
    elif uid_field == 'sensor_id' or uid_field == 'username' or uid_field == 'marker_id':
      return True
    return False

  def get(self, request, thing_type, uid=None):
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
    thing_class, thing_serializer, uid_field = get_class_and_serializer(thing_type)
    thing = None
    if uid is not None:
      if not self.isValidQueryParameter(uid, thing_type):
        return Response(status=status.HTTP_404_NOT_FOUND)
      try:
        thing = thing_class.objects.get(**{uid_field: uid})
      except thing_class.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
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
    _, thing_serializer, _ = get_class_and_serializer(thing_type)
    if uid is None:
      raise ValidationError(thing_serializer.errors)
    return self.post(request, thing_type, uid)

  def delete(self, request, thing_type, uid=None):
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
  def post(self, request):
    username = request.data.get('username')
    currentTopic = request.data.get('topic')

    if not username or not currentTopic:
      log.warn('Missing required parameters')
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
      log.warn("Access denied based on ACL restrictions.")
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
