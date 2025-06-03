# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import json
import traceback

from django.shortcuts import render

from scene_common import log

class Custom500Middleware:
  def __init__(self, get_response):
    self.get_response = get_response
    return

  def __call__(self, request):
    response = self.get_response(request)
    return response

  def process_exception(self, request, exception):
    error_message = traceback.format_exc()
    log.error(error_message)
    response = render(request, 'sscape/500_error.html', {
      'error_message': error_message,
      'request_info': self._stringify_request(request),
    })
    response.status_code = 500
    return response

  def _stringify_request(self, request):
    request_data = {
      'method': request.method,
      'path': request.path,
      'GET': request.GET.dict(),
      'POST': request.POST.dict(),
      'headers': {k: v for k, v in request.headers.items()},
    }
    return json.dumps(request_data, indent=2)
