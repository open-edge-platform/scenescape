# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import random
import time
import traceback
import uuid
from collections import namedtuple
import tempfile
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import user_passes_test
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth import user_logged_in, user_login_failed
from django.contrib.sessions.models import Session
from rest_framework.authtoken.models import Token
from django.db import transaction
from django.dispatch.dispatcher import receiver
from django.http import FileResponse, HttpResponse, HttpResponseNotFound, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import DetailView, ListView, RedirectView, TemplateView
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.core.files.storage import default_storage
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication

from manager.api import IsAdminOrReadOnly
from manager.ppl_generator import generate_pipeline_string_from_dict, PipelineGenerationValueError, PipelineGenerationNotImplementedError
from manager.models import Scene, ChildScene, \
  Cam, Asset3D, \
  SingletonSensor, \
  Region, RegionPoint, Tripwire, TripwirePoint, \
  UserSession, FailedLogin, \
  RegionOccupancyThreshold, SceneImport
from manager.forms import ROIForm, CamCalibrateForm
from manager.validators import validate_uuid

from scene_common.options import *
from scene_common.scene_model import SceneModel
from scene_common.transform import applyChildTransform
from scene_common import log

@receiver(user_login_failed)
def login_has_failed(sender, credentials, request, **kwargs):
  user = FailedLogin.objects.filter(ip=request.META.get('REMOTE_ADDR')).first()
  if user:
    log.warning("User had already failed a login will update delay")
    old_delay = user.delay
    user.delay = random.uniform(0.1, old_delay + 0.9)
    user.save()
  else:
    FailedLogin.objects.create(ip=request.META.get('REMOTE_ADDR'), delay=0.7)
    log.warning("User 1st wrong credentials attempt")

@receiver(user_logged_in)
def remove_other_sessions(sender, user, request, **kwargs):
  # Force other sessions to expire
  old_sessions = Session.objects.filter(usersession__user=user)

  request.session.save()

  old_sessions = old_sessions.exclude(session_key=request.session.session_key)
  if old_sessions:
    for session in old_sessions:
      session.delete()

  # create a link from the user to the current session (for later removal)
  UserSession.objects.get_or_create(
      user=user,
      session=Session.objects.get(pk=request.session.session_key)
  )
  failed_login = FailedLogin.objects.filter(ip=request.META.get('REMOTE_ADDR'))
  if failed_login:
    failed_login.delete()

class SuperUserCheck(UserPassesTestMixin):
  def test_func(self):
    return self.request.user.is_superuser

def _user_auth_token(user):
  if hasattr(user, "auth_token") and user.auth_token:
    return str(user.auth_token)
  return ""

def sheet_redirect(path, action, entity_id=None):
  """Redirect into a host page that opens a React sheet via ?ss=&id=."""
  sep = '&' if '?' in path else '?'
  url = f"{path}{sep}ss={action}"
  if entity_id is not None:
    url += f"&id={entity_id}"
  return redirect(url)

def scene_path(scene_id):
  return f"/{scene_id}/"

def superuser_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME,
                   login_url='sign_in'):

  actual_decorator = user_passes_test(
      lambda u: u.is_active and u.is_superuser,
      login_url=login_url,
      redirect_field_name=redirect_field_name
  )
  if view_func:
    return actual_decorator(view_func)
  return actual_decorator

@login_required(login_url="sign_in")
def index(request):
  scenes = Scene.objects.order_by('name')
  scenes_payload = []
  for scene in scenes:
    scenes_payload.append({
      'id': str(scene.id),
      'name': scene.name,
      'georeferenced': bool(scene.output_lla and scene.map_corners_lla),
      'thumbnailUrl': scene.thumbnail.url if scene.thumbnail else None,
      'mapUrl': scene.map.url if scene.map else None,
      'detailUrl': reverse('sceneDetail', args=[scene.id]),
      'detail3dUrl': reverse('scene_detail', args=[scene.id]),
      'manageUrl': f"{reverse('index')}?ss=scene-manage&id={scene.id}",
      'deleteUrl': (
        reverse('scene_delete', args=[scene.id])
        if request.user.is_superuser else None
      ),
      'counts': {
        'sensors': scene.sensor_set.count(),
        'regions': scene.regions.count(),
        'tripwires': scene.tripwires.count(),
      },
    })
  context = {
    'scenes': scenes,
    'scenes_home_bootstrap': {
      'authToken': _user_auth_token(request.user),
      'isSuperuser': request.user.is_superuser,
      'scenes': scenes_payload,
    },
  }
  return render(request, 'sscape/index.html', context)

def protected_media(request, path, media_root):
  if request.user.is_authenticated:
    if path != "":
      media_root_real = os.path.realpath(media_root)
      file = os.path.realpath(os.path.join(media_root, path))
      # startswith (not commonpath) is required here: it's the check CodeQL's
      # path-injection analysis recognizes as sanitizing the path below.
      if file.startswith(media_root_real + os.sep) and os.path.isfile(file):
        response = FileResponse(open(file, 'rb'))
        return response
    return HttpResponseNotFound()
  return HttpResponse("401 Unauthorized", status=401)

def list_resources(request, folder_name):
  """! List files in folder_name inside MEDIA_ROOT and return them as JSON."""
  media_root_real = os.path.realpath(settings.MEDIA_ROOT)
  base_path = os.path.realpath(os.path.join(settings.MEDIA_ROOT, folder_name))
  # startswith (not commonpath) is required here: it's the check CodeQL's
  # path-injection analysis recognizes as sanitizing the path below.
  if base_path.startswith(media_root_real + os.sep) and os.path.isdir(base_path):
    files = [f for f in os.listdir(base_path) if os.path.isfile(os.path.join(base_path, f))]
    return JsonResponse({"files": files})
  return JsonResponse({"error": "Invalid folder"}, status=400)

