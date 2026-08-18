## RESTler for fuzzing Scenescape REST API

### Overview

RESTler is an [open-source](https://github.com/microsoft/restler-fuzzer) REST fuzzer from Microsoft. It compiles an OpenAPI spec into a fuzzing grammar, then runs automated testing against the API.

On Scenescape, RESTler is used satisfy the CT631 SDL task, which specifies fuzz testing requirements for products with REST APIs. It's also a good way to discover edge cases that are unlikely to surface through manual testing.

### Fuzz testing repo contents

This directory contains the following:

- `fuzzing_openapi.yaml`: a curated manager API spec. The canonical manager spec is `docs/user-guide/api-docs/api.yaml`; the fuzzing spec intentionally excludes `/auth` and `/import-scene`.
- `run_fuzzing.sh`: script that will run inside the RESTler container. Sets up the environment, then compiles the grammar and executes the fuzzing run.
- `run_service_fuzzing.sh`: shared runner for service-specific campaigns.
- `run_autocalibration_fuzzing.sh`: runner for the Auto Camera Calibration API.
- `run_mapping_fuzzing.sh`: runner for the Mapping API.
- `.env`: list of variables for the fuzzing run. These need to be set before executing a run. See the step-by-step instructions [below](#performing-a-fuzz-test) for information about the specific variables.
- `settings.json`: RESTler configuration file.
- `token`: template file for the RESTler token auth mechanism. Will be modified at runtime by the test run script.

### Performing a fuzz test

0. Build and deploy Scenescape.
1. Build the RESTler Docker image from source:
   - `git clone https://github.com/microsoft/restler-fuzzer.git`
   - `cd restler-fuzzer`
   - `cp ../manager/secrets/certs/scenescape-ca.pem .`
   - `cp ../tests/security/fuzzing/Dockerfile .`
   - `docker build --build-arg http_proxy=http://proxy-dmz.intel.com:912 --build-arg https_proxy=http://proxy-dmz.intel.com:912 -t restler .`
2. Edit `.env` and set the following values:
   - `https_proxy` is the outbound web proxy, used to fetch package dependencies.
   - `instance_ip` is the IP address of the instance under test.
   - `auth_username` is the superuser of your instance (usually `admin`).
   - `auth_password` is the superuser's password (usually whatever `SUPASS` was when you deployed).
   - `restler_mode` is the RESTler mode to run. Supported values are `fuzz`, `fuzz-lean`, and `test`. See RESTler documentation for more details.
   - `time_budget_hours` is the length of time, in hours, that the `fuzz` mode will spend testing the API.
3. From the fuzzing folder, execute the Docker command to launch a RESTler container and run our script:
   - `cd tests/security/fuzzing`
   - `docker run --rm -v "$(pwd)":/workspace -e USER_ID=$(id -u) -e GROUP_ID=$(id -g) restler /workspace/run_fuzzing.sh`
4. When testing finishes (this takes a long time!), manager results are stored in `Fuzz/manager/`. See the RESTler documentation for more about how to interpret the results of a run, or talk to your security team!

### Fuzzing additional services

The Auto Calibration and Mapping APIs use their own canonical OpenAPI specs and
are run separately from the manager campaign. Results remain under this same
directory in `Fuzz/manager/`, `Fuzz/autocalibration/`, and `Fuzz/mapping/`.

The service runners need the repository mounted at `/repo` so they can copy the
canonical spec at runtime:

```bash
cd tests/security/fuzzing
docker run --rm \
   -v "$(pwd)":/workspace \
   -v "$(git rev-parse --show-toplevel)":/repo:ro \
   restler /workspace/run_autocalibration_fuzzing.sh
```

Run Mapping by replacing `run_autocalibration_fuzzing.sh` with
`run_mapping_fuzzing.sh`. The reverse-proxy routes are
`/api/v1/autocalibration` and `/api/v1/mapping`; direct standalone service
ports can be used by overriding `SERVER_URL` when the deployment exposes them.
Both service runners read `instance_ip`, `restler_mode`, and
`time_budget_hours` from `.env`; uppercase environment variables can override
those values for a one-off run.
