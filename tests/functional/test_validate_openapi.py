import subprocess
import os
import pytest

@pytest.mark.basic_acceptance
def test_validate_openapi():
    """Validate OpenAPI schema using swagger-cli."""
    docs_path = os.path.join(os.path.dirname(__file__), "../../../docs/user-guide/api-docs/")
    docs_path = os.path.abspath(docs_path)

    # Install swagger-cli
    subprocess.run(
        ["npm", "install", "--save-dev", "swagger-cli@2.0.0"],
        cwd=docs_path,
        check=True
    )

    # Validate api.yaml
    result = subprocess.run(
        ["npx", "swagger-cli", "validate", "api.yaml"],
        cwd=docs_path,
        check=True
    )

    assert result.returncode == 0