@login_required(login_url="sign_in")
def sceneDetail(request, scene_id):
  scene = get_object_or_404(Scene, pk=scene_id)
  child_rois, child_trips, child_sensors = getAllChildrenMetaData(scene_id)
  # FIXME add rest api call to remote child using child scene api token

  cameras = []
  sensors = []
  for sensor in scene.sensor_set.all().order_by("name"):
    if sensor.type == "camera":
      cameras.append({
        "id": str(sensor.id),
        "sensorId": sensor.sensor_id,
        "name": sensor.name,
        "calibrateHref": f"?ss=calibrate-cam&id={sensor.id}",
        "cmdTopic": f"scenescape/cmd/camera/{sensor.sensor_id}",
        "deleteUrl": (
          reverse("cam_delete", args=[sensor.id])
          if request.user.is_superuser else None
        ),
      })
    elif sensor.type == "generic":
      sensors.append({
        "id": str(sensor.id),
        "sensorId": sensor.sensor_id,
        "name": sensor.name,
        "iconUrl": sensor.icon.url if sensor.icon else None,
        "areaJson": sensor.areaJSON(),
        "calibrateHref": f"?ss=calibrate-sensor&id={sensor.id}",
        "editHref": f"?ss=sensor-edit&id={sensor.sensor_id}",
        "deleteUrl": (
          reverse("singleton_sensor_delete", args=[sensor.id])
          if request.user.is_superuser else None
        ),
      })

  children = []
  for link in scene.children.all():
    child = link.child
    child_name = child.name if child else (link.child_name or "Child")
    if child is not None:
      rest_uid = str(child.id)
    elif link.remote_child_id:
      rest_uid = str(link.remote_child_id)
    else:
      rest_uid = str(link.id)
    children.append({
      "id": str(link.id),
      "name": child_name,
      "childType": link.child_type,
      "remoteChildId": (
        str(link.remote_child_id) if link.remote_child_id else None
      ),
      "detailUrl": reverse("sceneDetail", args=[child.id]) if child else None,
      "thumbnailUrl": (
        child.thumbnail.url if child and child.thumbnail else None
      ),
      "mapUrl": child.map.url if child and child.map else None,
      "restUid": rest_uid,
      "editHref": f"?ss=child-edit&id={rest_uid}",
      "deleteUrl": (
        reverse("child_delete", args=[link.id])
        if request.user.is_superuser else None
      ),
    })

  auth_token = ""
  if hasattr(request.user, "auth_token") and request.user.auth_token:
    auth_token = str(request.user.auth_token)

  try:
    regions = json.loads(scene.roiJSON() or "[]")
  except (TypeError, json.JSONDecodeError):
    regions = []
  try:
    tripwires = json.loads(scene.tripwireJSON() or "[]")
  except (TypeError, json.JSONDecodeError):
    tripwires = []

  map_url = scene.map.url if scene.map else None
  thumb_url = scene.thumbnail.url if scene.thumbnail else None

  scene_detail_bootstrap = {
    "scene": {
      "id": str(scene.id),
      "name": scene.name,
      "scale": scene.scale,
      "mapUrl": map_url,
      "thumbnailUrl": thumb_url,
      "wssConnection": scene.wssConnection(),
      "outputLla": bool(scene.output_lla),
      "georeferenced": bool(scene.output_lla and scene.map_corners_lla),
    },
    "cameras": cameras,
    "sensors": sensors,
    "children": children,
    "regions": regions if isinstance(regions, list) else [],
    "tripwires": tripwires if isinstance(tripwires, list) else [],
    "counts": {
      "sensors": len(sensors),
      "regions": len(regions) if isinstance(regions, list) else 0,
      "tripwires": len(tripwires) if isinstance(tripwires, list) else 0,
      "children": len(children),
    },
    "urls": {
      "scenesHome": reverse("index"),
      "camList": reverse("cam_list"),
      "sensorList": reverse("singleton_sensor_list"),
      "scene3d": reverse("scene_detail", args=[scene.id]),
      "sceneEdit": reverse("scene_update", args=[scene.id]) if request.user.is_superuser else None,
      "sceneDelete": reverse("scene_delete", args=[scene.id]) if request.user.is_superuser else None,
      "camCreate": (
        f"{reverse('cam_create')}?scene={scene.id}" if request.user.is_superuser else None
      ),
    },
    "authToken": auth_token,
    "isSuperuser": request.user.is_superuser,
    "isKubernetes": bool(settings.KUBERNETES_SERVICE_HOST),
    "appVersion": getattr(settings, "APP_VERSION_NUMBER", None),
    "googleMapsApiKey": getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "",
    "mapboxApiKey": getattr(settings, "MAPBOX_API_KEY", "") or "",
    "deleteImpact": {
      "sensors": scene.sensor_set.count(),
      "regions": scene.regions.count(),
      "tripwires": scene.tripwires.count(),
    },
    "scenes": [
      {
        "id": str(s.id),
        "name": s.name,
        "georeferenced": bool(s.output_lla and s.map_corners_lla),
      }
      for s in Scene.objects.order_by("name")
    ],
  }

  return render(request, 'sscape/sceneDetail.html', {
    'scene': scene,
    'child_rois': child_rois,
    'child_tripwires': child_trips,
    'child_sensors': child_sensors,
    'scene_detail_bootstrap': scene_detail_bootstrap,
    'google_maps_api_key': getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "",
    'mapbox_api_key': getattr(settings, "MAPBOX_API_KEY", "") or "",
  })

