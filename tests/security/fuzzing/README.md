## RESTler for fuzzing Scenescape REST API

### Overview

RESTler is an [open-source](https://github.com/microsoft/restler-fuzzer) REST fuzzer from Microsoft. It compiles an OpenAPI spec into a fuzzing grammar, then runs automated testing against the API.

On Scenescape, RESTler is used to satisfy the CT631 SDL task, which specifies fuzz testing requirements for products with REST APIs. It's also a good way to discover edge cases that are unlikely to surface through manual testing.

### Fuzz testing repo contents

This directory contains the following:

- `fuzzing_openapi.yaml`: a curated manager API spec. The canonical manager spec is `docs/user-guide/api-docs/api.yaml`. Both `/auth` and `/import-scene/` are in that token spec; this fuzzing grammar leaves them out. `/auth` is called separately to obtain the token, and `/import-scene/` is a multipart ZIP upload. `/save-geospatial-snapshot/` is not in the token spec: it is a browser session endpoint.
- `run_fuzzing.sh`: script that will run inside the RESTler container for the manager API. Sets up the environment and authentication token, compiles the grammar, patches it so requests reuse the scene created earlier in the sequence, and executes the fuzzing run.
- `run_service_fuzzing.sh`: shared runner for service-specific campaigns. Compiles the canonical spec, pins or seeds identifiers that must exist on the deployment (see [Fuzzing additional services](#fuzzing-additional-services)), runs RESTler, and moves the results into `<test mode>/<service name>/`.
- `run_autocalibration_fuzzing.sh`: runner for the Auto Camera Calibration API.
- `run_mapping_fuzzing.sh`: runner for the Mapping API.
- `mapping_upload_fuzzing.py`: targeted multipart upload fuzzing for Mapping `POST /reconstruction`, which RESTler cannot generate. Run by `run_mapping_fuzzing.sh`.
- `.env`: list of variables for the fuzzing run. These need to be set before executing a run. See the step-by-step instructions [below](#performing-a-fuzz-test) for information about the specific variables. The file is tracked in Git; do not commit instance-specific values such as your IP address or password.
- `settings.json`: RESTler configuration file.
- `custom_dict.json`: custom RESTler dictionary values for the manager campaign. `run_fuzzing.sh` merges them into the compiled dictionary.
- `token`: template file for the RESTler token auth mechanism. Will be modified at runtime by the test run script.

### Performing a fuzz test

0. Build and deploy Scenescape.
1. Build the RESTler Docker image from source:
   - `git clone https://github.com/microsoft/restler-fuzzer.git`
   - `cd restler-fuzzer`
   - `cp ../manager/secrets/certs/scenescape-ca.pem .`
   - `cp ../tests/security/fuzzing/Dockerfile .`
   - `docker build --build-arg http_proxy=http://proxy-dmz.intel.com:912 --build-arg https_proxy=http://proxy-dmz.intel.com:912 -t restler .`
   - The Dockerfile builds on .NET 8 and patches two RESTler sources: coverage report lookup for sequences with several prerequisites, and a log-file name collision when copying driver logs. The build fails with a message asking you to review the fix if the cloned RESTler source no longer matches the code the patch expects.
2. Edit `.env` and set the following values:
   - `https_proxy` is the outbound web proxy, used to fetch package dependencies.
   - `instance_ip` is the IP address of the instance under test.
   - `auth_username` is the superuser of your instance (usually `admin`).
   - `auth_password` is the superuser's password (usually whatever `SUPASS` was when you deployed). The username and password are used only by the manager campaign. The Auto Calibration and Mapping runners send no credentials.
   - `restler_mode` is the RESTler mode to run. Supported values are `fuzz`, `fuzz-lean`, and `test`. See RESTler documentation for more details.
   - `time_budget_hours` is the length of time, in hours, that the `fuzz` mode will spend testing the API.
3. From the fuzzing folder, execute the Docker command to launch a RESTler container and run our script:
   - `cd tests/security/fuzzing`
   - `docker run --rm -v "$(pwd)":/workspace -e USER_ID=$(id -u) -e GROUP_ID=$(id -g) restler /workspace/run_fuzzing.sh`
4. When testing finishes (this takes a long time!), results are stored in
   `<test mode>/<service name>/` below this directory. For example:
   `Fuzz/manager/`, `Test/autocalibration/`, or `Fuzz-lean/mapping/`. The test
   mode directory is derived from `restler_mode`: `fuzz` becomes `Fuzz`,
   `fuzz-lean` becomes `Fuzz-lean`, and `test` becomes `Test`. See the RESTler
   documentation for more about how to interpret the results of a run, or talk
   to your security team!

### Reading the results

Each `<test mode>/<service name>/RestlerLogs/` directory contains:

- `RestlerResults/experiment<N>/logs/testing_summary.json`: final spec coverage (`final_spec_coverage`), requests sent, and `bug_buckets`. Empty `bug_buckets` means RESTler found no bugs.
- `coverage_failures_to_investigate.txt` (test mode): requests that never returned a valid status, with the request and response that blocked them. Check this first when coverage is lower than expected.
- `RestlerResults/experiment<N>/logs/network.testing.*.txt`: raw request and response traces.
- `ResultsAnalyzerStdErr.txt`: output of RESTler's post-run response analyzer.

The results analyzer has been observed to crash with `Unexpected response without prior request` after a long run. `testing_summary.json` is still written and valid, but `ResponseBuckets/` stays empty, so review the network traces directly if bucketed response analysis matters.

### Fuzzing additional services

The Auto Calibration and Mapping APIs use their own canonical OpenAPI specs and
are run separately from the manager campaign. Their results use the same
`<test mode>/<service name>/` layout as the manager campaign.

Before running a service campaign, make sure the service is deployed and
healthy. Auto Calibration is part of the default Compose services; Mapping
requires the `mapping` profile.

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
`run_mapping_fuzzing.sh`. The runners target the reverse-proxy routes
`/api/v1/autocalibration` and `/api/v1/mapping` on `web.scenescape.intel.com`.
Both service runners read `instance_ip`, `restler_mode`, and
`time_budget_hours` from `.env`; the uppercase environment variables
`INSTANCE_IP`, `RESTLER_MODE`, and `TIME_BUDGET_HOURS` override those values
for a one-off run (pass them with `docker run -e`). `SPEC_SOURCE` overrides the
spec file used.

You can configure the identifiers in `.env` or override them for a single run:

- **Camera:** Set `autocal_camera_id` in `.env` or pass
  `-e AUTOCAL_CAMERA_ID=<camera id>` to `docker run`. The camera must exist and
  belong to a calibration-enabled scene. The runner uses that camera's current
  scene ID.
- **Scene:** To select a scene directly, set `autocal_scene_id` in `.env` or
  pass `-e AUTOCAL_SCENE_ID=<scene uuid>` to `docker run`. The scene ID must be
  a UUID.

For example, set the camera ID in `.env`:

```bash
autocal_camera_id=your-camera-id
autocal_scene_id=your-scene-id #optional
```

#### Troubleshooting

- `command not found`, exit code 127: pass the script as an absolute path in the
  container (`/workspace/run_mapping_fuzzing.sh`), as in the examples.
- Low coverage in `test` mode: see `coverage_failures_to_investigate.txt` in
  [Reading the results](#reading-the-results). Longer runs in `fuzz` mode do not
  fix requests that fail because of missing setup data such as unknown IDs.

### Mapping upload fuzzing

RESTler cannot generate `multipart/form-data` bodies, so the compiled grammar
sends `POST /reconstruction` without any upload and the service rejects it with
`400`. The Mapping runner therefore does two extra things:

- Before fuzzing, it submits a request without files to obtain a real
  `request_id` and injects it into the status endpoint grammar. Rejected jobs
  still have a status record, so `GET /reconstruction/status/{request_id}` is
  exercised with an existing ID. The service discards records after one hour,
  so later requests with that ID return `404`.
- After RESTler finishes, it runs `mapping_upload_fuzzing.py`, which sends
  malformed uploads (corrupt images and video, hostile filenames, invalid
  `camera_ids` and `camera_locations`, broken multipart framing, size limits)
  and checks that the service stays healthy and returns no `5xx`. Accepted
  uploads are polled until their jobs reach `failed`; a `complete`, `processing`,
  or unresolvable job status is reported as a finding. Results are written to
  `<test mode>/mapping/UploadFuzzing/upload_fuzzing_report.json`, and the runner
  exits non-zero when there are findings.

The script sends no known-valid media, but some malformed uploads are accepted
with `200` and start background jobs; the script polls those jobs and requires
them to fail. RESTler cannot exercise the actual multipart upload path, so
`POST /reconstruction` coverage only reflects the `400` response to an empty
request. The upload campaign runs once after RESTler finishes and is not
limited by `time_budget_hours`; oversized uploads take the longest. The size
limit cases upload about 170 MB;
pass `-e MAPPING_UPLOAD_SKIP_LARGE=1` to `docker run` to skip them.

The script uses only the Python standard library, so it can also be run
directly (`seed` and `fuzz` commands, see `--help`). The `.env` file is not
read in that case: pass `--target-ip`.
