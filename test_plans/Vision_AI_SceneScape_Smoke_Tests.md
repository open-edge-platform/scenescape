# Vision_AI/SceneScape/Smoke Tests: Test Suite

## Test suite requirements mapping

- FAREQ-242: API documentation must be made available with the software package
- ITEP-69797: Test to measure the scenescape build happens under 10 mins
- ITEP-73648: Wrong path to the API specification in documentation
- SAIL-1161: Test docker-compose.yml README
- SAIL-1298: Write a best practices/guideline document for establishing test writing standards for Scenescape
- SAIL-1336: Test upgrade of Scenescape from previous to current version
- SAIL-1360: Track the different aspects of building a REST API for Intel SceneScape
- SAIL-1542: Verify API documentation is included in the software package
- SAIL-155: [Spike] Develop Getting Started Guide
- SAIL-1793: API Tests
- SAIL-2000: Coding Standards & Practices Fixes
- SAIL-2049: As a SceneScape user, I want to have clear instructions in the README on supported Intel platforms.
- SAIL-2160: Automate the test upgrade of Scenescape from previous to current version
- SAIL-2314: Upgrade from previous PV (2023.1.1) fails
- SAIL-2454: As a user, I want to read the readme docs via the web server
- SAIL-2581: EC.44 --> Software Coding Quality plan v1.0
- SAIL-2826: UUID migration fails from prior release
- SAIL-2941: SceneScape deployment fails on a fresh machine because of missing VDMS keys
- SAIL-3111: Installation Start Guide link is not updated
- SAIL-3202: In README.md, Learn More section, have a similar set of contents like the web service documentation pages
- SAIL-347: [Ci] [CodingConvention] Implement code cheking according to python coding standards
- SAIL-518: User and Developer Experience Improvements
- SAIL-885: System Test Plan

## Test suite setup

### Hardware Requirements

### Test suite prerequisites

-
- Scenescape deployed

## Vision_AI/SceneScape/Smoke Tests/01: Verify root directory README file

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- A README file should be present in the root directory of the source code repository.

### Test requirements mapping

- SAIL-1161: Test docker-compose.yml README
- SAIL-885: System Test Plan
- SAIL-518: User and Developer Experience Improvements
- SAIL-2049: As a SceneScape user, I want to have clear instructions in the README on supported Intel platforms.
- SAIL-3202: In README.md, Learn More section, have a similar set of contents like the web service documentation pages

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. A README file should be present in the root directory of the source code repository.
   - Test data: `# ls -l README.md`
1. The same file should be the top page in the SceneScape Documentation navigation panel.
   - Test data: `1. Make sure that SceneScape is up and running.

# ./deploy.sh

2. Login into the web UI and select the 'Documentation' page from the top bar.
3. Select the first entry in the left navigation panel.`

## Vision_AI/SceneScape/Smoke Tests/02: ​Test upgrade of Scenescape from previous to current version

**Affected Versions:** 2023.4, 2024.1, 2023.1, 2023.3, 2023.2, 2024.2

### Test summary

- Verify that Scene Scape works accordingly after migrating from an older version to a newer one

### Test requirements mapping

- SAIL-1336: Test upgrade of Scenescape from previous to current version
- SAIL-2826: UUID migration fails from prior release
- SAIL-2314: Upgrade from previous PV (2023.1.1) fails
- SAIL-2941: SceneScape deployment fails on a fresh machine because of missing VDMS keys
- SAIL-2160: Automate the test upgrade of Scenescape from previous to current version

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Download the old backup of Scene Scape,  "scenescape_2023.4.6-beta.tar",  from attachments. Copy it and unzip it into the latest Scene Scape git repo.
   - Test data: `# git status

# tar -xvf scenescape_2023.4.6-beta.tar`

1. Regenerate the TLS certificates and start the deployment of Scene Scape. Proceed with yes when prompted to backup the database.
   - Test data: `# make -BC certificates deploy-certificates

# ./deploy`

1. Launch the Scene Scape web browser page, login using the credentials provided during deployment and check that everything behaves properly
   - Test data: `https://&lt;ip_address&gt;" or "https://&lt;hostname&gt;"`

