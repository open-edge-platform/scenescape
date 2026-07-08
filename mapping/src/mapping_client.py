# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import mimetypes
import os
import time
from http import HTTPStatus
from urllib.parse import urljoin

from scene_common.rest_client import RESTClient

logger = logging.getLogger(__name__)


class MappingClient(RESTClient):
  """Client for mapping/reconstruction REST endpoints."""

  def _build_multipart_files(self, data, file_fields):
    """Build multipart file payload and return opened handles for caller cleanup."""
    data = data.copy()
    files = []
    handles = []
    try:
      for field in file_fields:
        if field not in data:
          continue
        paths = data.pop(field)
        if isinstance(paths, str):
          paths = [paths]
        for path in paths:
          if not os.path.exists(path):
            raise FileNotFoundError(
                f"File not found for field '{field}': {path}")
          mime_type, _ = mimetypes.guess_type(path)
          if mime_type is None:
            mime_type = "application/octet-stream"
          fh = open(path, 'rb')
          handles.append(fh)
          files.append((field, (os.path.basename(path), fh, mime_type)))
    except Exception:
      for fh in handles:
        try:
          fh.close()
        except Exception:
          logger.warning(
              "Failed to close file handle during cleanup", exc_info=True)
      raise

    return data, files if files else None, handles

  def performReconstruction(self, data):
    """Perform 3D reconstruction by uploading images and/or a video file."""
    handles = []
    try:
      data, files, handles = self._build_multipart_files(data, ['images', 'video'])
      path = urljoin(self.url, "reconstruction")

      # Do not force Content-Type for multipart requests.
      headers = self._headers()
      if 'Content-Type' in headers:
        del headers['Content-Type']

      data_args = self.prepareDataArgs(data, files)
      reply = self.session.post(
          path,
          **data_args,
          files=files,
          headers=headers,
          verify=self.verify_ssl,
          timeout=self.timeout,
      )
      return self.decodeReply(reply, [HTTPStatus.OK, HTTPStatus.ACCEPTED])
    finally:
      for fh in handles:
        fh.close()

  def getReconstructionStatus(self, request_id):
    """Get status for a reconstruction request."""
    reply = self.request("get", f"reconstruction/status/{request_id}")
    return self.decodeReply(reply, HTTPStatus.OK)

  def waitForReconstruction(self, request_id, timeout_s=900, poll_s=1.5):
    """Poll reconstruction status until complete/failed or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
      status = self.getReconstructionStatus(request_id)
      if not status:
        raise RuntimeError(
            f"Status check failed ({status.status_code}): {status.errors}")

      state = status.get("state")
      if state == "complete":
        result = status.get("result") or {}
        if not result.get("success", True):
          raise RuntimeError(result.get("error", "Reconstruction failed"))
        return result

      if state == "failed":
        raise RuntimeError(status.get("error") or "Reconstruction failed")

      time.sleep(poll_s)

    raise TimeoutError(
        f"Timed out waiting for mesh generation (request_id={request_id}) after {timeout_s}s")

  def healthCheckEndpoint(self):
    """Health check endpoint."""
    reply = self.request("get", "health")
    return self.decodeReply(reply, HTTPStatus.OK)