@superuser_required
def saveROI(request, scene_id):
  scene = get_object_or_404(Scene, pk=scene_id)

  if request.method == 'POST':
    form = ROIForm(request.POST)
    if form.is_valid():
      saveRegionData(scene, form)
      saveTripwireData(scene, form)
      return redirect('/' + str(scene.id))
    else:
      log.error("Form bad", request.POST)
  return redirect('/' + str(scene.id))

def saveTripwireData(scene, form):
  jdata = json.loads(form.cleaned_data['tripwires'],
                        object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))
  current_tripwire_ids = set()

  for trip in jdata:
    query_uuid = trip.uuid

    # when a new tripwire is created uuid is invalid
    if not validate_uuid(trip.uuid):
      query_uuid = uuid.uuid4()

    # Use the provided title or default to "tripwire_<query_uuid>"
    trip_title = trip.title if trip.title else f"tripwire_{query_uuid}"

    tripwire, _ = Tripwire.objects.update_or_create(uuid=query_uuid, defaults={
        'scene':scene, 'name':trip_title,
      })
    current_tripwire_ids.add(tripwire.uuid)

    current_tripwire_point_ids= set()
    for point in trip.points:
      point, _ = TripwirePoint.objects.update_or_create(tripwire=tripwire, x=point[0], y=point[1])
      current_tripwire_point_ids.add(point.id)

    # when tripwire is modified older points should be deleted
    TripwirePoint.objects.filter(tripwire = tripwire).exclude(id__in=current_tripwire_point_ids).delete()

    # notify on mqtt for every tripwire saved
    # ideally one notification after all tripwires are saved in db
    tripwire.notifydbupdate()

  # delete older tripwires
  tripwires_to_delete = Tripwire.objects.filter(scene=scene).exclude(uuid__in=current_tripwire_ids)
  TripwirePoint.objects.filter(tripwire__in=tripwires_to_delete).delete()

  # delete tripwires individually to trigger notifydbupdate
  for tw in tripwires_to_delete:
    tw.delete()

  return

def saveRegionData(scene, form):
  jdata = json.loads(form.cleaned_data['rois'],
                        object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))

  current_region_ids = set()

  for roi in jdata:
    query_uuid = roi.uuid

    # when a new roi is created uuid is invalid
    if not validate_uuid(roi.uuid):
      query_uuid = uuid.uuid4()

    # Use the provided title or default to "roi_<query_uuid>"
    roi_title = roi.title if roi.title else f"roi_{query_uuid}"

    region, _ = Region.objects.update_or_create(uuid=query_uuid, defaults={
      'scene': scene,
      'name': roi_title,
      'volumetric': getattr(roi, 'volumetric', False),
      'height': getattr(roi, 'height', 1),
      'buffer_size': getattr(roi, 'buffer_size', 0)
      })
    current_region_ids.add(region.uuid)

    current_region_point_ids= set()
    # sequence field stores order of points
    for point_idx,point in enumerate(roi.points):
      point, _ = RegionPoint.objects.update_or_create(region=region, x=point[0], y=point[1],
                                                      sequence=point_idx)
      current_region_point_ids.add(point.id)

    # when roi is modified older points should be deleted
    RegionPoint.objects.filter(region = region).exclude(id__in=current_region_point_ids).delete()

    if hasattr(roi, 'sectors'):
      sectors = []
      for sector in roi.sectors:
        sectors.append({"color": sector.color, "color_min": sector.color_min})

      RegionOccupancyThreshold.objects.update_or_create(region=region, defaults={
        'sectors': sectors, 'range_max': roi.range_max
      })

    # notify on mqtt for every region saved in db
    # ideally one notification after all regions are saved in db
    region.notifydbupdate()

  # delete older rois
  regions_to_delete = Region.objects.filter(scene=scene).exclude(uuid__in=current_region_ids)
  RegionPoint.objects.filter(region__in=regions_to_delete).delete()
  RegionOccupancyThreshold.objects.filter(region__in=regions_to_delete).delete()

  # delete regions individually to trigger notifydbupdate
  for region in regions_to_delete:
    region.delete()

  return

#Cam CRUD
class CamCreateView(SuperUserCheck, View):
  """React drawer only; URL redirects into ?ss=cam-create."""

  def _sheet(self, request):
    scene_id = request.GET.get('scene') or request.POST.get('scene')
    if scene_id:
      return sheet_redirect(scene_path(scene_id), 'cam-create')
    return sheet_redirect(reverse('cam_list'), 'cam-create')

  def get(self, request, *args, **kwargs):
    return self._sheet(request)

  def post(self, request, *args, **kwargs):
    return self._sheet(request)

class CamDeleteView(SuperUserCheck, DeleteView):
  model = Cam
  # Confirm UX is React; GET redirects away. POST still deletes.
  template_name = "sscape/embed_done.html"

  def get(self, request, *args, **kwargs):
    self.object = self.get_object()
    if self.object.scene_id:
      return redirect(scene_path(self.object.scene_id))
    return redirect(reverse('cam_list'))

  def get_success_url(self):
    if self.object.scene is not None:
      scene_id = self.object.scene.id
      return '/' + str(scene_id)
    return reverse_lazy('cam_list')

