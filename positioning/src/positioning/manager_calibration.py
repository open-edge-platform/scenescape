# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Read Manager-owned PTZ calibration and home pose for the Resolver."""

from requests.adapters import HTTPAdapter

from positioning.ptz_model import PTZCalibrationError, load_ptz_model
from positioning.resolver import PTZSourceCalibration
from scene_common.rest_client import RESTClient


class _ManagerTimeoutAdapter(HTTPAdapter):
  """Supply the timeout omitted by the shared REST client's HTTP calls."""

  def __init__(self, timeout):
    super().__init__()
    self.timeout = timeout

  def send(self, request, **kwargs):
    if kwargs.get("timeout") is None:
      kwargs["timeout"] = self.timeout
    return super().send(request, **kwargs)


class _ManagerRESTClient(RESTClient):
  """Apply Positioning's Manager timeout before authenticating."""

  def __init__(self, url, auth, rootcert, timeout=10):
    super().__init__(url, rootcert=rootcert, timeout=timeout)
    self.session.mount("http://", _ManagerTimeoutAdapter(timeout))
    self.session.mount("https://", _ManagerTimeoutAdapter(timeout))
    if auth:
      self._parseAuth(auth)


class ManagerCalibrationError(RuntimeError):
  """Raised when a Manager camera record cannot be loaded safely."""


class ManagerCalibrationLoader:
  """Lazily authenticate to Manager and load camera calibration on demand."""

  def __init__(self, url, auth, root_cert, client_factory=_ManagerRESTClient):
    self.url = url
    self.auth = auth
    self.root_cert = root_cert
    self.client_factory = client_factory
    self._client = None

  def load(self, source_id):
    """Return the current calibration, or None for a missing/incomplete record."""
    try:
      if self._client is None:
        self._client = self.client_factory(
          self.url, auth=self.auth, rootcert=self.root_cert, timeout=10)
      camera = self._client.getCamera(source_id)
    except Exception as error:
      self._client = None
      raise ManagerCalibrationError("Manager camera request failed") from error

    if camera.statusCode != 200:
      if camera.statusCode == 401:
        self._client = None
      raise ManagerCalibrationError(f"Manager camera request returned {camera.statusCode}")
    if camera.get("uid") != source_id:
      raise ManagerCalibrationError("Manager returned a different camera identity")
    calibration = camera.get("ptz_calibration")
    home_matrix = camera.get("pose_matrix")
    scene_id = camera.get("scene")
    if calibration is None or home_matrix is None or scene_id is None:
      return None
    try:
      model = load_ptz_model(calibration)
    except (PTZCalibrationError, KeyError, TypeError) as error:
      raise ManagerCalibrationError("Manager returned invalid PTZ calibration") from error
    return PTZSourceCalibration(model, home_matrix, f"scene:{scene_id}")
