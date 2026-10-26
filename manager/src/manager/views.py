# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import math
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
from django.db import IntegrityError, transaction
from django.dispatch.dispatcher import receiver
from django.http import FileResponse, HttpResponse, HttpResponseNotFound, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.core.files.storage import default_storage
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication, TokenAuthentication

from manager.api import IsAdminOrReadOnly
from manager import osm_query, osm_roi
from manager.ppl_generator import generate_pipeline_string_from_dict, PipelineGenerationValueError, PipelineGenerationNotImplementedError
from manager.models import Scene, ChildScene, \
  Cam, Asset3D, \
  SingletonSensor, SingletonScalarThreshold, \
  Region, RegionPoint, Tripwire, TripwirePoint, \
  SingletonAreaPoint, UserSession, FailedLogin, \
  RegionOccupancyThreshold, SceneImport, sendUpdateCommand
from manager.forms import CamCalibrateForm, ROIForm, SingletonForm, SingletonDetailsForm, \
  SceneUpdateForm, SceneImportForm, CamCreateForm, SingletonCreateForm, ChildSceneForm
from manager.validators import add_form_error, validate_uuid


def _is_number(v):
  """True for real, finite numbers; rejects bool (an int subclass) and NaN/Infinity."""
  return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


MIN_REGION_POINTS = 3
MIN_TRIPWIRE_POINTS = 2


def _valid_points(points, min_points):
  """True if points has at least min_points entries, each an [x, y] pair of finite, non-bool numbers."""
  return isinstance(points, (list, tuple)) and len(points) >= min_points and all(
    isinstance(p, (list, tuple)) and len(p) == 2 and _is_number(p[0]) and _is_number(p[1])
    for p in points)


REGION_NAME_MAX_LENGTH = Region._meta.get_field('name').max_length
REGION_TYPE_MAX_LENGTH = Region._meta.get_field('roi_type').max_length


def _scoped_uuid(model, query_uuid, scene):
  """Force a fresh uuid if the client-supplied one belongs to another scene,
  so a reused/guessed uuid can't reassign that scene's region/tripwire."""
  if model.objects.filter(uuid=query_uuid).exclude(scene=scene).exists():
    return uuid.uuid4()
  return query_uuid


def _dedupe_name(name, seen):
  """Append a numeric suffix to keep a name unique within one save batch.

  shortcut: silently renames rather than rejecting the save; upgrade to a form
  error if users need to be told about the collision instead.
  """
  seen[name] = seen.get(name, 0) + 1
  return name if seen[name] == 1 else f"{name}-{seen[name]}"

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
  context = {'scenes': scenes}
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
  scene = get_object_or_404(Scene, pk=scene_id)
  child_rois, child_trips, child_sensors = getAllChildrenMetaData(scene_id)

  osm_roi_disabled_reason = None
  if scene.map_type != 'geospatial_map':
    osm_roi_disabled_reason = "Scene map is not geospatial"
  elif not os.environ.get(osm_query.API_KEY_ENV_VAR):
    osm_roi_disabled_reason = f"OSM API key ({osm_query.API_KEY_ENV_VAR}) is not configured"

  return render(request, 'sscape/sceneDetail.html', {'scene': scene, 'child_rois': child_rois,
                                                     'child_tripwires': child_trips, 'child_sensors': child_sensors,
                                                     'osm_roi_disabled_reason': osm_roi_disabled_reason})

@superuser_required
def saveROI(request, scene_id):
  scene = get_object_or_404(Scene, pk=scene_id)

  if request.method == 'POST':
    form = ROIForm(request.POST)
    if form.is_valid():
      try:
        # Inner atomic block so a tripwire validation error also rolls back region changes;
        # ATOMIC_REQUESTS alone would commit them because the 400 is returned, not raised.
        with transaction.atomic():
          regions_changed = saveRegionData(scene, form)
          tripwires_changed = saveTripwireData(scene, form)
      except ValueError as e:
        form.add_error(None, str(e))
        return render(request, 'sscape/sceneDetail.html', {'form': form, 'scene': scene}, status=400)
      # Single batched notification per save, regardless of how many regions/tripwires changed.
      if regions_changed or tripwires_changed:
        transaction.on_commit(lambda: sendUpdateCommand(scene_id=scene.id))
      return redirect('/' + str(scene.id))
    else:
      log.error("Form bad", request.POST)
  else:
    form = ROIForm(initial = {'rois': scene.roiJSON()})
  return render(request, 'sscape/sceneDetail.html', {'form': form, 'scene': scene})