class CamDetailView(SuperUserCheck, View):
  """Legacy detail URL → calibrate sheet on the camera list."""

  def get(self, request, *args, **kwargs):
    cam = get_object_or_404(Cam, pk=kwargs['pk'])
    if cam.scene_id:
      return sheet_redirect(reverse('cam_list'), 'calibrate-cam', cam.pk)
    return redirect(reverse('cam_list'))

class CamListView(LoginRequiredMixin, ListView):
  model = Cam
  template_name = "cam/cam_list.html"

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    primary = None
    if self.request.user.is_superuser:
      primary = {
        'label': '+ New Camera',
        'href': f"{reverse('cam_list')}?ss=cam-create",
        'id': 'new-camera',
      }
    rows = []
    for cam in context['object_list']:
      scene = cam.scene
      actions = []
      if self.request.user.is_superuser:
        if scene:
          actions.append({
            'label': 'Manage',
            'href': f"{reverse('cam_list')}?ss=calibrate-cam&id={cam.id}",
          })
        else:
          actions.append({
            'label': 'Edit',
            'href': f"{reverse('cam_list')}?ss=cam-edit&id={cam.sensor_id}",
          })
        actions.append({
          'label': 'Delete',
          'href': reverse('cam_delete', args=[cam.id]),
          'tone': 'danger',
        })
      rows.append({
        'id': str(cam.id),
        'cells': [
          {'text': str(cam)},
          {'text': cam.sensor_id},
          {
            'text': str(scene) if scene else '--',
            'href': (
              f"{reverse('sceneDetail', args=[scene.id])}?from=cam-list"
              if scene else None
            ),
          },
        ],
        'actions': actions,
      })
    context['admin_list_bootstrap'] = {
      'title': 'Cameras',
      'breadcrumbs': [{'label': 'Cameras'}],
      'primaryAction': primary,
      'columns': ['Camera Name', 'Camera ID', 'Scene'],
      'rows': rows,
      'emptyMessage': 'No cameras are available.',
      'isSuperuser': self.request.user.is_superuser,
    }
    context['list_sheets_bootstrap'] = {
      'authToken': _user_auth_token(self.request.user),
      'isSuperuser': self.request.user.is_superuser,
      'kind': 'cam',
      'defaultSceneId': None,
      'isKubernetes': bool(settings.KUBERNETES_SERVICE_HOST),
      'cameras': [
        {
          'id': str(cam.id),
          'sensorId': cam.sensor_id,
          'name': str(cam),
          'sceneId': str(cam.scene_id) if cam.scene_id else None,
        }
        for cam in context['object_list']
      ],
      'scenes': [
        {'id': str(s.id), 'name': s.name}
        for s in Scene.objects.order_by('name')
      ],
    }
    return context

class CamUpdateView(SuperUserCheck, View):
  """React sheet only; URL redirects into ?ss=cam-edit."""

  def get(self, request, *args, **kwargs):
    cam = get_object_or_404(Cam, pk=kwargs['pk'])
    return sheet_redirect(reverse('cam_list'), 'cam-edit', cam.sensor_id)

  def post(self, request, *args, **kwargs):
    return self.get(request, *args, **kwargs)

#Scene CRUD
class SceneCreateView(SuperUserCheck, View):
  """React sheet only; URL redirects into ?ss=scene-create."""

  def get(self, request, *args, **kwargs):
    return sheet_redirect(reverse('index'), 'scene-create')

  def post(self, request, *args, **kwargs):
    return sheet_redirect(reverse('index'), 'scene-create')

class SceneDeleteView(SuperUserCheck, DeleteView):
  model = Scene
  template_name = "sscape/embed_done.html"
  success_url = reverse_lazy('index')

  def get(self, request, *args, **kwargs):
    return redirect(reverse('index'))

class SceneDetailView(LoginRequiredMixin, DetailView):
  model = Scene
  template_name = "scene/scene_detail.html"

  def get_context_data(self, **kwargs):
    # Call the base implementation first to get a context
    context = super().get_context_data(**kwargs)
    # Add in a QuerySet of all available 3D assets
    context['assets'] = Asset3D.objects.all()
    context['child_rois'], context['child_tripwires'], context['child_sensors'] = getAllChildrenMetaData(context['scene'].id)

    return context

class SceneListView(LoginRequiredMixin, RedirectView):
  """Scenes home is React on index; keep URL for bookmarks."""
  permanent = False

  def get_redirect_url(self, *args, **kwargs):
    return reverse('index')

class SceneUpdateView(SuperUserCheck, View):
  """React manage panel only; no Django embed form."""

  def get(self, request, *args, **kwargs):
    scene = get_object_or_404(Scene, pk=kwargs['pk'])
    return sheet_redirect(scene_path(scene.pk), 'scene-manage')

  def post(self, request, *args, **kwargs):
    return self.get(request, *args, **kwargs)

class SceneImportView(SuperUserCheck, View):
  """React modal only; URL redirects into ?ss=scene-import."""

  def get(self, request, *args, **kwargs):
    return sheet_redirect(reverse('index'), 'scene-import')

  def post(self, request, *args, **kwargs):
    return sheet_redirect(reverse('index'), 'scene-import')

#Singleton Sensor CRUD
class SingletonSensorCreateView(SuperUserCheck, View):
  """React drawer only; URL redirects into ?ss=sensor-create."""

  def _sheet(self, request):
    scene_id = request.GET.get('scene') or request.POST.get('scene')
    if scene_id:
      return sheet_redirect(scene_path(scene_id), 'sensor-create')
    return sheet_redirect(reverse('singleton_sensor_list'), 'sensor-create')

  def get(self, request, *args, **kwargs):
    return self._sheet(request)

  def post(self, request, *args, **kwargs):
    return self._sheet(request)

