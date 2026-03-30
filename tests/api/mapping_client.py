# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import mimetypes
import os
from http import HTTPStatus
from urllib.parse import urljoin

from scene_common.rest_client import RESTClient

logger = logging.getLogger(__name__)


class MappingClient(RESTClient):
  """Client for mapping/reconstruction REST endpoints.

  Extends RESTClient with mapping-specific methods that don't belong
  in the general-purpose REST client.
  """

  def _build_multipart_files(self, data, file_fields):
    """Extract file path strings from data dict and open them as file handles
    for multipart/form-data requests.

    Caller MUST close the returned handles (use try/finally).

    @param      data            dict potentially containing file path strings
    @param      file_fields     list of field names to treat as file paths;
                                each value may be a single path string or a list of paths
    @return                     (cleaned_data, files_list, file_handles)
                                - cleaned_data: data dict with file fields removed
                                - files_list:   list of (field, (filename, handle, mimetype))
                                                tuples ready to pass as requests `files=`
                                - file_handles: list of open file handles to close after request
    """
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
    """Perform 3D reconstruction by uploading images and/or a video file.

    Sends a multipart/form-data POST to /reconstruction.

    @param      data            dict with reconstruction parameters:
                                  - images (str or list[str]): image file paths (field name "images")
                                  - video  (str or list[str]): video file path(s) (field name "video")
                                  - output_format (str):       "glb" or "json"
                                  - mesh_type (str):           "mesh" or "pointcloud"
                                  - use_keyframes (bool):      True/False
                                `images` and `video` are opened as binary multipart parts;
                                all remaining keys become plain form fields.
    @return                     dict with reconstruction info on success,
                                empty with `errors` set on failure
    """
    handles = []
    try:
      data, files, handles = self._build_multipart_files(
          data, ['images', 'video'])
      full_path = urljoin(self.url, "reconstruction")
      headers = {'Authorization': f"Token {self.token}"}
      data_args = self.prepareDataArgs(data, files)
      reply = self.session.post(full_path, **data_args, files=files,
                                headers=headers, verify=self.verify_ssl)
      return self.decodeReply(reply, [HTTPStatus.OK, HTTPStatus.ACCEPTED])
    finally:
      for fh in handles:
        fh.close()

  def getReconstructionStatus(self, request_id):
    """Poll the status of an async reconstruction job.

    @param      request_id      request_id returned by performReconstruction
    @return                     dict with job state on success:
                                  - state: "queued" | "processing" | "complete" | "failed"
                                  - message: optional progress message
                                  - result: final result dict (when state == "complete")
                                  - error: error description (when state == "failed")
    """
    return self._get(f"reconstruction/status/{request_id}", None)

  def healthCheckEndpoint(self):
    """Health check endpoint

    @return                     dict with health status on success,
                                empty with `errors` set on failure
    """
    return self._get("health", None)

  def listModels(self, filter=None):
    """List available models

    @param      filter          Optional dict with filter parameters
    @return                     dict with list of models on success,
                                empty with `errors` set on failure
    """
    return self._get("models", filter)
