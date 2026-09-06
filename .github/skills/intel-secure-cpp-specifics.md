<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->

# Intel Secure C++ Specifics

## Purpose

This skill provides guidance for secure C++ coding in Scenescape's geometry and vision components, grounded in Intel Secure Coding Standards - C++ Specifics.

**Applies to:**

- `scene_common/src/fast_geometry/` (C++ geometry extension)
- `controller/src/robot_vision/` (C++ vision processing)
- `tracker/` (C++ tracking component)
- Any new C++ modules

---

## Core Principles

### Memory Management (RAII)

✅ **DO:**

```cpp
// Use RAII: Resource Acquisition Is Initialization
class CameraMatrix {
  std::unique_ptr<float[]> data_;
  size_t size_;
public:
  CameraMatrix(size_t n) : data_(new float[n]), size_(n) {}
  ~CameraMatrix() { /* automatically freed by unique_ptr */ }
};

// Use smart pointers
std::unique_ptr<Geometry> geom(new Geometry()); // Prefer unique_ptr
std::shared_ptr<Camera> cam(new Camera());      // Use shared_ptr only if needed
```

❌ **DON'T:**

```cpp
// Raw new/delete
float* data = new float[1024];
// ... risk of memory leak if exception or early return ...
delete[] data;

// malloc/free (C-style)
float* data = (float*)malloc(1024 * sizeof(float));
free(data);
```

### String Handling

✅ **DO:**

```cpp
std::string camera_name = "camera_1";
std::string full_path = camera_name + "_calibration.json";

// Use std::string_view for non-owning references
void process_camera(std::string_view name) {
  // read-only access without copying
}

// Use std::format (C++20) or fmt::format
std::string message = std::format("Camera {} position: {}", id, pos);
```

❌ **DON'T:**

```cpp
// C-style strings and unsafe functions
char name[255];
strcpy(name, user_input);  // Buffer overflow risk
strcat(name, ".json");     // Dangerous

// printf family
printf("Position: %d %d\n", x, y);  // Prone to format string attacks
sprintf(buffer, "Name: %s", name);  // No bounds checking
```

### Type Safety & Const Correctness

✅ **DO:**

```cpp
// Use strong typing
struct Point { float x, y, z; };
struct Camera { float focal_length; };

// Explicit casts
int size = static_cast<int>(data.size());

// Const for read-only
const Point& get_position() const { return position_; }
void set_position(const Point& p) { position_ = p; }

// nullptr for null pointers
Point* position = nullptr;  // Strongly typed
if (position != nullptr) { /* ... */ }
```

❌ **DON'T:**

```cpp
// Weak typing (void*)
void* data = geometry_data;  // What type is this?

// Implicit casting
int size = data.size();  // May lose precision

// NULL macro (C-style)
Point* position = NULL;

// Uninitialized pointers
Point* position;  // May contain garbage
```

### Integer Arithmetic

✅ **DO:**

```cpp
// Check for overflow before operations
size_t total_size = num_cameras * points_per_camera;
if (num_cameras > SIZE_MAX / points_per_camera) {
  throw std::overflow_error("Size calculation overflow");
}

// Guard division by zero
if (divisor != 0) {
  result = numerator / divisor;
} else {
  throw std::runtime_error("Division by zero");
}

// Check INT_MIN/-1 for signed division
if (!(value == INT_MIN && divisor == -1)) {
  result = value / divisor;
}
```

❌ **DON'T:**

```cpp
// Unsigned/signed mix
int signed_val = -10;
unsigned int unsigned_val = 20;
int result = signed_val + unsigned_val;  // Unexpected conversion

// Unguarded division
result = a / b;  // May crash if b == 0

// Integer overflow
int overflow = INT_MAX + 1;  // Undefined behavior
```

### Error Handling

✅ **DO:**

```cpp
// Check return values
int result = calibrate_camera(cam);
if (result != SUCCESS) {
  log_error("Camera calibration failed");
  throw std::runtime_error("Calibration error");
}

// Use exceptions, not assert for security
if (!validate_matrix(M)) {
  throw std::invalid_argument("Invalid matrix");
}

// Use std::optional for optional results
std::optional<Point> find_feature(const Image& img) {
  if (/* found */) return Point{x, y};
  return std::nullopt;
}
```

❌ **DON'T:**

```cpp
// Ignore return values
calibrate_camera(cam);  // Result ignored; may fail silently

// Use assert for runtime validation
assert(validate_matrix(M));  // Removed in release builds!

// Silent failures
if (load_config(file)) { /* continue */ }  // What failed?
```

### Function Design

✅ **DO:**

```cpp
// Limit parameters (ideally ≤6)
Point apply_transform(const Point& p, const Matrix& M, const Vector& t) {
  return M * p + t;
}

// Clear error handling
[[nodiscard]] bool validate_image(const Image& img);

// Pure functions where possible
float distance(const Point& a, const Point& b) {
  return std::sqrt((a.x - b.x) * (a.x - b.x) +
                   (a.y - b.y) * (a.y - b.y));
}
```

❌ **DON'T:**

```cpp
// Too many parameters
Point complex_op(int a, int b, int c, int d, int e, int f, int g) { /* ... */ }

// Variadic functions (error-prone)
void log_message(const char* fmt, ...);  // Use std::format instead

// Functions with hidden side effects
Point get_position();  // Modifies global state? Unclear
```

---

## Review Checklist

When reviewing or generating C++ code:

- [ ] All heap allocations use `std::unique_ptr<T>` or `std::shared_ptr<T>` (no raw `new`/`delete`)
- [ ] No `malloc`/`free` (C-style memory management)
- [ ] All pointers initialized to `nullptr` (not `NULL`)
- [ ] All strings use `std::string` (not C-style char arrays)
- [ ] No `printf` family functions (use `std::format` or `fmt::format`)
- [ ] Return values checked for all functions that may fail
- [ ] Integer arithmetic guarded against overflow/underflow
- [ ] Division by zero prevented (checked divisor)
- [ ] Const-correctness enforced (const members, const references)
- [ ] Assert not used for security validation (use exceptions)
- [ ] Type casts use `static_cast<T>`, `const_cast<T>` explicitly (never C-style casts)
- [ ] No `void*` for type safety