class SingletonSensorDeleteView(SuperUserCheck, DeleteView):
  model = SingletonSensor
  template_name = "sscape/embed_done.html"

  def get(self, request, *args, **kwargs):
    self.object = self.get_object()
    if self.object.scene_id:
      return redirect(scene_path(self.object.scene_id))
    return redirect(reverse('singleton_sensor_list'))

  def get_success_url(self):
    if self.object.scene is not None:
      scene_id = self.object.scene.id
      return '/' + str(scene_id)
    return reverse_lazy('singleton_sensor_list')

class SingletonSensorDetailView(SuperUserCheck, View):
  """Legacy detail URL → calibrate sheet on the sensor list."""

  def get(self, request, *args, **kwargs):
    sensor = get_object_or_404(SingletonSensor, pk=kwargs['pk'])
    if sensor.scene_id:
      return sheet_redirect(
        reverse('singleton_sensor_list'), 'calibrate-sensor', sensor.pk
      )
    return redirect(reverse('singleton_sensor_list'))

class SingletonSensorListView(LoginRequiredMixin, ListView):
  model = SingletonSensor
  template_name = "singleton_sensor/singleton_sensor_list.html"

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    primary = None
    if self.request.user.is_superuser:
      primary = {
        'label': '+ New Sensor',
        'href': f"{reverse('singleton_sensor_list')}?ss=sensor-create",
        'id': 'new-sensor',
      }
    rows = []
    for sensor in context['object_list']:
      scene = sensor.scene
      actions = []
      if self.request.user.is_superuser:
        if scene:
          actions.append({
            'label': 'Manage',
            'href': (
              f"{reverse('singleton_sensor_list')}"
              f"?ss=calibrate-sensor&id={sensor.id}"
            ),
          })
        else:
          actions.append({
            'label': 'Edit',
            'href': (
              f"{reverse('singleton_sensor_list')}"
              f"?ss=sensor-edit&id={sensor.sensor_id}"
            ),
          })
        actions.append({
          'label': 'Delete',
          'href': reverse('singleton_sensor_delete', args=[sensor.id]),
          'tone': 'danger',
        })
      rows.append({
        'id': str(sensor.id),
        'cells': [
          {'text': str(sensor)},
          {'text': sensor.sensor_id},
          {
            'text': str(scene) if scene else '--',
            'href': (
              f"{reverse('sceneDetail', args=[scene.id])}?from=sensor-list"
              if scene else None
            ),
          },
        ],
        'actions': actions,
      })
    context['admin_list_bootstrap'] = {
      'title': 'Sensors',
      'breadcrumbs': [{'label': 'Sensors'}],
      'primaryAction': primary,
      'columns': ['Sensor Name', 'Sensor ID', 'Scene'],
      'rows': rows,
      'emptyMessage': 'No sensors are available.',
      'isSuperuser': self.request.user.is_superuser,
    }
    context['list_sheets_bootstrap'] = {
      'authToken': _user_auth_token(self.request.user),
      'isSuperuser': self.request.user.is_superuser,
      'kind': 'sensor',
      'defaultSceneId': None,
      'sensors': [
        {
          'id': str(sensor.id),
          'sensorId': sensor.sensor_id,
          'name': str(sensor),
          'sceneId': str(sensor.scene_id) if sensor.scene_id else None,
        }
        for sensor in context['object_list']
      ],
      'scenes': [
        {'id': str(s.id), 'name': s.name}
        for s in Scene.objects.order_by('name')
      ],
    }
    return context

class SingletonSensorUpdateView(SuperUserCheck, View):
  """React sheet only; URL redirects into ?ss=sensor-edit."""

  def get(self, request, *args, **kwargs):
    sensor = get_object_or_404(SingletonSensor, pk=kwargs['pk'])
    return sheet_redirect(
      reverse('singleton_sensor_list'), 'sensor-edit', sensor.sensor_id
    )

  def post(self, request, *args, **kwargs):
    return self.get(request, *args, **kwargs)

# 3D Asset CRUD
class AssetCreateView(SuperUserCheck, View):
  """React drawer only; URL redirects into ?ss=asset-create."""

  def get(self, request, *args, **kwargs):
    return sheet_redirect(reverse('asset_list'), 'asset-create')

  def post(self, request, *args, **kwargs):
    return sheet_redirect(reverse('asset_list'), 'asset-create')

class AssetDeleteView(SuperUserCheck, DeleteView):
  model = Asset3D
  template_name = "sscape/embed_done.html"
  success_url = reverse_lazy('asset_list')

  def get(self, request, *args, **kwargs):
    return redirect(reverse('asset_list'))

