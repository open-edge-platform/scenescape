# How to enable different models for inferencing

## What Models are Supported?

Intel® SceneScape supports various models from OpenVINO™ that are suitable for scene analytics, and for convenience uses a short name to identify each (shown in **bold**):

- **pv0078:** person-vehicle-bike-detection-crossroad-0078
- **pv1016:** person-vehicle-bike-detection-crossroad-1016
- **pv0001:** pedestrian-and-vehicle-detector-adas-0001
- **v0002:** vehicle-detection-adas-0002
- **retail:** person-detection-retail-0013
- **hpe:** human-pose-estimation-0001
- **reid:** person-reidentification-retail-0031
- **pv2000:** person-vehicle-bike-detection-2000
- **pv2001:** person-vehicle-bike-detection-2001
- **pv2002:** person-vehicle-bike-detection-2002
- **v0200:** vehicle-detection-0200
- **v0201:** vehicle-detection-0201
- **v0202:** vehicle-detection-0202

Adding additional models can be very easy. For bounding box detection models with output similar to [pv0078](https://docs.openvinotoolkit.org/latest/_models_intel_person_vehicle_bike_detection_crossroad_0078_description_person_vehicle_bike_detection_crossroad_0078.html), edit [model-config.json](../../model-config.json) with the new model's directory path and other information.

## Model configuration

The following model-config parameters are allowed, to be used to help in configuring the inferencing:

- **blacklist**: Detector and GetiDetector classes support blacklisting of detection categories. This means that all detections matching the blacklisted categories will be filtered out. This can be useful when there is different pipeline to process different categories. Expects a list of categories to ignore (`{"blacklist" : ["category1"]}`).
- **categories**: Specify the categories that the inference engine can detect. Auto-populated for GetiDetectors. Expects a list of categories (`{"categories" : ["background", "vehicle", "person"]}`). For YoloV8Detector models, it should specify the yaml file containing the model's known categories. Expects a file path (string).
- **colorspace**: Used to specify if a model should be fed pixel data in a particular colorspace. Valid values are "BGR", "RGB" and "GRAY"; default is "BGR". Expects a string (`{"colorspace": "BGR"}`).
- **directory**: Path to the model's xml/bin files. Expects a directory path (string).
- **external_id**: Used to identify the matching model to use when using an OVMS server. Expects a string.
- **history**: Used by MotionDetector, indicates how many frames to use as history. Expects an integer.
- **keep_aspect**: Tells percebro to maintain the original-frame aspect ratio when scaling input data to the inference engine.
  Expects boolean (0 or 1).
- **model_path**: Used by TrOCR and DSDetector models to specify the path to load the inference engine from. Expects a string.
- **nms_threshold**: Used by DSDetector, parameter used internally for non-max suppression algorithm. Expects a float.
- **normalize_input**: Used to specify that the model expects input values in range [0.0 - 1.0], and thus percebro should normalize the input data. Percebro will feed data in range [0 - 255] otherwise. Expects boolean (0 or 1).
- **normalized_output**: Used to specify that the model's output (specifically the bounding boxes) is in range [0 - 1], and thus percebro should scale the detection according to the model's input shape. Percebro will expect bounding boxes in [0 - model.height], [0 - model.width] otherwise. Expects boolean (0 or 1).
- **output_order**: Used to specify the model's result ordering (namely the category, confidence, and bounding box) when the model has a different shape to the sample ones (from open-model-zoo). See the [output_order](#output_order) section below for more details. Expects a dict.
- **password_file**: Used to specify the filename that contains the password required to decrypt a DSDetector model. Expects a file path (string).
- **pattern**: Used to specify the pattern that a detection must match for TextRecognition engines. Note that the pattern will be compiled (re.compile) into a regex. Special characters (such as '\') must be escaped. Expects a string.
- **secondary_model_path**: Used to specify the path for a second internal model, when required. Used for transformer OCR models. Expects a string.
- **threshold**: Used by detector engines to set an independent threshold for that model, in the range (0.0 to 1.0). Note that it will override the default '-e' option provided to percebro. When used in a MotionDetector, threshold for motion detection, expects an integer.
- **xml**: Used to specify the model's xml file's name, when the Detector class (or subclasses) are unable to guess it. Expects a string.

## output_order

If the model's output is different than the default (see the description about the retail model below), specify the required parameters for Intel® SceneScape to understand the model in the [model-config.json](model-config.json).
The following parameters are required. Note these are all per-detection indexes:

- **category** of the detection (entry in labels list) that represents the label for the detected object.
- **confidence** of the detection.
- **originX** left-most bounding pixel for the detection.
- **originY** top-most bounding pixel for the detection.
- **oppositeX** right-most bounding pixel for the detection
- **oppositeY** bottom-most bounding pixel for the detection.

The **retail** model serves as an example for the default output format. It is as follows ([from OMZ](https://github.com/openvinotoolkit/open_model_zoo/tree/master/models/intel/person-detection-retail-0013#outputs)):

```
[image_id, label, confidence, x_min, y_min, x_max, y_max]
```

Making the 'output_order' entry (note this is the default):

```
"output_order": {"category":1, "confidence":2, "originX":3, "originY":4, "oppositeX":5, "oppositeY":6 }
```

Note that the 'label' entry refers to the detection category.

For a model with the following output order:

```
[label, x_min, y_min, x_max, y_max, confidence]
```

The corresponding 'output_order' parameter to handle this model would be:

```
"output_order": {"category":0, "confidence":5, "originX":1, "originY":2, "oppositeX":3, "oppositeY":4 }
```

Note: If the model does not have a category index (for single-class detectors for example), specify "category" as -1.

If the detector does not provide output in this straight-forward way (for example, post-processing of the output is required to generate top-left bottom-right bounding boxes), create a class in [detector.py](../../detector.py) to determine how it should be handled.

By default, a small set of OMZ models are downloaded during the build. All OMZ models (supported by scenescape) can be downloaded by using any of these commands-

```
make install-models MODELS=all
```

or,

```
make install-models MODELS=all
```

Please note that the default precision for OMZ models is FP32. Other precisions (e.g., FP16, FP16-INT8) can be downloaded using the command below-

```
make install-models PRECISIONS=FP32,FP16
```

## Transformer based OCR models

Transformer OCR models are supported by default, using the 'transformers' library.
In order to instantiate one of these models, a model-config sample is shown.

```
[
    {   "model": "trocr", "engine": "TrOCR",
        "pattern": "\\d{4}\\s[a-zA-Z]{3}",
        "model_path":"microsoft/trocr-base-printed"
    }
]
```

Please note that the transformer library will internally download and instantiate the model, at runtime.

Typically, a pre-stage is used to find text areas of interest before feeding to the OCR inference model. A sample config including a Geti-trained text-detector, is shown:

```
[
    {   "model": "textdet", "engine": "GetiDetector", "keep_aspect": 1,
        "directory": "/opt/intel/openvino/deployment_tools/intel_models/textdet",
        "categories": ["arabic", "english"],
        "blacklist": ["arabic"]
    },
    {   "model": "trocr", "engine": "TrOCR",
        "pattern": "\\d{4}\\s[a-zA-Z]{3}",
        "model_path":"microsoft/trocr-base-printed",
        "secondary_model_path":"microsoft/trocr-base-printed"
    }
]
```

Note that the `model_path` path is tied to the TrOCRProcessor engine, while the `secondary_model_path` will be tied to the VisionEncoderDecoderModel. This allows for having independent locally trained models or versions of each.

For completeness, the sample percebro command to instantiate this text-detection + OCR pipeline is:

```
$ percebro/percebro -i video.mp4 --intrinsics=70 -m textdet+trocr broker
```

Note about Proxy:
When percebro is run inside a container and behind a proxy, said proxy configuration must be added in the docker-compose.yml corresponding service entry, in order for the TrOCR Detector to be able to reach the outside network. This can be achieved by passing the 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', or 'no_proxy' variables, as required.

```
  retail-video:
    image: scenescape:<version>
    init: true
    networks:
      scenescape:
    depends_on:
     - broker
     - ntpserv
    environment:
     - "DS_MODULE"
     - "HTTP_PROXY"
     - "HTTPS_PROXY"
     - "NO_PROXY"
     - "http_proxy"
     - "https_proxy"
     - "no_proxy"
    command:
```

## Yolo Object Detection Models

To enable percebro container to work with a YOLO object detection model, you need to install ultralytics package in percebro container. You can either add `ultralytics==8.0.43` to percebro/requirements-runtime.txt and rebuild percebro container using `make -C percebro`. Alternatively, you can create your own container that uses scenescape-percebro as the base image and pip install ultralytics package in the new Dockerfile. Consequently, you should edit the docker-compose.yml file to use your newly built container.

# How to enable 3D Vehicle Detection Model from DeepScenario

Percebro supports [DeepScenario](https://www.deepscenario.com) models which generate 3D bounding box detections.
In order to instantiate these models, 4 files are required:

- The **encrypted model** ('model.enc' in this example)
- The file containing the **password** for the model ('password.txt' in this example)
- The file containing the detectable **categories** ('categories.json' in this example)
- The file containing the **DeepScenario APIs** ('utils.py' in this example)

For purposes of this example, these 4 files will be assumed to be located in a directory 'models/deepscenario'. Note the path inside the container will become '/opt/intel/openvino/deployment_tools/intel_models/deepscenario':

Note these files are NOT provided by Intel® SceneScape, and thus must be explicitly mounted into the container. In this example, we will be using the already existing volume mount of './model_installer/models' into '/opt/intel/openvino/deployment_tools/intel_models'. Care must be taken to ensure these files are available to the percebro container as necessary.

## Model configuration files

As with other models, a corresponding entry in a model-config JSON file must be created. Note the necessary entries **model_path**, **password_file**, and **categories**:

```
$ cat models/deepscenario/ds-model-config.json

[
  {
    "model": "vehicle3d", "engine" :"DetectorDS",
    "directory": "ignore",
    "model_path":"/opt/intel/openvino/deployment_tools/intel_models/deepscenario/model.enc",
    "password_file":"/opt/intel/openvino/deployment_tools/intel_models/deepscenario/password.txt",
    "categories": "/opt/intel/openvino/deployment_tools/intel_models/deepscenario/categories.json",
    "nms_threshold": 0.65
  }
]
```

Additionally, in order for Intel® SceneScape to properly load the DeepScenario APIs, the **DS_MODULE** environment variable must be specified:

`$ DS_MODULE=/opt/intel/openvino/deployment_tools/intel_models/deepscenario/utils.py`

This variable can either be exported before bringing up the system (via `docker compose up`), or can be set in a `.env` file, as supported by docker:

```
$ cat .env
DS_MODULE=/opt/intel/openvino/deployment_tools/intel_models/deepscenario/utils.py
```

## Docker compose configuration

Finally, in order to complete the system configuration, the relevant percebro container configuration must be updated both with environment variable settings we just described. Ensure the path to the ds-model-config.json file is also relative to the container:

```
  garage-video:
    image: scenescape:<version>
    init: true
    networks:
      scenescape:
    depends_on:
     - broker
     - ntpserv
    environment:
     - "DS_MODULE"
    command:
     - "percebro"
     - "--camera=parkingCamera1.mp4"
     - "--cameraid=camera1"
     - "--intrinsics={\"fov\":70}"
     - "--camerachain=vehicle3d"
     - "--modelconfig=/opt/intel/openvino/deployment_tools/intel_models/deepscenario/ds-model-config.json"
     - "--ntp=ntpserv"
     - "--auth=/run/secrets/percebro.auth"
     - "broker.scenescape.intel.com"
    devices:
      - "/dev/dri:/dev/dri"
    volumes:
     - ./model_installer/models:/opt/intel/openvino/deployment_tools/intel_models
    secrets:
     - certs
     - percebro.auth
    restart: always

```

## System Bring up

After a successful DeepScenario model load, you should be able to query the docker container's logs, and observe the string 'DetectorDS: Success loading module':

```
$ docker logs applicationsaiscene-intelligenceopensail-retail-video-1 -f
TIMEZONE IS
2024-04-10 17:42:42 Broker broker.scenescape.intel.com:1883 online: Connecting
2024-04-10 17:42:43 Broker broker.scenescape.intel.com:1883 online: 0
Took 1 seconds
Container is ready
2024-04-10 17:42:46 Getting MAC the hard way
2024-04-10 17:42:46 HW Accel unavailable
2024-04-10 17:42:46 HW Accel unavailable
2024-04-10 17:42:46 Range camera1 0 178.5
2024-04-10 17:42:46 Range camera2 0 178.5
2024-04-10 17:42:46 DetectorDS: Loading dependencies
2024-04-10 17:42:46 DetectorDS: Success loading module
2024-04-10 17:42:46 Starting model vehicle3d on CPU
```
