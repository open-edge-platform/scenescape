#!/bin/bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Script to generate Django migrations
# This should be run during development or as part of the release process
# DO NOT run this in production or at container startup

import django.core.validators
import django.db.models.deletion
import manager.fields
import manager.models
import manager.validators
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

  initial = True

  dependencies = [
      ('sessions', '0001_initial'),
      migrations.swappable_dependency(settings.AUTH_USER_MODEL),
  ]

  operations = [
      migrations.CreateModel(
          name='Asset3D',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('name', models.CharField(max_length=200, unique=True, verbose_name='Class Name')),
              ('x_size', models.FloatField(default=1.0, validators=[django.core.validators.MinValueValidator(0.0)], verbose_name='Object size in x-axis')),
              ('y_size', models.FloatField(default=1.0, validators=[django.core.validators.MinValueValidator(0.0)], verbose_name='Object size in y-axis')),
              ('z_size', models.FloatField(default=1.0, validators=[django.core.validators.MinValueValidator(0.0)], verbose_name='Object size in z-axis')),
              ('x_buffer_size', models.FloatField(default=0.0, verbose_name='Object buffer size in x-axis')),
              ('y_buffer_size', models.FloatField(default=0.0, verbose_name='Object buffer size in y-axis')),
              ('z_buffer_size', models.FloatField(default=0.0, verbose_name='Object buffer size in z-axis')),
              ('mark_color', models.CharField(blank=True, default='#888888', max_length=20, verbose_name='Mark Color')),
              ('model_3d', models.FileField(blank=True, null=True, upload_to='', validators=[django.core.validators.FileExtensionValidator(['glb']), manager.validators.validate_glb])),
              ('rotation_x', models.FloatField(blank=True, default=0.0, null=True, verbose_name='X Rotation (degrees)')),
              ('rotation_y', models.FloatField(blank=True, default=0.0, null=True, verbose_name='Y Rotation (degrees)')),
              ('rotation_z', models.FloatField(blank=True, default=0.0, null=True, verbose_name='Z Rotation (degrees)')),
              ('translation_x', models.FloatField(blank=True, default=0.0, null=True, verbose_name='X Translation (meters)')),
              ('translation_y', models.FloatField(blank=True, default=0.0, null=True, verbose_name='Y Translation (meters)')),
              ('translation_z', models.FloatField(blank=True, default=0.0, null=True, verbose_name='Z Translation (meters)')),
              ('scale', models.FloatField(blank=True, default=1.0, null=True, verbose_name='Scale')),
              ('rotation_from_velocity', models.BooleanField(choices=[(True, 'Yes'), (False, 'No')], default=False, null=True)),
              ('tracking_radius', models.FloatField(default=2.0, verbose_name='Tracking radius (meters)')),
              ('shift_type', models.IntegerField(choices=[(1, 'Type 1 (default)'), (2, 'Type 2 (may work better for wide and short objects)')], default=1, null=True)),
              ('project_to_map', models.BooleanField(choices=[(True, 'Yes'), (False, 'No')], default=False, null=True)),
              ('geometric_center', manager.fields.ListField(blank=True, default=manager.models.default_geometric_center, help_text='Geometric center offset [x, y, z] in meters from bottom center', null=True)),
              ('mass', models.FloatField(blank=True, default=1.0, null=True, validators=[django.core.validators.MinValueValidator(0.0)], verbose_name='Mass (kg)')),
              ('center_of_mass', manager.fields.ListField(blank=True, default=manager.models.default_center_of_mass, help_text='Center of mass offset [x, y, z] in meters from geometric center', null=True)),
              ('is_static', models.BooleanField(blank=True, choices=[(True, 'Yes'), (False, 'No')], default=False, help_text='Whether object can move on its own', null=True, verbose_name='Is Static')),
              ('ttl', models.FloatField(blank=True, default=0.0, help_text='Time to live for track expiration (0 = infinite)', null=True, validators=[django.core.validators.MinValueValidator(0.0)], verbose_name='Time to Live (seconds)')),
              ('linear_damping', models.FloatField(blank=True, default=0.05, help_text='Resistance to linear motion (0.0 - 1.0)', null=True, validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)], verbose_name='Linear Damping')),
              ('angular_damping', models.FloatField(blank=True, default=0.05, help_text='Resistance to angular motion (0.0 - 1.0)', null=True, validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)], verbose_name='Angular Damping')),
              ('coefficient_of_restitution', models.FloatField(blank=True, default=0.5, help_text='Bounciness for collisions (0.0 - 1.0)', null=True, validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)], verbose_name='Coefficient of Restitution')),
              ('friction_coefficients', manager.fields.ListField(blank=True, default=manager.models.default_friction_coefficients, help_text='Friction coefficients [static, dynamic]', null=True)),
          ],
      ),
      migrations.CreateModel(
          name='BoundingBox',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('name', models.CharField(max_length=200)),
          ],
      ),
      migrations.CreateModel(
          name='BoundingBoxPoints',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('sequence', models.IntegerField(blank=True, default=None, null=True)),
              ('x', models.FloatField(blank=True, default=None, null=True)),
              ('y', models.FloatField(blank=True, default=None, null=True)),
          ],
      ),
      migrations.CreateModel(
          name='Sensor',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('sensor_id', models.CharField(default=None, max_length=20, unique=True, verbose_name='Sensor ID')),
              ('name', models.CharField(max_length=200, unique=True)),
              ('type', models.CharField(choices=[('camera', 'Camera'), ('generic', 'generic')], max_length=200)),
              ('icon', models.ImageField(blank=True, default=None, null=True, upload_to='')),
          ],
      ),
      migrations.CreateModel(
          name='DataLog',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('timestamp', models.FloatField(db_index=True)),
          ],
      ),
      migrations.CreateModel(
          name='DatabaseStatus',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('is_ready', models.BooleanField(default=False)),
          ],
      ),
      migrations.CreateModel(
          name='FailedLogin',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('ip', models.GenericIPAddressField(null=True)),
              ('delay', models.FloatField(default=0.0)),
          ],
          options={
              'verbose_name': 'FailedLogin Entry',
              'verbose_name_plural': 'FailedLogin Entries',
              'db_table': 'db_failedlogin_entry',
          },
      ),
      migrations.CreateModel(
          name='MobileObject',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('timestamp', models.FloatField(db_index=True)),
              ('pid', models.IntegerField(default=None)),
              ('x', models.FloatField(blank=True, default=None, null=True)),
              ('y', models.FloatField(blank=True, default=None, null=True)),
              ('previous', models.OneToOneField(blank=True, default=None, null=True, on_delete=django.db.models.deletion.CASCADE, to='manager.mobileobject')),
          ],
      ),
      migrations.CreateModel(
          name='Scene',
          fields=[
              ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
              ('name', models.CharField(max_length=200, unique=True)),
              ('map_type', models.CharField(choices=[('map_upload', 'Map Upload'), ('geospatial_map', 'Geospatial Map')], default='map_upload', max_length=20, null=True, verbose_name='Map Type')),
              ('thumbnail', models.ImageField(default=None, editable=False, null=True, upload_to='')),
              ('map', models.FileField(blank=True, default=None, null=True, upload_to='', validators=[django.core.validators.FileExtensionValidator(['glb', 'png', 'jpeg', 'jpg', 'zip', 'ply', 'mp4', 'mov', 'mkv', 'webm', 'avi']), manager.validators.validate_map_file], verbose_name='Scene map as .glb or .ply or image or .zip or video')),
              ('scale', models.FloatField(blank=True, default=None, null=True, validators=[django.core.validators.MinValueValidator(5e-324)], verbose_name='Pixels per meter')),
              ('use_tracker', models.BooleanField(blank=True, choices=[(True, 'Yes'), (False, 'No')], default=True, verbose_name='Use tracker')),
              ('rotation_x', models.FloatField(default=0.0, null=True, verbose_name='X Rotation (degrees)')),
              ('rotation_y', models.FloatField(default=0.0, null=True, verbose_name='Y Rotation (degrees)')),
              ('rotation_z', models.FloatField(default=0.0, null=True, verbose_name='Z Rotation (degrees)')),
              ('translation_x', models.FloatField(default=0.0, null=True, verbose_name='X Translation (meters)')),
              ('translation_y', models.FloatField(default=0.0, null=True, verbose_name='Y Translation (meters)')),
              ('translation_z', models.FloatField(default=0.0, null=True, verbose_name='Z Translation (meters)')),
              ('scale_x', models.FloatField(default=1.0, null=True, verbose_name='X Scale')),
              ('scale_y', models.FloatField(default=1.0, null=True, verbose_name='Y Scale')),
              ('scale_z', models.FloatField(default=1.0, null=True, verbose_name='Z Scale')),
              ('map_processed', models.DateTimeField(editable=False, null=True, verbose_name='Last Processed at')),
              ('output_lla', models.BooleanField(choices=[(True, 'Yes'), (False, 'No')], default=False, null=True, verbose_name='Output geospatial coordinates')),
              ('map_corners_lla', models.JSONField(blank=True, default=None, help_text="Provide the array of four map corners geospatial coordinates (lat, long, alt).\nRequired only if 'Output geospatial coordinates' is set to `Yes`.\nExpected order: starting from the bottom-left corner counterclockwise.\nExpected JSON format: '[ [lat1, lon1, alt1], [lat2, lon2, alt2], [lat3, lon3, alt3], [lat4, lon4, alt4] ]'", null=True, validators=[manager.validators.validate_map_corners_lla], verbose_name='Geospatial coordinates of the four map corners in JSON format')),
              ('geospatial_provider', models.CharField(blank=True, choices=[('google', 'Google Maps'), ('mapbox', 'Mapbox')], default='google', help_text='The map provider used for geospatial maps (google or mapbox)', max_length=20, null=True, verbose_name='Geospatial Map Provider')),
              ('map_zoom', models.FloatField(blank=True, default=15.0, help_text='Zoom level for the geospatial map view', null=True, validators=[django.core.validators.MinValueValidator(0.0)], verbose_name='Map Zoom Level')),
              ('map_center_lat', models.FloatField(blank=True, default=None, help_text='Center latitude for the geospatial map view', null=True, verbose_name='Map Center Latitude')),
              ('map_center_lng', models.FloatField(blank=True, default=None, help_text='Center longitude for the geospatial map view', null=True, verbose_name='Map Center Longitude')),
              ('map_bearing', models.FloatField(blank=True, default=0.0, help_text='Rotation angle for the geospatial map view in degrees', null=True, verbose_name='Map Bearing/Rotation (degrees)')),
              ('trs_matrix', models.JSONField(blank=True, default=None, editable=False, help_text='4x4 transformation matrix (translation-rotation-scale) stored as JSON [[...], [...], [...], [...]]', null=True, verbose_name='Transformation matrix (Translation, Rotation, Scale) coordinates to LLA (Latitude, Longitude, Altitude)')),
              ('camera_calibration', models.CharField(choices=[('AprilTag', 'AprilTag'), ('Markerless', 'Markerless'), ('Manual', 'Manual')], default='Manual', max_length=20, verbose_name='Calibration Type')),
              ('polycam_data', models.FileField(blank=True, null=True, upload_to='', validators=[django.core.validators.FileExtensionValidator(['zip'])])),
              ('dataset_dir', models.CharField(blank=True, editable=False, max_length=200)),
              ('output_dir', models.CharField(blank=True, editable=False, max_length=200)),
              ('output', models.CharField(blank=True, editable=False, max_length=500, null=True)),
              ('retrieval_conf', models.JSONField(blank=True, editable=False, null=True)),
              ('global_descriptor_file', models.FileField(blank=True, editable=False, null=True, upload_to='', validators=[django.core.validators.FileExtensionValidator(['h5'])])),
              ('number_of_localizations', models.IntegerField(blank=True, default=50, null=True, verbose_name='Number Of Localizations')),
              ('global_feature', models.CharField(blank=True, default='netvlad', max_length=200, verbose_name='Global Feature Matching Algorithm')),
              ('local_feature', models.JSONField(blank=True, default=manager.models.Scene._getDefaultSiftDict, null=True)),
              ('matcher', models.JSONField(blank=True, default=manager.models.Scene._getDefaultNnRatioDict, null=True)),
              ('minimum_number_of_matches', models.IntegerField(blank=True, default=20, null=True, verbose_name='Minimum Number Of Matches')),
              ('polycam_hash', models.CharField(blank=True, editable=False, max_length=100, null=True)),
              ('apriltag_size', models.FloatField(blank=True, default=0.162, max_length=10, null=True, verbose_name='AprilTag Size (meters)')),
              ('regulated_rate', models.FloatField(blank=True, default=30, validators=[django.core.validators.MinValueValidator(0.001)], verbose_name='Regulate Rate (Hz)')),
              ('external_update_rate', models.FloatField(blank=True, default=30, validators=[django.core.validators.MinValueValidator(0.001)], verbose_name='Max External Update Rate (Hz)')),
              ('inlier_threshold', models.FloatField(blank=True, default=0.5, validators=[django.core.validators.MinValueValidator(0.0)], verbose_name='Feature Match Confidence Threshold')),
          ],
      ),
      migrations.CreateModel(
          name='SceneImport',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('zipFile', models.FileField(null=True, upload_to=manager.models.sanitizeZipPath)),
          ],
      ),
      migrations.CreateModel(
          name='Region',
          fields=[
              ('boundingbox_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='manager.boundingbox')),
              ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
              ('buffer_size', models.FloatField(default=0.0, validators=[django.core.validators.MinValueValidator(0)])),
              ('height', models.FloatField(default=1.0, validators=[django.core.validators.MinValueValidator(0.001)])),
              ('volumetric', models.BooleanField(choices=[(True, 'Yes'), (False, 'No')], default=False, null=True)),
              ('scene', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='regions', to='manager.scene')),
          ],
          bases=('manager.boundingbox',),
      ),
      migrations.CreateModel(
          name='Cam',
          fields=[
              ('sensor_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='manager.sensor')),
              ('command', models.CharField(default=None, max_length=512, null=True, verbose_name='Camera (Video Source)')),
              ('camerachain', models.CharField(default=None, max_length=64, null=True, verbose_name='Camera Chain')),
              ('threshold', models.FloatField(blank=True, default=None, null=True)),
              ('aspect', models.CharField(blank=True, default=None, max_length=64, null=True)),
              ('cv_subsystem', models.CharField(choices=[('AUTO', 'AUTO'), ('GPU', 'GPU'), ('CPU', 'CPU')], default='AUTO', max_length=64, null=True, verbose_name='Decode Device')),
              ('undistort', models.BooleanField(default=False, verbose_name='Undistort')),
              ('transforms', manager.fields.ListField(blank=True, default=list)),
              ('transform_type', models.CharField(choices=[('matrix', 'Matrix'), ('euler', 'Euler Angles'), ('quaternion', 'Quaternion'), ('3d-2d point correspondence', '3D-2D Point Correspondence')], default='3d-2d point correspondence', max_length=26)),
              ('width', models.IntegerField(default=640)),
              ('height', models.IntegerField(default=480)),
              ('scene_x', models.IntegerField(blank=True, default=None, null=True)),
              ('scene_y', models.IntegerField(blank=True, default=None, null=True)),
              ('scene_z', models.IntegerField(blank=True, default=None, null=True)),
              ('intrinsics_fx', models.FloatField(blank=True, default=None, null=True, validators=[django.core.validators.MinValueValidator(0.001)])),
              ('intrinsics_fy', models.FloatField(blank=True, default=None, null=True, validators=[django.core.validators.MinValueValidator(0.001)])),
              ('intrinsics_cx', models.FloatField(blank=True, default=None, null=True, validators=[django.core.validators.MinValueValidator(0.001)])),
              ('intrinsics_cy', models.FloatField(blank=True, default=None, null=True, validators=[django.core.validators.MinValueValidator(0.001)])),
              ('distortion_k1', models.FloatField(blank=True, default=None, null=True)),
              ('distortion_k2', models.FloatField(blank=True, default=None, null=True)),
              ('distortion_p1', models.FloatField(blank=True, default=None, null=True)),
              ('distortion_p2', models.FloatField(blank=True, default=None, null=True)),
              ('distortion_k3', models.FloatField(blank=True, default=None, null=True)),
              ('sensor', models.CharField(blank=True, max_length=512, null=True)),
              ('sensorchain', models.CharField(blank=True, max_length=64, null=True)),
              ('sensorattrib', models.CharField(blank=True, max_length=64, null=True)),
              ('window', models.BooleanField(default=False)),
              ('usetimestamps', models.BooleanField(default=False)),
              ('virtual', models.CharField(blank=True, max_length=512, null=True)),
              ('debug', models.BooleanField(default=False)),
              ('override_saved_intrinstics', models.BooleanField(default=False)),
              ('frames', models.IntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)])),
              ('stats', models.BooleanField(default=False)),
              ('waitforstable', models.BooleanField(default=False)),
              ('preprocess', models.BooleanField(default=False)),
              ('realtime', models.BooleanField(default=False)),
              ('faketime', models.BooleanField(default=False)),
              ('modelconfig', models.CharField(blank=True, default='model_config.json', max_length=512, null=True, verbose_name='Model Config')),
              ('rootcert', models.CharField(blank=True, max_length=64, null=True)),
              ('cert', models.CharField(blank=True, max_length=64, null=True)),
              ('cvcores', models.IntegerField(blank=True, null=True)),
              ('ovcores', models.IntegerField(blank=True, null=True)),
              ('unwarp', models.BooleanField(default=False)),
              ('ovmshost', models.CharField(blank=True, max_length=64, null=True)),
              ('framerate', models.IntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)])),
              ('maxcache', models.IntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)])),
              ('filter', models.CharField(choices=[('bottom', 'Bottom'), ('top', 'Top'), ('none', 'None (default)')], default='none', max_length=64)),
              ('disable_rotation', models.BooleanField(default=False)),
              ('maxdistance', models.FloatField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0.001)])),
              ('use_camera_pipeline', models.BooleanField(blank=True, default=False, help_text='Enable to directly apply the Camera Pipeline string in the camera VA pipeline instead of generating it automatically from camera settings.', null=True, verbose_name='Use Camera Pipeline')),
              ('camera_pipeline', models.TextField(blank=True, help_text="The camera pipeline string in gst-launch-1.0 syntax which will be applied in camera VA pipeline once 'Use Camera Pipeline' is enabled and 'Save Camera' button is clicked. Please review and/or adjust it before applying.", max_length=5000, null=True)),
              ('detection_labels', models.TextField(blank=True, help_text='Detection labels to use, one per line', max_length=2000, null=True, verbose_name='Detection Labels')),
          ],
          bases=('manager.sensor',),
      ),
      migrations.CreateModel(
          name='SingletonSensor',
          fields=[
              ('sensor_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='manager.sensor')),
              ('map_x', models.FloatField(blank=True, default=None, null=True)),
              ('map_y', models.FloatField(blank=True, default=None, null=True)),
              ('area', models.CharField(choices=[('scene', 'scene'), ('circle', 'circle'), ('poly', 'poly')], default='scene', max_length=16)),
              ('radius', models.FloatField(blank=True, default=None, null=True)),
              ('singleton_type', models.CharField(choices=[('environmental', 'environmental'), ('attribute', 'attribute')], default='environmental', max_length=20, verbose_name='Type of Sensor')),
          ],
          bases=('manager.sensor',),
      ),
      migrations.CreateModel(
          name='Vehicle',
          fields=[
              ('mobileobject_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='manager.mobileobject')),
          ],
          bases=('manager.mobileobject',),
      ),
      migrations.AddField(
          model_name='sensor',
          name='scene',
          field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='manager.scene'),
      ),
      migrations.AddField(
          model_name='mobileobject',
          name='scene',
          field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='manager.scene'),
      ),
      migrations.CreateModel(
          name='CalibrationMarker',
          fields=[
              ('marker_id', models.CharField(max_length=50, primary_key=True, serialize=False)),
              ('apriltag_id', models.CharField(max_length=10)),
              ('dims', manager.fields.ListField(default=list)),
              ('scene', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='manager.scene')),
          ],
      ),
      migrations.CreateModel(
          name='UserSession',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('session', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='sessions.session')),
              ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
          ],
      ),
      migrations.CreateModel(
          name='RegionOccupancyThreshold',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('sectors', models.JSONField(default=list)),
              ('range_max', models.IntegerField(default=10)),
              ('region', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='roi_occupancy_threshold', to='manager.region')),
          ],
      ),
      migrations.CreateModel(
          name='Event',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('timestamp', models.FloatField(db_index=True)),
              ('region', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='manager.region')),
          ],
      ),
      migrations.CreateModel(
          name='Tripwire',
          fields=[
              ('boundingbox_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='manager.boundingbox')),
              ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
              ('height', models.FloatField(default=1.0)),
              ('scene', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tripwires', to='manager.scene')),
          ],
          bases=('manager.boundingbox',),
      ),
      migrations.CreateModel(
          name='RegionPoint',
          fields=[
              ('boundingboxpoints_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='manager.boundingboxpoints')),
              ('region', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='points', to='manager.region')),
          ],
          bases=('manager.boundingboxpoints',),
      ),
      migrations.CreateModel(
          name='TripwirePoint',
          fields=[
              ('boundingboxpoints_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='manager.boundingboxpoints')),
              ('tripwire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='points', to='manager.tripwire')),
          ],
          bases=('manager.boundingboxpoints',),
      ),
      migrations.CreateModel(
          name='SingletonScalarThreshold',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('sectors', models.JSONField(default=list)),
              ('range_max', models.IntegerField(default=10)),
              ('singleton', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='singleton_scalar_threshold', to='manager.singletonsensor')),
          ],
      ),
      migrations.CreateModel(
          name='SingletonAreaPoint',
          fields=[
              ('boundingboxpoints_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='manager.boundingboxpoints')),
              ('singleton', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='points', to='manager.singletonsensor')),
          ],
          bases=('manager.boundingboxpoints',),
      ),
      migrations.CreateModel(
          name='CamLog',
          fields=[
              ('log', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='camLog', serialize=False, to='manager.datalog')),
              ('pid', models.IntegerField(blank=True, default=None, null=True)),
              ('x', models.FloatField(blank=True, default=None, null=True)),
              ('y', models.FloatField(blank=True, default=None, null=True)),
              ('width', models.FloatField(blank=True, default=None, null=True)),
              ('height', models.FloatField(blank=True, default=None, null=True)),
              ('sensor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='manager.sensor')),
          ],
      ),
      migrations.CreateModel(
          name='SceneLog',
          fields=[
              ('log', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='manager.datalog')),
              ('scene', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='manager.scene')),
          ],
      ),
      migrations.CreateModel(
          name='PubSubACL',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('topic', models.CharField(choices=[('CHANNEL', 'CHANNEL'), ('CMD_CAMERA', 'CMD_CAMERA'), ('CMD_DATABASE', 'CMD_DATABASE'), ('CMD_KUBECLIENT', 'CMD_KUBECLIENT'), ('CMD_SCENE_UPDATE', 'CMD_SCENE_UPDATE'), ('DATA_AUTOCALIB_CAM_POSE', 'DATA_AUTOCALIB_CAM_POSE'), ('DATA_CAMERA', 'DATA_CAMERA'), ('DATA_EXTERNAL', 'DATA_EXTERNAL'), ('DATA_REGION', 'DATA_REGION'), ('DATA_REGULATED', 'DATA_REGULATED'), ('DATA_SCENE', 'DATA_SCENE'), ('DATA_SENSOR', 'DATA_SENSOR'), ('EVENT', 'EVENT'), ('IMAGE_CALIBRATE', 'IMAGE_CALIBRATE'), ('IMAGE_CAMERA', 'IMAGE_CAMERA'), ('SYS_CHILDSCENE_STATUS', 'SYS_CHILDSCENE_STATUS'), ('ANALYTICS_CLUSTERS', 'ANALYTICS_CLUSTERS')], max_length=50)),
              ('access', models.IntegerField(choices=[(0, 'No access'), (1, 'Read only'), (2, 'Write only'), (3, 'Read and Write')], default=0)),
              ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='acls', to=settings.AUTH_USER_MODEL)),
          ],
          options={
              'constraints': [models.UniqueConstraint(fields=('user', 'topic'), name='manager_pubsubacl_unique_user_topic')],
          },
      ),
      migrations.CreateModel(
          name='ChildScene',
          fields=[
              ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
              ('child_name', models.CharField(blank=True, default=None, max_length=200, null=True, verbose_name='Child Name')),
              ('remote_child_id', models.UUIDField(blank=True, default=None, null=True, unique=True, verbose_name='Remote Child ID')),
              ('child_type', models.CharField(default='local', max_length=15)),
              ('transform1', models.FloatField(blank=True, default=1.0, null=True)),
              ('transform2', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform3', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform4', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform5', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform6', models.FloatField(blank=True, default=1.0, null=True)),
              ('transform7', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform8', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform9', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform10', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform11', models.FloatField(blank=True, default=1.0, null=True)),
              ('transform12', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform13', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform14', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform15', models.FloatField(blank=True, default=0.0, null=True)),
              ('transform16', models.FloatField(blank=True, default=1.0, null=True)),
              ('transform_type', models.CharField(choices=[('matrix', 'Matrix'), ('euler', 'Euler Angles'), ('quaternion', 'Quaternion')], default='matrix', max_length=10)),
              ('host_name', models.CharField(blank=True, max_length=200, null=True, verbose_name='Hostname or IP')),
              ('mqtt_username', models.CharField(blank=True, max_length=200, null=True, verbose_name='MQTT Username')),
              ('mqtt_password', models.CharField(blank=True, max_length=200, null=True, verbose_name='MQTT Password')),
              ('retrack', models.BooleanField(blank=True, choices=[(True, 'Yes'), (False, 'No')], default=True, verbose_name='Retrack objects')),
              ('child', models.OneToOneField(blank=True, default=None, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='parent', to='manager.scene')),
              ('parent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='children', to='manager.scene')),
          ],
          options={
              'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('child__isnull', False), ('child_name__isnull', True)), models.Q(('child__isnull', True), ('child_name__isnull', False)), _connector='OR'), name='manager_childscene_either_child_or_child_name'), models.UniqueConstraint(fields=('child', 'parent'), name='manager_childscene_local_child_unique_relationships'), models.UniqueConstraint(fields=('child_name', 'parent'), name='manager_childscene_remote_child_unique_relationships'), models.CheckConstraint(condition=models.Q(('child', models.F('parent')), _negated=True), name='manager_childscene_prevent_self_follow')],
          },
      ),
  ]