class AssetListView(LoginRequiredMixin, ListView):
  model = Asset3D
  template_name = "asset/asset_list.html"

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    primary = None
    if self.request.user.is_superuser:
      primary = {
        'label': '+ New Object',
        'href': f"{reverse('asset_list')}?ss=asset-create",
        'id': 'new-asset',
      }
    rows = []
    for asset in context['object_list']:
      actions = []
      if self.request.user.is_superuser:
        actions.append({
          'label': 'Update',
          'href': f"{reverse('asset_list')}?ss=asset-edit&id={asset.id}",
          'id': f'obj-manage-{asset.name}',
        })
        actions.append({
          'label': 'Delete',
          'href': reverse('asset_delete', args=[asset.id]),
          'tone': 'danger',
        })
      rows.append({
        'id': str(asset.id),
        'cells': [{'text': asset.name}],
        'actions': actions,
      })
    context['admin_list_bootstrap'] = {
      'title': 'Object Library',
      'breadcrumbs': [{'label': 'Object Library'}],
      'primaryAction': primary,
      'columns': ['Name'],
      'rows': rows,
      'emptyMessage': 'No objects are available.',
      'isSuperuser': self.request.user.is_superuser,
    }
    context['list_sheets_bootstrap'] = {
      'authToken': _user_auth_token(self.request.user),
      'isSuperuser': self.request.user.is_superuser,
      'kind': 'asset',
      'defaultSceneId': None,
      'scenes': [],
    }
    return context

class AssetUpdateView(SuperUserCheck, View):
  """React sheet only; URL redirects into ?ss=asset-edit."""

  def get(self, request, *args, **kwargs):
    asset = get_object_or_404(Asset3D, pk=kwargs['pk'])
    return sheet_redirect(reverse('asset_list'), 'asset-edit', asset.pk)

  def post(self, request, *args, **kwargs):
    return self.get(request, *args, **kwargs)

# Scene Child CRUD
class ChildCreateView(SuperUserCheck, View):
  """React drawer only; URL redirects into ?ss=child-create."""

  def _sheet(self, request):
    scene_id = request.GET.get('scene') or request.POST.get('scene')
    if scene_id:
      return sheet_redirect(scene_path(scene_id), 'child-create')
    return sheet_redirect(reverse('index'), 'child-create')

  def get(self, request, *args, **kwargs):
    return self._sheet(request)

  def post(self, request, *args, **kwargs):
    return self._sheet(request)

class ChildDeleteView(SuperUserCheck, DeleteView):
  model = ChildScene
  template_name = "sscape/embed_done.html"

  def get(self, request, *args, **kwargs):
    self.object = self.get_object()
    if self.object.parent_id:
      return redirect(scene_path(self.object.parent_id))
    return redirect(reverse('index'))

  def get_success_url(self):
    if self.object.parent_id:
      return scene_path(self.object.parent_id)
    return reverse_lazy('index')

class ChildUpdateView(SuperUserCheck, View):
  """React sheet only; URL redirects into ?ss=child-edit."""

  def get(self, request, *args, **kwargs):
    child = get_object_or_404(ChildScene, pk=kwargs['pk'])
    parent = child.parent
    if parent is None:
      return redirect(reverse('index'))
    if child.child_id:
      rest_uid = str(child.child_id)
    elif child.remote_child_id:
      rest_uid = str(child.remote_child_id)
    else:
      rest_uid = str(child.pk)
    return sheet_redirect(scene_path(parent.id), 'child-edit', rest_uid)

  def post(self, request, *args, **kwargs):
    return self.get(request, *args, **kwargs)

class ModelListView(LoginRequiredMixin, TemplateView):
  template_name = "model/model_list.html"

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    dir_structure = {}
    '''
    root : Prints out directories only from what you specified.
    dirs : Prints out sub-directories from root.
    files : Prints out all files from root and directories.
    '''
    for dirpath, dirnames, filenames in os.walk(settings.MODEL_ROOT):
      # Sort the directories and files alphabetically
      dirnames.sort(key=lambda s: s.lower())
      filenames.sort(key=lambda s: s.lower())

      # Relative path value
      folder = os.path.relpath(dirpath, settings.MODEL_ROOT)

      # Reset to the root directory structure
      current_level = dir_structure

      if folder != '.': # if not root folder
        for part in folder.split(os.sep):
          # Enter deeper level if the current directory exists in the dictionary
          # Otherwise, create a new entry for the directory
          current_level = current_level.setdefault(part, {})

      # Add sub-directories to the current level
      for dirname in dirnames:
        current_level[dirname] = {}

      # Add files to the current level
      for filename in filenames:
        current_level[filename] = None

    context['directory_structure'] = dir_structure
    context['models_directory_bootstrap'] = {
      'isSuperuser': self.request.user.is_superuser,
    }

    return context

def get_login_delay(request):
  log.info(request.META.get('REMOTE_ADDR'))
  user = FailedLogin.objects.filter(ip=request.META.get('REMOTE_ADDR')).first()
  if user:
    return user.delay
  else:
    return 0

def sign_in(request):
  form = AuthenticationForm()
  maxLength = form['username'].field.max_length
  if request.method == 'POST':
    delay = get_login_delay(request)
    if delay:
      time.sleep(delay)

    if len(request.POST['username']) <= maxLength:
      form = AuthenticationForm(data=request.POST, request=request)
      value_next = request.GET.get('next')
    else:
      form.cleaned_data = {}
      form.add_error(None, 'Username should not be more than {} characters'.format(maxLength))

    if form.is_valid():
      user = authenticate(username=request.POST['username'], password=request.POST['password'], request=request)
      if user is not None:
        Token.objects.get_or_create(user=user)
        login(request, user)

        if value_next:
          if url_has_allowed_host_and_scheme(url=value_next, allowed_hosts={request.get_host()}):
            return redirect(value_next)
          else:
            return redirect('index')

        if Scene.objects.count() == 1:
          return redirect('sceneDetail', Scene.objects.first().id)

        return redirect('index')

  return render(request, 'sscape/sign_in.html', {'form': form})

def sign_out(request):
  logout(request)
  return HttpResponseRedirect("/")

def account_locked(request):
  return render(request, 'sscape/account_locked.html')

