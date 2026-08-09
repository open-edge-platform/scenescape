# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import hashlib
import os

from django import forms
from django.db.models import Q
from django.forms import ModelForm

from manager.models import Scene, SceneImport, ChildScene
from manager.validators import validate_zip_file

class ROIForm(forms.Form):
  rois = forms.CharField()
  tripwires = forms.CharField()

class SceneImportForm(ModelForm):
  class Meta:
    model = SceneImport
    fields = ('__all__')

class SceneUpdateForm(ModelForm):
  class Meta:
    model = Scene
    fields = ('__all__')

  def updatePolycamHash(self, zip_file):
    # Re-uploading a zip (even one identical to the current data) must always be allowed to save.
    file_hash = hashlib.sha256(zip_file.read()).hexdigest()
    zip_file.seek(0)
    self.instance.polycam_hash = file_hash
    return

  def clean(self):
    cleaned_data = super().clean()
    new_polycam_file = cleaned_data.get('polycam_data')
    new_map_file = cleaned_data.get('map')
    map_file_ext = os.path.splitext(self.instance.map.name)[1].lower() if self.instance.map else None

    if new_map_file:
      map_file_ext = os.path.splitext(new_map_file.name)[1].lower()
      if map_file_ext == ".zip":
        self.updatePolycamHash(new_map_file)
        validate_zip_file(new_map_file)
    if new_polycam_file:
      self.updatePolycamHash(new_polycam_file)
      validate_zip_file(new_polycam_file, map_file_ext == ".glb")
    else:
      self.instance.polycam_hash = ""

    if cleaned_data['output_lla'] and (cleaned_data.get('map_corners_lla') is None or cleaned_data.get('map') is None):
      raise forms.ValidationError("If 'Output geospatial coordinates' is enabled then map corners LLA and map file are required.")
    return cleaned_data

class ChildSceneForm(forms.ModelForm):
  class Meta:
    model = ChildScene
    child_types = [
      ('local', 'local'),
      ('remote', 'remote')
    ]
    fields = ['child_type', 'child', 'remote_child_id', 'child_name', 'parent', 'host_name', \
          'mqtt_username', 'mqtt_password', 'retrack', 'transform_type', \
          'transform1', 'transform2', 'transform3', 'transform4', \
          'transform5', 'transform6', 'transform7', 'transform8', \
          'transform9', 'transform10', 'transform11', 'transform12', \
          'transform13', 'transform14', 'transform15', 'transform16']
    widgets = {
      'child_type' : forms.RadioSelect(choices=child_types),
      'retrack': forms.CheckboxInput(),
    }

  def __init__(self, *args, **kwargs):
    super(ChildSceneForm, self).__init__(*args, **kwargs)
    childScenes = ChildScene.objects.all()
    filteredScenes = Scene.objects.all()
    is_update = hasattr(self.instance, "parent")

    if is_update:
      parent = self.instance.parent
      self.fields['parent'].queryset = Scene.objects.filter(name=self.instance.parent)
      self.fields['child'].queryset = Scene.objects.filter(name=self.instance.child)
    else:
      parent = self.initial.get('parent', None)
      self.fields['parent'].queryset = Scene.objects.all()
      self.fields['child'].queryset = Scene.objects.none()

    # Filter out all the Scenes that have a parent and ones that create circular dependencies
    for childObj in childScenes:
      filteredScenes = filteredScenes.filter(~Q(name=childObj.child))
      if self._isParentInHierarchy(parent, childObj):
        filteredScenes = filteredScenes.filter(~Q(name=childObj.parent))

    self.fields['child'].queryset |= filteredScenes
    return

  def _isParentInHierarchy(self, parent, child):
    stack = [child]
    while stack:
      current_child = stack.pop()
      if parent == current_child.child:
        return True
      for childObj in ChildScene.objects.filter(parent=current_child.child):
        stack.append(childObj)
    return False

  def clean(self):
    cleaned_data = super().clean()
    if cleaned_data['child_type'] == 'remote':
      if cleaned_data['child_name'] == cleaned_data['parent'].name:
        self.add_error('child_name', "Parent and child cannot have same name.")
      elif cleaned_data['remote_child_id'] == cleaned_data['parent'].id:
        self.add_error('remote_child_id', "Parent and child cannot have same id.")
      elif Scene.objects.filter(id=cleaned_data['remote_child_id']).exists():
        self.add_error('remote_child_id', "Scene with this id already exists. Create a local child scene.")
    return cleaned_data
