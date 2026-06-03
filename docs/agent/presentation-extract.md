# Slide 1: Example Use Case: Smart-Parking

User’s goals:
- Detect cars position and trajectory in time. Minimize identity switches during tracking.
- Recognize license plate (mostly local plates) for each car entering / exiting the parking.
- Get the most performance out of Intel hardware.

Installed cameras:
- Entrance front view
- Exit front view
- Bird-eye view (overlapping field of view with the others two)

# Slide 2: Technical Problems: How Intel Helps to Solve

„ Detect cars position and trajectory in time with minimized identity switches”  solved by SceneScape
- Cross-camera fusion in 3D required to assign license plate numbers to tracked objects
- Re-identification (based on visual embeddings)  needed to better maintain identity

„Build Optimal Visual Pipelines for AI Tasks”  solved by VIPPET:
- AI Task 1: detect car from high angle view with re-identification (with bird-eye view camera)
- AI Task 2: Licence Plate Recognition (with etry / exit front view cameras)

„Train Custom AI Models”  solved by Geti:
- Public models do not detect cars from bird-eye view well enough
- Public models do not detect local licence plates well enough

# Slide 3: Building Solution: Exapmle of Step-by-Step Process

Note: This is an example flow, other are possible too (for example SceneScape can be set up first).

1. Camera Setup (detect camera IPs)
2. Data Acquisition (synchronized video capture from all cameras with cars on the parking)
3. Geti Training* [optional]
4. DLS Pipeline Development (VIPPET)*
5. Scene Setup & Development (SceneScape)
6. Production Package Preparation (export artifacts)
7. Deployment (import artifacts and run on edge device)

Multiple iterations possible for steps 2-5
*) Steps repeated for both LPR and top-view car detection with Re-ID

# Slide 4: Building Solution: Step-by-Step Process

[Process Model page from DrawIO diagram]

# Slide 5: Building End-to-End Solution: What does not help?

No video capture from cameras => User needs to capture on their own and manually upload to Geti.
No integration between SceneScape and VIPPET. Both have incompatible model management and pipeline building solutions.
Complexity of using Geti trained / custom model in SceneScape => user needs to upload model to K8S / Docker volume and edit configuration file(s) manually
Using a pipeline built with VIPPET in SceneScape => No straightforward way to use it in DLSPS and SceneScape. Pipeline configuration is different.

# Slide 6: Why VA Platform (MLOps) integration and reuse?

Improve user’s time needed to build a solution and experience with OEP:
- Provide consistent ecosystem of complementary and interconnected but still independent (generic) services with clear responsibilities and API
- Reduce deployment / configuration effort and complexity for common MLOps use cases
- Eliminate manual steps where possible to minimize iteration time (from initial setup and experimentation to evaluated production-ready solution)

Increase reuse across OEP (reduce redundancy & maintanance burden), examples:
- Reuse VIPPET pipeline building feature in SceneScape
- Reuse VIPPET (Model Downloader) for model management in SceneScape
- Use a common pipeline definition format and a common pipeline runner backend (DLSPS) across VIPPET and SceneScape

# Slide 7: Goals for 2026.1 Release

Identify user flows for common use cases with SceneScape
Identify main components and their:
Roles and responsibilities (clear separation of concerns)
High level interactions & Dependencies
Define & document high level architecture that will be input for per-component design and requirements.
Define initial set of high-level requirements.
Identify a subset of requirements to be included in 2026.2 Engineering Commit.

Feature link
Note: SceneScape – VIPPET integration is higher priority than with Geti but we aim at future-proof design that covers all of them.

# Slide 8: Components: High Level Interactions

[Component Interaction Page from DrawIO diagram]

# Slide 9: VA Platform Integration: Proposed Timeline

Phase 1 (2026.1)
[As in the slide 7]

Phase 2 (2026.2):
1. Model Downloader (Manager) integration
2. Switch to Gst Analytics Python
3. Simplify / break down Python adapter (phase 1)
4. VIPPET integration design
5. Stream Manager integration design

Phase 3 (2026.3):
1. VIPPET integration (phase 1)
2. Simplify / break down Python adapter (phase 2)
3. Stream Manager integration (phase 1)

Phase 4 (2027.0):
1. VIPPET integration (phase 2)
2. Stream Manager integration (phase 2)


# Silde 10: Requirements for SceneScape – Model Manager (Model Downloader) integration implementation

SceneScape:
- All model download in SceneScape is performed via Model Downloader
- Deploy Model Downloader as part of SceneScape demo / sample apps with model storage shared with DLSPS
- User can reuse common Model Downloader instance across VIPPET and SceneScape deployments (models downloaded in VIPPET are autoamtically accessible in SceneScape and vice versa) when SceneScape is deployed in Docker Compose and Kind
- SceneScape uses Model Downloader REST API to download a predefined set of models on deployment of SceneScape demo / sample app
- SceneScape uses Model Downloader REST API for listing of downloaded models and using them in dynamically configured pipelines
- A new set of default models downloaded for SceneScape is selected and verified

Model Downloader:
- Set of already downloaded models, their paths within storage and metadata is available in run-time via REST API
  - Covered by feature ITEP-92375.xml (specifically persistent registry, GET models w/ metadata)
