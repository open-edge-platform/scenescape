# JavaScript Coding Standards for SceneScape

## Code Style

### Linting & Formatting

- **Linter**: ESLint (config in `.github/resources/eslint.config.js`)
- **Formatter**: Prettier (config in `.github/resources/.prettierrc.json`)
- **Commands**:
  ```bash
  make lint-javascript    # Run ESLint
  make prettier-write     # Auto-format all code
  make prettier-check     # Check formatting
  ```

### Indentation

- Use **2 spaces** (never tabs)
- Consistent with Prettier configuration

### Line Length

- Enforced by Prettier configuration
- Typically 80-100 characters

### Semicolons

- Use semicolons consistently (enforced by Prettier)

### Quotes

- Prefer **double quotes** for strings (enforced by Prettier)

## Naming Conventions

- **Classes**: `PascalCase` (e.g., `MapboxPlugin`, `GoogleMapsPlugin`, `MapInterface`)
- **Functions/Methods**: `camelCase` (e.g., `generateSnapshot`, `saveSnapshotToServer`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_ZOOM`, `MAP_CENTER`)
- **Variables**: `camelCase` (e.g., `sceneData`, `cameraList`)
- **Private members**: Prefix with underscore `_` (convention only, not enforced)

## Architecture Patterns

### Class-Based Components

SceneScape uses ES6 classes for map plugins and UI components:

```javascript
class MapboxPlugin extends MapInterface {
  constructor() {
    super();
    this.map = null;
    this.accessToken = null;
  }

  async initialize(containerId, config = {}) {
    // Implementation
  }

  generateSnapshot() {
    // Implementation
  }
}
```

### Plugin Pattern

Map providers implement a common interface:

```javascript
class MapInterface {
  async initialize(containerId, config) {}
  moveToLocation(input) {}
  generateBounds() {}
  generateSnapshot() {}
  getBounds() {}
  getCenter() {}
  getZoom() {}
}
```

### Async/Await

Prefer async/await over promises for readability:

```javascript
// Good
async function fetchSceneData(sceneId) {
  try {
    const response = await fetch(`/api/v1/scenes/${sceneId}/`);
    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Failed to fetch scene:", error);
    return null;
  }
}

// Avoid
function fetchSceneData(sceneId) {
  return fetch(`/api/v1/scenes/${sceneId}/`)
    .then((response) => response.json())
    .catch((error) => console.error(error));
}
```

## DOM Manipulation

### jQuery Usage

SceneScape uses jQuery for DOM manipulation:

```javascript
$(document).ready(function () {
  $("#login-submit").on("click", handleLogin);

  $(".roi-color").each(function () {
    // Process each element
  });
});
```

### Event Handlers

```javascript
// Attach handlers
$("#button-id").on("click", function (event) {
  event.preventDefault();
  // Handle click
});

// Delegate for dynamic elements
$(document).on("click", ".dynamic-class", function () {
  // Handle click on dynamically added elements
});
```

### Element Selection

```javascript
// By ID
const element = document.getElementById("map");
const $element = $("#map");

// By class
const elements = document.querySelectorAll(".roi-item");
const $elements = $(".roi-item");
```

## AJAX Requests

### Fetch API with CSRF

```javascript
async function saveData(data) {
  const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");

  const response = await fetch("/api/v1/endpoint/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken.value,
    },
    body: JSON.stringify(data),
  });

  if (response.ok) {
    const result = await response.json();
    return result;
  } else {
    console.error("Request failed:", response.status);
    return null;
  }
}
```

### FormData for File Uploads

```javascript
const formData = new FormData();
formData.append("image_data", imageData);
formData.append("csrfmiddlewaretoken", csrfToken.value);

const response = await fetch("/api/v1/save-snapshot/", {
  method: "POST",
  headers: {
    "X-CSRFToken": csrfToken.value,
  },
  body: formData,
});
```

## Error Handling

### Try-Catch with Async

```javascript
async function processOperation() {
  try {
    const result = await riskyOperation();
    console.log("Success:", result);
    return result;
  } catch (error) {
    console.error("Operation failed:", error);
    showErrorMessage(error.message);
    return null;
  }
}
```

### Null Checks

```javascript
// Good - early return
function processScene(scene) {
  if (!scene) {
    console.error("Scene is null");
    return;
  }

  // Process scene
}

// Good - optional chaining
const cameraCount = scene?.cameras?.length ?? 0;
```

## Canvas & Graphics

### Canvas Manipulation

```javascript
const canvas = document.createElement("canvas");
canvas.width = 1280;
canvas.height = 1280;
const ctx = canvas.getContext("2d");

