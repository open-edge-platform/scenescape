# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import os
import random
import socket
import time
from collections import namedtuple
from uuid import UUID

from django.conf import settings
from django.contrib.admin.views.decorators import user_passes_test
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth import user_logged_in, user_login_failed
from django.contrib.sessions.models import Session
from django.db import IntegrityError, OperationalError, connection
from django.dispatch.dispatcher import receiver
from django.http import FileResponse, HttpResponse, HttpResponseNotFound, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from manager.models import Scene, ChildScene, \
  Cam, Asset3D, \
  SingletonSensor, SingletonScalarThreshold, \
  Region, RegionPoint, Tripwire, TripwirePoint, \
  SingletonAreaPoint, UserSession, FailedLogin, DatabaseStatus, \
  RegionOccupancyThreshold, CalibrationMarker
from manager.forms import CamCalibrateForm, ROIForm, SingletonForm, SingletonDetailsForm, \
  SceneUpdateForm, CamCreateForm, SingletonCreateForm, ChildSceneForm
from scene_common.options import *
from scene_common.scene_model import SceneModel
from scene_common.transform import applyChildTransform
from manager.validators import add_form_error, validate_uuid
from scene_common import log
from django.http import JsonResponse
from manager.models import PubSubACL
from django.contrib.auth.models import User

# Imports for REST API
import threading
import uuid
from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework import authentication, permissions
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework import status
from rest_framework import generics
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from manager.serializers import *
from scene_common.timestamp import get_epoch_time, get_iso_time
from scene_common.mqtt import PubSub

@receiver(user_login_failed)
def login_has_failed(sender, credentials, request, **kwargs):
  user = FailedLogin.objects.filter(ip=request.META.get('REMOTE_ADDR')).first()
  if user:
    log.warn("User had already failed a login will update delay")
    old_delay = user.delay
    user.delay = random.uniform(0.1, old_delay + 0.9)
    user.save()
  else:
    FailedLogin.objects.create(ip=request.META.get('REMOTE_ADDR'), delay=0.7)
    log.warn("User 1st wrong credentials attempt")

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

class IsAdminOrReadOnly(permissions.BasePermission):
  def has_permission(self, request, view):
    if request.method in permissions.SAFE_METHODS:
      return request.user.is_authenticated
    return request.user.is_superuser

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
      file = os.path.join(media_root, path)
      if os.path.exists(file):
        response = FileResponse(open(file, 'rb'))
        return response
    return HttpResponseNotFound()
  return HttpResponse("401 Unauthorized", status=401)

@login_required(login_url="sign_in")
def sceneDetail(request, scene_id):
  scene = get_object_or_404(Scene, pk=scene_id)
  child_rois, child_trips, child_sensors = getAllChildrenMetaData(scene_id)
  # FIXME add rest api call to remote child using child scene api token

  return render(request, 'sscape/sceneDetail.html', {'scene': scene, 'child_rois': child_rois,
                                                     'child_tripwires': child_trips, 'child_sensors': child_sensors})

@superuser_required
def saveROI(request, scene_id):
  scene = get_object_or_404(Scene, pk=scene_id)

  if request.method == 'POST':
    form = ROIForm(request.POST)
    if form.is_valid():
      log.info('Form received {}'.format(form.cleaned_data))
      saveRegionData(scene, form)
      saveTripwireData(scene, form)
      return redirect('/' + str(scene.id))
    else:
      log.error("Form bad", request.POST)
  else:
    form = ROIForm(initial = {'rois': scene.roiJSON()})
  return render(request, 'sscape/sceneDetail.html', {'form': form, 'scene': scene})

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
        'scene':scene, 'name':roi_title,
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
class CamCreateView(SuperUserCheck, CreateView):
  model = Cam
  form_class = CamCreateForm
  template_name = "cam/cam_create.html"

  def form_valid(self, form):
    form.instance.type = 'camera'
    return super(CamCreateView, self).form_valid(form)

  def get_success_url(self):
    scene_id = self.object.scene.id
    return '/' + str(scene_id)

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
    scene_id = self.object.scene.id
    return '/' + str(scene_id)