def saveTripwireData(scene, form):
  """Save tripwires from the form. Returns True if anything was created, updated or deleted.

  Notification is batched by the caller (saveROI) instead of per-tripwire, to avoid
  flooding MQTT with one update per tripwire in a single save.
  """
  jdata = json.loads(form.cleaned_data['tripwires'],
                        object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))

  if not all(_valid_points(trip.points, MIN_TRIPWIRE_POINTS) for trip in jdata):
    raise ValueError(f'Each tripwire needs at least {MIN_TRIPWIRE_POINTS} numeric, finite [x, y] points')

  current_tripwire_ids = set()
  changed = False
  seen_names = {}

  for trip in jdata:
    changed = True
    query_uuid = trip.uuid

    # when a new tripwire is created uuid is invalid
    if not validate_uuid(trip.uuid):
      query_uuid = uuid.uuid4()
    query_uuid = _scoped_uuid(Tripwire, query_uuid, scene)

    # Use the provided title or default to "tripwire_<query_uuid>"
    trip_title = trip.title if trip.title else f"tripwire_{query_uuid}"
    trip_title = _dedupe_name(trip_title, seen_names)

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

  # delete older tripwires; bulk delete (not per-instance) to avoid triggering
  # the model's own per-instance notifydbupdate() on top of the batched notification
  tripwires_to_delete = Tripwire.objects.filter(scene=scene).exclude(uuid__in=current_tripwire_ids)
  if tripwires_to_delete.exists():
    changed = True
  TripwirePoint.objects.filter(tripwire__in=tripwires_to_delete).delete()
  tripwires_to_delete.delete()

  return changed

def _save_one_region(scene, roi, seen_names):
  """Create/update one Region (with its points and optional sectors) from a parsed roi.

  Returns the saved Region.
  """
  query_uuid = roi.uuid

  # when a new roi is created uuid is invalid
  if not validate_uuid(roi.uuid):
    query_uuid = uuid.uuid4()
  query_uuid = _scoped_uuid(Region, query_uuid, scene)

  # Use the provided title or default to "roi_<query_uuid>"
  roi_title = roi.title if roi.title else f"roi_{query_uuid}"
  roi_title = _dedupe_name(roi_title, seen_names)

  region, _ = Region.objects.update_or_create(uuid=query_uuid, defaults={
    'scene': scene,
    'name': roi_title,
    'volumetric': getattr(roi, 'volumetric', False),
    'height': getattr(roi, 'height', 1),
    'buffer_size': getattr(roi, 'buffer_size', 0),
    'roi_type': getattr(roi, 'type', '')
    })

  current_region_point_ids = set()
  # sequence field stores order of points
  for point_idx, point in enumerate(roi.points):
    point, _ = RegionPoint.objects.update_or_create(region=region, x=point[0], y=point[1],
                                                    sequence=point_idx)
    current_region_point_ids.add(point.id)

  # when roi is modified older points should be deleted
  RegionPoint.objects.filter(region=region).exclude(id__in=current_region_point_ids).delete()

  if hasattr(roi, 'sectors'):
    sectors = [{"color": sector.color, "color_min": sector.color_min} for sector in roi.sectors]
    RegionOccupancyThreshold.objects.update_or_create(region=region, defaults={
      'sectors': sectors, 'range_max': roi.range_max
    })

  return region


def saveRegionData(scene, form):
  """Save regions (manual or OSM-derived) from the form. Returns True if anything was
  created, updated or deleted.

  Notification is batched by the caller (saveROI) instead of per-region, to avoid
  flooding MQTT with one update per region in a single save (e.g. 50 OSM ROIs).
  """
  jdata = json.loads(form.cleaned_data['rois'],
                        object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))

  if not all(_valid_points(roi.points, MIN_REGION_POINTS) for roi in jdata):
    raise ValueError(f'Each roi needs at least {MIN_REGION_POINTS} numeric, finite [x, y] points')

  current_region_ids = set()
  changed = False
  seen_names = {}

  for roi in jdata:
    changed = True
    region = _save_one_region(scene, roi, seen_names)
    current_region_ids.add(region.uuid)

  # delete older rois; bulk delete (not per-instance) to avoid triggering the
  # model's own per-instance notifydbupdate() on top of the batched notification
  regions_to_delete = Region.objects.filter(scene=scene).exclude(uuid__in=current_region_ids)
  if regions_to_delete.exists():
    changed = True
  RegionPoint.objects.filter(region__in=regions_to_delete).delete()
  RegionOccupancyThreshold.objects.filter(region__in=regions_to_delete).delete()
  regions_to_delete.delete()

  return changed

