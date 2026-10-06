# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import socket
import tempfile
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
from manager.mapping_store import (
  DIGEST_HEADER, MappingStoreError, activate_revision, delete_head_artifact,
  delete_revision, download_digest, isoformat_z, store_artifact, validate_slug,
)
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
    return ChildScene, ChildSceneSerializer, 'pk'
  elif thing_type in ("calibrationmarker", "calibrationmarkers"):
    return CalibrationMarker, CalibrationMarkerSerializer, 'marker_id'
  return None, None, None


class ListThings(generics.ListAPIView):
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [permissions.IsAuthenticated]

  def get_queryset(self):
    thing_class, _, _ = get_class_and_serializer(self.args[0])
    queryset = thing_class.objects.all()
    if thing_class is Cam:
      queryset = queryset.select_related('scene')
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


class SceneMappingArtifactView(APIView):
  """!Upload, download, or delete one mapping method's resume zip.

  The zip is one method's opaque blob plus two optional standard members:
  ``manifest.json`` (method metadata, fiducials, proposed cameras, mesh
  transform) and ``mesh.glb``. A ``mesh.glb`` becomes this method's GLB
  revision; it becomes the scene default only with form field ``activate``.
  Form fields ``sha256``, ``fiducials``, ``contributor``, ``map_revision`` and
  ``activate`` arrive on the same request. Unknown form keys are ignored.
  """
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [permissions.IsAuthenticated]

  def _get_scene(self, scene_id):
    try:
      return Scene.objects.get(pk=scene_id)
    except (Scene.DoesNotExist, ValueError, DjangoValidationError):
      return None

  def get(self, request, scene_id, method):
    """!Download the head zip for ``method``, or 404 if this method has none."""
    scene = self._get_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    try:
      validate_slug(method)
    except DjangoValidationError as exc:
      return Response({"error": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
    from manager.models import SceneMappingArtifact
    artifact = SceneMappingArtifact.objects.filter(
      scene=scene, method=method, head=True).first()
    if artifact is None or not artifact.bundle:
      return Response(status=status.HTTP_404_NOT_FOUND)
    filename = os.path.basename(artifact.bundle.name) or f"{method}.zip"
    response = FileResponse(artifact.bundle.open("rb"), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response[DIGEST_HEADER] = download_digest(artifact)
    return response

  def put(self, request, scene_id, method):
    """!Store a new head zip. Multipart file field: ``bundle``."""
    scene = self._get_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    upload = request.FILES.get("bundle")
    if upload is None:
      return Response({"error": "bundle file is required"}, status=status.HTTP_400_BAD_REQUEST)
    sha256 = request.data.get("sha256")
    if sha256 is None or sha256 == "":
      return Response({"error": "sha256 is required"}, status=status.HTTP_400_BAD_REQUEST)
    tmp_path = None
    try:
      tmp_path = _spool_upload(upload)
      artifact = store_artifact(
        scene,
        method,
        tmp_path,
        str(sha256),
        request.data.get("fiducials"),
        str(request.data.get("contributor") or ""),
        request.data.get("map_revision"),
        activate=_truthy(request.data.get("activate")),
      )
    except MappingStoreError as exc:
      return Response({"error": str(exc)}, status=exc.status)
    finally:
      if tmp_path:
        try:
          os.remove(tmp_path)
        except OSError:
          pass
    log.info("Mapping artifact uploaded", scene.pk, method, artifact.sha256)
    return Response(_artifact_payload(artifact), status=status.HTTP_200_OK)

  def delete(self, request, scene_id, method):
    """!Delete this method's head zip. Older revisions stay until depth eviction."""
    scene = self._get_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    try:
      removed = delete_head_artifact(scene, method)
    except DjangoValidationError as exc:
      return Response({"error": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
    if not removed:
      return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(status=status.HTTP_204_NO_CONTENT)


def _truthy(value):
  if isinstance(value, bool):
    return value
  return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _spool_upload(upload):
  handle = tempfile.NamedTemporaryFile(prefix="mapping-artifact-", suffix=".zip", delete=False)
  try:
    for chunk in upload.chunks():
      handle.write(chunk)
  finally:
    handle.close()
  return handle.name


def _artifact_payload(artifact):
  created = isoformat_z(artifact.created)
  return {
    "id": artifact.id,
    "method": artifact.method,
    "created": created,
    "contributor": artifact.contributor,
    "sha256": artifact.sha256,
    "size": artifact.size,
    "fiducials": artifact.fiducials or [],
    "manifest": artifact.manifest or {},
    "map_revision": artifact.map_revision_id,
  }


def _revision_payload(scene, revision, request=None):
  def _url(field):
    if not field or not field.name:
      return None
    url = field.url
    return request.build_absolute_uri(url) if request is not None else url

  artifacts = list(revision.artifacts.filter(head=True).values_list("id", flat=True))
  return {
    "id": revision.id,
    "method": revision.method,
    "contributor": revision.contributor,
    "created": isoformat_z(revision.created),
    "sha256": revision.sha256,
    "transform": revision.transform or {},
    "is_default": scene.default_map_revision_id == revision.id,
    "file": _url(revision.file),
    "thumbnail": _url(revision.thumbnail),
    "artifacts": artifacts,
  }


def _lookup_scene(scene_id):
  try:
    return Scene.objects.get(pk=scene_id)
  except (Scene.DoesNotExist, ValueError, DjangoValidationError):
    return None


class SceneMappingArtifactListView(APIView):
  """!Every method's live artifact for a scene, with manifest metadata."""
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [permissions.IsAuthenticated]

  def get(self, request, scene_id):
    scene = _lookup_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    from manager.models import SceneMappingArtifact
    rows = SceneMappingArtifact.objects.filter(scene=scene, head=True).order_by("method")
    return Response([_artifact_payload(row) for row in rows])


class SceneMapRevisionListView(APIView):
  """!All GLB revisions of a scene, newest first, flagged with the default."""
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [permissions.IsAuthenticated]

  def get(self, request, scene_id):
    scene = _lookup_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    rows = scene.map_revisions.order_by("-created", "-id")
    return Response({
      "default": scene.default_map_revision_id,
      "revisions": [_revision_payload(scene, row, request) for row in rows],
    })


class SceneMapRevisionView(APIView):
  """!Inspect or delete one GLB revision; POST ``…/activate`` makes it default."""
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  def _lookup(self, scene_id, revision_id):
    scene = _lookup_scene(scene_id)
    if scene is None:
      return None, None
    from manager.models import SceneMapRevision
    try:
      revision = SceneMapRevision.objects.get(pk=revision_id, scene=scene)
    except (SceneMapRevision.DoesNotExist, ValueError, DjangoValidationError):
      return scene, None
    return scene, revision

  def get(self, request, scene_id, revision_id):
    scene, revision = self._lookup(scene_id, revision_id)
    if revision is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(_revision_payload(scene, revision, request))

  def post(self, request, scene_id, revision_id):
    scene, revision = self._lookup(scene_id, revision_id)
    if revision is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    try:
      activate_revision(scene, revision)
    except MappingStoreError as exc:
      return Response({"error": str(exc)}, status=exc.status)
    scene.refresh_from_db()
    log.info("Map revision activated", scene.pk, revision.method, str(revision.pk))
    return Response(_revision_payload(scene, revision, request))

  def delete(self, request, scene_id, revision_id):
    scene, revision = self._lookup(scene_id, revision_id)
    if revision is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    try:
      delete_revision(scene, revision)
    except MappingStoreError as exc:
      return Response({"error": str(exc)}, status=exc.status)
    return Response(status=status.HTTP_204_NO_CONTENT)

class MappingServiceStatusView(APIView):
  """GET mapping-service/status: is server-side reconstruction available?

  Lets devices decide whether to offer "build a model" at all. Mirrors the
  session-auth ``mapping-service/status/`` page view for token clients.
  """
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [permissions.IsAuthenticated]

  def get(self, request):
    from manager.mesh_generator import MappingServiceClient, MeshGenerator
    try:
      health = MappingServiceClient().checkHealth() or {}
    except Exception as exc:  # noqa: BLE001 - health is advisory
      health = {"available": False, "error": str(exc)}
    out = {
      "available": bool(health.get("available")),
      "ready": bool(health.get("ready", health.get("available"))),
      "method": MeshGenerator().reconstructionMethod() if health.get("available") else None,
    }
    if health.get("error"):
      out["error"] = str(health["error"])
    return Response(out)


class SceneReconstructView(APIView):
  """!Run a world-model reconstruction from the scene's ``keyframes`` artifact.

  POST starts a job on the mapping service (body: ``mesh_type``, ``max_images``)
  and returns its ``request_id``. GET ``…/reconstruct/<request_id>`` polls it;
  once complete the result is stored as a *candidate* artifact + GLB revision
  for the service's method. Nothing becomes the default map here.
  """
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  def post(self, request, scene_id):
    scene = _lookup_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    from manager.mesh_generator import MeshGenerator
    generator = MeshGenerator()
    mesh_type = str(request.data.get("mesh_type") or "mesh")
    if mesh_type not in ("mesh", "pointcloud"):
      return Response({"error": "mesh_type must be mesh or pointcloud"},
                      status=status.HTTP_400_BAD_REQUEST)
    max_images = request.data.get("max_images")
    try:
      max_images = int(max_images) if max_images not in (None, "") else None
    except ValueError:
      return Response({"error": "max_images must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
    use_priors = request.data.get("use_priors")
    if use_priors not in (None, ""):
      use_priors = _truthy(use_priors)
    else:
      use_priors = None
    try:
      result = generator.startReconstructionFromKeyframes(scene, mesh_type, max_images, use_priors)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller
      log.error("Reconstruction start failed", scene.pk, str(exc))
      return Response({"success": False, "error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    if not result.get("success"):
      return Response(result, status=status.HTTP_409_CONFLICT)
    result["method"] = generator.reconstructionMethod()
    return Response(result, status=status.HTTP_202_ACCEPTED)

  def get(self, request, scene_id, request_id):
    scene = _lookup_scene(scene_id)
    if scene is None:
      return Response(status=status.HTTP_404_NOT_FOUND)
    from manager.mesh_generator import MeshGenerator
    generator = MeshGenerator()
    status_data = generator.mapping_client.getReconstructionStatus(request_id)
    if not status_data.get("success") or status_data.get("state") != "complete":
      return Response(status_data)
    from manager.models import SceneMappingArtifact
    existing = SceneMappingArtifact.objects.filter(
      scene=scene, manifest__source__request_id=request_id).first()
    if existing is not None:
      status_data["finalized"] = True
      status_data["artifact"] = _artifact_payload(existing)
      status_data.pop("result", None)
      return Response(status_data)
    finalize = generator.finalizeMeshFromStatus(scene, request_id)
    if not finalize.get("success"):
      return Response({**status_data, "finalized": False, "error": finalize.get("error")},
                      status=status.HTTP_502_BAD_GATEWAY)
    status_data["finalized"] = True
    status_data["artifact"] = finalize["artifact"]
    status_data.pop("result", None)
    return Response(status_data)


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

    if uid_field in ['uuid'] or thing_type in ['region', 'tripwire', 'scene']:
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
