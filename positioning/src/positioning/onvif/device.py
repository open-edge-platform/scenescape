# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ONVIF device, media, and PTZ operations needed for pan/tilt polling."""

import datetime
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit
from html import escape

from positioning.onvif.soap import (
  OnvifFault, OnvifTransportError, SoapClient, child_text, find_child, find_path, local_name)

DEVICE_PATH = "/onvif/device_service"
GENERIC_PAN_TILT_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"

_DEVICE_WSDL = "http://www.onvif.org/ver10/device/wsdl"
_MEDIA_WSDL = "http://www.onvif.org/ver10/media/wsdl"
_PTZ_WSDL = "http://www.onvif.org/ver20/ptz/wsdl"
_EVENTS_WSDL = "http://www.onvif.org/ver10/events/wsdl"


@dataclass(frozen=True)
class PositionSpace:
  uri: str
  pan_min: float
  pan_max: float
  tilt_min: float
  tilt_max: float


@dataclass(frozen=True)
class PtzStatus:
  pan: float
  tilt: float
  zoom: Optional[float]
  space_uri: Optional[str]
  pan_tilt_move_status: Optional[str]


@dataclass(frozen=True)
class DeviceInformation:
  manufacturer: Optional[str]
  model: Optional[str]
  firmware_version: Optional[str]


def _parse_float(value, what):
  try:
    return float(value)
  except (TypeError, ValueError):
    raise OnvifTransportError(f"Malformed {what} in ONVIF response") from None


def _format_host(host):
  return f"[{host}]" if ":" in host and not host.startswith("[") else host


