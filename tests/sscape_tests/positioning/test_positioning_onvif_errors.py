# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ONVIF security boundaries and malformed device responses without network access."""

import json
from unittest import mock

import pytest
import requests
from defusedxml import ElementTree as SafeET

from positioning.onvif import (
  Credentials, OnvifError, OnvifFault, OnvifPtzDevice, OnvifTransportError, PositionSpace,
  load_credentials)
from positioning.onvif.events import EventMessage, PullPointSubscription, parse_notifications
from positioning.onvif.soap import MAX_RESPONSE_BYTES, SoapClient, credentials_from_env


@pytest.fixture
def soap_client():
  session = mock.MagicMock()
  client = SoapClient(Credentials("test-user", "test-password"), session=session)
  yield client, session
  client.close()


@pytest.mark.parametrize("excess", [0, 1])
def test_soap_response_size_boundary(soap_client, excess):
  client, session = soap_client
  response = session.post.return_value.__enter__.return_value
  response.status_code = 200
  opening = b'<Envelope><Body><Response>'
  closing = b'</Response></Body></Envelope>'
  content = opening + b" " * (MAX_RESPONSE_BYTES - len(opening) - len(closing) + excess) + closing
  response.iter_content.return_value = (content[offset:offset + 16384]
                                        for offset in range(0, len(content), 16384))
  if excess:
    with pytest.raises(OnvifTransportError, match="exceeds size limit"):
      client.call("https://camera/ptz", "urn:test/GetStatus", "<Request/>")
  else:
    assert client.call("https://camera/ptz", "urn:test/GetStatus", "<Request/>").tag == "Response"
  response.iter_content.assert_called_once_with(chunk_size=16384)
  session.post.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("during_read", [False, True])
def test_soap_timeout_is_sanitized_and_response_is_closed(soap_client, during_read):
  client, session = soap_client
  error = requests.Timeout("private URL and test-password must not be exposed")
  if during_read:
    session.post.return_value.__enter__.return_value.iter_content.side_effect = error
  else:
    session.post.side_effect = error
  with pytest.raises(OnvifTransportError, match="^Timeout calling GetStatus$") as raised:
    client.call("https://camera/ptz", "urn:test/GetStatus", "<Request/>", timeout_s=0.25)
  assert raised.value.__suppress_context__
  assert "test-password" not in str(raised.value)
  assert session.post.call_args.kwargs["timeout"] == 0.25
  assert session.post.call_args.kwargs["allow_redirects"] is False
  assert session.trust_env is False
  assert session.verify is True
  if during_read:
    session.post.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("content,status,expected", [
  (b"<Envelope><Body><Response/></Body></Envelope>", 500, "HTTP 500 for GetStatus"),
  (b"<Envelope><Body/></Envelope>", 200, "Empty SOAP body for GetStatus"),
  (b"<Envelope/>", 200, "HTTP 200 without SOAP body for GetStatus"),
  (b"", 503, "HTTP 503 without SOAP body for GetStatus"),
  (b"<invalid", 200, "HTTP 200 without SOAP body for GetStatus"),
])
def test_soap_rejects_http_errors_and_missing_bodies(content, status, expected):
  with pytest.raises(OnvifTransportError) as raised:
    SoapClient._parse(content, status, "urn:test/GetStatus")
  assert str(raised.value) == expected


@pytest.mark.parametrize("payload", ["{", "[]", "null", '{"username": "user"}',
                                     '{"username": "", "password": "value"}',
                                     '{"username": "user", "password": 123}'])
def test_malformed_credentials_are_rejected(tmp_path, payload):
  path = tmp_path / "credentials.json"
  path.write_text(payload, encoding="utf-8")
  with pytest.raises(ValueError):
    load_credentials(path)


