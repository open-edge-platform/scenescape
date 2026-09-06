<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->

# Intel Secure Python Specifics

## Purpose

This skill provides guidance for secure Python coding across Scenescape's microservices, grounded in Intel Secure Coding Standards - Python Specifics.

**Applies to:**

- `manager/` (Django REST API)
- `controller/` (MQTT handlers, gRPC services)
- `autocalibration/` (REST API)
- `cluster_analytics/`, `mapping/` (services)

---

## Core Principles

### Input Validation & Deserialization

✅ **DO:**

```python
import json
from typing import Any, Dict

# Parse JSON safely
def load_config(config_str: str) -> Dict[str, Any]:
    return json.loads(config_str)  # Safe; no code execution

# Parameterized queries
from django.db import models
cameras = models.Camera.objects.filter(
    id=camera_id  # Never: f"id={camera_id}"
)

# Type hints for validation
def process_camera_data(camera_id: int, config: dict) -> bool:
    if not isinstance(camera_id, int) or camera_id <= 0:
        raise ValueError("Invalid camera_id")
    return True
```

❌ **DON'T:**

```python
import pickle
import yaml

# Pickle deserialization: RCE risk!
data = pickle.loads(untrusted_input)  # NEVER for untrusted data

# YAML without safe loader: RCE risk!
config = yaml.load(user_config)  # Use yaml.safe_load() only

# String concatenation in queries: SQL injection!
query = f"SELECT * FROM cameras WHERE id={camera_id}"
cursor.execute(query)

# eval/exec: Arbitrary code execution
result = eval(user_expression)  # NEVER!
exec(user_code)  # NEVER!
```

### String Handling & Formatting

✅ **DO:**

```python
from string import Template

# Use Template for user-controlled format strings
user_name = "attacker'; DROP TABLE cameras; --"
safe_template = Template("Welcome, $name!")
message = safe_template.substitute(name=user_name)

# Use f-strings for hardcoded formats
camera_id = 42
fixed_message = f"Camera {camera_id} initialized"

# String comparison
if password == expected_password:  # Correct equality check
    authenticate()
```

❌ **DON'T:**

```python
# str.format() with user input: Information leakage!
user_input = "{0.__class__.__bases__[0].__subclasses__()}"
message = "User: {}".format(user_input)  # Exposes internals

# %-formatting with user input: Same risk
message = "Name: %s" % user_input

# 'is' operator for string comparison
if password is expected_password:  # Object identity, not equality!
    authenticate()

# Single backslashes in paths
path = "C:\new\camera\data.json"  # "\n" = newline, "\c" = invalid escape
```

### Authentication & Credentials

✅ **DO:**

```python
import hmac
import os

# Constant-time comparison for auth tokens/HMACs
def verify_token(provided_token: str, expected_token: str) -> bool:
    return hmac.compare_digest(provided_token, expected_token)

# Environment variables for secrets
broker_password = os.environ.get("MQTT_PASSWORD")
if not broker_password:
    raise RuntimeError("MQTT_PASSWORD not set")

# Memory scrubbing for sensitive data
def clear_password(password: str) -> None:
    # Python strings are immutable; use:
    # - securesystemlib, cryptography.hazmat for key material
    # - Or: memoryview for mutable buffers
    del password  # Minimal; not guaranteed
```

❌ **DON'T:**

```python
# String comparison for auth: Timing attacks!
if user_token == stored_token:  # Short-circuits; leaks timing
    authenticate()

# Hard-coded secrets in code
MQTT_PASSWORD = "super_secret_123"  # Visible in source!
API_KEY = "dev_key_abc"

# Logging secrets
logger.info(f"Auth token: {token}")  # Exposed in logs
print(f"Database password: {db_pass}")
```

### File & Network I/O

✅ **DO:**