#Cam CRUD
class CamCreateView(SuperUserCheck, CreateView):
  model = Cam
  form_class = CamCreateForm
  template_name = "cam/cam_create.html"

  def get_initial(self):
    initial = super().get_initial()
    scene_id = self.request.GET.get('scene')
    if scene_id:
      try:
        scene = Scene.objects.get(id=scene_id)
        initial['scene'] = scene
      except Scene.DoesNotExist:
        pass
    return initial

  def form_valid(self, form):
    form.instance.type = 'camera'
    return super(CamCreateView, self).form_valid(form)

  # Return 400 Bad Request when form validation fails
  def form_invalid(self, form):
    return self.render_to_response(self.get_context_data(form=form), status=400)

  def get_success_url(self):
    if self.object.scene is not None:
      scene_id = self.object.scene.id
      return '/' + str(scene_id)
    return reverse_lazy('cam_list')

class CamDeleteView(SuperUserCheck, DeleteView):
  model = Cam
  template_name = "cam/cam_delete.html"

  def get_success_url(self):
    if self.object.scene is not None:
      scene_id = self.object.scene.id
      return '/' + str(scene_id)
    return reverse_lazy('cam_list')

class CamDetailView(SuperUserCheck, DetailView):
  model = Cam
  template_name = "cam/cam_detail.html"

class CamListView(LoginRequiredMixin, ListView):
  model = Cam
  template_name = "cam/cam_list.html"

class CamUpdateView(SuperUserCheck, UpdateView):
  model = Cam
  fields = ['sensor_id', 'name', 'scene']
  template_name = "cam/cam_update.html"

  def get_success_url(self):
    if self.object.scene is not None:
      scene_id = self.object.scene.id
      return '/' + str(scene_id)
    return reverse_lazy('cam_list')

#Scene CRUD
class SceneCreateView(SuperUserCheck, CreateView):
  model = Scene
  fields = ['name', 'map_type', 'map', 'scale', 'output_lla', 'map_corners_lla',
            'geospatial_provider', 'map_zoom', 'map_center_lat', 'map_center_lng', 'map_bearing']
  template_name = "scene/scene_create.html"
  success_url = reverse_lazy('index')

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['google_maps_api_key'] = settings.GOOGLE_MAPS_API_KEY
    context['mapbox_api_key'] = settings.MAPBOX_API_KEY
    return context

  def form_valid(self, form):
    # Check if a generated map filename was provided
    generated_filename = self.request.POST.get('generated_map_filename')
    if generated_filename:
      # Set the map field to the generated file
      form.instance.map = generated_filename
    return super().form_valid(form)

class SceneDeleteView(SuperUserCheck, DeleteView):
  model = Scene
  template_name = "scene/scene_delete.html"
  success_url = reverse_lazy('index')

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

class SceneListView(LoginRequiredMixin, ListView):
  model = Scene
  template_name = "scene/scene_list.html"

class SceneUpdateView(SuperUserCheck, UpdateView):
  model = Scene
  form_class = SceneUpdateForm
  template_name = "scene/scene_update.html"
  success_url = reverse_lazy('index')

  def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['google_maps_api_key'] = settings.GOOGLE_MAPS_API_KEY
    context['mapbox_api_key'] = settings.MAPBOX_API_KEY
    return context

  def form_valid(self, form):
    # Check if a generated map filename was provided
    generated_filename = self.request.POST.get('generated_map_filename')
    if generated_filename:
      # Set the map field to the generated file
      form.instance.map = generated_filename
    return super().form_valid(form)