// Draw image
ctx.drawImage(image, 0, 0);

// Get base64 data
const imageData = canvas.toDataURL("image/png");
```

### SVG Manipulation

```javascript
// Create SVG element
const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
svg.setAttribute("width", "100");
svg.setAttribute("height", "100");

// Add to DOM
$("#svgout").append(svg);
```

## Console Logging

### Development Logging

```javascript
// Debug information
console.log("Processing scene:", sceneId);

// Warnings
console.warn("Camera not found:", cameraId);

// Errors
console.error("Failed to load scene:", error);

// Structured data
console.log("Response:", { status, data, timestamp });
```

### Production Considerations

Remove or guard verbose logging in production code:

```javascript
if (DEBUG_MODE) {
  console.log("Detailed debug info:", debugData);
}
```

## Comments

### Function Documentation

```javascript
/**
 * Generate a snapshot of the current map view
 * @returns {Promise<string>} Base64-encoded image data
 */
async function generateSnapshot() {
  // Implementation
}
```

### Inline Comments

```javascript
// Hide map controls before screenshot
const style = document.createElement("style");
style.textContent = `...`;

// Process each ROI point
points.forEach((point, index) => {
  // Transform coordinates to map space
  const transformed = transformPoint(point);
});
```

## Common Patterns

### Show/Hide Elements

```javascript
// Show
$("#element").show();
$("#element").css("display", "block");

// Hide
$("#element").hide();
$("#element").css("display", "none");
```

### Add/Remove Classes

```javascript
$("#element").addClass("active");
$("#element").removeClass("disabled");
$("#element").toggleClass("selected");
```

### Update Content

```javascript
// Text
$("#message").text("Operation complete");

// HTML
$("#container").html("<div>New content</div>");

// Attributes
$("#image").attr("src", imageUrl);
```

### Animation & Effects

```javascript
// Fade in/out
$("#element").fadeIn(300);
$("#element").fadeOut(300);

// Scroll into view
element.scrollIntoView({ behavior: "smooth" });
```

## Map Provider Integration

### Mapbox

```javascript
mapboxgl.accessToken = apiKey;
const map = new mapboxgl.Map({
  container: "map",
  style: "mapbox://styles/mapbox/satellite-v9",
  center: [lng, lat],
  zoom: 15,
});
```

### Google Maps

```javascript
const map = new google.maps.Map(document.getElementById("map"), {
  center: { lat, lng },
  zoom: 15,
  mapTypeId: "satellite",
});
```

## File Organization

### Manager Static Files

```
manager/src/static/js/
├── geospatial/
│   ├── mapbox-plugin.js
│   ├── google-maps-plugin.js
│   └── map-interface.js
└── sscape.js
```

### Script Loading

Scripts are loaded via Django templates:

```html
{% load static %}
<script src="{% static 'js/sscape.js' %}"></script>
<script src="{% static 'js/geospatial/mapbox-plugin.js' %}"></script>
```

## Anti-Patterns to Avoid

❌ **Don't use var**:

```javascript
// Bad
var count = 0;

// Good
const count = 0;
let counter = 0;
```

❌ **Don't modify global scope unnecessarily**:

```javascript
// Bad
window.myGlobalVar = "value";

// Good - use module pattern or classes
const MyModule = {
  value: "value",
};
```

❌ **Don't use == for comparisons**:

```javascript
// Bad
if (value == null) {
}

// Good
if (value === null) {
}
if (value == null) {
} // OK only for null/undefined check
```

❌ **Don't create functions in loops**:

```javascript
// Bad
for (let i = 0; i < items.length; i++) {
  $("#item-" + i).on("click", function () {
    process(i); // i will be wrong
  });
}

// Good
items.forEach((item, index) => {
  $(`#item-${index}`).on("click", () => process(index));
});
```

## Browser Compatibility

- Target modern browsers (ES6+ support)
- Use polyfills where necessary
- Test in Chrome, Firefox, Edge, Safari

## Performance Tips

- Minimize DOM queries (cache selectors)
- Use event delegation for dynamic content
- Debounce/throttle frequent events (scroll, resize)
- Load scripts at bottom of page or use `defer`

```javascript
// Cache selector
const $container = $("#container");
$container.addClass("active");
$container.append(element);

// Don't repeat
$("#container").addClass("active");
$("#container").append(element);
```