#Scene CRUD
class SceneCreateView(SuperUserCheck, CreateView):
  model = Scene
  fields = ['name', 'map', 'scale']
  template_name = "scene/scene_create.html"
  success_url = reverse_lazy('index')

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

#Singleton Sensor CRUD
class SingletonSensorCreateView(SuperUserCheck, CreateView):
  model = SingletonSensor
  form_class = SingletonCreateForm
  template_name = "singleton_sensor/singleton_sensor_create.html"
  success_url = reverse_lazy('singleton_sensor_list')

  def form_valid(self, form):
    form.instance.type = 'generic'
    return super(SingletonSensorCreateView, self).form_valid(form)

  def get_success_url(self):
    scene_id = self.object.scene.id
    return '/' + str(scene_id)

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
    scene_id = self.object.scene.id
    return '/' + str(scene_id)

# 3D Asset CRUD
class AssetCreateView(SuperUserCheck, CreateView):
  model = Asset3D
  fields = ['name', 'x_size', 'y_size', 'z_size', 'mark_color', 'model_3d', 'scale', 'tracking_radius', 'shift_type']
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
            'rotation_x', 'rotation_y', 'rotation_z', \
            'translation_x', 'translation_y', 'translation_z', \
            'tracking_radius', 'shift_type', 'project_to_map', 'rotation_from_velocity']
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
  cam_inst = get_object_or_404(Cam, pk=sensor_id)

  if request.method == 'POST':
    form = CamCalibrateForm(request.POST, request.FILES, instance=cam_inst)
    if form.is_valid():
      log.info('Form received {}'.format(form.cleaned_data))
      cam_inst.save()

      return redirect(sceneDetail, scene_id=cam_inst.scene_id)
    else:
      log.warn('Form not valid!')
  else:
    form = CamCalibrateForm(instance=cam_inst)

  return render(request, 'cam/cam_calibrate.html', {'form': form, 'caminst': cam_inst})

@superuser_required
def genericCalibrate(request, sensor_id):
  obj_inst = get_object_or_404(SingletonSensor, pk=sensor_id)
  size = None
  scene = SceneModel(obj_inst.scene.name, obj_inst.scene.map.path if
                     obj_inst.scene.map else None, obj_inst.scene.scale)
  if scene.background is not None:
    size = scene.background.shape[1::-1]
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
        obj_inst.map_x, obj_inst.map_y = float(x), float(y)
        obj_inst.map_x = obj_inst.map_x / obj_inst.scene.scale

        if size:
          obj_inst.map_y = (size[1] - obj_inst.map_y) / obj_inst.scene.scale
        else:
          obj_inst.map_y = obj_inst.map_y / obj_inst.scene.scale

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
      log.warn('Form not valid!')

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
      sensor_x = obj_inst.map_x * obj_inst.scene.scale
    if obj_inst.map_y is not None:
      if size:
        sensor_y = (size[1] - (obj_inst.map_y * obj_inst.scene.scale))
      else:
        sensor_y = obj_inst.map_y * obj_inst.scene.scale
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

# REST API

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

class ManageThing(APIView):
  authentication_classes = [authentication.TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  def isValidQueryParameter(self, uid, thing_type):
    _, thing_serializer, uid_field = get_class_and_serializer(thing_type)
    if uid_field == 'pk' and thing_type != 'scene' and uid.isdigit():
      return True
    elif (uid_field == 'uuid' and thing_type in ['region', 'tripwire']) or (uid_field == 'pk' and thing_type == 'scene'):
      try:
        val = UUID(uid, version=4)
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

def getAllChildrenMetaData(scene_id):
  children = ChildScene.objects.filter(parent=scene_id)
  child_rois = []
  child_trips = []
  child_sensors = []
  for c in children:
    if c.child_type == "local":
      child_scene = get_object_or_404(Scene, pk=c.child.id)
      current_child_name = c.child.name

      for r in json.loads(child_scene.roiJSON()):
        r['from_child_scene'] = current_child_name
        child_rois.append(applyChildTransform(r, c.cameraPose))

      for t in json.loads(child_scene.tripwireJSON()):
        t['from_child_scene'] = current_child_name
        child_trips.append(applyChildTransform(t, c.cameraPose))

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