class SceneImportView(SuperUserCheck, CreateView):
  model = SceneImport
  form_class = SceneImportForm
  template_name = "scene/scene_import.html"
  success_url = reverse_lazy('index')

#Singleton Sensor CRUD
class SingletonSensorCreateView(SuperUserCheck, CreateView):
  model = SingletonSensor
  form_class = SingletonCreateForm
  template_name = "singleton_sensor/singleton_sensor_create.html"
  success_url = reverse_lazy('singleton_sensor_list')

  def get_initial(self):
    initial = super().get_initial()
    scene_id = self.request.GET.get('scene')
    if scene_id:
      try:
        scene = Scene.objects.get(id=scene_id)
        initial['scene'] = scene
      except Scene.DoesNotExist:
        pass
    return initial

  def form_valid(self, form):
    form.instance.type = 'generic'
    return super(SingletonSensorCreateView, self).form_valid(form)

  def get_success_url(self):
    if self.object.scene is not None:
      scene_id = self.object.scene.id
      return '/' + str(scene_id)
    return reverse_lazy('singleton_sensor_list')

class SingletonSensorDeleteView(SuperUserCheck, DeleteView):
  model = SingletonSensor
  template_name = "singleton_sensor/singleton_sensor_delete.html"
  def get_success_url(self):
    if self.object.scene is not None:
      scene_id = self.object.scene.id
      return '/' + str(scene_id)
    return reverse_lazy('singleton_sensor_list')

class SingletonSensorDetailView(SuperUserCheck, DetailView):
  model = SingletonSensor
  template_name = "singleton_sensor/singleton_sensor_detail.html"

class SingletonSensorListView(LoginRequiredMixin, ListView):
  model = SingletonSensor
  template_name = "singleton_sensor/singleton_sensor_list.html"

class SingletonSensorUpdateView(SuperUserCheck, UpdateView):
  model = SingletonSensor
  fields = ['sensor_id', 'name', 'scene']
  template_name = "singleton_sensor/singleton_sensor_update.html"

  def get_success_url(self):
    if self.object.scene is not None:
      scene_id = self.object.scene.id
      return '/' + str(scene_id)
    return reverse_lazy('singleton_sensor_list')

# 3D Asset CRUD
class AssetCreateView(SuperUserCheck, CreateView):
  model = Asset3D
  fields = ['name', 'x_size', 'y_size', 'z_size', 'mark_color', 'model_3d', 'scale', 'tracking_radius', 'shift_type',
            'geometric_center', 'mass', 'center_of_mass', 'is_static', 'ttl',
            'linear_damping', 'angular_damping', 'coefficient_of_restitution', 'friction_coefficients']
  template_name = "asset/asset_create.html"
  success_url = reverse_lazy('asset_list')

  def form_valid(self, form):
    form.instance.type = 'generic'
    return super(AssetCreateView, self).form_valid(form)

class AssetDeleteView(SuperUserCheck, DeleteView):
  model = Asset3D
  template_name = "asset/asset_delete.html"
  success_url = reverse_lazy('asset_list')

class AssetListView(LoginRequiredMixin, ListView):
  model = Asset3D
  template_name = "asset/asset_list.html"

class AssetUpdateView(SuperUserCheck, UpdateView):
  model = Asset3D
  fields = ['name', 'model_3d', 'scale', 'mark_color',
    'x_size', 'y_size', 'z_size',  \
    'x_buffer_size', 'y_buffer_size', 'z_buffer_size',  \
    'rotation_x', 'rotation_y', 'rotation_z', \
    'translation_x', 'translation_y', 'translation_z', \
    'tracking_radius', 'shift_type', 'project_to_map', 'rotation_from_velocity', \
    'geometric_center', 'mass', 'center_of_mass', 'is_static', 'ttl', \
    'linear_damping', 'angular_damping', 'coefficient_of_restitution', 'friction_coefficients']
  template_name = "asset/asset_update.html"
  success_url = reverse_lazy('asset_list')

# Scene Child CRUD
class ChildCreateView(SuperUserCheck, CreateView):
  model = ChildScene
  form_class = ChildSceneForm
  template_name = "child/child_create.html"

  def get_initial(self):
    initial = super().get_initial()
    initial['parent'] = self.parent()
    return initial

  def form_valid(self, form):
    return super(ChildCreateView, self).form_valid(form)

  def get_success_url(self):
    if self.object.parent is not None:
      scene_id = self.object.parent.id
      return '/' + str(scene_id)
    return reverse_lazy('index')

  def parent(self):
    parent_id = self.request.GET.get('scene')
    obj = get_object_or_404(Scene, pk=parent_id)

    return obj

