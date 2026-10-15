# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""SOAP 1.2 transport with WS-Security UsernameToken digest authentication.

Device responses are untrusted: XML is parsed with defusedxml and response size is
bounded. Credentials never appear in URLs, exceptions, reprs, or logs.
"""

import base64
import datetime
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from html import escape

import requests
from defusedxml import ElementTree as SafeET
from requests.auth import HTTPDigestAuth

NS = {
  "s": "http://www.w3.org/2003/05/soap-envelope",
  "tt": "http://www.onvif.org/ver10/schema",
  "tds": "http://www.onvif.org/ver10/device/wsdl",
  "trt": "http://www.onvif.org/ver10/media/wsdl",
  "tptz": "http://www.onvif.org/ver20/ptz/wsdl",
  "tev": "http://www.onvif.org/ver10/events/wsdl",
  "wsnt": "http://docs.oasis-open.org/wsn/b-2",
  "wstop": "http://docs.oasis-open.org/wsn/t-1",
  "wsa": "http://www.w3.org/2005/08/addressing",
}
_WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
_WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
_PASSWORD_DIGEST = ("http://docs.oasis-open.org/wss/2004/01/"
                    "oasis-200401-wss-username-token-profile-1.0#PasswordDigest")
_BASE64_BINARY = ("http://docs.oasis-open.org/wss/2004/01/"
                  "oasis-200401-wss-soap-message-security-1.0#Base64Binary")

MAX_RESPONSE_BYTES = 1024 * 1024


class OnvifError(Exception):
  """Base class for ONVIF client failures."""


class OnvifTransportError(OnvifError):
  """Connection, timeout, HTTP, size, or XML parsing failure."""


class OnvifFault(OnvifError):
  """SOAP fault returned by the device."""

  def __init__(self, code, subcode, reason):
    self.code = code
    self.subcode = subcode
    self.reason = reason
    super().__init__(f"SOAP fault {code}/{subcode}: {reason}")

  @property
  def not_authorized(self):
    return "NotAuthorized" in (self.subcode or "") or "NotAuthorized" in (self.code or "")


@dataclass(frozen=True)
class Credentials:
  username: str
  password: str = field(repr=False)

  def __post_init__(self):
    if not isinstance(self.username, str) or not self.username:
      raise ValueError("ONVIF username must be a non-empty string")
    if not isinstance(self.password, str):
      raise ValueError("ONVIF password must be a string")


def load_credentials(path):
  """Read `{"username": ..., "password": ...}` from a mounted secret file."""
  with open(path, "r", encoding="utf-8") as secret_file:
    try:
      data = json.load(secret_file)
    except json.JSONDecodeError as error:
      raise ValueError(f"ONVIF credentials file is not valid JSON: {path}") from error
  if not isinstance(data, dict):
    raise ValueError(f"ONVIF credentials file must contain a JSON object: {path}")
  return Credentials(data.get("username"), data.get("password"))


def credentials_from_env(prefix="ONVIF"):
  username = os.environ.get(f"{prefix}_USERNAME")
  password = os.environ.get(f"{prefix}_PASSWORD")
  if not username or password is None:
    return None
  return Credentials(username, password)


def local_name(tag):
  return tag.rsplit("}", 1)[-1]


def find_child(element, name):
  """First direct child whose local name matches, ignoring vendor namespaces."""
  for child in element:
    if local_name(child.tag) == name:
      return child
  return None


def find_path(element, *names):
  for name in names:
    if element is None:
      return None
    element = find_child(element, name)
  return element


def child_text(element, *names):
  node = find_path(element, *names)
  if node is None or node.text is None:
    return None
  return node.text.strip()


def _format_created(moment):
  return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class SoapClient:
  """Synchronous SOAP client; one instance per thread (requests.Session is not shared)."""

  def __init__(self, credentials, timeout_s=1.0, verify=True, session=None,
               wall_clock=time.time):
    self._credentials = credentials
    self.timeout_s = timeout_s
    self._wall_clock = wall_clock
    self.clock_offset_s = 0.0
    self._session = session or requests.Session()
    # Camera traffic must not be routed through host HTTP proxies.
    self._session.trust_env = False
    self._session.verify = verify
    # Used only if the device answers with an HTTP Digest challenge.
    self._session.auth = HTTPDigestAuth(credentials.username, credentials.password)

  def close(self):
    self._session.close()

  def _security_header(self):
    nonce = os.urandom(16)
    created_at = datetime.datetime.fromtimestamp(
      self._wall_clock() + self.clock_offset_s, tz=datetime.timezone.utc)
    created = _format_created(created_at)
    # WS-Security UsernameToken PasswordDigest is defined as SHA-1 by the ONVIF/OASIS profile.
    digest = hashlib.sha1(  # nosec B324
      # lgtm [py/weak-sensitive-data-hashing]
      nonce + created.encode() + self._credentials.password.encode()).digest()
    return (
      f'<wsse:Security xmlns:wsse="{_WSSE}" xmlns:wsu="{_WSU}">'
      "<wsse:UsernameToken>"
      f"<wsse:Username>{escape(self._credentials.username)}</wsse:Username>"
      f'<wsse:Password Type="{_PASSWORD_DIGEST}">{base64.b64encode(digest).decode()}</wsse:Password>'
      f'<wsse:Nonce EncodingType="{_BASE64_BINARY}">{base64.b64encode(nonce).decode()}</wsse:Nonce>'
      f"<wsu:Created>{created}</wsu:Created>"
      "</wsse:UsernameToken></wsse:Security>")

  def envelope(self, body, header="", authenticate=True):
    namespaces = " ".join(f'xmlns:{prefix}="{uri}"' for prefix, uri in NS.items())
    security = self._security_header() if authenticate else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?><s:Envelope {namespaces}>'
            f"<s:Header>{security}{header}</s:Header><s:Body>{body}</s:Body></s:Envelope>")

  def call(self, url, action, body, header="", authenticate=True, timeout_s=None):
    """POST a SOAP request and return the first element inside the response Body."""
    payload = self.envelope(body, header, authenticate).encode("utf-8")
    headers = {"Content-Type": f'application/soap+xml; charset=utf-8; action="{action}"'}
    try:
      with self._session.post(url, data=payload, headers=headers, stream=True,
                              timeout=timeout_s or self.timeout_s, allow_redirects=False) as response:
        content = self._read_bounded(response)
        status_code = response.status_code
    except requests.RequestException as error:
      raise OnvifTransportError(f"{type(error).__name__} calling {action.rsplit('/', 1)[-1]}") from None
    return self._parse(content, status_code, action)

  @staticmethod
  def _read_bounded(response):
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=16384):
      total += len(chunk)
      if total > MAX_RESPONSE_BYTES:
        raise OnvifTransportError("ONVIF response exceeds size limit")
      chunks.append(chunk)
    return b"".join(chunks)

  @staticmethod
  def _parse(content, status_code, action):
    operation = action.rsplit("/", 1)[-1]
    try:
      root = SafeET.fromstring(content) if content else None
    except Exception:
      root = None
    body = find_child(root, "Body") if root is not None and local_name(root.tag) == "Envelope" else None
    if body is None:
      raise OnvifTransportError(f"HTTP {status_code} without SOAP body for {operation}")
    fault = find_child(body, "Fault")
    if fault is not None:
      raise OnvifFault(
        child_text(fault, "Code", "Value"),
        child_text(fault, "Code", "Subcode", "Value"),
        child_text(fault, "Reason", "Text"))
    if status_code >= 400:
      raise OnvifTransportError(f"HTTP {status_code} for {operation}")
    for child in body:
      return child
    raise OnvifTransportError(f"Empty SOAP body for {operation}")