def test_credentials_file_round_trip_and_password_repr(tmp_path):
  path = tmp_path / "credentials.json"
  path.write_text(json.dumps({"username": "test-user", "password": "test-password"}),
                  encoding="utf-8")
  credentials = load_credentials(path)
  assert credentials == Credentials("test-user", "test-password")
  assert credentials.password not in repr(credentials)


@pytest.mark.parametrize("username,password,available", [
  (None, None, False), ("user", None, False), ("", "value", False),
  ("user", "", True), ("user", "value", True),
])
def test_credentials_from_environment(monkeypatch, username, password, available):
  for name, value in (("PROBE_USERNAME", username), ("PROBE_PASSWORD", password)):
    if value is None:
      monkeypatch.delenv(name, raising=False)
    else:
      monkeypatch.setenv(name, value)
  credentials = credentials_from_env("PROBE")
  if available:
    assert credentials == Credentials(username, password)
  else:
    assert credentials is None


@pytest.fixture
def device():
  transport = mock.Mock()
  client = OnvifPtzDevice("camera.example", 443, Credentials("user", "value"),
                          soap_client=transport, wall_clock=lambda: 0.0)
  client.xaddrs = {"ptz": "https://camera.example/ptz", "media": "https://camera.example/media"}
  client.profile_token = "profile-a"
  client.node_token = "node-a"
  return client


@pytest.mark.parametrize("utc", ["<Year>invalid</Year>", "<Year>2026</Year>"])
def test_device_rejects_malformed_clock_response(device, utc):
  device.soap.call.return_value = SafeET.fromstring(
    f"<Response><SystemDateAndTime><UTCDateTime><Date>{utc}</Date>"
    "</UTCDateTime></SystemDateAndTime></Response>")
  with pytest.raises(OnvifTransportError, match="Malformed GetSystemDateAndTime response"):
    device.sync_clock()


def test_device_missing_utc_resets_clock_offset(device):
  device.soap.clock_offset_s = 123.0
  device.soap.call.return_value = SafeET.fromstring("<Response><SystemDateAndTime/></Response>")
  assert device.sync_clock() == 0.0
  assert device.soap.clock_offset_s == 0.0
  assert device.soap.call.call_args.kwargs["authenticate"] is False


@pytest.mark.parametrize("services", ["", "<Media><XAddr>https://camera.example/media</XAddr></Media>",
                                    "<PTZ><XAddr>https://camera.example/ptz</XAddr></PTZ>"])
def test_device_rejects_missing_media_or_ptz_services(device, services):
  device.soap.call.side_effect = [
    SafeET.fromstring("<ClockResponse/>"),
    SafeET.fromstring(f"<Response><Capabilities>{services}</Capabilities></Response>"),
  ]
  with pytest.raises(OnvifTransportError, match="does not advertise ONVIF Media and PTZ"):
    device.connect()


def test_device_missing_capabilities_returns_only_device_endpoint(device):
  device.soap.call.return_value = SafeET.fromstring("<Response/>")
  assert device.get_capabilities() == {"device": device.device_url}


@pytest.mark.parametrize("position", ["", "<Position/>",
                                     '<Position><PanTilt x="invalid" y="0"/></Position>',
                                     '<Position><PanTilt x="0"/></Position>'])
def test_device_rejects_missing_or_malformed_position(device, position):
  device.soap.call.return_value = SafeET.fromstring(
    f"<Response><PTZStatus>{position}</PTZStatus></Response>")
  with pytest.raises(OnvifTransportError, match="no pan/tilt position|Malformed .* position"):
    device.get_status()


@pytest.mark.parametrize("nodes", ["", '<PTZNode token="other-a"/><PTZNode token="other-b"/>'])
def test_device_rejects_missing_or_ambiguous_nodes(device, nodes):
  device.soap.call.return_value = SafeET.fromstring(f"<Response>{nodes}</Response>")
  with pytest.raises(OnvifTransportError, match="PTZ node .* was not found"):
    device._absolute_pan_tilt_spaces()


