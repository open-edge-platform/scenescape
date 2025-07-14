# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

'''
sscape URL Configuration
'''

from django.contrib import admin
from django.urls import include, path
from django.conf.urls.static import static
from django.conf import settings
from manager import views
from manager.calculate_intrinsics_view import CalculateCameraIntrinsics
from manager.model_directory_view import ModelDirectory
from manager.views import SingletonSensorDeleteView
from manager.views import SingletonSensorUpdateView
from manager.views import SingletonSensorDetailView
from manager.views import SingletonSensorCreateView
from manager.views import SingletonSensorListView
from manager.views import CamDeleteView
from manager.views import CamUpdateView
from manager.views import CamDetailView
from manager.views import CamCreateView
from manager.views import CamListView
from manager.views import SceneDeleteView
from manager.views import SceneUpdateView
from manager.views import SceneDetailView
from manager.views import SceneCreateView
from manager.views import SceneListView
from manager.views import AssetDeleteView
from manager.views import AssetUpdateView
from manager.views import AssetCreateView
from manager.views import AssetListView
from manager.views import ChildDeleteView
from manager.views import ChildUpdateView
from manager.views import ChildCreateView
from manager.views import ModelListView

# Imports for REST API
from django.urls import re_path
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
  path('admin/', admin.site.urls),
  path('', views.index, name='index'),
  path('<uuid:scene_id>/', views.sceneDetail, name='sceneDetail'),
  path('<uuid:scene_id>/roi', views.saveROI, name='save-roi'),
  path('scene/list/', SceneListView.as_view(), name='scene_list'),
  path('scene/create/', SceneCreateView.as_view(), name='scene_create'),
  path('scene/detail/<uuid:pk>/', SceneDetailView.as_view(), name='scene_detail'),
  path('scene/update/<uuid:pk>/', SceneUpdateView.as_view(), name='scene_update'),
  path('scene/delete/<uuid:pk>/', SceneDeleteView.as_view(), name='scene_delete'),
  path('cam/list/', CamListView.as_view(), name='cam_list'),
  path('cam/create/', CamCreateView.as_view(), name='cam_create'),
  path('cam/detail/<int:pk>/', CamDetailView.as_view(), name='cam_detail'),
  path('cam/update/<int:pk>/', CamUpdateView.as_view(), name='cam_update'),
  path('cam/delete/<int:pk>/', CamDeleteView.as_view(), name='cam_delete'),
  path('cam/calibrate/<int:sensor_id>', views.cameraCalibrate, name='cam_calibrate'),
  path('singleton_sensor/list/', SingletonSensorListView.as_view(), name='singleton_sensor_list'),
  path('singleton_sensor/create/', SingletonSensorCreateView.as_view(), name='singleton_sensor_create'),
  path('singleton_sensor/detail/<int:pk>/', SingletonSensorDetailView.as_view(), name='singleton_sensor_detail'),
  path('singleton_sensor/update/<int:pk>/', SingletonSensorUpdateView.as_view(), name='singleton_sensor_update'),
  path('singleton_sensor/delete/<int:pk>/', SingletonSensorDeleteView.as_view(), name='singleton_sensor_delete'),
  path('singleton_sensor/calibrate/<int:sensor_id>', views.genericCalibrate, name='singleton_sensor_calibrate'),
  path('asset/list/', AssetListView.as_view(), name='asset_list'),
  path('asset/create/', AssetCreateView.as_view(), name='asset_create'),
  path('asset/update/<int:pk>/', AssetUpdateView.as_view(), name='asset_update'),
  path('asset/delete/<int:pk>/', AssetDeleteView.as_view(), name='asset_delete'),
  path('child/create/', ChildCreateView.as_view(), name='child_create'),
  path('child/update/<int:pk>/', ChildUpdateView.as_view(), name='child_update'),
  path('child/delete/<int:pk>/', ChildDeleteView.as_view(), name='child_delete'),
  path('sign_in/', views.sign_in, name="sign_in"),
  path('sign_out/', views.sign_out, name="sign_out"),
  path('account_locked/', views.account_locked, name="account_locked"),
  re_path(r'^%s(?P<path>.*)$' % settings.MEDIA_URL[1:],
          views.protected_media,
          {'media_root': settings.MEDIA_ROOT}),
  re_path(r'^%s(?P<path>.*)$' % settings.DOCS_URL[1:],
          views.protected_media,
          {'media_root': settings.DOCS_ROOT}),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
  import debug_toolbar
  urlpatterns = [
    path('__debug__/', include(debug_toolbar.urls)),
  ] + urlpatterns

if settings.KUBERNETES_SERVICE_HOST:
  urlpatterns += [
    path('model/list/', ModelListView.as_view(), name='model_list'),
    re_path(r'^%s(?P<path>.*)$' % settings.MODEL_URL[1:],
            views.protected_media,
            {'media_root': settings.MODEL_ROOT},
            name="model_resources"),
  ]

# REST API

urlpatterns += [
  re_path(r'api/v1/(scenes)$', views.ListThings.as_view()),
  re_path(r'api/v1/(scene)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(scene)/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$', views.ManageThing.as_view()),
  re_path(r'api/v1/(cameras)$', views.ListThings.as_view()),
  re_path(r'api/v1/(camera)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(camera)/([^/]+)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(sensors)$', views.ListThings.as_view()),
  re_path(r'api/v1/(sensor)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(sensor)/([^/]+)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(regions)$', views.ListThings.as_view()),
  re_path(r'api/v1/(region)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(region)/([^/]+)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(tripwires)$', views.ListThings.as_view()),
  re_path(r'api/v1/(tripwire)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(tripwire)/([^/]+)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(users)$', views.ListThings.as_view()),
  re_path(r'api/v1/(user)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(user)/([^/]+)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(frame)$', views.CameraManager.as_view()),
  re_path(r'api/v1/(video)$', views.CameraManager.as_view()),
  re_path(r'api/v1/(assets)$', views.ListThings.as_view()),
  re_path(r'api/v1/(asset)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(asset)/([^/]+)$', views.ManageThing.as_view()),
  re_path(r'api/v1/scenes/(child)$', views.ListThings.as_view()),
  re_path(r'api/v1/(child)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(child)/([^/]+)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(calibrationmarkers)$', views.ListThings.as_view()),
  re_path(r'api/v1/(calibrationmarker)$', views.ManageThing.as_view()),
  re_path(r'api/v1/(calibrationmarker)/([^/]+)$', views.ManageThing.as_view())
]

urlpatterns += [
  path('api/', include('rest_framework.urls')),
  path('api/v1/auth', views.CustomAuthToken.as_view(), name='api_token_auth'),
  path('api/v1/database-ready', views.DatabaseReady.as_view()),
  path('api/v1/calculateintrinsics', CalculateCameraIntrinsics.as_view()),
  path('api/v1/aclcheck', views.ACLCheck.as_view())
]

if settings.KUBERNETES_SERVICE_HOST:
  urlpatterns += [
    path('api/v1/model-directory/', ModelDirectory.as_view(), name='model-directory'),
  ]
