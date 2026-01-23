import logging
import os
import json
import glob
import pytest
from api_client.base_http_client import BaseHttpClient

# ===============================
# Logging Configuration
# ===============================
LOG_FILE = os.path.join(os.path.dirname(__file__), "api_test.log")

# Create a custom logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # capture all logs

# Formatter
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # INFO to console
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler(LOG_FILE, mode="w")
file_handler.setLevel(logging.DEBUG)  # DEBUG to file
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.info("Logger initialized. Logs will be written to console and %s", LOG_FILE)

# ===============================
# Setup Base HTTP Client
# ===============================
API_TOKEN = os.environ.get(
    "API_TOKEN", "default_api_token_here"
)
BASE_URL = os.environ.get("API_BASE_URL", "https://localhost/api/v1")

http_client = BaseHttpClient(base_url=BASE_URL, token=API_TOKEN, verify_ssl=False)

saved_vars = {}

# ===============================
# Initialize API Clients
# ===============================
from api_client.scene_api import SceneApi
from api_client.camera_api import CameraApi
from api_client.sensor_api import SensorApi
from api_client.region_api import RegionApi
from api_client.tripwire_api import TripwireApi
from api_client.user_api import UserApi
from api_client.asset_api import AssetApi
from api_client.child_api import ChildApi

scene_api = SceneApi(http_client)
camera_api = CameraApi(http_client)
sensor_api = SensorApi(http_client)
region_api = RegionApi(http_client)
tripwire_api = TripwireApi(http_client)
user_api = UserApi(http_client)
asset_api = AssetApi(http_client)
child_api = ChildApi(http_client)

API_MAP = {
    "scene": scene_api,
    "camera": camera_api,
    "sensor": sensor_api,
    "region": region_api,
    "tripwire": tripwire_api,
    "user": user_api,
    "asset": asset_api,
    "child": child_api,
}

# ===============================
# Scenario Loading
# ===============================
def load_scenarios(folder="scenarios"):
    scenario_files = glob.glob(f"{folder}/*.json")
    scenarios = []
    for f in scenario_files:
        with open(f, "r") as sf:
            data = json.load(sf)
            scenarios.extend(data)
    return scenarios


def substitute_variables(obj):
    if isinstance(obj, dict):
        return {k: substitute_variables(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute_variables(x) for x in obj]
    if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
        var_name = obj[2:-1]
        return saved_vars.get(var_name, obj)
    return obj


# ===============================
# Pytest Parametrize
# ===============================
scenarios = load_scenarios()

@pytest.mark.parametrize(
    "scenario",
    scenarios,
    ids=lambda s: s.get("id", s.get("title", "unnamed")),
)
def test_api_scenario(scenario):
    api_name = scenario["api"]
    method_name = scenario["method"]
    request_data = substitute_variables(scenario.get("request", {}))
    expected = scenario.get("expected", {})
    save_vars = scenario.get("save", {})

    logger.info(f"=== Scenario: {scenario.get('title', scenario.get('id', 'unnamed'))} ===")
    logger.info(f"API Name      : {api_name}")
    logger.info(f"Method Name   : {method_name}")
    logger.info(f"Request Data  : {request_data}")
    logger.info(f"Expected      : {expected}")
    logger.info(f"Save Variables: {save_vars}")

    api = API_MAP.get(api_name)
    if not api:
        pytest.fail(f"Unknown API client: {api_name}")

    if not hasattr(api, method_name):
        pytest.fail(f"API {api_name} has no method {method_name}")

    api_method = getattr(api, method_name)
    response = api_method(**request_data)
    try:
        response_body = response.json()
    except Exception:
        response_body = response.text

    logger.info(f"Response Status : {response.status_code}")
    logger.info(f"Response Body   : {json.dumps(response_body, indent=2) if isinstance(response_body, dict) else response_body}")


    for var_name, path in save_vars.items():
        logger.info(f"Saving variable '{var_name}' from response path '{path}'")
        
        # Parse response JSON
        val = response.json() if hasattr(response, "json") else response

        for key in path.split("."):
            if isinstance(val, dict):
                val = val.get(key)
            else:
                val = getattr(val, key, None)

        if val is not None:
            saved_vars[var_name] = val
            os.environ[var_name] = str(val)
            logger.info(f"Saved variable '{var_name}' = {val}")
        else:
            logger.warning(f"Could not find path '{path}' in response")


    expected_status = expected.get("status_code", 200)
    assert response.status_code == expected_status, f"Expected {expected_status}, got {response.status_code}"