def test_device_uses_only_advertised_node_when_token_does_not_match(device):
  device.soap.call.return_value = SafeET.fromstring(
    '<Response><PTZNode token="other"><SupportedPTZSpaces><RelativePanTiltTranslationSpace/>'
    '<AbsolutePanTiltPositionSpace><URI>urn:test:space</URI><XRange><Min>-1</Min><Max>1</Max>'
    '</XRange><YRange><Min>-2</Min><Max>2</Max></YRange></AbsolutePanTiltPositionSpace>'
    '</SupportedPTZSpaces></PTZNode></Response>')
  assert device._absolute_pan_tilt_spaces() == (PositionSpace("urn:test:space", -1, 1, -2, 2),)


def test_device_uses_single_position_space_without_uri_or_profile_default(device):
  space = PositionSpace("urn:test:space", -1, 1, -1, 1)
  device.position_spaces = (space,)
  assert device.position_space(None) is space


@pytest.mark.parametrize("repeated_failure", [False, True])
def test_device_resynchronizes_and_retries_authorization_only_once(device, repeated_failure):
  fault = OnvifFault("Sender", "NotAuthorized", "clock drift")
  response = SafeET.fromstring("<Response/>")
  device.soap.call.side_effect = [fault, fault if repeated_failure else response]
  with mock.patch.object(device, "sync_clock") as resync:
    if repeated_failure:
      with pytest.raises(OnvifFault) as raised:
        device.call("https://camera.example/ptz", "urn:test/GetStatus", "<Request/>", timeout_s=0.5)
      assert raised.value is fault
    else:
      assert device.call("https://camera.example/ptz", "urn:test/GetStatus", "<Request/>",
                          timeout_s=0.5) is response
  resync.assert_called_once_with()
  assert device.soap.call.call_args_list == [
    mock.call("https://camera.example/ptz", "urn:test/GetStatus", "<Request/>", timeout_s=0.5),
  ] * 2


def test_device_does_not_retry_unrelated_soap_fault(device):
  fault = OnvifFault("Receiver", "ActionNotSupported", "unsupported operation")
  device.soap.call.side_effect = fault
  with mock.patch.object(device, "sync_clock") as resync:
    with pytest.raises(OnvifFault) as raised:
      device.call("https://camera.example/ptz", "urn:test/GetStatus", "<Request/>")
    assert raised.value is fault
  resync.assert_not_called()
  assert device.soap.call.call_count == 1


@pytest.mark.parametrize("address", [None, "ftp://camera.example/ptz", "https://camera.example"])
def test_device_rejects_invalid_service_address(device, address):
  with pytest.raises(OnvifTransportError, match="invalid service address"):
    device.trusted_xaddr(address)


def test_https_device_rejects_same_host_transport_downgrade(device):
  with pytest.raises(OnvifTransportError, match="insecure service address"):
    device.trusted_xaddr("http://camera.example/ptz")


def test_device_rewrites_foreign_host_without_downgrading_scheme(device):
  assert device.trusted_xaddr("http://untrusted.example:8443/ptz?channel=1") == (
    "https://camera.example:8443/ptz?channel=1")


def test_device_without_events_service_returns_no_topics(device):
  assert device.get_event_topics() == []
  device.soap.call.assert_not_called()


