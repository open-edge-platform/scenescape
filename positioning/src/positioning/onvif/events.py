# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ONVIF PullPoint event subscription (WS-BaseNotification over SOAP 1.2)."""

import time
from dataclasses import dataclass, field
from html import escape
from typing import Dict, List, Optional

from defusedxml.ElementTree import tostring

from positioning.onvif.soap import OnvifError, child_text, find_child, find_path, local_name

_EVENTS_WSDL = "http://www.onvif.org/ver10/events/wsdl"
_SUBSCRIPTION_MANAGER = "http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager"
_IS_REFERENCE_PARAMETER = '{http://www.w3.org/2005/08/addressing}IsReferenceParameter'


def normalize_topic(topic):
  """`tns1:PTZController/tnsaxis:Move/Channel_1` -> `PTZController/Move/Channel_1`."""
  return "/".join(part.rsplit(":", 1)[-1] for part in (topic or "").strip().split("/") if part)


@dataclass(frozen=True)
class EventMessage:
  topic: str
  utc_time: Optional[str]
  property_operation: Optional[str]
  source: Dict[str, str] = field(default_factory=dict)
  data: Dict[str, str] = field(default_factory=dict)


def _simple_items(element):
  items = {}
  for item in element if element is not None else ():
    if local_name(item.tag) == "SimpleItem" and item.get("Name") is not None:
      items[item.get("Name")] = item.get("Value")
  return items


def parse_notifications(response):
  messages = []
  for notification in response:
    if local_name(notification.tag) != "NotificationMessage":
      continue
    message = find_path(notification, "Message", "Message")
    if message is None:
      continue
    messages.append(EventMessage(
      topic=normalize_topic(child_text(notification, "Topic")),
      utc_time=message.get("UtcTime"),
      property_operation=message.get("PropertyOperation"),
      source=_simple_items(find_child(message, "Source")),
      data=_simple_items(find_child(message, "Data"))))
  return messages


class PullPointSubscription:
  """Creates, pulls, renews, and always unsubscribes one PullPoint subscription.

  Some devices (e.g. Axis) share one subscription endpoint and identify the
  subscription through WS-Addressing reference parameters, which are echoed on
  every follow-up request.
  """

  def __init__(self, device, termination_s=60, monotonic=time.monotonic):
    self._device = device
    self.termination_s = termination_s
    self._monotonic = monotonic
    self.address: Optional[str] = None
    self._reference_parameters: List[str] = []
    self._expires_at = 0.0

  def __enter__(self):
    self.create()
    return self

  def __exit__(self, *exc):
    self.unsubscribe()

  def create(self):
    events_url = self._device.xaddrs.get("events")
    if not events_url:
      raise OnvifError("Device does not advertise an ONVIF Events service")
    response = self._device.call(
      events_url, f"{_EVENTS_WSDL}/EventPortType/CreatePullPointSubscriptionRequest",
      "<tev:CreatePullPointSubscription><tev:InitialTerminationTime>"
      f"PT{int(self.termination_s)}S</tev:InitialTerminationTime></tev:CreatePullPointSubscription>")
    reference = find_child(response, "SubscriptionReference")
    self.address = self._device.trusted_xaddr(child_text(reference, "Address"))
    parameters = find_child(reference, "ReferenceParameters")
    self._reference_parameters = []
    for parameter in parameters if parameters is not None else ():
      parameter.set(_IS_REFERENCE_PARAMETER, "true")
      self._reference_parameters.append(tostring(parameter, encoding="unicode"))
    self._expires_at = self._monotonic() + self.termination_s

  def _header(self, action):
    return (f"<wsa:Action>{action}</wsa:Action><wsa:To>{escape(self.address)}</wsa:To>"
            + "".join(self._reference_parameters))

  def _subscription_call(self, action, body, timeout_s=None):
    return self._device.soap.call(self.address, action, body, header=self._header(action),
                                  timeout_s=timeout_s)

  def pull(self, timeout_s=1, message_limit=16):
    """Long-poll for up to `timeout_s` seconds; renews the subscription when half-expired."""
    if self._monotonic() > self._expires_at - self.termination_s / 2:
      self.renew()
    action = f"{_EVENTS_WSDL}/PullPointSubscription/PullMessagesRequest"
    response = self._subscription_call(
      action,
      f"<tev:PullMessages><tev:Timeout>PT{int(timeout_s)}S</tev:Timeout>"
      f"<tev:MessageLimit>{int(message_limit)}</tev:MessageLimit></tev:PullMessages>",
      timeout_s=timeout_s + self._device.soap.timeout_s)
    return parse_notifications(response)

  def renew(self):
    self._subscription_call(
      f"{_SUBSCRIPTION_MANAGER}/RenewRequest",
      f"<wsnt:Renew><wsnt:TerminationTime>PT{int(self.termination_s)}S</wsnt:TerminationTime></wsnt:Renew>")
    self._expires_at = self._monotonic() + self.termination_s

  def unsubscribe(self):
    """Best effort: devices cap concurrent PullPoints, so never leak one."""
    if self.address is None:
      return
    try:
      self._subscription_call(f"{_SUBSCRIPTION_MANAGER}/UnsubscribeRequest", "<wsnt:Unsubscribe/>")
    except OnvifError:
      pass
    finally:
      self.address = None
