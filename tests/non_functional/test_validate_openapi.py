# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename

TEST_NAME = "NEX-T10572"

@pytest.mark.basic_acceptance
def test_validate_openapi(record_xml_attribute):
  """Validate the OpenAPI schema using openapi-spec-validator."""
  record_xml_attribute("name", TEST_NAME)

  api_path = os.path.join(os.path.dirname(__file__), "../../docs/user-guide/api-docs/api.yaml")
  spec_dict = read_from_filename(api_path)[0]

  try:
    validate(spec_dict)
  except Exception as e:
    pytest.fail(f"OpenAPI validation failed: {e}")
