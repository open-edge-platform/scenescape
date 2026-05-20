# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess
import os
import pytest

TEST_NAME = "NEX-T10572"

@pytest.mark.basic_acceptance
def test_validate_openapi(record_xml_attribute, swagger_cli):
    """Validate OpenAPI schema using swagger-cli."""
    docs_path = os.path.join(os.path.dirname(__file__), "../../docs/user-guide/api-docs/")
    docs_path = os.path.abspath(docs_path)

    record_xml_attribute("name", TEST_NAME)

    # Validate api.yaml
    result = subprocess.run(
        ["npx", "swagger-cli", "validate", "api.yaml"],
        cwd=docs_path,
        check=True
    )

    assert result.returncode == 0
