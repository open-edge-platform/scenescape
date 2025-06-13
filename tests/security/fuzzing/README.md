## RESTler for fuzzing the SceneScape REST API

### Overview

RESTler is an [open-source](https://github.com/microsoft/restler-fuzzer) REST fuzzer from Microsoft. It compiles an OpenAPI spec into a fuzzing grammar, then runs automated testing against the API.

On SceneScape, RESTler is used satisfy the CT631 SDL task, which specifies fuzz testing requirements for products with REST APIs. It's also a good way to discover edge cases that are unlikely to surface through manual testing.

### Fuzz testing repo contents

This directory contains the following:
* `fuzzing_openapi.yaml`: a customized version of the SceneScape OpenAPI spec, designed to reflect the reality of the API as closely as possible, whereas `docs/api/api.yaml` represents how the API should look in theory. The more accurate the spec, the better the fuzzing results will be.
* `run_fuzzing.sh`:  script that will run inside the RESTler container. Sets up the environment, then compiles the grammar and executes the fuzzing run.
* `.env`: list of variables for the fuzzing run. These need to be set before executing a run. See the step-by-step instructions [below](#performing-a-fuzz-test) for information about the specific variables.
* `settings.json`: RESTler configuration file.
* `token`: template file for the RESTler token auth mechanism. Will be modified at runtime by the test run script.

### Performing a fuzz test

0. Build the RESTler Docker image from source:
    * `git clone https://github.com/microsoft/restler-fuzzer.git restler && cd restler && docker build -t restler .`
1. Deploy SceneScape.
2. Copy your generated root CA (usually `manager/secrets/certs/scenescape-ca.pem`) to the fuzzing folder (`tests/security/fuzzing`)
3. Edit `.env` and set the following values:
    * `https_proxy` is the outbound web proxy, used to fetch package dependencies.
    * `instance_ip` is the IP address of the instance under test.
    * `auth_username` is the superuser of your instance (usually `admin`).
    * `auth_password` is the superuser's password (usually whatever `SUPASS` was when you deployed).
    * `restler_mode` is the RESTler mode to run. Supported values are `fuzz`, `fuzz-lean`, and `test`. See RESTler documentation for more details.
    * `time_budget` is the length of time, in hours, that the `fuzz` mode will spend testing the API.
4. From the fuzzing folder, execute the Docker command to launch a RESTler container and run our script:
    * `docker run --rm -v ./:/workspace restler sh /workspace/run_fuzzing.sh`
5. When testing finishes (this takes a long time!), you will have results in the `Fuzz`, `FuzzLean`, or `Test` folders, depending on which RESTler mode you ran. See the RESTler documentation for more about how to interpret the results of a run, or talk to your security team!