class ChildDeleteView(SuperUserCheck, DeleteView):
  model = ChildScene
  template_name = "child/child_delete.html"
  success_url = reverse_lazy('index')

class ChildUpdateView(SuperUserCheck, UpdateView):
  model = ChildScene
  form_class = ChildSceneForm
  template_name = "child/child_update.html"

  def get_success_url(self):
    if self.object.parent is not None:
      scene_id = self.object.parent.id
      return '/' + str(scene_id)
    return reverse_lazy('index')

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
      user = form.get_user()
      if user is not None:
        Token.objects.get_or_create(user=user)
        login(request, user)

        allowed = set(settings.ALLOWED_HOSTS)
        if value_next:
          if url_has_allowed_host_and_scheme(url=value_next, allowed_hosts=allowed):
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
  cam_inst = get_object_or_404(Cam, pk=sensor_id)

  if request.method == 'POST':
    form = CamCalibrateForm(request.POST, request.FILES, instance=cam_inst)
    if form.is_valid():
      log.info('Form received {}'.format(form.cleaned_data))

      if settings.KUBERNETES_SERVICE_HOST:
        if cam_inst.use_camera_pipeline and not cam_inst.camera_pipeline:
          form.add_error(None, f"ERROR! Camera Pipeline field cannot be empty if 'Use Camera Pipeline' is enabled.")

          generated_pipeline_url = reverse('generate_camera_pipeline', kwargs={'sensor_id': cam_inst.pk})
          return render(request, 'cam/cam_calibrate.html', {
            'form': form,
            'caminst': cam_inst,
            'generated_pipeline_url': generated_pipeline_url
          })

        # validate the camera settings by generating the pipeline
        try:
          generated_pipeline = generate_pipeline_string_from_dict(form.cleaned_data)
          log.info(f"Camera settings validated. Successfully generated pipeline: {generated_pipeline[:100]}...")
        except (PipelineGenerationValueError, PipelineGenerationNotImplementedError) as e:
          log.error(f"Invalid camera settings for camera {cam_inst.name}: {e}")
          form.add_error(None, f"ERROR! Invalid camera settings: {str(e)}.")

          generated_pipeline_url = reverse('generate_camera_pipeline', kwargs={'sensor_id': cam_inst.pk})
          return render(request, 'cam/cam_calibrate.html', {
            'form': form,
            'caminst': cam_inst,
            'generated_pipeline_url': generated_pipeline_url
          })
        # otherwise show generic error message and not reveal any internal details
        except Exception as e:
          log.error(f"Invalid camera settings for camera {cam_inst.name}: {e}")
          form.add_error(None, f"ERROR! Invalid camera settings: internal error.")

          generated_pipeline_url = reverse('generate_camera_pipeline', kwargs={'sensor_id': cam_inst.pk})
          return render(request, 'cam/cam_calibrate.html', {
            'form': form,
            'caminst': cam_inst,
            'generated_pipeline_url': generated_pipeline_url
          })

      instance = form.save()
      return redirect(sceneDetail, scene_id=instance.scene_id)
    else:
      log.warning('Form not valid!')
  else:
    form = CamCalibrateForm(instance=cam_inst)

  # Generate the URL for the endpoint
  generated_pipeline_url = reverse('generate_camera_pipeline', kwargs={'sensor_id': cam_inst.pk})

  return render(request, 'cam/cam_calibrate.html', {
    'form': form,
    'caminst': cam_inst,
    'generated_pipeline_url': generated_pipeline_url
  })

