#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Targeted multipart upload fuzzing for the Mapping POST /reconstruction endpoint.

RESTler cannot generate multipart/form-data bodies, so upload parsing (image decoding, video
handling through ffmpeg, form fields, size limits) is exercised here. Only the standard library is
used so the script runs inside the RESTler image.

Commands:
  seed  Print a real reconstruction request_id (for the RESTler status endpoint grammar).
  fuzz  Send malformed uploads, check the service stays healthy, and write a JSON report.
"""

import argparse
import http.client
import itertools
import json
import random
import re
import socket
import ssl
import struct
import sys
import time
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_HOST = "web.scenescape.intel.com"
DEFAULT_BASE_PATH = "/api/v1/mapping"
RANDOM_SEED = 12345  # same seed as the RESTler campaign
BOUNDARY = "----mappingfuzz7d1c"
MULTIPART_TYPE = f"multipart/form-data; boundary={BOUNDARY}"
REQUEST_TIMEOUT_S = 300
POLL_TIMEOUT_S = 20
POLL_INTERVAL_S = 0.5
REQUEST_ID_RE = re.compile(r"[0-9a-f]{32}")

# Limits enforced by mapping/src/api_service_base.py
MAX_IMAGES = 50
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_REQUEST_BYTES = 100 * 1024 * 1024

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
NOT_AN_IMAGE = b"not an image"


class _PinnedConnection(http.client.HTTPSConnection):
  """HTTPS connection to a fixed IP that validates the certificate against the host name."""

  def __init__(self, host, target_ip, tls_context, timeout):
    super().__init__(host, timeout=timeout, context=tls_context)
    self._target_ip = target_ip
    self._tls_context = tls_context

  def connect(self):
    sock = socket.create_connection((self._target_ip, self.port), self.timeout)
    self.sock = self._tls_context.wrap_socket(sock, server_hostname=self.host)


class ApiClient:
  """Minimal client for the Mapping API behind the reverse proxy."""

  def __init__(self, target_ip, host, base_path, cafile=None):
    self.target_ip = target_ip
    self.host = host
    self.base_path = base_path
    self.tls_context = ssl.create_default_context(cafile=cafile)

  def request(self, method, path, body=None, content_type=None):
    """Send one request and return (status, response body bytes)."""
    conn = _PinnedConnection(self.host, self.target_ip, self.tls_context, REQUEST_TIMEOUT_S)
    headers = {"Accept": "application/json"}
    if content_type:
      headers["Content-Type"] = content_type
    try:
      conn.request(method, self.base_path + path, body=body, headers=headers)
      response = conn.getresponse()
      return response.status, response.read()
    finally:
      conn.close()


@dataclass
class Part:
  """One multipart form part."""
  name: str
  data: bytes
  filename: str | None = None
  content_type: str | None = None


@dataclass
class Case:
  """One request to send. An empty `expect` accepts any non-5xx status."""
  name: str
  parts: list = field(default_factory=list)
  raw_body: bytes | None = None
  content_type: str = MULTIPART_TYPE
  expect: frozenset = frozenset()


@dataclass
class Result:
  """Outcome of one case; `problem` is set when it counts as a finding."""
  name: str
  status: int | None
  job_state: str | None
  problem: str | None
  elapsed_s: float


def encode_multipart(parts):
  """Encode parts without escaping so cases can carry hostile names and values."""
  chunks = []
  for part in parts:
    disposition = f'form-data; name="{part.name}"'
    if part.filename is not None:
      disposition += f'; filename="{part.filename}"'
    header = f"--{BOUNDARY}\r\nContent-Disposition: {disposition}\r\n"
    if part.content_type:
      header += f"Content-Type: {part.content_type}\r\n"
    chunks.append(header.encode("utf-8") + b"\r\n" + part.data + b"\r\n")
  chunks.append(f"--{BOUNDARY}--\r\n".encode("utf-8"))
  return b"".join(chunks)


def _image(data, filename="frame.png", content_type="image/png"):
  return Part("images", data, filename, content_type)


def _video(data, filename="clip.mp4"):
  return Part("video", data, filename, "video/mp4")


def _field(name, value):
  return Part(name, value.encode("utf-8"))


def _case(name, *parts, expect=()):
  return Case(name, list(parts), expect=frozenset(expect))


def _png_chunk(kind, payload):
  crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
  return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _png_with_dimensions(width, height):
  header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
  return (PNG_SIGNATURE + _png_chunk(b"IHDR", header)
          + _png_chunk(b"IDAT", zlib.compress(b"")) + _png_chunk(b"IEND", b""))


def _image_cases(rng):
  jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
  return [
      _case("image_empty_file", _image(b""), expect={400}),
      _case("image_plain_text", _image(NOT_AN_IMAGE)),
      _case("image_truncated_png", _image(PNG_SIGNATURE + b"\x00\x00")),
      _case("image_png_huge_dimensions", _image(_png_with_dimensions(65535, 65535))),
      _case("image_truncated_jpeg",
            _image(jpeg_header + rng.randbytes(64), "frame.jpg", "image/jpeg")),
      _case("image_gif_huge_dimensions",
            _image(b"GIF89a\xff\xff\xff\xff\x00\x00\x00;", "frame.gif", "image/gif")),
      _case("image_random_bytes", _image(rng.randbytes(4096))),
      _case("image_content_type_mismatch", _image(PNG_SIGNATURE, content_type="text/html")),
      _case("image_two_corrupt_with_ids", _image(NOT_AN_IMAGE), _image(NOT_AN_IMAGE),
            _field("camera_ids", "cam-1"), _field("camera_ids", "cam-2")),
  ]


def _filename_cases():
  filenames = {
      "traversal": "../../../../etc/passwd",
      "null_byte": "frame\x00.png",
      "very_long": "a" * 10000 + ".png",
      "unicode": "frame-\u00e9\uff21.png",
      "embedded_quote": 'a".png',
      "empty": "",
  }
  return [_case(f"image_filename_{label}", _image(NOT_AN_IMAGE, filename=value))
          for label, value in filenames.items()]


def _field_cases():
  image = _image(NOT_AN_IMAGE)
  invalid_camera_ids = {
      "traversal": "../x",
      "too_long": "a" * 65,
      "newline": "cam\nid",
      "trailing_newline": "cam-1\n",
      "unicode": "cam-\u00e9",
      "space": "cam 1",
      "semicolon": "cam;1",
  }
  cases = [_case(f"camera_id_{label}", image, _field("camera_ids", value), expect={400})
           for label, value in invalid_camera_ids.items()]
  cases += [
      _case("camera_locations_malformed_json", image, _field("camera_locations", "{not json")),
      _case("camera_locations_deep_nesting", image,
            _field("camera_locations", "[" * 100000 + "]" * 100000)),
      _case("camera_locations_huge_integer", image, _field("camera_locations", "9" * 100000)),
      _case("output_format_invalid", image, _field("output_format", "exe"), expect={400}),
      _case("output_format_oversized", image, _field("output_format", "A" * 1000000),
            expect={400, 413}),
      _case("mesh_type_invalid", image, _field("mesh_type", "../../x"), expect={400}),
      _case("use_keyframes_garbage", image, _field("use_keyframes", "\x00\xff")),
      _case("output_format_duplicated", image, _field("output_format", "json"),
            _field("output_format", "glb")),
      _case("unknown_field", image, _field("unexpected", "1")),
  ]
  return cases


def _video_cases(rng):
  hls_playlist = b"#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:1.0,\nfile:///etc/hostname\n#EXT-X-ENDLIST\n"
  return [
      _case("video_random_bytes", _video(rng.randbytes(2048))),
      _case("video_empty", _video(b"")),
      _case("video_truncated_mp4", _video(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")),
      _case("video_hls_playlist_local_file", _video(hls_playlist)),
      _case("video_concat_script_local_file",
            _video(b"ffconcat version 1.0\nfile '/etc/hostname'\n")),
      _case("video_filename_traversal", _video(rng.randbytes(256), "../../../tmp/clip.mp4")),
  ]


def _framing_cases():
  closing = f"--{BOUNDARY}--\r\n".encode("utf-8")
  base = encode_multipart([_image(NOT_AN_IMAGE), _field("output_format", "json")])
  return [
      Case("framing_missing_terminator", raw_body=base[:-len(closing)]),
      Case("framing_truncated_mid_part", raw_body=base[:len(base) // 2]),
      Case("framing_wrong_boundary", raw_body=base,
           content_type="multipart/form-data; boundary=other"),
      Case("framing_no_boundary", raw_body=base, content_type="multipart/form-data"),
      Case("framing_json_content_type", raw_body=b'{"images": []}',
           content_type="application/json"),
      Case("framing_empty_body", raw_body=b""),
      Case("framing_many_form_parts", [_field(f"f{i}", "x") for i in range(5000)]),
  ]


def _size_cases():
  """Yield oversized uploads lazily so only one large body is in memory at a time."""
  yield _case("size_image_over_limit", _image(PNG_SIGNATURE + b"\x00" * MAX_IMAGE_BYTES),
              expect={400, 413})
  yield _case("size_too_many_images", *[_image(NOT_AN_IMAGE) for _ in range(MAX_IMAGES + 1)],
              expect={400})
  yield _case("size_video_over_limit", _video(b"\x00" * (MAX_VIDEO_BYTES + 1)),
              expect={400, 413})
  yield _case("size_request_over_limit", _video(b"\x00" * (MAX_REQUEST_BYTES + 1)),
              expect={413})


def build_cases(skip_large):
  """Return all cases in a fixed order; oversized uploads are generated lazily."""
  rng = random.Random(RANDOM_SEED)
  cases = itertools.chain(_image_cases(rng), _filename_cases(), _field_cases(),
                          _video_cases(rng), _framing_cases())
  if skip_large:
    return cases
  return itertools.chain(cases, _size_cases())


def _parse_json(body):
  try:
    data = json.loads(body)
  except ValueError:
    return {}
  return data if isinstance(data, dict) else {}


def _valid_request_id(value):
  return isinstance(value, str) and REQUEST_ID_RE.fullmatch(value) is not None


def _wait_for_job(client, response_body):
  """Poll an accepted job; return its final state, or a marker if it cannot be followed."""
  request_id = _parse_json(response_body).get("request_id")
  if not _valid_request_id(request_id):
    return "no-request-id"
  deadline = time.monotonic() + POLL_TIMEOUT_S
  state = "processing"
  while state == "processing" and time.monotonic() < deadline:
    time.sleep(POLL_INTERVAL_S)
    try:
      poll_status, reply = client.request("GET", f"/reconstruction/status/{request_id}")
    except (OSError, http.client.HTTPException):
      return "status-unreachable"
    if poll_status != 200:
      return f"status-http-{poll_status}"
    state = _parse_json(reply).get("state", "unknown")
  return state


def _classify(case, status, job_state):
  if status >= 500:
    return f"server error {status}"
  if case.expect and status not in case.expect:
    return f"expected status in {sorted(case.expect)}, got {status}"
  if job_state == "complete":
    return "job built from invalid media completed successfully"
  if status == 200 and job_state != "failed":
    return f"could not confirm rejection of invalid media: {job_state}"
  return None


def run_case(client, case):
  """Send one case and classify the outcome."""
  body = case.raw_body if case.raw_body is not None else encode_multipart(case.parts)
  started = time.monotonic()
  try:
    status, response = client.request("POST", "/reconstruction", body, case.content_type)
  except (OSError, http.client.HTTPException) as exc:
    return Result(case.name, None, None, f"transport error: {exc!r}", time.monotonic() - started)
  job_state = _wait_for_job(client, response) if status == 200 else None
  return Result(case.name, status, job_state, _classify(case, status, job_state),
                time.monotonic() - started)


def service_healthy(client):
  """Return True when /health answers 200."""
  try:
    status, _ = client.request("GET", "/health")
  except (OSError, http.client.HTTPException):
    return False
  return status == 200


def _format_result(result):
  label = "FAIL" if result.problem else "ok  "
  return f"{label} {result.name}: status={result.status} job={result.job_state} " \
         f"{result.problem or ''}".rstrip()


def run_campaign(client, cases):
  """Run every case, stopping early if the service stops answering health checks."""
  results = []
  for case in cases:
    result = run_case(client, case)
    results.append(result)
    print(_format_result(result), flush=True)
    if not service_healthy(client):
      results.append(Result(f"health_after_{case.name}", None, None,
                            "service unhealthy after this case; campaign aborted", 0.0))
      break
  return results


def write_report(output_dir, results):
  """Write the JSON report and return its path."""
  output_dir.mkdir(parents=True, exist_ok=True)
  report = {
      "cases": [asdict(result) for result in results],
      "findings": [asdict(result) for result in results if result.problem],
  }
  path = output_dir / "upload_fuzzing_report.json"
  path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
  return path


def seed_request_id(client):
  """Register a job without media and return its request_id.

  The service records a status before validating input, so a request without files is
  rejected with 400 but its request_id is still queryable.
  """
  body = encode_multipart([_field("output_format", "glb")])
  status, response = client.request("POST", "/reconstruction", body, MULTIPART_TYPE)
  request_id = _parse_json(response).get("request_id")
  if status != 400 or not _valid_request_id(request_id):
    raise SystemExit(f"could not obtain a request_id from the mapping service (status {status})")
  return request_id


def parse_args(argv):
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("command", choices=("seed", "fuzz"))
  parser.add_argument("--target-ip", required=True, help="IP address of the instance under test")
  parser.add_argument("--host", default=DEFAULT_HOST, help="host name used for TLS and Host header")
  parser.add_argument("--base-path", default=DEFAULT_BASE_PATH)
  parser.add_argument("--cafile", help="CA bundle; defaults to the system trust store")
  parser.add_argument("--output-dir", type=Path, help="report directory (fuzz only)")
  parser.add_argument("--skip-large", action="store_true",
                      help="skip the oversized uploads (about 170 MB of traffic)")
  args = parser.parse_args(argv)
  if args.command == "fuzz" and args.output_dir is None:
    parser.error("fuzz requires --output-dir")
  return args


def main(argv=None):
  args = parse_args(argv)
  client = ApiClient(args.target_ip, args.host, args.base_path, args.cafile)
  if args.command == "seed":
    print(seed_request_id(client))
    return 0
  results = run_campaign(client, build_cases(args.skip_large))
  report_path = write_report(args.output_dir, results)
  findings = [result for result in results if result.problem]
  print(f"{len(results)} cases, {len(findings)} finding(s); report: {report_path}")
  return 1 if findings else 0


if __name__ == "__main__":
  sys.exit(main())
