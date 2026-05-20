import subprocess
import pytest


@pytest.fixture(scope="session")
def swagger_cli():
    """Install swagger-cli with npm for the test session and remove after."""
    # Install swagger-cli
    subprocess.run(["npm", "install", "-g", "swagger-cli"], check=True)

    yield

    # Cleanup: remove swagger-cli
    subprocess.run(["npm", "uninstall", "-g", "swagger-cli"], check=True)