@superuser_required
def genericCalibrate(request, sensor_id):
  obj_inst = get_object_or_404(SingletonSensor, pk=sensor_id)
  scene = SceneModel(obj_inst.scene.name, obj_inst.scene.map.path if
                     obj_inst.scene.map else None, obj_inst.scene.scale)

  if request.method == 'POST' and 'save_sensor_details' not in request.POST:
    form = SingletonForm(request.POST, request.FILES)
    detail_form  = SingletonDetailsForm(instance=obj_inst)

    if form.is_valid():
      log.info('Form received {}'.format(form.cleaned_data))

      pts = form.cleaned_data['rois']
      x = form.cleaned_data['sensor_x']
      y = form.cleaned_data['sensor_y']
      radius = form.cleaned_data['sensor_r']

      obj_inst.area = form.cleaned_data['area']
      obj_inst.scene = form.cleaned_data['scene']
      obj_inst.sensor_id = form.cleaned_data['sensor_id']
      obj_inst.name = form.cleaned_data['name']
      obj_inst.singleton_type = form.cleaned_data['singleton_type']
      if len(request.FILES) != 0:
        log.info("Detected a file")
        obj_inst.icon = request.FILES['icon']

      if (x != '') and (y != ''):
        # sensor_x/sensor_y are meters in form fields
        obj_inst.map_x, obj_inst.map_y = float(x), float(y)

      if (radius != ''):
        obj_inst.radius = float(radius) / obj_inst.scene.scale

      if (pts != ''):
        jdata = json.loads(form.cleaned_data['rois'])
        if isinstance(jdata, list) and len(jdata) > 0:
          roi_pts = jdata[0]['points']
          obj_inst.points.all().delete()
          for point in roi_pts:
            SingletonAreaPoint(singleton=obj_inst, x=float(point[0]), y=float(point[1])).save()


      if 'sectors' in form.cleaned_data and form.cleaned_data['sectors'] != '':
        jdata = json.loads(form.cleaned_data['sectors'])
        range_max = jdata.pop()['range_max']
        SingletonScalarThreshold.objects.update_or_create(singleton=obj_inst, defaults={
          'sectors': jdata, 'range_max': range_max
        })

      try:
        obj_inst.save()
      except IntegrityError as e:
        form = add_form_error(e, form)
        return render(request, 'singleton_sensor/singleton_sensor_calibrate.html', {'form': form, 'objinst': obj_inst, 'detail_form': detail_form})

      # notify that DB has been updated
      obj_inst.notifydbupdate()
      detail_form  = SingletonDetailsForm(instance=obj_inst)

      #return render(request, 'singleton_sensor/singleton_sensor_calibrate.html', {'form': form, 'objinst': obj_inst, 'detail_form':detail_form})
      return redirect(sceneDetail, scene_id=obj_inst.scene_id)
    else:
      log.warning('Form not valid!')

  else:
    if request.method == 'POST' and 'save_sensor_details' in request.POST:
      obj_inst = get_object_or_404(SingletonSensor, pk=sensor_id)

      if len(request.FILES) != 0:
        obj_inst.icon = request.FILES['icon']

      detail_form = SingletonDetailsForm(request.POST, instance=obj_inst)
      detail_form.save()

    if len(obj_inst.points.all()) > 0:
      rdict = {'title': obj_inst.name, 'points':[] }
      for point in obj_inst.points.all():
        rdict['points'].append([point.x, point.y])
      rois_val = json.dumps([rdict])
    else:
      rois_val = json.dumps([])

    sensor_x = None
    sensor_y = None
    radius = None

    if obj_inst.map_x is not None:
      sensor_x = obj_inst.map_x
    if obj_inst.map_y is not None:
      sensor_y = obj_inst.map_y
    if obj_inst.radius:
      radius = obj_inst.radius * obj_inst.scene.scale

    color_ranges = []
    sectors, range_max = obj_inst.get_sectors()
    color_ranges = sectors + [{"range_max": range_max}]

    initial={'area':obj_inst.area,
        'sensor_x': sensor_x,
        'sensor_y': sensor_y,
        'sensor_r': radius,
        'rois': rois_val,
        'sensor_id': obj_inst.sensor_id,
        'name': obj_inst.name,
        'scene': obj_inst.scene,
        'icon': obj_inst.icon,
        'singleton_type': obj_inst.singleton_type,
        'sectors': color_ranges,
      }
    form = SingletonForm(initial=initial)
    detail_form = SingletonDetailsForm(instance=obj_inst)

  return render(request, 'singleton_sensor/singleton_sensor_calibrate.html', {'form': form, 'objinst': obj_inst, 'detail_form':detail_form})

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


