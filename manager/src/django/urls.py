# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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

# Imports for REST API
from django.urls import re_path
from manager import api

urlpatterns = [
  path('admin/', admin.site.urls),
  path('', views.index, name='index'),
  path('<uuid:scene_id>/', views.sceneDetail, name='sceneDetail'),
  path('<uuid:scene_id>/roi', views.saveROI, name='save-roi'),
  path('scene/list/', views.SceneListView.as_view(), name='scene_list'),
  path('scene/create/', views.SceneCreateView.as_view(), name='scene_create'),
  path('scene/import/', views.SceneImportView.as_view(), name='scene_import'),
  path('scene/detail/<uuid:pk>/', views.SceneDetailView.as_view(), name='scene_detail'),
  path('scene/update/<uuid:pk>/', views.SceneUpdateView.as_view(), name='scene_update'),
  path('scene/delete/<uuid:pk>/', views.SceneDeleteView.as_view(), name='scene_delete'),
  path('cam/list/', views.CamListView.as_view(), name='cam_list'),
  path('cam/create/', views.CamCreateView.as_view(), name='cam_create'),
  path('cam/detail/<int:pk>/', views.CamDetailView.as_view(), name='cam_detail'),
  path('cam/update/<int:pk>/', views.CamUpdateView.as_view(), name='cam_update'),
  path('cam/delete/<int:pk>/', views.CamDeleteView.as_view(), name='cam_delete'),
  path('cam/calibrate/<int:sensor_id>', views.cameraCalibrate, name='cam_calibrate'),
  path('cam/generate_pipeline/<int:sensor_id>', views.generate_camera_pipeline, name='generate_camera_pipeline'),
  path('singleton_sensor/list/', views.SingletonSensorListView.as_view(), name='singleton_sensor_list'),
  path('singleton_sensor/create/', views.SingletonSensorCreateView.as_view(), name='singleton_sensor_create'),
  path('singleton_sensor/detail/<int:pk>/', views.SingletonSensorDetailView.as_view(), name='singleton_sensor_detail'),
  path('singleton_sensor/update/<int:pk>/', views.SingletonSensorUpdateView.as_view(), name='singleton_sensor_update'),
  path('singleton_sensor/delete/<int:pk>/', views.SingletonSensorDeleteView.as_view(), name='singleton_sensor_delete'),
  path('singleton_sensor/calibrate/<int:sensor_id>', views.genericCalibrate, name='singleton_sensor_calibrate'),
  path('asset/list/', views.AssetListView.as_view(), name='asset_list'),
  path('asset/create/', views.AssetCreateView.as_view(), name='asset_create'),
  path('asset/update/<int:pk>/', views.AssetUpdateView.as_view(), name='asset_update'),
  path('asset/delete/<int:pk>/', views.AssetDeleteView.as_view(), name='asset_delete'),
  path('child/create/', views.ChildCreateView.as_view(), name='child_create'),
  path('child/update/<int:pk>/', views.ChildUpdateView.as_view(), name='child_update'),
  path('child/delete/<int:pk>/', views.ChildDeleteView.as_view(), name='child_delete'),
  path('sign_in/', views.sign_in, name="sign_in"),
  path('sign_out/', views.sign_out, name="sign_out"),
  path('account_locked/', views.account_locked, name="account_locked"),
  path('media/list/<str:folder_name>/', views.list_resources, name='list_resources'),
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
    path('model/list/', views.ModelListView.as_view(), name='model_list'),
    re_path(r'^%s(?P<path>.*)$' % settings.MODEL_URL[1:],
            views.protected_media,
            {'media_root': settings.MODEL_ROOT},
            name="model_resources"),
  ]

# REST API

urlpatterns += [
  re_path(r'api/v1/(scenes)$', api.ListThings.as_view()),
  re_path(r'api/v1/(scene)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(scene)/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$', api.ManageThing.as_view()),
  re_path(r'api/v1/(cameras)$', api.ListThings.as_view()),
  re_path(r'api/v1/(camera)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(camera)/([^/]+)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(sensors)$', api.ListThings.as_view()),
  re_path(r'api/v1/(sensor)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(sensor)/([^/]+)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(regions)$', api.ListThings.as_view()),
  re_path(r'api/v1/(region)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(region)/([^/]+)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(tripwires)$', api.ListThings.as_view()),
  re_path(r'api/v1/(tripwire)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(tripwire)/([^/]+)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(users)$', api.ListThings.as_view()),
  re_path(r'api/v1/(user)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(user)/([^/]+)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(frame)$', api.CameraManager.as_view()),
  re_path(r'api/v1/(video)$', api.CameraManager.as_view()),
  re_path(r'api/v1/(assets)$', api.ListThings.as_view()),
  re_path(r'api/v1/(asset)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(asset)/([^/]+)$', api.ManageThing.as_view()),
  re_path(r'api/v1/scenes/(child)$', api.ListThings.as_view()),
  re_path(r'api/v1/(child)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(child)/([^/]+)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(calibrationmarkers)$', api.ListThings.as_view()),
  re_path(r'api/v1/(calibrationmarker)$', api.ManageThing.as_view()),
  re_path(r'api/v1/(calibrationmarker)/([^/]+)$', api.ManageThing.as_view())
]

urlpatterns += [
  path('api/', include('rest_framework.urls')),
  path('api/v1/auth', api.CustomAuthToken.as_view(), name='api_token_auth'),
  path('api/v1/database-ready', api.DatabaseReady.as_view()),
  path('api/v1/calculateintrinsics', CalculateCameraIntrinsics.as_view()),
  path('api/v1/aclcheck', api.ACLCheck.as_view()),
  path("api/v1/import-scene/", api.SceneImportAPIView.as_view())

]

if settings.KUBERNETES_SERVICE_HOST:
  urlpatterns += [
    path('api/v1/model-directory/', ModelDirectory.as_view(), name='model-directory'),
  ]
