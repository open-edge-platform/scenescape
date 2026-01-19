# Python Coding Standards for SceneScape

## Import Organization

Organize imports in this order:

1. Standard library imports
2. Third-party imports (external packages)
3. Local application imports (scene_common, manager, controller, etc.)

```python
# Standard library
import json
import os
from pathlib import Path

# Third-party
import numpy as np
from django.http import HttpResponse

# Local
from scene_common import log
from scene_common.geometry import Point
from manager.models import Scene
```

## Naming Conventions

- **Classes**: `PascalCase` (e.g., `SceneController`, `RESTClient`)
- **Functions/Methods**: `snake_case` (e.g., `get_scene_data`, `validate_message`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `TOPIC_BASE`, `CHUNK_SIZE`)
- **Private members**: Prefix with single underscore `_` (e.g., `_process_data`, `_internal_state`)

## Code Style

### Linting & Formatting

- **Linters**: pylint and flake8 (both must pass)
- **Formatter**: autopep8
- **Commands**:
  ```bash
  make lint-python        # Run both pylint and flake8
  make format-python      # Auto-format with autopep8
  ```

### Indentation

- Use **2 spaces** (never tabs)
- Checked via `make indent-check`

### Line Length

- Target: 100 characters (soft limit)
- Hard limit: 120 characters

### Docstrings

Use docstrings for classes and public methods:

```python
def process_detection(self, detection_data):
    """Process detection data from sensor.

    Args:
        detection_data: Dictionary containing detection information

    Returns:
        Processed detection object or None on failure
    """
```

## Django Patterns

### Models

- Import from `scene_common` for shared geometry/camera classes
- Use `ArrayField` for PostgreSQL array storage
- Implement `__str__` for admin interface readability

```python
from django.db import models
from scene_common.geometry import Region as ScenescapeRegion

class Scene(models.Model):
    name = models.CharField(max_length=255)
    map = models.FileField(upload_to='maps/')

    def __str__(self):
        return self.name
```

### Views

- Use class-based views for CRUD operations (`CreateView`, `UpdateView`, `DeleteView`)
- Use `@login_required` decorator for protected views
- Return `JsonResponse` for AJAX endpoints

### API Endpoints (Django REST Framework)

- Use serializers from `manager.serializers`
- Implement custom permissions (e.g., `IsAdminOrReadOnly`)
- Return proper HTTP status codes

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

class SceneAPI(APIView):
    def get(self, request, scene_id):
        # Implementation
        return Response(data, status=status.HTTP_200_OK)
```

## Scene Common Library Patterns

### MQTT/PubSub

```python
from scene_common.mqtt import PubSub

pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker, keepalive=60)
pubsub.onMessage = self.handle_message
pubsub.connect()
```

### Schema Validation

```python
from scene_common.schema import SchemaValidation

schema_val = SchemaValidation(schema_file)
if not schema_val.validateMessage("detector", message_data):
    log.error("Validation failed")
```

### REST Client

```python
from scene_common.rest_client import RESTClient

client = RESTClient(rest_url, rest_auth, root_cert)
result = client.getScene(scene_id)
```

### Logging

```python
from scene_common import log

log.info("Processing started")
log.error("Failed to process")
log.debug("Debug information")
```

## Type Hints

Use type hints for function signatures:

```python
from typing import Optional, List, Dict, Union
from pathlib import Path

def process_images(
    image_paths: List[Path],
    config: Optional[Dict] = None
) -> Union[np.ndarray, None]:
    pass
```

## Error Handling

Use specific exceptions and log appropriately:

```python
try:
    result = dangerous_operation()
except FileNotFoundError as e:
    log.error(f"File not found: {e}")
    return None
except Exception as e:
    log.error(f"Unexpected error: {e}")
    raise
```

## Performance Patterns

### Avoid Deep Copies When Possible

```python
# Good - shallow copy
data = original_data.copy()

# Use only when needed
data = copy.deepcopy(original_data)
```

### Use List Comprehensions

```python
# Preferred
results = [process(item) for item in items if item.valid]

# Over
results = []
for item in items:
    if item.valid:
        results.append(process(item))
```

## Common Anti-Patterns to Avoid

❌ **Don't use mutable default arguments**:

```python
# Bad
def process(data, cache={}):
    pass

# Good
def process(data, cache=None):
    if cache is None:
        cache = {}
```

❌ **Don't catch bare exceptions unless re-raising**:

```python
# Bad
try:
    risky_operation()
except:
    pass

# Good
try:
    risky_operation()
except SpecificException as e:
    log.error(f"Failed: {e}")
```

❌ **Don't use `from module import *`**:

```python
# Bad
from scene_common.geometry import *

# Good
from scene_common.geometry import Point, Region
```

## Virtual Environment Setup

Development uses `.venv` in project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-runtime.txt
```

VS Code configuration should point to `.venv/bin/python`.

## Dependencies

- Add to `requirements-runtime.txt` for runtime dependencies
- Add to `requirements-build.txt` for build-time dependencies
- Rebuild Docker image after dependency changes
