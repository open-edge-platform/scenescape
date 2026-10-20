# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""In-process fake ONVIF PTZ camera (HTTP/SOAP 1.2) for poller tests."""

import base64
import datetime
import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from defusedxml import ElementTree as SafeET

GENERIC_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"
DEGREES_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/SphericalPositionSpaceDegrees"
AXIS_EVENT_NS = "http://www.axis.com/2009/event"

_ENVELOPE = (
  '<?xml version="1.0" encoding="UTF-8"?>'
  '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"'
  ' xmlns:tt="http://www.onvif.org/ver10/schema"'
  ' xmlns:tds="http://www.onvif.org/ver10/device/wsdl"'
  ' xmlns:trt="http://www.onvif.org/ver10/media/wsdl"'
  ' xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl"'
  ' xmlns:tev="http://www.onvif.org/ver10/events/wsdl"'
  ' xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"'
  ' xmlns:wstop="http://docs.oasis-open.org/wsn/t-1"'
  ' xmlns:wsa5="http://www.w3.org/2005/08/addressing"'
  ' xmlns:tns1="http://www.onvif.org/ver10/topics"'
  f' xmlns:tnsaxis="{AXIS_EVENT_NS}">'
  "<env:Body>{body}</env:Body></env:Envelope>")


def _fault(subcode, reason):
  return _ENVELOPE.format(body=(
    "<env:Fault><env:Code><env:Value>env:Sender</env:Value>"
    f"<env:Subcode><env:Value>ter:{subcode}</env:Value></env:Subcode></env:Code>"
    f'<env:Reason><env:Text xml:lang="en">{reason}</env:Text></env:Reason></env:Fault>'))


def _local(tag):
  return tag.rsplit("}", 1)[-1]


