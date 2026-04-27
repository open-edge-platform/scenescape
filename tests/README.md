# Running tests for Intel® SceneScape on Docker

## Setup environment

```bash
# Set up SUPASS, build docker and test environment
SUPASS=change_me make build-all && make setup_tests
```

## Running tests

You can run all or specific test groups using `make`:

```bash

# Run all basic acceptance tests
make -C tests basic-acceptance-tests

# Run standard tests (functional + UI)
make -C tests standard-tests

# Run release tests
make -C tests release-tests

# Run broken tests (known unstable or failing)
make -C tests broken-tests

# Run a specific test
make -C tests mqtt-roi

```

For a complete and up-to-date list of all test targets and their definitions, see the [Tests Makefile](tests/Makefile)

## Unit test taxonomy

The repository keeps two categories under the `unit-tests` umbrella:

- Pure unit tests: fast logic-focused tests that typically avoid Django request/ORM integration.
  - Umbrella target: `make -C tests logic-unit-tests`
  - Example leaf target: `make -C tests scene-unit`
- Django integration unit tests: Django `TestCase`/test-client/ORM based backend tests grouped under a dedicated umbrella.
  - Umbrella target: `make -C tests django-integration-unit`
  - Included targets: `account-security-unit`, `cam-unit`, `scene-django-unit`, `singleton-sensor-unit`, `views-unit`

Notes:

- `make -C tests unit-tests` still runs both categories.
- The Django scene CRUD tests in `tests/sscape_tests/scene/` are run by `scene-django-unit`.

## Running tests on kubernetes

Refer to [Running tests on kubernetes](kubernetes/README.md)
