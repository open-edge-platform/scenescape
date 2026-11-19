# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Isolated tests for the ONVIF onboarding probe and its sample statistics."""

import json
from types import SimpleNamespace
from unittest import mock

import pytest

from positioning.onvif import OnvifError
from positioning.onvif import probe
from positioning.v1 import ptz_pb2


def sample(sequence=1, moving=False):
  message = ptz_pb2.PTZSample(
    camera_id="probe", adapter_instance_id="instance-a", sequence=sequence,
    timestamp_uncertainty_ns=sequence * 1_000_000,
    reported_move_status=(ptz_pb2.REPORTED_MOVE_STATUS_MOVING if moving
                          else ptz_pb2.REPORTED_MOVE_STATUS_IDLE))
  message.measured_at.FromNanoseconds(sequence * 200_000_000)
  message.position.pan = sequence * 0.1
  message.position.tilt = -sequence * 0.1
  message.position.position_space_uri = "urn:test:space"
  message.position.pan_min = message.position.tilt_min = -1
  message.position.pan_max = message.position.tilt_max = 1
  return message


@pytest.mark.parametrize("echo", [False, True])
def test_collecting_sink_acknowledges_and_optionally_prints_sample(echo, capsys):
  sink = probe._CollectingSink(echo)
  message = sample(7)
  ack = sink.submit_ptz_sample(message)
  assert sink.samples == [message]
  assert ack.result == ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED
  assert ack.accepted_sequence == 7
  output = capsys.readouterr()
  assert output.err == ""
  if echo:
    payload = json.loads(output.out)
    assert payload["camera_id"] == "probe"
    assert payload["sequence"] == "7"
    assert payload["position"]["position_space_uri"] == "urn:test:space"
  else:
    assert output.out == ""


def test_summary_without_samples():
  assert probe.summarize([], 2.0, 0) == {"samples": 0}


def test_summary_of_single_sample_has_no_intervals():
  summary = probe.summarize([sample()], 2.0, 0)
  assert summary["samples"] == 1
  assert summary["achieved_rate_hz"] == 0.5
  assert summary["interval_s"] is None
  assert summary["uncertainty_ms"] == {"median": 1.0, "p95": 1.0, "max": 1.0}


def test_summary_reports_timing_ranges_and_move_counts():
  summary = probe.summarize([sample(1), sample(2, moving=True), sample(3)], 0.6, 2)
  assert summary == {
    "samples": 3,
    "achieved_rate_hz": 5.0,
    "overrun_ticks": 2,
    "interval_s": {"median": 0.2, "max": 0.2},
    "uncertainty_ms": {"median": 2.0, "p95": 3.0, "max": 3.0},
    "pan": pytest.approx([0.1, 0.3]),
    "tilt": pytest.approx([-0.3, -0.1]),
    "position_space": {"uri": "urn:test:space", "pan": [-1.0, 1.0], "tilt": [-1.0, 1.0]},
    "reported_move_status": {"REPORTED_MOVE_STATUS_IDLE": 2, "REPORTED_MOVE_STATUS_MOVING": 1},
    "adapter_instance_id": "instance-a",
  }


@pytest.mark.parametrize("arguments", [[], ["--host", "camera", "--scheme", "ftp"],
                                     ["--host", "camera", "--move-status", "invalid"]])
def test_parser_rejects_missing_host_or_invalid_choices(arguments, capsys):
  with pytest.raises(SystemExit) as raised:
    probe.build_argparser().parse_args(arguments)
  assert raised.value.code == 2
  assert "error:" in capsys.readouterr().err


