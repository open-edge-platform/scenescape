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
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views import View
from django.views.generic import DetailView, RedirectView, TemplateView
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
  return render(request, 'sscape/index.html', {})

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

@superuser_required
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
  # Ensure scene exists (404) without embedding full island bootstrap.
  get_object_or_404(Scene, pk=scene_id)
  return render(request, 'sscape/sceneDetail.html', {
    'scene_id': str(scene_id),
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

class CamListView(LoginRequiredMixin, TemplateView):
  template_name = "cam/cam_list.html"


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

class SingletonSensorListView(LoginRequiredMixin, TemplateView):
  template_name = "singleton_sensor/singleton_sensor_list.html"


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

class AssetListView(LoginRequiredMixin, TemplateView):
  template_name = "asset/asset_list.html"


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

def get_login_delay(request):
  log.info(request.META.get('REMOTE_ADDR'))
  user = FailedLogin.objects.filter(ip=request.META.get('REMOTE_ADDR')).first()
  if user:
    return user.delay
  else:
    return 0

def _wants_json(request) -> bool:
  accept = request.headers.get("Accept", "")
  return (
    "application/json" in accept
    or request.headers.get("X-Requested-With") == "XMLHttpRequest"
  )


def _sign_in_success_url(request, value_next: str | None) -> str:
  allowed = set(settings.ALLOWED_HOSTS)
  if value_next:
    if url_has_allowed_host_and_scheme(url=value_next, allowed_hosts=allowed):
      return value_next
    return reverse("index")
  if Scene.objects.count() == 1:
    return reverse("sceneDetail", args=[Scene.objects.first().id])
  return reverse("index")


@ensure_csrf_cookie
def sign_in(request):
  form = AuthenticationForm()
  maxLength = form['username'].field.max_length
  value_next = request.GET.get('next')
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
      user = form.get_user()
      if user is not None:
        Token.objects.get_or_create(user=user)
        login(request, user)
        redirect_to = _sign_in_success_url(request, value_next)
        if _wants_json(request):
          return JsonResponse({"ok": True, "redirect": redirect_to})
        return redirect(redirect_to)

    if _wants_json(request):
      errors = [str(e) for e in form.non_field_errors()]
      for field, field_errors in form.errors.items():
        if field == "__all__":
          continue
        for err in field_errors:
          errors.append(str(err))
      if not errors:
        errors = ["Invalid username or password."]
      return JsonResponse({"ok": False, "errors": errors}, status=400)

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

    elif c.child_type == "remote":
      current_child_name = c.child_name
      for region in (c.cached_rois or []):
        region = dict(region)
        region['from_child_scene'] = current_child_name
        child_rois.append(applyChildTransform(region, c.cameraPose))
      for tripwire in (c.cached_tripwires or []):
        tripwire = dict(tripwire)
        tripwire['from_child_scene'] = current_child_name
        child_trips.append(applyChildTransform(tripwire, c.cameraPose))
      for sensor in (c.cached_sensors or []):
        sensor = dict(sensor)
        sensor['from_child_scene'] = current_child_name
        if sensor.get('area') in [CIRCLE, POLY]:
          child_sensors.append(applyChildTransform(sensor, c.cameraPose))
        else:
          child_sensors.append(sensor)

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
