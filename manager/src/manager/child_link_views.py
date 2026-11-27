# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""REST endpoints that attach georeference-placed children to a root scene."""

from django.http import JsonResponse
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.views import APIView

from manager import hierarchy
from manager.api import IsAdminOrReadOnly
from manager.models import Scene
from manager.serializers import ChildLinkBatchSerializer, PlacedChildSerializer


def _parent_or_404(scene_uid):
  parent = Scene.objects.filter(pk=scene_uid).first()
  if parent is None:
    return None, JsonResponse({'error': 'Scene not found'}, status=404)
  return parent, None


class ChildLinks(APIView):
  """Placement status of a scene's children (GET) and a batch attach of georeference-placed children (POST).

  A batch is all-or-nothing: any rejected item returns 400 with per-item errors and writes nothing.
  Children already linked with an up-to-date placement are reported as unchanged; stale ones are recomputed.
  """
  authentication_classes = [SessionAuthentication, TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  def get(self, request, scene_uid):
    parent, not_found = _parent_or_404(scene_uid)
    if not_found:
      return not_found
    return JsonResponse({'results': hierarchy.placement_status(parent)})

  def post(self, request, scene_uid):
    batch = ChildLinkBatchSerializer(data=request.data)
    if not batch.is_valid():
      return JsonResponse({'error': batch.errors}, status=400)
    parent, not_found = _parent_or_404(scene_uid)
    if not_found:
      return not_found
    children = [item['child'] for item in batch.validated_data['children']]
    try:
      results, errors = hierarchy.attach_children(parent, children)
    except hierarchy.HierarchyError as error:
      return JsonResponse({'error': str(error)}, status=error.status)
    if errors:
      return JsonResponse({'errors': errors}, status=400)
    return JsonResponse({'results': results})


class PlacedChild(APIView):
  """Create a scene shell inside a root scene's frame, linked with the placed transform."""
  authentication_classes = [SessionAuthentication, TokenAuthentication]
  permission_classes = [IsAdminOrReadOnly]

  def post(self, request, scene_uid):
    rectangle = PlacedChildSerializer(data=request.data)
    if not rectangle.is_valid():
      return JsonResponse({'error': rectangle.errors}, status=400)
    parent, not_found = _parent_or_404(scene_uid)
    if not_found:
      return not_found
    try:
      shell, _, result = hierarchy.create_placed_child(parent, **rectangle.validated_data)
    except hierarchy.HierarchyError as error:
      return JsonResponse({'error': str(error)}, status=error.status)
    return JsonResponse({
      'child': str(shell.pk),
      'name': shell.name,
      'heading_deg': result.heading_deg,
      'residual_m': result.provenance['residual_m'],
    }, status=201)