## Vision_AI/SceneScape/Smoke Tests/03: Make CI/CD validate that Python indentation conforms to standard

**Affected Versions:** 2022.2, 2023.4, 2024.1, 2022.4, 2023.1, 2022.1, 2023.3, 2023.2, 2024.2

### Test summary

- Need to have CI/CD check to make sure that all Python scripts are indented using 2 spaces, not 4. This can probably be done by re-using the Python indentation tool and setting it to use 2 spaces and then comparing the output against the original file.

Note: No FAREQ or SAIL JIRA requirement to link with this Test Case, but see the SceneScape team Coding Standards &amp; Practices

### Test requirements mapping

- SAIL-2000: Coding Standards & Practices Fixes
- SAIL-1298: Write a best practices/guideline document for establishing test writing standards for Scenescape
- SAIL-347: [Ci] [CodingConvention] Implement code cheking according to python coding standards
- SAIL-2581: EC.44 --> Software Coding Quality plan v1.0

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1.

## Vision_AI/SceneScape/Smoke Tests/04: Verify API documentation is included in the software package

**Affected Versions:** 2024.1, 2024.2

### Test summary

- This test should verify that API documentation is included in the software release package and can be viewed by a user in a web browser. 
  Swagger generated documentation is an example of expected format

### Test requirements mapping

- FAREQ-242: API documentation must be made available with the software package
- SAIL-1542: Verify API documentation is included in the software package
- SAIL-2454: As a user, I want to read the readme docs via the web server
- SAIL-518: User and Developer Experience Improvements
- SAIL-1793: API Tests
- SAIL-1360: Track the different aspects of building a REST API for Intel SceneScape
- ITEP-73648: Wrong path to the API specification in documentation

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Bring up the SceneScape Web UI.
   - Test data: `# ./deploy.sh`
1. Navigate to the 'Documentation' button from the top panel.
1. From the left navigation panel, select the instruction to view the API page.
   - Test data: `The navigation path is: SceneScape -&gt; Instructions for the viewing the API spec:`
1. Follow the steps in the Instruction page to open the Swagger API viewer.

## Vision_AI/SceneScape/Smoke Tests/05: Review Getting Started Guide

**Affected Versions:** 2024.1, 2024.2

### Test summary

- Review the latest version of the Getting started guide to ensure it will meet the needs of a new user of SceneScape:

Example location for main branch:
https://github.com/open-edge-platform/scenescape/blob/main/docs/user-guide/getting-started-guide.md

### Test requirements mapping

- SAIL-155: [Spike] Develop Getting Started Guide
- SAIL-518: User and Developer Experience Improvements
- SAIL-3111: Installation Start Guide link is not updated

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. In the repo folder open README.md file
1. Open the "Getting Started" link
1. Follow the guide:Perform the instructionsCheck if the instructions are clear and up to dateLook for typos and formatting issuesVerify if every step is appropriately explained and commented

## Vision_AI/SceneScape/Smoke Tests/06: Check GPU acceleration Kubernetes is enabled

**Affected Versions:** 2024.2

### Test summary

-

### Test requirements mapping

-

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Build SceneScape with Kubernetes support
   - Test data: `make -C kubernetes`
1. Enter in SceneScape web interface
   - Test data: `https://&lt;hostname&gt;`
1. Configure camera with GPU support
   - Test data: `Insert "retail=GPU" in modelchain
     Insert "GPU" in CV Advanced subsystem.

Inspect with intel_gpu_top GPU usage`

1. Remove Kubernetes cluster
   - Test data: `make -C kubernetes clean-all`

## Vision_AI/SceneScape/Smoke Tests/07: Test to measure the scenescape build happens under 10 mins

**Affected Versions:**

### Test summary

- Test is supposed to check if building new environment for deployment of SceneScape takes less than 10 minutes.

### Test requirements mapping

- ITEP-69797: Test to measure the scenescape build happens under 10 mins

### Test priority

- P3

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Clean the environment using commands "make clean-all" and "docker builder prune -af"
1. Deploy the application using "make" or "make build-all" command
1. Measure build time