class FakeOnvifCamera:
  """Configurable fake device; set attributes to change state between calls."""

  def __init__(self, username="operator", password="fake-secret-Pa55", advertise_host="10.255.0.1",
               clock_offset_s=0.0, require_reference_parameters=False, with_events=True,
               subscription_lease_s=60):
    self.username = username
    self.password = password
    self.advertise_host = advertise_host
    self.clock_offset_s = clock_offset_s
    self.require_reference_parameters = require_reference_parameters
    self.with_events = with_events
    self.subscription_lease_s = subscription_lease_s
    self.pan = 0.25
    self.tilt = -0.5
    self.zoom = 0.0
    self.move_status = "IDLE"
    self.status_space = GENERIC_SPACE
    self.status_failures = 0
    self.status_delay_s = 0.0
    self.raw_status_response = None
    self.events = []
    self.operations = []
    self.unsubscribed = 0
    self._lock = threading.Lock()
    camera = self

    class Handler(BaseHTTPRequestHandler):
      def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        status, response = camera.handle(body)
        payload = response.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/soap+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

      def log_message(self, *args):
        pass

    self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    self.port = self.server.server_address[1]
    self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
    self._thread.start()

  def close(self):
    self.server.shutdown()
    self.server.server_close()

  def push_move_event(self, is_moving, operation="Changed"):
    with self._lock:
      self.events.append((is_moving, operation))

  def _device_now(self):
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=self.clock_offset_s)

  def _authorized(self, header):
    token = None
    for element in header.iter() if header is not None else ():
      if _local(element.tag) == "UsernameToken":
        token = {_local(child.tag): (child.text or "") for child in element}
    if not token or token.get("Username") != self.username:
      return False
    nonce = base64.b64decode(token.get("Nonce", ""))
    # Mirrors WS-Security verification; this is not password-hash storage.
    # codeql[py/weak-sensitive-data-hashing]
    expected = base64.b64encode(hashlib.sha1( # nosec B324
      nonce + token.get("Created", "").encode() + self.password.encode()
    ).digest()).decode()
    if token.get("Password") != expected:
      return False
    created = datetime.datetime.strptime(token["Created"], "%Y-%m-%dT%H:%M:%SZ").replace(
      tzinfo=datetime.timezone.utc)
    return abs((created - self._device_now()).total_seconds()) < 5

  def _xaddr(self, path):
    return f"http://{self.advertise_host}:{self.port}{path}"

  def handle(self, raw):
    root = SafeET.fromstring(raw)
    header = next((child for child in root if _local(child.tag) == "Header"), None)
    body = next(child for child in root if _local(child.tag) == "Body")
    request = next(iter(body))
    operation = _local(request.tag)
    with self._lock:
      self.operations.append((operation, header))
    if operation == "GetSystemDateAndTime":
      now = self._device_now()
      return 200, _ENVELOPE.format(body=(
        "<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime><tt:UTCDateTime>"
        f"<tt:Time><tt:Hour>{now.hour}</tt:Hour><tt:Minute>{now.minute}</tt:Minute>"
        f"<tt:Second>{now.second}</tt:Second></tt:Time>"
        f"<tt:Date><tt:Year>{now.year}</tt:Year><tt:Month>{now.month}</tt:Month>"
        f"<tt:Day>{now.day}</tt:Day></tt:Date>"
        "</tt:UTCDateTime></tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse>"))
    if not self._authorized(header):
      return 400, _fault("NotAuthorized", "Sender not authorized")
    handler = getattr(self, f"_op_{operation}", None)
    if handler is None:
      return 400, _fault("ActionNotSupported", operation)
    return handler(request, header)

  def _op_GetCapabilities(self, request, header):
    events = (f"<tt:Events><tt:XAddr>{self._xaddr('/onvif/event_service')}</tt:XAddr></tt:Events>"
              if self.with_events else "")
    return 200, _ENVELOPE.format(body=(
      "<tds:GetCapabilitiesResponse><tds:Capabilities>"
      f"<tt:Device><tt:XAddr>{self._xaddr('/onvif/device_service')}</tt:XAddr></tt:Device>"
      f"{events}<tt:Media><tt:XAddr>{self._xaddr('/onvif/media_service')}</tt:XAddr></tt:Media>"
      f"<tt:PTZ><tt:XAddr>{self._xaddr('/onvif/ptz_service')}</tt:XAddr></tt:PTZ>"
      "</tds:Capabilities></tds:GetCapabilitiesResponse>"))

  def _op_GetDeviceInformation(self, request, header):
    return 200, _ENVELOPE.format(body=(
      "<tds:GetDeviceInformationResponse><tds:Manufacturer>Fake</tds:Manufacturer>"
      "<tds:Model>PTZ-1</tds:Model><tds:FirmwareVersion>1.0</tds:FirmwareVersion>"
      "<tds:SerialNumber>0</tds:SerialNumber><tds:HardwareId>0</tds:HardwareId>"
      "</tds:GetDeviceInformationResponse>"))

  def _op_GetProfiles(self, request, header):
    return 200, _ENVELOPE.format(body=(
      '<trt:GetProfilesResponse><trt:Profiles token="profile_static" fixed="true">'
      "<tt:Name>static</tt:Name></trt:Profiles>"
      '<trt:Profiles token="profile_ptz" fixed="true"><tt:Name>ptz</tt:Name>'
      '<tt:PTZConfiguration token="ptzcfg"><tt:Name>ptz</tt:Name><tt:NodeToken>node0</tt:NodeToken>'
      f"<tt:DefaultAbsolutePantTiltPositionSpace>{GENERIC_SPACE}</tt:DefaultAbsolutePantTiltPositionSpace>"
      "</tt:PTZConfiguration></trt:Profiles></trt:GetProfilesResponse>"))

  def _op_GetNodes(self, request, header):
    def space(uri, x_min, x_max, y_min, y_max):
      return ("<tt:AbsolutePanTiltPositionSpace>"
              f"<tt:URI>{uri}</tt:URI>"
              f"<tt:XRange><tt:Min>{x_min}</tt:Min><tt:Max>{x_max}</tt:Max></tt:XRange>"
              f"<tt:YRange><tt:Min>{y_min}</tt:Min><tt:Max>{y_max}</tt:Max></tt:YRange>"
              "</tt:AbsolutePanTiltPositionSpace>")
    return 200, _ENVELOPE.format(body=(
      '<tptz:GetNodesResponse><tptz:PTZNode token="node0"><tt:Name>node0</tt:Name>'
      "<tt:SupportedPTZSpaces>"
      f"{space(GENERIC_SPACE, -1, 1, -1, 1)}{space(DEGREES_SPACE, -180, 180, -90, 90)}"
      "</tt:SupportedPTZSpaces></tptz:PTZNode></tptz:GetNodesResponse>"))

  def _op_GetStatus(self, request, header):
    if self.status_delay_s:
      time.sleep(self.status_delay_s)
    with self._lock:
      if self.status_failures:
        self.status_failures -= 1
        return 500, "<html>busy</html>"
    if self.raw_status_response is not None:
      return 200, self.raw_status_response
    space = f' space="{self.status_space}"' if self.status_space else ""
    return 200, _ENVELOPE.format(body=(
      "<tptz:GetStatusResponse><tptz:PTZStatus><tt:Position>"
      f'<tt:PanTilt x="{self.pan}" y="{self.tilt}"{space}/><tt:Zoom x="{self.zoom}"/></tt:Position>'
      f"<tt:MoveStatus><tt:PanTilt>{self.move_status}</tt:PanTilt></tt:MoveStatus>"
      f"<tt:UtcTime>{self._device_now().strftime('%Y-%m-%dT%H:%M:%SZ')}</tt:UtcTime>"
      "</tptz:PTZStatus></tptz:GetStatusResponse>"))

  def _op_GetEventProperties(self, request, header):
    return 200, _ENVELOPE.format(body=(
      "<tev:GetEventPropertiesResponse><wstop:TopicSet>"
      '<tns1:PTZController><tnsaxis:Move><Channel_1 wstop:topic="true">'
      '<tt:MessageDescription IsProperty="true"/></Channel_1></tnsaxis:Move>'
      "</tns1:PTZController></wstop:TopicSet></tev:GetEventPropertiesResponse>"))

  def _has_reference_parameter(self, header):
    for element in header.iter() if header is not None else ():
      if element.tag == f"{{{AXIS_EVENT_NS}}}SubscriptionId" and element.text == "7":
        return True
    return False

  def _subscription_lease_xml(self):
    current = self._device_now()
    termination = current + datetime.timedelta(seconds=self.subscription_lease_s)
    return (f"<tev:CurrentTime>{current.strftime('%Y-%m-%dT%H:%M:%SZ')}</tev:CurrentTime>"
            f"<tev:TerminationTime>{termination.strftime('%Y-%m-%dT%H:%M:%SZ')}</tev:TerminationTime>")

  def _op_CreatePullPointSubscription(self, request, header):
    return 200, _ENVELOPE.format(body=(
      "<tev:CreatePullPointSubscriptionResponse>"
      f"{self._subscription_lease_xml()}<tev:SubscriptionReference>"
      f"<wsa5:Address>{self._xaddr('/onvif/services')}</wsa5:Address>"
      "<wsa5:ReferenceParameters><tnsaxis:SubscriptionId>7</tnsaxis:SubscriptionId>"
      "</wsa5:ReferenceParameters></tev:SubscriptionReference>"
      "</tev:CreatePullPointSubscriptionResponse>"))

  def _check_subscription(self, header):
    if self.require_reference_parameters and not self._has_reference_parameter(header):
      return 400, _fault("InvalidArgs", "Missing subscription reference")
    return None

  def _op_PullMessages(self, request, header):
    error = self._check_subscription(header)
    if error:
      return error
    with self._lock:
      events, self.events = self.events, []
    if not events:
      time.sleep(0.05)
    utc = self._device_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    messages = "".join(
      "<wsnt:NotificationMessage>"
      '<wsnt:Topic Dialect="http://docs.oasis-open.org/wsn/t-1/TopicExpression/Simple">'
      "tns1:PTZController/tnsaxis:Move/Channel_1</wsnt:Topic><wsnt:Message>"
      f'<tt:Message UtcTime="{utc}" PropertyOperation="{operation}">'
      '<tt:Source><tt:SimpleItem Name="PTZConfigurationToken" Value="1"/></tt:Source>'
      f'<tt:Data><tt:SimpleItem Name="is_moving" Value="{int(moving)}"/></tt:Data>'
      "</tt:Message></wsnt:Message></wsnt:NotificationMessage>"
      for moving, operation in events)
    return 200, _ENVELOPE.format(body=(
      f"<tev:PullMessagesResponse><tev:CurrentTime>{utc}</tev:CurrentTime>"
      f"<tev:TerminationTime>{utc}</tev:TerminationTime>{messages}</tev:PullMessagesResponse>"))

  def _op_Renew(self, request, header):
    error = self._check_subscription(header)
    if error:
      return error
    return 200, _ENVELOPE.format(body=(
      f"<wsnt:RenewResponse>{self._subscription_lease_xml()}</wsnt:RenewResponse>"))

  def _op_Unsubscribe(self, request, header):
    error = self._check_subscription(header)
    if error:
      return error
    with self._lock:
      self.unsubscribed += 1
    return 200, _ENVELOPE.format(body="<wsnt:UnsubscribeResponse/>")
