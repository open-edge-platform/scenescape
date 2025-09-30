# Running tests for SceneScape on Docker

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

## Running tests on kubernetes

Refer to [Running tests on kubernetes](kubernetes/README.md)
