# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for mesh generate/status HTTP helpers and idempotency."""

from unittest.mock import patch

from django.test import TestCase

from manager.mesh_http import (
  mesh_generation_status_payload,
  start_mesh_generation_payload,
)
from manager.models import MeshGenerationRequest, Scene

TEST_NAME = "NEX-T18751"


class MeshHttpIdempotencyTests(TestCase):
  def setUp(self):
    self.scene = Scene.objects.create(name="mesh-idempotency-scene")

  @patch("manager.mesh_generator.MeshGenerator")
  def test_start_records_in_progress(self, mock_gen_cls):
    gen = mock_gen_cls.return_value
    gen.startMeshGeneration.return_value = {
      "success": True,
      "request_id": "req-abc",
    }
    payload, code = start_mesh_generation_payload(self.scene)
    self.assertEqual(code, 200)
    self.assertTrue(payload["success"])
    job = MeshGenerationRequest.objects.get(request_id="req-abc")
    self.assertEqual(job.state, MeshGenerationRequest.STATE_IN_PROGRESS)
    self.assertEqual(job.scene_id, self.scene.pk)

  @patch("manager.mesh_generator.MeshGenerator")
  def test_status_skips_finalize_when_already_complete(self, mock_gen_cls):
    MeshGenerationRequest.objects.create(
      request_id="req-done",
      scene=self.scene,
      state=MeshGenerationRequest.STATE_COMPLETE,
    )
    gen = mock_gen_cls.return_value
    gen.mapping_client.getReconstructionStatus.return_value = {
      "success": True,
      "state": "complete",
      "result": {"success": True},
    }
    payload, code = mesh_generation_status_payload(self.scene, "req-done")
    self.assertEqual(code, 200)
    self.assertTrue(payload.get("finalized"))
    gen.finalizeMeshFromStatus.assert_not_called()

  @patch("manager.mesh_generator.MeshGenerator")
  def test_status_finalizes_once_then_idempotent(self, mock_gen_cls):
    MeshGenerationRequest.objects.create(
      request_id="req-new",
      scene=self.scene,
      state=MeshGenerationRequest.STATE_IN_PROGRESS,
    )
    gen = mock_gen_cls.return_value
    gen.mapping_client.getReconstructionStatus.return_value = {
      "success": True,
      "state": "complete",
      "result": {"success": True},
    }
    gen.finalizeMeshFromStatus.return_value = {"success": True}

    first, code1 = mesh_generation_status_payload(self.scene, "req-new")
    second, code2 = mesh_generation_status_payload(self.scene, "req-new")
    self.assertEqual(code1, 200)
    self.assertEqual(code2, 200)
    self.assertTrue(first.get("finalized"))
    self.assertTrue(second.get("finalized"))
    self.assertEqual(gen.finalizeMeshFromStatus.call_count, 1)
    job = MeshGenerationRequest.objects.get(request_id="req-new")
    self.assertEqual(job.state, MeshGenerationRequest.STATE_COMPLETE)