@pytest.mark.parametrize("timestamps,expected", [
  ("", "missing lease timestamps"),
  ("<CurrentTime>2026-10-20T00:00:00Z</CurrentTime>", "missing lease timestamps"),
  ("<TerminationTime>2026-10-20T00:01:00Z</TerminationTime>", "missing lease timestamps"),
  ("<CurrentTime>invalid</CurrentTime><TerminationTime>2026-10-20T00:01:00Z</TerminationTime>",
   "invalid lease timestamps"),
  ("<CurrentTime>2026-10-20T00:00:00Z</CurrentTime><TerminationTime>invalid</TerminationTime>",
   "invalid lease timestamps"),
  ("<CurrentTime>2026-10-20T00:00:00Z</CurrentTime>"
   "<TerminationTime>2026-10-20T00:00:00Z</TerminationTime>", "expired lease"),
  ("<CurrentTime>2026-10-20T00:00:00Z</CurrentTime>"
   "<TerminationTime>2026-10-19T23:59:59Z</TerminationTime>", "expired lease"),
])
def test_subscription_rejects_invalid_lease_without_replacing_previous_deadline(
    device, timestamps, expected):
  subscription = PullPointSubscription(device, monotonic=lambda: 10.0)
  subscription.address = "https://camera.example/events/subscription"
  device.soap.call.return_value = SafeET.fromstring(f"<RenewResponse>{timestamps}</RenewResponse>")
  with pytest.raises(OnvifError, match=expected):
    subscription.renew()
  assert subscription._expires_at == 0.0
  assert subscription._lease_s == 60


@pytest.mark.parametrize("current,termination", [
  ("2026-10-20T00:00:00Z", "2026-10-20T00:00:20Z"),
  ("2026-10-20T00:00:00", "2026-10-20T00:00:20"),
  ("2026-10-20T02:00:00+02:00", "2026-10-20T00:00:20Z"),
])
def test_subscription_uses_granted_lease_duration(device, current, termination):
  subscription = PullPointSubscription(device, monotonic=lambda: 10.0)
  subscription.address = "https://camera.example/events/subscription"
  device.soap.call.return_value = SafeET.fromstring(
    f"<RenewResponse><CurrentTime>{current}</CurrentTime>"
    f"<TerminationTime>{termination}</TerminationTime></RenewResponse>")
  subscription.renew()
  assert subscription._lease_s == 20.0
  assert subscription._expires_at == 30.0


def test_subscription_requires_events_service(device):
  with pytest.raises(OnvifError, match="does not advertise an ONVIF Events service"):
    PullPointSubscription(device).create()
  device.soap.call.assert_not_called()


def test_subscription_unsubscribe_without_address_is_noop(device):
  subscription = PullPointSubscription(device)
  subscription.unsubscribe()
  device.soap.call.assert_not_called()


def test_subscription_clears_address_even_when_unsubscribe_fails(device):
  subscription = PullPointSubscription(device)
  subscription.address = "https://camera.example/events/subscription"
  device.soap.call.side_effect = OnvifError("subscription already expired")
  subscription.unsubscribe()
  assert subscription.address is None
  assert device.soap.call.call_count == 1
  subscription.unsubscribe()
  assert device.soap.call.call_count == 1


def test_malformed_notifications_do_not_hide_valid_messages():
  response = SafeET.fromstring(
    '<PullMessagesResponse><Unrelated/><NotificationMessage/>'
    '<NotificationMessage><Message/></NotificationMessage>'
    '<NotificationMessage><Topic>tns:PTZController/tns:Move</Topic><Message>'
    '<Message UtcTime="2026-10-20T00:00:00Z" PropertyOperation="Changed">'
    '<Source><SimpleItem/><ElementItem Name="ignored" Value="x"/>'
    '<SimpleItem Name="channel" Value="1"/></Source>'
    '<Data><SimpleItem/><SimpleItem Name="is_moving" Value="1"/></Data>'
    '</Message></Message></NotificationMessage></PullMessagesResponse>')
  assert parse_notifications(response) == [EventMessage(
    topic="PTZController/Move", utc_time="2026-10-20T00:00:00Z", property_operation="Changed",
    source={"channel": "1"}, data={"is_moving": "1"})]


def test_notification_without_optional_fields_has_empty_metadata():
  response = SafeET.fromstring(
    "<PullMessagesResponse><NotificationMessage><Message><Message/>"
    "</Message></NotificationMessage></PullMessagesResponse>")
  assert parse_notifications(response) == [EventMessage("", None, None)]