@superuser_required
def cameraCalibrate(request, sensor_id):
  """Embed-only 3D CamCanvas + Viewport for the React calibrate panel."""
  cam_inst = get_object_or_404(Cam, pk=sensor_id)
  embed = request.GET.get('embed') == '1' or request.POST.get('embed') == '1'

  if not embed:
    if cam_inst.scene_id:
      return sheet_redirect(
        reverse('cam_list'), 'calibrate-cam', cam_inst.pk
      )
    return redirect(reverse('cam_list'))
  if not cam_inst.scene_id:
    return redirect(reverse('cam_list'))

  if request.method == 'POST':
    form = CamCalibrateForm(request.POST, request.FILES, instance=cam_inst)
    if form.is_valid():
      log.info('Form received {}'.format(form.cleaned_data))

      if settings.KUBERNETES_SERVICE_HOST:
        if cam_inst.use_camera_pipeline and not cam_inst.camera_pipeline:
          form.add_error(
            None,
            "ERROR! Camera Pipeline field cannot be empty if "
            "'Use Camera Pipeline' is enabled.")
          generated_pipeline_url = reverse(
            'generate_camera_pipeline', kwargs={'sensor_id': cam_inst.pk})
          return render(request, 'cam/cam_calibrate.html', {
            'form': form,
            'caminst': cam_inst,
            'generated_pipeline_url': generated_pipeline_url,
            'embed': embed,
          })
        try:
          generated_pipeline = generate_pipeline_string_from_dict(
            form.cleaned_data)
          log.info(
            "Camera settings validated. Successfully generated pipeline: "
            f"{generated_pipeline[:100]}...")
        except (PipelineGenerationValueError,
                PipelineGenerationNotImplementedError) as e:
          log.error(f"Invalid camera settings for camera {cam_inst.name}: {e}")
          form.add_error(None, f"ERROR! Invalid camera settings: {str(e)}.")
          generated_pipeline_url = reverse(
            'generate_camera_pipeline', kwargs={'sensor_id': cam_inst.pk})
          return render(request, 'cam/cam_calibrate.html', {
            'form': form,
            'caminst': cam_inst,
            'generated_pipeline_url': generated_pipeline_url,
            'embed': embed,
          })
        except Exception as e:
          log.error(f"Invalid camera settings for camera {cam_inst.name}: {e}")
          form.add_error(None, "ERROR! Invalid camera settings: internal error.")
          generated_pipeline_url = reverse(
            'generate_camera_pipeline', kwargs={'sensor_id': cam_inst.pk})
          return render(request, 'cam/cam_calibrate.html', {
            'form': form,
            'caminst': cam_inst,
            'generated_pipeline_url': generated_pipeline_url,
            'embed': embed,
          })

      form.save()
      return render(request, 'cam/cam_calibrate_done.html', {
        'reload': True,
      })
    log.warning('Form not valid!')
  else:
    form = CamCalibrateForm(instance=cam_inst)

  generated_pipeline_url = reverse(
    'generate_camera_pipeline', kwargs={'sensor_id': cam_inst.pk})

  return render(request, 'cam/cam_calibrate.html', {
    'form': form,
    'caminst': cam_inst,
    'generated_pipeline_url': generated_pipeline_url,
    'embed': embed,
  })

def getAllChildrenMetaData(scene_id):
  children = ChildScene.objects.filter(parent=scene_id)
  child_rois = []
  child_trips = []
  child_sensors = []
  for c in children:
    if c.child_type == "local":
      child_scene = get_object_or_404(Scene, pk=c.child.id)
      current_child_name = c.child.name

      for region in json.loads(child_scene.roiJSON()):
        region['from_child_scene'] = current_child_name
        child_rois.append(applyChildTransform(region, c.cameraPose))

      for tripwire in json.loads(child_scene.tripwireJSON()):
        tripwire['from_child_scene'] = current_child_name
        child_trips.append(applyChildTransform(tripwire, c.cameraPose))

      child_scene_sensors = list(filter(lambda x: x.type=='generic', child_scene.sensor_set.all()))
      current_child_sensors = [json.loads(s.areaJSON())|{'title': s.name} for s in child_scene_sensors]

      for cs in current_child_sensors:
        cs['from_child_scene'] = current_child_name
        if cs['area'] in [CIRCLE, POLY]:
          child_sensors.append(applyChildTransform(cs, c.cameraPose))
        else:
          child_sensors.append(cs)

    # FIXME add rest api call to remote child using child scene api token

  return json.dumps(child_rois), json.dumps(child_trips), json.dumps(child_sensors)

