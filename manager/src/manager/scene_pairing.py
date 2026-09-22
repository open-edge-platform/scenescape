# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compact scene pairing URI and QR used by the manager UI."""

from hashlib import sha256
from io import BytesIO
from urllib.parse import urlencode

import segno


def fingerprint(name, uid):
  name_hex = sha256(str(name).encode("utf-8")).hexdigest()[:2]
  uid_hex = str(uid).replace("-", "").lower()[:6]
  return name_hex + uid_hex


def pairing_uri(host, username, name, uid):
  query = urlencode(
    {"u": host, "a": username, "s": fingerprint(name, uid)},
    safe=".:",
  )
  return f"s2://?{query}"


def matches(name, uid, key):
  return fingerprint(name, uid) == str(key).strip().lower()


def qr_svg(data, scale=8, border=4):
  qr = segno.make(data, error="m")
  buf = BytesIO()
  qr.save(buf, kind="svg", scale=scale, border=border, xmldecl=False)
  return buf.getvalue().decode("utf-8")