@pytest.fixture
def runtime(monkeypatch):
  device = mock.Mock()
  device.get_device_information.return_value = SimpleNamespace(
    manufacturer="Test", model="PTZ", firmware_version="1")
  device.soap.clock_offset_s = 0.1254
  device.xaddrs = {"ptz": "https://camera/ptz", "media": "https://camera/media"}
  device.profile_token = "profile-a"
  device.node_token = "node-a"
  device.default_space_uri = "urn:test:space"
  device.position_spaces = [SimpleNamespace(
    uri="urn:test:space", pan_min=-1, pan_max=1, tilt_min=-1, tilt_max=1)]
  device.get_event_topics.return_value = ["PTZController/Move"]
  env_credentials = mock.Mock(return_value=object())
  file_credentials = mock.Mock(return_value=object())
  device_factory = mock.Mock(return_value=device)
  monitor_factory = mock.Mock()
  stop = mock.Mock()
  workers = []
  settings = SimpleNamespace(emit_sample=True)

  def make_poller(source_id, factory, sink, interval, mode, monitor):
    poller = mock.Mock(overruns=0)
    poller.run.side_effect = lambda stop_event: (
      sink.submit_ptz_sample(sample()) if settings.emit_sample else None)
    return poller

  def make_worker(target, args, daemon):
    worker = mock.Mock()
    worker.start.side_effect = lambda: target(*args)
    workers.append(worker)
    return worker

  poller_factory = mock.Mock(side_effect=make_poller)
  monkeypatch.setattr(probe, "credentials_from_env", env_credentials)
  monkeypatch.setattr(probe, "load_credentials", file_credentials)
  monkeypatch.setattr(probe, "OnvifPtzDevice", device_factory)
  monkeypatch.setattr(probe, "MoveEventMonitor", monitor_factory)
  monkeypatch.setattr(probe, "PTZPoller", poller_factory)
  monkeypatch.setattr(probe, "threading", SimpleNamespace(
    Event=mock.Mock(return_value=stop), Thread=mock.Mock(side_effect=make_worker)))
  monkeypatch.setattr(probe, "time", SimpleNamespace(monotonic=mock.Mock(side_effect=[10.0, 12.0])))
  monkeypatch.setattr(probe, "logging", mock.Mock())
  return SimpleNamespace(
    device=device, device_factory=device_factory, env_credentials=env_credentials,
    file_credentials=file_credentials, monitor_factory=monitor_factory,
    poller_factory=poller_factory, workers=workers, stop=stop, settings=settings)


def test_main_rejects_missing_credentials(runtime, capsys):
  runtime.env_credentials.return_value = None
  assert probe.main(["--host", "camera"]) == 2
  assert "Provide --credentials-file" in capsys.readouterr().err
  runtime.device_factory.assert_not_called()


def test_main_requires_topic_for_event_mode(runtime, capsys):
  assert probe.main(["--host", "camera", "--move-status", "event"]) == 2
  assert "requires --move-event-topic" in capsys.readouterr().err
  runtime.device_factory.assert_not_called()


def test_main_closes_device_after_connection_failure(runtime, capsys):
  runtime.device.connect.side_effect = OnvifError("camera unavailable")
  assert probe.main(["--host", "camera"]) == 1
  assert "ONVIF connect failed: camera unavailable" in capsys.readouterr().err
  runtime.device.close.assert_called_once_with()
  runtime.poller_factory.assert_not_called()


@pytest.mark.parametrize("event_mode", [False, True])
@pytest.mark.parametrize("emit_sample", [False, True])
def test_main_reports_results_and_cleans_up_workers(runtime, capsys, event_mode, emit_sample):
  runtime.settings.emit_sample = emit_sample
  arguments = ["--host", "camera", "--duration", "2"]
  if event_mode:
    arguments.extend(["--credentials-file", "creds.json", "--move-status", "event",
                      "--move-event-topic", "PTZController/Move", "--list-topics", "--samples"])
  assert probe.main(arguments) == (0 if emit_sample else 1)

  output = capsys.readouterr()
  decoder = json.JSONDecoder()
  report, offset = decoder.raw_decode(output.err)
  summary = json.loads(output.err[offset:])
  assert report["device"]["model"] == "PTZ"
  assert report["clock_offset_s"] == 0.125
  assert report["services"] == ["media", "ptz"]
  assert report["profile_token"] == "profile-a"
  assert report["absolute_pan_tilt_spaces"][0]["uri"] == "urn:test:space"
  assert summary == probe.summarize([sample()] if emit_sample else [], 2.0, 0)
  runtime.device.close.assert_called_once_with()
  runtime.stop.wait.assert_called_once_with(2.0)
  runtime.stop.set.assert_called_once_with()
  assert len(runtime.workers) == (2 if event_mode else 1)
  for worker in runtime.workers:
    worker.start.assert_called_once_with()
    worker.join.assert_called_once_with(5.0)
  if event_mode:
    assert report["event_topics"] == ["PTZController/Move"]
    runtime.file_credentials.assert_called_once_with("creds.json")
    runtime.env_credentials.assert_not_called()
    runtime.monitor_factory.assert_called_once_with(
      "probe", runtime.poller_factory.call_args.args[1], "PTZController/Move", "is_moving")
  else:
    runtime.device.get_event_topics.assert_not_called()
    runtime.monitor_factory.assert_not_called()
  runtime.device_factory.assert_called_once_with(
    "camera", 443,
    runtime.file_credentials.return_value if event_mode else runtime.env_credentials.return_value,
    scheme="https", timeout_s=1.0, profile_token=None)
  assert bool(output.out) == (event_mode and emit_sample)


def test_main_stops_and_joins_workers_after_keyboard_interrupt(runtime, capsys):
  runtime.stop.wait.side_effect = KeyboardInterrupt
  assert probe.main(["--host", "camera"]) == 0
  runtime.stop.set.assert_called_once_with()
  runtime.workers[0].join.assert_called_once_with(5.0)
  assert '"samples": 1' in capsys.readouterr().err
