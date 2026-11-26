# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

import pytest

import detection_replay

CAMERAS = ["--camera", "cam-a", "/media/a.mp4", "/meta/a.json",
           "--camera", "cam-b", "/media/b.mp4", "/meta/b.json"]


def describe(*extra):
  return detection_replay.pipeline_description(detection_replay.parse_args([*CAMERAS, *extra]))


def test_one_branch_per_camera():
  description = describe()
  assert description.count("filesrc ") == 2
  assert "cameraid=cam-a" in description and "cameraid=cam-b" in description
  assert "sscape_detection_replay metadata=/meta/b.json sync-mode=time" in description


def test_branch_mirrors_detection_only_pipeline():
  branch = describe().split("filesrc ")[1]
  elements = [element.split()[0] for element in branch.split(" ! ")]
  assert elements == [
    "location=/media/a.mp4", "decodebin", "videoconvert", "video/x-raw,format=BGR",
    "identity", "sscape_timestamp_capture", "sscape_detection_replay",
    "gvametaconvert", "sscape_post_inference_data_publish", "fakesink",
  ]


def test_options_reach_elements():
  description = describe("--sync", "frame", "--detection-labels", "person,car",
                         "--ntp-server", "ntp", "--mqtt-host", "broker", "--mqtt-port", "1884")
  assert "sync-mode=frame" in description
  assert "detection-labels=person,car" in description
  assert "sscape_timestamp_capture ntp-server=ntp" in description
  assert "mqtt-host=broker mqtt-port=1884" in description


def test_empty_ntp_server_uses_system_clock():
  assert "ntp-server" not in describe("--ntp-server", "")


@pytest.mark.parametrize("value, expected", [
  ("/media/a.mp4", "/media/a.mp4"),
  ("/media/my video.mp4", '"/media/my video.mp4"'),
  ("/media/it's.mp4", '"/media/it\'s.mp4"'),
  ('/media/a"b\\c.mp4', '"/media/a\\"b\\\\c.mp4"'),
  ("a ! b", '"a ! b"'),
  ("", '""'),
])
def test_gst_quote(value, expected):
  assert detection_replay.gst_quote(value) == expected


def test_paths_with_spaces_are_quoted():
  args = detection_replay.parse_args(["--camera", "cam", "/media/my video.mp4", "/meta/a.json"])
  assert 'location="/media/my video.mp4"' in detection_replay.pipeline_description(args)


def test_duplicate_camera_ids_are_rejected():
  args = detection_replay.parse_args(["--camera", "cam", "a.mp4", "a.json",
                                      "--camera", "cam", "b.mp4", "b.json"])
  with pytest.raises(ValueError):
    detection_replay.pipeline_description(args)


def test_missing_files_exit_with_error(tmp_path, capsys):
  assert detection_replay.main(["--camera", "cam", str(tmp_path / "v.mp4"), str(tmp_path / "m.json")]) == 2
  assert "File not found" in capsys.readouterr().err


def test_print_pipeline(capsys):
  assert detection_replay.main([*CAMERAS, "--print-pipeline"]) == 0
  assert "cameraid=cam-a" in capsys.readouterr().out


def test_plugin_path_extends_gst_and_python_paths(monkeypatch):
  monkeypatch.setenv("ADDITIONAL_GST_PLUGIN_PATH", "/a:/b")
  monkeypatch.setenv("GST_PLUGIN_PATH", "/system")
  monkeypatch.delenv("PYTHONPATH", raising=False)
  monkeypatch.setattr(detection_replay.sys, "path", [])
  detection_replay.extend_plugin_path()
  assert os.environ["GST_PLUGIN_PATH"] == "/system:/a:/b"
  assert os.environ["PYTHONPATH"] == "/a/python:/b/python"
  assert detection_replay.sys.path == ["/a/python", "/b/python"]