- Model metadata should include model name / ID, precision, public download reference / Geti reference, checksum, optional attributes
- Automatically check model existence in the target path and skip download for cached models that have been already downloaded [partially supported , improvements planned as part of 2026.2 feature scope]

# Slide 11: Requirements for SceneScape – VIPPET – DLSPS integration (design)

SceneScape:
- Deploy DLSPS as part of SceneScape demo / sample apps with model storage shared with Model Manager
- Deploy DLSPS as part of SceneScape demo / sample apps with a generic static config (no predefined pipeline definition or pipeline count)
- User can configure SceneScape statically and  in run-time to use specific VIPPET instance (host, port, token / credentials)
- Use VIPPET REST API for retrieval of pipeline definitions by name (ID) and version
- Use DLSPS REST API for run-time instantation, starting and stopping of individual camera streams
- Store pipeline definition templates (in a format compatible with VIPPET and DLSPS) as part of Scene configuration independently from scene cameras (video sources) configuration
- Allow to associate pipeline definition with one or more video sources (camera, file) as part of Scene configuration
- Allow user to specify parameters of pipeline definition template via UI per camera (incl. video source (no default value), camera ID (no default value), model precision (with default value), inference device for each model (with default value), NTP usage - (with default value), classified object class, per camera confidence threshold)
- Allow user to start and stop camera streams via REST API and UI

VIPPET:
- User can customize any pipeline built in VIPPET to be compatible with SceneScape pipeline requirements (either automatically or manually by adding predefined elements). User can run and verify SceneScape-customized pipeline just as any other pipeline.
- Multiple version of a pipeline definition are maintained and can be retrieved by pipeline ID and version via API [versions can be supported with pipeline variants existing in VIPPET]
- User can use arbitrary model chain (multi-stage inference) in a SceneScape pipeline definition template with arbitrary models (Phase 1: cover 80% customer use cases with most representative predefined templates provided by SceneScape team)
- User can modify a model chain in a SceneScape pipeline definition template, including adding / removing / editing inference stages and builting arbitrary multi-stage pipelines with arbitrary models (UI-driven or intent-driven using AI Agent) (Phase 2: cover all of customer use cases with full configurability)
- Any pipeline definition template built with VIPPET can be get via API in a format compatible with DLSPS
- Pipeline definition exposed via REST API should either contain complete model metadata or contain a unique model ID that allows to retrieve complete model metadata via Model Downloader REST API in a separate query (to allow for retrieval / identification of a specific model after pipeline building process is completed). This should be possible for each model used in the pipeline.
- Pipeline definition exposed via REST API should either contain model path within storage or contain a unique model ID that allows to retrieve model path via Model Downloader REST API in a separate query (to allow running the pipeline with DLSPS). This should be possible for each model used in the pipeline.
- Pipeline definition exposed via REST API should be a template that allows for partial parametrization within SceneScape per each instantated pipeline. The pipeline definition parameters list includes, but is not limited to: video source (no default value), camera ID (no default value), model precision (with default value), inference device for each model (with default value), NTP usage (with default value), classified object class.

DLSPS:
- Any pipeline definition template built with VIPPET can be instantiated in run-time via DLSPS REST API using a generic static config (no hard-coded static config / pipeline template dependency)
- Arbitrary number of pipelines with a common pipeline definition and multiple video sources can be instantiated with cross-stream batching via DLSPS REST API

# Slide 12: Requirements for SceneScape – DLStreamer integration

SceneScape:
- SceneScape Python adapter functionality analyzed for replacement with native / custom DLS elements (design/implementation)
- Use Gst Analytics Python instead of gvapython for custom logic (implementation)

DLS:
- Subset of SceneScape Python adapter functionalities become DLS features / built-in / custom plugin elements (design/implementation)

# Slide 13: Requirements for SceneScape – Stream Manager integration

SceneScape:
- User can configure SceneScape statically in helm chart to use external Stream Manager instance (host, port, token / credentials)
- User can list available cameras and video captures in UI (using Stream Manager REST API) along with their metadata (stream / camera ID, stream URL, capture timestamp etc.)
- User can select multiple synchronized captured video files as video sources in SceneScape pipelines
- SceneScape DLSPS pipeline sends video streams from multiple cameras with absolute timestamps to Stream Manager service for online / offline video analysis (enabled / disabled by SceneScape deployment static configuration)

Stream Manager (Intel VST):
- [Video capture] Synchronized video capture from a selected subset of cameras to files (may use NTP timestamps from cameras if available). Store association of individual files to cameras and association of files to each other by timestamp {start, end} pair.
- [Video capture] Available cameras, RTSP streams and captured video files can be listed using REST API
- [Video offline/online analysis] Multiple video streams are received over network with absolute timestamps and with camera ID
- [Video offline/online analysis] Multiple video streams are stored with absolute timestamps and with camera ID
- [Video offline/online analysis] Individual video frames are retrieved by absolute timestamps and camera ID
- [Video offline/online analysis] Video frame collections are retrieved by absolute timestamp range and camera ID
- Synchronized view and RTSP feed from multiple cameras (may use NTP timestamps from cameras if available).