class OnvifPtzDevice:
  """Connection to one ONVIF PTZ camera; not thread-safe, create one per thread."""

  def __init__(self, host, port, credentials, scheme="https", timeout_s=1.0, verify=True,
               profile_token=None, soap_client=None, wall_clock=time.time):
    if scheme not in ("http", "https"):
      raise ValueError("ONVIF scheme must be 'http' or 'https'")
    self.host = host
    self.port = port
    self.scheme = scheme
    self.requested_profile_token = profile_token
    self.device_url = urlunsplit((scheme, f"{_format_host(host)}:{port}", DEVICE_PATH, "", ""))
    self._wall_clock = wall_clock
    self.soap = soap_client or SoapClient(credentials, timeout_s, verify, wall_clock=wall_clock)
    self.xaddrs: Dict[str, str] = {}
    self.profile_token: Optional[str] = None
    self.node_token: Optional[str] = None
    self.default_space_uri: Optional[str] = None
    self.position_spaces: Tuple[PositionSpace, ...] = ()

  def close(self):
    self.soap.close()

  def connect_services(self):
    """Synchronize the WS-Security clock offset and resolve service endpoints."""
    self.sync_clock()
    self.xaddrs = self.get_capabilities()
    return self

  def connect(self):
    """Resolve service endpoints, PTZ profile, and advertised absolute position spaces."""
    self.connect_services()
    if "ptz" not in self.xaddrs or "media" not in self.xaddrs:
      raise OnvifTransportError("Device does not advertise ONVIF Media and PTZ services")
    self._select_profile()
    self.position_spaces = self._absolute_pan_tilt_spaces()
    return self

  def sync_clock(self):
    """Estimate device-minus-host clock offset for WS-Security timestamps (1 s resolution)."""
    start = self._wall_clock()
    response = self.soap.call(self.device_url, f"{_DEVICE_WSDL}/GetSystemDateAndTime",
                              "<tds:GetSystemDateAndTime/>", authenticate=False)
    midpoint = (start + self._wall_clock()) / 2
    utc = find_path(response, "SystemDateAndTime", "UTCDateTime")
    if utc is None:
      self.soap.clock_offset_s = 0.0
      return 0.0
    try:
      device_time = datetime.datetime(
        int(child_text(utc, "Date", "Year")), int(child_text(utc, "Date", "Month")),
        int(child_text(utc, "Date", "Day")), int(child_text(utc, "Time", "Hour")),
        int(child_text(utc, "Time", "Minute")), int(child_text(utc, "Time", "Second")),
        tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
      raise OnvifTransportError("Malformed GetSystemDateAndTime response") from None
    self.soap.clock_offset_s = device_time.timestamp() - midpoint
    return self.soap.clock_offset_s

  def call(self, url, action, body, timeout_s=None):
    try:
      return self.soap.call(url, action, body, timeout_s=timeout_s)
    except OnvifFault as fault:
      if not fault.not_authorized:
        raise
    # WS-Security rejects drifting device clocks; resynchronize once and retry.
    self.sync_clock()
    return self.soap.call(url, action, body, timeout_s=timeout_s)

  def trusted_xaddr(self, xaddr):
    """Keep device-advertised paths but never send credentials to a different host."""
    parts = urlsplit((xaddr or "").strip())
    if parts.scheme not in ("http", "https") or not parts.path:
      raise OnvifTransportError("Device advertised an invalid service address")
    port = parts.port or self.port
    if parts.hostname != self.host.strip("[]"):
      parts = parts._replace(scheme=self.scheme)
    elif self.scheme == "https" and parts.scheme == "http":
      raise OnvifTransportError("HTTPS camera advertised an insecure service address")
    return urlunsplit((parts.scheme, f"{_format_host(self.host)}:{port}", parts.path, parts.query, ""))

  def get_capabilities(self):
    response = self.call(self.device_url, f"{_DEVICE_WSDL}/GetCapabilities",
                          "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>")
    capabilities = find_child(response, "Capabilities")
    xaddrs = {"device": self.device_url}
    if capabilities is None:
      return xaddrs
    for service in ("Media", "PTZ", "Events"):
      xaddr = child_text(capabilities, service, "XAddr")
      if xaddr:
        xaddrs[service.lower()] = self.trusted_xaddr(xaddr)
    return xaddrs

  def get_device_information(self):
    response = self.call(self.device_url, f"{_DEVICE_WSDL}/GetDeviceInformation",
                          "<tds:GetDeviceInformation/>")
    return DeviceInformation(child_text(response, "Manufacturer"), child_text(response, "Model"),
                             child_text(response, "FirmwareVersion"))

  def _select_profile(self):
    response = self.call(self.xaddrs["media"], f"{_MEDIA_WSDL}/GetProfiles", "<trt:GetProfiles/>")
    for profile in response:
      if local_name(profile.tag) != "Profiles":
        continue
      token = profile.get("token")
      ptz_config = find_child(profile, "PTZConfiguration")
      if ptz_config is None:
        continue
      if self.requested_profile_token and token != self.requested_profile_token:
        continue
      self.profile_token = token
      self.node_token = child_text(ptz_config, "NodeToken")
      self.default_space_uri = child_text(ptz_config, "DefaultAbsolutePantTiltPositionSpace")
      return
    wanted = f" '{self.requested_profile_token}'" if self.requested_profile_token else ""
    raise OnvifTransportError(f"No media profile{wanted} with a PTZ configuration")

  def _absolute_pan_tilt_spaces(self):
    response = self.call(self.xaddrs["ptz"], f"{_PTZ_WSDL}/GetNodes", "<tptz:GetNodes/>")
    nodes = [node for node in response if local_name(node.tag) == "PTZNode"]
    selected = next((node for node in nodes if node.get("token") == self.node_token), None)
    if selected is None and len(nodes) == 1:
      selected = nodes[0]
    if selected is None:
      raise OnvifTransportError("PTZ node for the selected profile was not found")
    supported = find_child(selected, "SupportedPTZSpaces")
    spaces = []
    for space in supported if supported is not None else ():
      if local_name(space.tag) != "AbsolutePanTiltPositionSpace":
        continue
      spaces.append(PositionSpace(
        child_text(space, "URI"),
        _parse_float(child_text(space, "XRange", "Min"), "pan range"),
        _parse_float(child_text(space, "XRange", "Max"), "pan range"),
        _parse_float(child_text(space, "YRange", "Min"), "tilt range"),
        _parse_float(child_text(space, "YRange", "Max"), "tilt range")))
    return tuple(spaces)

  def position_space(self, uri):
    """Advertised range for the URI reported by GetStatus (or the profile default)."""
    uri = uri or self.default_space_uri
    if uri is None and len(self.position_spaces) == 1:
      return self.position_spaces[0]
    uri = uri or GENERIC_PAN_TILT_SPACE
    return next((space for space in self.position_spaces if space.uri == uri), None)

  def get_status(self):
    response = self.call(
      self.xaddrs["ptz"], f"{_PTZ_WSDL}/GetStatus",
      f"<tptz:GetStatus><tptz:ProfileToken>{escape(self.profile_token)}</tptz:ProfileToken></tptz:GetStatus>")
    status = find_child(response, "PTZStatus")
    pan_tilt = find_path(status, "Position", "PanTilt")
    if pan_tilt is None:
      raise OnvifTransportError("GetStatus response has no pan/tilt position")
    zoom = find_path(status, "Position", "Zoom")
    return PtzStatus(
      pan=_parse_float(pan_tilt.get("x"), "pan position"),
      tilt=_parse_float(pan_tilt.get("y"), "tilt position"),
      zoom=_parse_float(zoom.get("x"), "zoom position") if zoom is not None and zoom.get("x") else None,
      space_uri=pan_tilt.get("space"),
      pan_tilt_move_status=child_text(status, "MoveStatus", "PanTilt"))

  def get_event_topics(self):
    """Leaf topic paths advertised by GetEventProperties, namespace prefixes removed."""
    if "events" not in self.xaddrs:
      return []
    response = self.call(self.xaddrs["events"], f"{_EVENTS_WSDL}/EventPortType/GetEventPropertiesRequest",
                          "<tev:GetEventProperties/>")
    topic_set = find_child(response, "TopicSet")
    topics = []

    def walk(element, path):
      for child in element:
        child_path = path + [local_name(child.tag)]
        if child.get("{http://docs.oasis-open.org/wsn/t-1}topic") == "true":
          topics.append("/".join(child_path))
        if local_name(child.tag) != "MessageDescription":
          walk(child, child_path)

    if topic_set is not None:
      walk(topic_set, [])
    return topics
