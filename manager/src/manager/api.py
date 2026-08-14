# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import socket
import threading
import uuid
import asyncio
from datetime import datetime, timezone

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, OperationalError, connection
from django.http import FileResponse, HttpResponse
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
from manager.validators import validate_mapping_bundle_zip
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


class ListThings(generics.ListAPIView):
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
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [permissions.IsAuthenticated]

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


class SceneMappingBundleView(APIView):
  """!Upload/download the shared mapping-session bundle for a scene.

  This is separate from the visualization `map` field (a renderable glb/ply/
  image/video): the bundle carries the raw SLAM artifacts (rtabmap.db,
  baseline point cloud/mesh, metadata) a handheld needs to resume mapping or
  relocalize into a map another handheld already built, cached locally just
  like a restarting handheld does with its own map. No merge/conflict
  resolution yet — each upload simply replaces the scene's stored bundle.
  """
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [permissions.IsAuthenticated]

  def _get_scene(self, scene_id):
    try:
      return Scene.objects.get(pk=scene_id)
    except (Scene.DoesNotExist, ValueError, DjangoValidationError):
      return None

  def get(self, request, scene_id):
    """!Download the scene's mapping bundle, or 404 if none has been contributed."""
    scene = self._get_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    if not scene.mapping_bundle:
      return Response(status=status.HTTP_404_NOT_FOUND)
    filename = os.path.basename(scene.mapping_bundle.name) or "mapping_bundle.zip"
    response = FileResponse(scene.mapping_bundle.open('rb'), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

  def put(self, request, scene_id):
    """!Replace the scene's mapping bundle. Multipart field: `mapping_bundle`.

    Optional `contributor` form field records who last contributed (e.g. the
    handheld's camera_id) for basic provenance — no fusion/merge logic yet.
    """
    scene = self._get_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)

    upload = request.FILES.get('mapping_bundle')
    if upload is None:
      return Response({"error": "mapping_bundle file is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
      validate_mapping_bundle_zip(upload)
    except DjangoValidationError as exc:
      return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    scene.mapping_bundle = upload
    scene.mapping_bundle_updated = get_iso_time()
    scene.mapping_bundle_contributor = str(request.data.get('contributor') or '')[:200]
    scene.save(update_fields=['mapping_bundle', 'mapping_bundle_updated', 'mapping_bundle_contributor'])

    log.info("Mapping bundle uploaded for scene", scene.pk, "by", scene.mapping_bundle_contributor or "unknown")
    return Response({
      "uid": scene.pk,
      "mapping_bundle_updated": scene.mapping_bundle_updated,
      "mapping_bundle_contributor": scene.mapping_bundle_contributor,
    }, status=status.HTTP_200_OK)

  def delete(self, request, scene_id):
    """!Clear the scene's mapping bundle."""
    scene = self._get_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    scene.mapping_bundle.delete(save=False)
    scene.mapping_bundle = None
    scene.mapping_bundle_updated = None
    scene.mapping_bundle_contributor = ""
    scene.save(update_fields=['mapping_bundle', 'mapping_bundle_updated', 'mapping_bundle_contributor'])
    return Response(status=status.HTTP_204_NO_CONTENT)

class ManageThing(APIView):
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]

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
    ) if thing else thing_serializer(data=request.data)

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

  def put(self, request, thing_type, uid=None):
    self.validateUnknownParams(request)
    if uid is None:
      return Response(
        {"error": "UID is required"},
        status=status.HTTP_400_BAD_REQUEST
      )
    return self.post(request, thing_type, uid)

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
      connection.ensure_connection()
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


class ServiceHealth(APIView):
  def checkDatabase(self):
    try:
      connection.ensure_connection()
      return True
    except OperationalError:
      return False

  def get(self, request):
    database_connected = self.checkDatabase()
    try:
      db_status = DatabaseStatus.objects.first() if database_connected else None
      user_count = User.objects.count() if database_connected else 0
    except OperationalError:
      database_connected = False
      db_status = None
      user_count = 0

    db_status_ready = bool(db_status and db_status.is_ready)
    ready = bool(database_connected and db_status_ready and user_count > 0)

    if ready:
      health_status = "healthy"
      http_status = status.HTTP_200_OK
    elif database_connected:
      health_status = "degraded"
      http_status = status.HTTP_202_ACCEPTED
    else:
      health_status = "unhealthy"
      http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    payload = {
      "status": health_status,
      "ready": ready,
      "component": "manager",
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "version": "1.0",
      "details": {
        "database": {
          "connected": database_connected,
          "schema_ready": db_status_ready,
        },
        "users": {
          "count": user_count,
        },
      },
    }

    return Response(payload, status=http_status)


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
      log.warning('Missing required parameters')
      return Response(
        {'detail': 'Missing required parameters.'},
        status=status.HTTP_400_BAD_REQUEST
      )

    try:
      user = User.objects.get(username=username)
    except User.DoesNotExist:
      log.warning("Access denied: unknown user '%s'.", username)
      return Response({'result': 'deny'}, status=status.HTTP_403_FORBIDDEN)

    try:
      requestedAccess = int(request.data['acc'])
    except (KeyError, TypeError, ValueError):
      log.warning('Missing or invalid acc parameter')
      return Response(
        {'detail': 'Missing or invalid acc parameter.'},
        status=status.HTTP_400_BAD_REQUEST
      )

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