def _invalid_bounds(bounds):
  """True if bounds is present but not a dict of 4 numeric minX/minY/maxX/maxY keys."""
  if bounds is None:
    return False
  return (
    not isinstance(bounds, dict)
    or not all(k in bounds for k in ('minX', 'minY', 'maxX', 'maxY'))
    or not all(_is_number(bounds[k]) for k in ('minX', 'minY', 'maxX', 'maxY'))
  )


def _bearing_pivot(scene):
  """Scene-local (x, y) pivot for the bearing rotation, in the same frame as ROI points.

  Prefers the scene's saved map center; falls back to the map_corners_lla bbox midpoint.
  """
  if scene.map_center_lat is not None and scene.map_center_lng is not None:
    center_lat, center_lng = scene.map_center_lat, scene.map_center_lng
  else:
    south, west, north, east = osm_roi.bbox_from_map_corners(scene.map_corners_lla)
    center_lat, center_lng = (south + north) / 2.0, (west + east) / 2.0
  return osm_roi.lla_to_local_xy(scene.trs_matrix, center_lat, center_lng)


class OsmRoiPreviews(APIView):
  """Preview OSM-derived polygon ROIs before creation.

  Derives the query bounding box from the scene's saved map_corners_lla.
  Fetches line geometries from OSM (cached on the scene after first fetch),
  converts to scene-local coordinates, buffers to polygons, and returns a
  preview list with temporary UUIDs without persisting to DB.

  Includes the scene's map_bearing so the frontend can rotate the canvas
  preview to match the current map orientation.

  Optional "bounds" ({minX, minY, maxX, maxY} in scene-local meters) scopes the
  preview to a sub-region, keeping any polygon that at least partially overlaps
  it (full, unclipped shape) - equivalent to dragging a selection box in the
  Regions tab UI.
  """
  authentication_classes = [SessionAuthentication, TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  def post(self, request, scene_uid):
    try:
      bounds = request.data.get('bounds')
      if _invalid_bounds(bounds):
        return JsonResponse({'error': 'bounds must have numeric minX, minY, maxX, maxY'}, status=400)

      # Get the scene; 404 if not found or invalid UUID
      try:
        scene = Scene.objects.get(pk=scene_uid)
      except (Scene.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Scene not found or invalid UUID'}, status=404)

      if not scene.map_corners_lla:
        return JsonResponse({
          'error': 'Scene map corners not set. '
                   'Click "Generate Geospatial Bounds & Snapshot" in scene editor first.'
        }, status=400)

      previews = osm_roi.build_roi_previews(scene)
      if bounds is not None:
        previews = osm_roi.filter_by_bounds(previews, bounds)

      center_x, center_y = _bearing_pivot(scene)

      return JsonResponse({
        'rois': previews,
        'bearing': scene.map_bearing or 0.0,  # degrees, for canvas rotation correction
        'center': [center_x, center_y],  # scene-local meters pivot for the bearing rotation
      })

    except osm_roi.OsmRoiError as e:
      log.error(f"OSM ROI preview validation error: {e}")
      log.error(f"Traceback: {traceback.format_exc()}")
      return JsonResponse({'error': 'Unable to preview ROIs from OSM with the provided scene data'}, status=400)
    except osm_query.FeatureLimitError as e:
      log.warning(f"OSM feature limit exceeded while previewing ROIs: {e}")
      return JsonResponse({
        'error': 'Too many roads and footways in this area. Select a smaller area and try again.'
      }, status=400)
    except osm_query.OsmQueryError as e:
      log.error(f"OSM query error while previewing ROIs: {e}")
      log.error(f"Traceback: {traceback.format_exc()}")
      return JsonResponse({'error': 'Unable to fetch OSM data for ROI preview'}, status=400)
    except Exception as e:
      log.error(f"Error previewing OSM ROIs: {e}")
      log.error(f"Traceback: {traceback.format_exc()}")
      return JsonResponse({'error': 'An internal error has occurred'}, status=500)


class _RoiValidationError(ValueError):
  """Raised for any invalid roi entry in an OsmRois POST body; message is user-facing."""


def _validate_roi(roi, seen_uuids):
  """Validate and normalize one roi dict.

  Returns (uuid, name, roi_type, points) on success. Raises _RoiValidationError
  (with a user-facing message) on the first problem found.
  """
  if not isinstance(roi, dict):
    raise _RoiValidationError('Each roi must be an object')

  points = roi.get('points')
  if not _valid_points(points, MIN_REGION_POINTS):
    raise _RoiValidationError(
      f'Each roi needs a "points" list of at least {MIN_REGION_POINTS} [x, y] number pairs')

  roi_uuid = roi.get('uuid')
  query_uuid = roi_uuid if isinstance(roi_uuid, str) and validate_uuid(roi_uuid) else str(uuid.uuid4())
  if query_uuid in seen_uuids:
    raise _RoiValidationError(f'Duplicate roi uuid in request: {query_uuid}')

  roi_name = str(roi.get('name')) if roi.get('name') else f"roi_{query_uuid}"
  roi_type = str(roi.get('type') or '')
  if len(roi_name) > REGION_NAME_MAX_LENGTH:
    raise _RoiValidationError(f'roi name exceeds {REGION_NAME_MAX_LENGTH} characters')
  if len(roi_type) > REGION_TYPE_MAX_LENGTH:
    raise _RoiValidationError(f'roi type exceeds {REGION_TYPE_MAX_LENGTH} characters')

  return query_uuid, roi_name, roi_type, points


def _validate_rois(rois):
  """Validate every roi up front, so a bad entry can't leave a partially-accepted batch behind.

  Returns (to_create, seen_uuids). Raises _RoiValidationError on the first invalid roi.
  """
  to_create = []
  seen_uuids = set()
  for roi in rois:
    query_uuid, roi_name, roi_type, points = _validate_roi(roi, seen_uuids)
    seen_uuids.add(query_uuid)
    to_create.append((query_uuid, roi_name, roi_type, points))
  return to_create, seen_uuids


def _create_rois(scene, to_create):
  """Create all validated ROIs in one transaction and schedule the scene update notification."""
  created = []
  with transaction.atomic():
    for query_uuid, roi_name, roi_type, points in to_create:
      region = Region.objects.create(
        uuid=query_uuid, scene=scene, name=roi_name, volumetric=False,
        buffer_size=0, roi_type=roi_type)
      for point_idx, point in enumerate(points):
        RegionPoint.objects.create(region=region, x=point[0], y=point[1], sequence=point_idx)
      created.append({'uuid': str(region.uuid), 'name': region.name})

  transaction.on_commit(lambda: sendUpdateCommand(scene_id=scene.id))
  return created


class OsmRois(APIView):
  """Persist chosen OSM ROI previews (from OsmRoiPreviews) as new Regions.

  Unlike the form-based saveROI endpoint, which replaces the scene's entire
  region set with whatever it's given, this only creates the posted ROIs -
  other existing regions in the scene are left untouched. Lets API callers
  accept previews without first re-submitting every other region in the scene.
  """
  authentication_classes = [SessionAuthentication, TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  def post(self, request, scene_uid):
    rois = request.data.get('rois')
    if not isinstance(rois, list) or not rois:
      return JsonResponse({'error': 'rois must be a non-empty list'}, status=400)

    try:
      scene = Scene.objects.get(pk=scene_uid)
    except (Scene.DoesNotExist, ValueError):
      return JsonResponse({'error': 'Scene not found or invalid UUID'}, status=404)

    try:
      to_create, seen_uuids = _validate_rois(rois)
    except _RoiValidationError as e:
      return JsonResponse({'error': str(e)}, status=400)

    # Additive only: never overwrite an existing region through a reused uuid.
    existing = Region.objects.filter(uuid__in=seen_uuids).values_list('uuid', flat=True)
    if existing:
      return JsonResponse(
        {'error': 'Regions with these uuids already exist',
         'existing': sorted(str(u) for u in existing)}, status=409)

    try:
      created = _create_rois(scene, to_create)
    except Exception as e:
      log.error(f"Error accepting OSM ROIs: {e}")
      log.error(f"Traceback: {traceback.format_exc()}")
      return JsonResponse({'error': 'An internal error has occurred'}, status=500)

    return JsonResponse({'created': created})


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
    # Include any warnings from finalization (e.g., unanchored cameras)
    if finalize_result.get("unanchored_cameras"):
      status_data["unanchored_cameras"] = finalize_result["unanchored_cameras"]
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
