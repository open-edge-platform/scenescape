# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from unittest.mock import Mock

from scene_common.rest_client import RESTClient


def _json_response(status_code, content):
  response = Mock()
  response.status_code = status_code
  response.headers = {"Content-Type": "application/json"}
  response.content = json.dumps(content).encode("utf-8")
  return response


class TestRESTClientPagination:
  def setup_method(self):
    self.client = RESTClient("https://manager.example/api/v1", token="test-token")
    self.client.session = Mock()

  def test_get_follows_next_url_and_aggregates_results(self):
    next_url = "https://manager.example/api/v1/assets?name=crate&page=2"
    self.client.session.get.side_effect = [
      _json_response(200, {
        "count": 2,
        "next": next_url,
        "previous": None,
        "results": [{"name": "crate-a"}],
      }),
      _json_response(200, {
        "count": 2,
        "next": None,
        "previous": "https://manager.example/api/v1/assets?name=crate&page=1",
        "results": [{"name": "crate-b"}],
      }),
    ]

    result = self.client._get("assets", {"name": "crate"})

    assert [asset["name"] for asset in result["results"]] == ["crate-a", "crate-b"]
    assert self.client.session.get.call_count == 2
    first_call, next_call = self.client.session.get.call_args_list
    assert first_call.args[0] == "https://manager.example/api/v1/assets"
    assert first_call.kwargs["params"] == {"name": "crate"}
    assert next_call.args[0] == next_url
    assert "params" not in next_call.kwargs

  def test_get_returns_later_page_http_error(self):
    next_url = "https://manager.example/api/v1/assets?page=2"
    self.client.session.get.side_effect = [
      _json_response(200, {
        "count": 2,
        "next": next_url,
        "previous": None,
        "results": [{"name": "crate-a"}],
      }),
      _json_response(500, {}),
    ]

    result = self.client._get("assets", None)

    assert result.status_code == 500
    assert result.errors == {}
