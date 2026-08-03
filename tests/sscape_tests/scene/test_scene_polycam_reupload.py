# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import hashlib
import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from manager.forms import SceneUpdateForm
from manager.models import Scene


def buildPolycamZipBytes(image_content=b"jpg-bytes"):
  buffer = io.BytesIO()
  with zipfile.ZipFile(buffer, "w") as zf:
    zf.writestr("dataset/mesh_info.json", "{}")
    zf.writestr("dataset/raw.glb", b"glb-bytes")
    zf.writestr("dataset/keyframes/images/frame0.jpg", image_content)
    zf.writestr("dataset/keyframes/depth/frame0.png", b"png-bytes")
    zf.writestr("dataset/keyframes/cameras/frame0.json", "{}")
  return buffer.getvalue()


class ScenePolycamReuploadTestCase(TestCase):
  def setUp(self):
    self.zip_bytes = buildPolycamZipBytes()
    self.scene = Scene.objects.create(name="test_polycam_scene")
    self.scene.polycam_hash = hashlib.sha256(self.zip_bytes).hexdigest()
    self.scene.save()

  def _requiredFormData(self):
    # Minimal set of fields the model requires (blank=False) for the form to reach clean().
    return {
      "name": self.scene.name,
      "map_type": "map_upload",
      "rotation_x": "0", "rotation_y": "0", "rotation_z": "0",
      "translation_x": "0", "translation_y": "0", "translation_z": "0",
      "scale_x": "1", "scale_y": "1", "scale_z": "1",
      "output_lla": "False",
      "camera_calibration": "Markerless",
    }

  def test_reupload_identical_polycam_data_is_allowed(self):
    upload = SimpleUploadedFile("dataset.zip", self.zip_bytes, content_type="application/zip")
    form = SceneUpdateForm(data=self._requiredFormData(), files={"polycam_data": upload}, instance=self.scene)
    self.assertTrue(form.is_valid(), form.errors)
    self.assertNotIn("polycam_data", form.errors)

  def test_reupload_new_polycam_data_is_allowed(self):
    new_zip_bytes = buildPolycamZipBytes(image_content=b"different-jpg-bytes")
    self.assertNotEqual(hashlib.sha256(new_zip_bytes).hexdigest(), self.scene.polycam_hash)
    upload = SimpleUploadedFile("dataset.zip", new_zip_bytes, content_type="application/zip")
    form = SceneUpdateForm(data=self._requiredFormData(), files={"polycam_data": upload}, instance=self.scene)
    self.assertTrue(form.is_valid(), form.errors)
    self.assertNotIn("polycam_data", form.errors)

  def test_invalid_polycam_zip_is_still_rejected(self):
    invalid_zip_bytes = io.BytesIO()
    with zipfile.ZipFile(invalid_zip_bytes, "w") as zf:
      zf.writestr("dataset/not_a_dataset.txt", "no polycam data here")
    upload = SimpleUploadedFile("dataset.zip", invalid_zip_bytes.getvalue(), content_type="application/zip")
    form = SceneUpdateForm(data=self._requiredFormData(), files={"polycam_data": upload}, instance=self.scene)
    self.assertFalse(form.is_valid())
    self.assertIn("mesh_info.json", str(form.errors))