class SaveGeospatialSnapshot(APIView):
  """Save geospatial snapshot as PNG and return filename for map field."""
  # Called from an authenticated browser session, not an external API client
  authentication_classes = [SessionAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  def post(self, request):
    try:
      import base64
      from django.utils import timezone

      # Get the image data from the request
      image_data = request.data.get('image_data')
      if not image_data:
        return JsonResponse({'error': 'No image data provided'}, status=400)

      # Remove data URL prefix if present
      if image_data.startswith('data:image/png;base64,'):
        image_data = image_data.replace('data:image/png;base64,', '')

      # Decode base64 image data
      try:
        image_binary = base64.b64decode(image_data)
      except Exception as decode_error:
        return JsonResponse({'error': 'Failed to decode image data'}, status=400)

      # Generate unique filename
      timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
      filename = f'geospatial_map_{timestamp}.png'

      # Save to media directory
      file_path = os.path.join(settings.MEDIA_ROOT, filename)
      os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

      with open(file_path, 'wb') as f:
        f.write(image_binary)

      # Return the filename for the map field
      return JsonResponse({
        'success': True,
        'filename': filename,
        'media_url': settings.MEDIA_URL + filename
      })

    except Exception as e:
      log.error("Error saving geospatial snapshot")
      return JsonResponse({'error': 'An internal error has occurred'}, status=500)

@superuser_required
def generate_camera_pipeline(request, sensor_id):
  """Generate camera pipeline preview for a specific camera sensor."""
  log.debug(f"generate_camera_pipeline called with sensor_id={sensor_id}, method={request.method}")

  if request.method != 'POST':
    return JsonResponse({"error": "Only POST method allowed"}, status=405)

  try:
    form_data = json.loads(request.body.decode('utf-8'))
    log.debug(f"Received form data: {form_data}")
  except json.JSONDecodeError as e:
    log.error(f"JSON decode error: {e}")
    return JsonResponse({"error": "Invalid JSON data"}, status=400)
  except UnicodeDecodeError as e:
    log.error(f"Unicode decode error: {e}")
    return JsonResponse({"error": "Invalid request encoding"}, status=400)

  try:
    pipeline = generate_pipeline_string_from_dict(form_data)
    return JsonResponse({
      "pipeline": pipeline,
      "success": True
    })
  # error messages specific for pipeline generation are controlled and should be relayed to user
  except (PipelineGenerationValueError, PipelineGenerationNotImplementedError) as e:
    log.error(f"Pipeline generation error: {e}")
    log.error(f"Traceback: {traceback.format_exc()}")
    return JsonResponse({"error": str(e)}, status=500)
  # otherwise show generic error message and not reveal any internal details
  except Exception as e:
    log.error(f"Exception occurred: {e}")
    log.error(f"Traceback: {traceback.format_exc()}")
    return JsonResponse({"error": "Error generating pipeline"}, status=500)

@superuser_required
def generate_mesh_status(request, pk):
  scene = get_object_or_404(Scene, pk=pk)
  request_id = request.GET.get("request_id")
  if not request_id:
    return JsonResponse({"success": False, "error": "missing request_id"}, status=400)

  try:
    from .mesh_generator import MeshGenerator
    mesh_generator = MeshGenerator()

    status_data = mesh_generator.mapping_client.getReconstructionStatus(request_id)

    # If mapping service couldn't find it / errored, just return it
    if not status_data.get("success"):
      return JsonResponse(status_data, status=200)

    state = status_data.get("state")

    if state != "complete":
      return JsonResponse(status_data, status=200)

    with transaction.atomic():
      scene = Scene.objects.select_for_update().get(pk=scene.pk)

      if hasattr(scene, "mesh_state") and scene.mesh_state == "complete":
        status_data["finalized"] = True
        return JsonResponse(status_data, status=200)
      finalize_result = mesh_generator.finalizeMeshFromStatus(scene, request_id)

      if not finalize_result.get("success"):
        if hasattr(scene, "mesh_state"):
          scene.mesh_state = "failed"
          scene.save(update_fields=["mesh_state"])
        return JsonResponse(finalize_result, status=500)

      if hasattr(scene, "mesh_state"):
        scene.mesh_state = "complete"
        scene.save(update_fields=["mesh_state"])

    status_data["finalized"] = True
    return JsonResponse(status_data, status=200)

  except Exception as e:
    log.error(f"Mesh status error: {e}")
    log.error(f"Traceback: {traceback.format_exc()}")
    return JsonResponse({
      "success": False,
      "error": "An internal error occurred while getting mesh status",
    }, status=500)

@superuser_required
def generate_mesh(request, pk):
  """Generate 3D mesh from scene cameras using mapping service."""
  if request.method != 'POST':
    return JsonResponse({"error": "Only POST method allowed"}, status=405)

  try:
    from .mesh_generator import MeshGenerator

    # Get scene object
    scene = get_object_or_404(Scene, pk=pk)

    # Initialize mesh generator
    mesh_type = request.POST.get("mesh_type", "mesh")
    uploaded_map = request.FILES.get("map", None)
    mesh_generator = MeshGenerator()

    # Generate mesh
    result = mesh_generator.startMeshGeneration(scene, mesh_type, uploaded_map=uploaded_map)
    if result.get("success"):
      return JsonResponse({
        "success": True,
        "message": "Mesh generated successfully",
        "request_id": result["request_id"],
        "processing_time": result.get("processing_time", 0),
      })

    return JsonResponse({
      "success": False,
      "error": result.get("error", "Unknown error occurred while generating mesh"),
      "processing_time": result.get("processing_time", 0),
    }, status=400)

  except Exception as e:
    log.error(f"Mesh generation error: {e}")
    import traceback
    log.error(f"Traceback: {traceback.format_exc()}")
    return JsonResponse({
      "success": False,
      "error": "An internal error occurred while generating mesh",
    }, status=500)

@superuser_required
def check_mapping_service_status(request):
  """Check if the mapping service is available and ready."""
  if request.method != 'GET':
    return JsonResponse({"error": "Only GET method allowed"}, status=405)

  try:
    from manager.mesh_generator import MappingServiceClient

    # Check mapping service health
    client = MappingServiceClient()
    health_status = client.checkHealth()

    return JsonResponse(health_status)

  except Exception as e:
    log.error(f"Error checking mapping service status: {e}")
    return JsonResponse({
      "available": False,
      "error": f"An internal error occurred while checking mapping service status"
    }, status=500)