```python
import os
from contextlib import contextmanager

# Context managers for resource cleanup
with open("camera_config.json") as f:
    config = json.load(f)  # Automatically closes

# Canonicalize file paths
import pathlib
config_path = pathlib.Path(user_path).resolve()
if not str(config_path).startswith(str(CONFIG_DIR.resolve())):
    raise ValueError("Path traversal attempt")

# Network binding to specific interface
app.run(host="127.0.0.1", port=5000)  # Localhost only
# For services: bind to service network interface, not 0.0.0.0
```

❌ **DON'T:**

```python
# Manual file closing: Easy to leak
f = open("config.json")
data = f.read()
# f.close() forgotten; file handle leaked

# Network binding to all interfaces: Public exposure!
app.run(host="0.0.0.0", port=5000)  # Accessible on all interfaces!

# Development servers in production: No TLS, no robustness
from flask import Flask
app = Flask(__name__)
app.run()  # Flask dev server; use gunicorn/uWSGI for production!
```

### Error Handling & Logging

✅ **DO:**

```python
import logging

logger = logging.getLogger(__name__)

# Handle all exceptions explicitly
try:
    calibrate_camera(camera_id)
except ValueError as e:
    logger.error(f"Invalid camera: {camera_id}")  # Safe message
    raise
except Exception as e:
    logger.error("Unexpected error during calibration")  # No sensitive detail
    raise

# Meaningful error messages without leaking info
def validate_input(data: dict) -> bool:
    if "camera_id" not in data:
        raise KeyError("Missing required field: camera_id")
    return True
```

❌ **DON'T:**

```python
# Silent failures or ignored exceptions
try:
    calibrate_camera(camera_id)
except:
    pass  # What failed? No logging!

# Logging sensitive data
logger.info(f"Auth attempt with password: {password}")  # Exposed!
logger.debug(f"Database connection: {db_url}")  # Credentials visible

# Exposing system internals
except Exception as e:
    return str(e)  # May leak stack traces, paths
```

### Project Structure

✅ **DO:**

```bash
# Virtual environment isolation
python3 -m venv venv
source venv/bin/activate

# Use absolute imports
from controller.mqtt import PubSub  # Clear; no ambiguity
from scene_common.geometry import Point

# Type annotations
from typing import List, Dict, Optional

def get_cameras() -> List[Camera]:
    return database.query(Camera).all()
```

❌ **DON'T:**

```bash
# No virtual environment: Dependency conflicts!
pip install requirements.txt  # System-wide pollution

# Relative imports: Confusing
from .mqtt import PubSub  # Ambiguous in large projects

# No type hints: Runtime errors
def process(data):  # What type is data?
    return data["camera_id"]  # KeyError? No warning
```

---

## Production Deployment

✅ **DO:**

```python
# Django/Flask: Use production WSGI server
# In Dockerfile or docker-compose.yml
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
# or
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0"]
```

❌ **DON'T:**

```python
# Flask development server (no TLS, no concurrency handling)
if __name__ == "__main__":
    app.run()  # NEVER in production!

# Django development server
python manage.py runserver  # NEVER in production!
```

---

## Review Checklist

When reviewing or generating Python code:

- [ ] No `pickle`/`cPickle` for untrusted data (use `json`/`yaml.safe_load`)
- [ ] No `eval()` or `exec()` on untrusted input
- [ ] String formatting: Use `string.Template` or f-strings only (not `str.format()` with user input)
- [ ] Auth comparison: Use `hmac.compare_digest()` (not `==`)
- [ ] Parameterized queries: Use ORM or parameterized API (not string concatenation)
- [ ] All file/socket/DB operations use context managers (`with` statement)
- [ ] Secrets from environment variables (not hard-coded)
- [ ] Secrets NOT logged or printed
- [ ] All exceptions explicitly caught and handled
- [ ] Error messages do not expose system internals
- [ ] Virtual environment used (venv, requirements-runtime.txt)
- [ ] Absolute imports used (not relative)
- [ ] Type annotations for public functions
- [ ] Production servers (gunicorn, uvicorn, etc.) used, not Flask/Django dev
