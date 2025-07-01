# Custom model integration

Intel® SceneScape handles inference models using a **Detector** class, which interacts with OpenVINO, by loading and configuring inference models, pre-processing input data, handling asynchronous inference, and post-processing the results.

In order to enable a custom, synchronous inference model into Intel® SceneScape, a similar **Detector** class must be defined, that can handle model configuration, pre-processing, inference, and post-processing in a similar way.

There are 2 modules that enable the use of inference models, and 2 configuration files that specify which model to load, and how to configure the model.

The modules are the **Detector**, which defines how the inference model will be loaded and interacted with, and the **Inferizer**, which instantiates the Detectors.

The configuration files are the *model-config.json*, which links a camerachain name with a **Detector** and specifies configuration parameters, and *docker-compose.yml* which is used to instantiate and configure the video analytics pipeline within Intel® SceneScape as a whole.

This document specifies 5 steps required to enable a model of this type:

- [Prerequisites](#prerequisites) : Changes in the build configuration files to add any 3rd-party pre-requisites.
- [Detector](#detector): How to define the Detector class, and required hooks to integrate with Intel® SceneScape's video pipeline (Percebro).
- [Inferizer](#inferizer): Changes to the inferizer module to find the new Detector class that will manage the new model.
- [Build](#build): Changes to the build system to integrate the new custom Detector.
- [Configuration](#configuration): Creating and updating configuration files to run the video pipeline using the newly defined model.

## Prerequisites

For system-wide packages (installed using apt), add the package into the RUN command in *percebro/Dockerfile*:

```
...
RUN : \
    ; apt-get update \
    ; apt-get install -y --no-install-recommends \
        # Keep package list in alphabetical order
        cmake \
        my-system-package \
    ...
```

Add any additional Python-specific requirements not already satisfied by Intel® SceneScape in *percebro/requirements-buildtime.txt* and *percebro/requirements-runtime.txt*.

```
# Keep package list in alphabetical order
...
urllib3
my-pip-package
```

## Detector
To integrate a custom model with Intel® SceneScape, a translation layer between the inference model and Intel® SceneScape is required both to preprocess and feed data into the model and to report out the inference results. This is done using a class derived from the **Detector** class.

The base **Detector** class is implemented in *percebro/src/detector.py*, and it is the base class used to interact with OpenVINO-based deep learning models and other computer vision techniques.

The new Detector class being implemented must be derived from this base class,
and extend or overload the functionality described below.

### Derived class

Derived Detectors need to import the **Detector** base class, as well as the **IAData** container class for input and output data, from *manager.detector*.

### APIs required for **synchronous** detector module deployment:

#### **__init__**(self, asynchronous=False, distributed=False)

##### arguments

###### **asynchronous**

Boolean flag indicating the model should be run in asynchronous mode. Ignore/set to False.

###### **distributed**

Boolean flag indicating the model should be run in distributed mode. Ignore/set to False.

As mentioned earlier, the new Detector class (called **MyDetector** in these examples) must be derived from the parent **Detector** class.
This class will be initialized as part of the **Inferizer**'s initialization.
For OpenVINO models, if there is any step to bring up the model, like model decryption, this is the best place to do so.

At the end of your model's required initialization, call the `super().__init__()` function, to ensure the base class is properly initialized.

```
from manager.detector import Detector, IAData

class MyDetector(Detector):
  def __init__(self, asynchronous=False, distributed=False):
    self.infer = load_module()
    super().__init__(asynchronous=False, distributed=False)
    return

  def load_module():
    # Load module,
    # Get function pointer to inference call:
    infer_ptr = ...
    return infer_ptr
```


#### **loadConfig**(self, mdict)

This function is used to configure the *Detector* modules with the parameters requested in the *model-config.json* file. It receives a dict (`mdict`) containing the configuration options for the instantiated model. See more about this file in [Configuration](#configuration).

Note that the options in each model entry are sanitized and only the options listed in *percebro/inferizer.py* `valid_entries` list will be propagated.
 example: `blacklist`, `categories`, `colorspace`, etc.

```
  def loadConfig(self, mdict):
    self.param1 = mdict['model_param1']
    ...
    self.categories = None
    if 'categories' in mdict:
      if isinstance(mdict['categories'], list):
        self.categories = mdict['categories']

    return
```

#### **configureDetector**(self)

This function typically configures OpenVINO parameters (such as number of threads, streams, input and output blob shapes, etc), so it must be defined as empty for use cases when the inference will be done outside of Intel® SceneScape's OpenVINO infrastructure.

```
  def configureDetector(self):
    return
```

#### **detect**(self, input, debugFlag=False)

This function typically performs the pre-processing required before inference on each input frame, as well as performing the inference synchronously, or trigger the inference for asynchronous models.

For an example of a synchronous, non-OpenVINO detector, please see *manager.detector_atag.py*.

##### arguments

###### **input**

Note the `input` is either `None`, or of type **IAData** (defined in *percebro/src/detector.py*)
   and will have the following attributes:
- `id` : UUID of the input buffer.
- `data` : list containing frames to process (of type numpy array, as read from cv2).
- `cam` :  Camera Matrix of the camera that captured the frames for this input object. The format is `[[fx, 0, cx], [0, fy, cy], [0, 0, 1]]`.
- `max_distance_squared`: The square of the max distance configured for objects. Objects farther away than this value should be discarded by the detector.

Calling detect with input is None is used to allow the queue-management logic to run
even if there is no input data to process.

###### **debugFlag**
`debugFlag` is unused.

##### Processing detections and expected output

The detection results of each image being processed (entries in `input.data`) needs to be encapsulated by an **IAData** object.
The **IAData** constructor requires:
`data` : the data itself
`id` : the input buffer
`save` : any data related to this frame that might be needed to post-process the results. The `max_distance_squared` parameter must be passed in this fashion as well, to allow for distance-based filtering.

These results must be presented in a list, and appended to the Detector's `tasksComplete` list.
Note that the `tasksComplete` list should be protected by acquiring the Detector's `taskLock`.

After this is done, the base class' `detect` function should be called, with input set to `None`,
to ensure the results are propagated to the appropriate internal queues.

```
  def detect(self, input, debugFlag=False):
    if input:
      results = []
      for frame in input.data:
        input_data = preprocess_frame(frame)
        output_data = self.infer( input_data, params... )
        results.append(IAData(output_data, input.id, [params..., input.max_distance_squared]))

      self.taskLock.acquire()
      self.tasksComplete.append(results)
      self.taskLock.release()

    return super().detect(None)
```

#### **postprocess**(self, result)

This function is used to post-process the results of the inference step,
and produce and present them in a format that is manageable by Intel® SceneScape.

Note that this function will be called independently for each of the results
that were appended to the tasksComplete list.

##### arguments

###### **result**

This is an **IAData** object, containing the result from the detect call.
It has the following attributes:

- `data` : The output of the inference call (self.infer in the example above)
- `id`   : The id of the input buffer that produced this result
- `save` : The detection-specific data that is needed for post-processing this result.

##### Expected output

`postprocess` must return a list, containing all of the detections for the processed frame.
Each of the detections in the result needs to be converted into a dict object.
This dict object must contain the following values:

##### 2D object detection
- `id` - A unique numeric identifier for this detection. Should start at 1.
- `category` - The category of the detected object, in string format. Must be lowercase.
- `score` - The detection confidence, from 0 to 1.
- `bounding_box` - The bounding box for this detection, in pixel coordinates, in dict format. The dict's values must be `x`, `y`, `height`, and `width`.

##### 3D object detection
- `id` - A unique numeric identifier for this detection. Should start at 1.
- `category` - The category of the detected object, in string format. Must be lowercase.
- `score` - The detection confidence, from 0 to 1.
- `translation` - The detected object position, in 3-dimensions (x, y, z), in array format.
- `rotation` - The detected object's rotation, in quaternion format, in array format.
- `dimension` - The detected object's, in 3-dimensions (width, height, depth), in array format.
- `center_of_mass` - The detected object's center of mass, in 3-dimensions, in dict format. It should contain values for `x`, `y`, and `z`, as well as `width`, `height` and `depth`.

#### Filtering:
Note that additionally, the `postprocess` function should throw away objects based on two conditions:

*Object category*:
  The object has an invalid or inexistent `id`, or the category is blacklisted (categories to be ignored are listed in `self.blacklist`)

*Object distance*:
  The object is farther away than the requested distance in the `input` object from the detect call (`input.max_distance_squared`). Note the `max_distance_squared value` is the square of the requested distance (to avoid a square root computation with each detection), or `None`, if no distance maximum has been established.

```
  def postprocess(self, result):
    params... , max_distance_squared = result.save
    objects = []
    for res in result:
      detection = generateDetection(res)

      # Filter out based on distance
      if max_distance_squared and detection.distance*detection.distance > max_distance_squared:
        continue

      # Filter out based on unknown category
      if detection.category_id >= len(self.categories):
        continue

      # Filter out based on blacklisted category
      category = self.categories[detection.category_id]
      if category in self.blacklist:
        continue

      obj = {}
      obj['category'] = category
      obj['confidence'] = detection.score
      obj['translation'] = detection.translation
      obj['rotation'] = detection.rotation
      obj['size'] = detection.dimension
      obj['id'] = len(objects) + 1
      objects.append(obj)
    return objects

  def generateDetection(res):
    # This function should process the output of the model,
    # and generate score, translation, rotation, etc.
    obj = ...
    return obj
```

In this sample code, `generateDetection` should translate the inference result into the required into `category_id`, `score`, `translation`, `rotation`, and `dimension`.

## Inferizer

The inferizer component is in charge of loading inference models, thus we need to be able to instantiate the new Detector class from this module.
Following the names used in the examples before, considering the new Detector class is named '**MyDetector**', and assuming it will be found in the file *percebro/src/my_detector.py*, add the corresponding import to the **Inferizer** module, in *percebro/src/inferizer.py*:

```
...
from detector_yolo import YoloV8Detector

from my_detector import MyDetector
```

In order to add a detector type to the list of known models, add an entry in the `engine_mapping` dict, following the existing structure:
```
class Inferizer:
  engine_mapping = {
    ...
    'MyDetector': MyDetector
  }
```

The string used here will be used to select the model in the model-config.json, in the (Configuration)[#configuration] step.

If your detector requires extra configuration options in the model config,
configuration parameters not already available,
add them to the **Inferizer** class `valid_entries` list.

```
  #Valid config entries for model-config:
  valid_entries = [ 'blacklist',
                    ...
                    'model_param1'
                  ]

```
This will allow these options to be propagated to your new **MyDetector** class.


## Build

Create a **MyDetector** class and save it in *percebro/src/my_detector.py*

### Building

Once all the changes have been made, proceed to building Intel® SceneScape, following the instructions in the main [README](https://github.com/open-edge-platform/scenescape/blob/main/README.md), for Installation and First run.

If the system has already been deployed, percebro can be re-built with the `make -C percebro` command.

## Configuration

### model-config.json

In order to use the recently enabled model, a model-config file must be created, that contains name and configuration parameters that will be passed to the model as appropriate.

See percebro/README.md under the section 'Model configuration' for more information.

In this example, this file is placed under the *models* directory, as *models/my_model_config.json*.

Note that the string for the `model` attribute will be the name used as the camerachain in the command line, in the *docker-compose.yml* file.

Note also, that the string for the `engine` attribute must match the one just added in the `engine_mapping` dict in *percebro/inferizer.py*.

```
[
  { "model" : "mymodel", "engine": "MyDetector",
    "categories": ["test", "black"],
    "parameter1": ...
  }
]
```

### docker-compose.yml

Finally, the last step is to enable your model in the *docker-compose.yml* file.

The recommendation is to place inference models under the *models* directory, which is mapped by default to */opt/intel/openvino/deployment_tools/intel_models* path inside the container.

The following updates should be done for the arguments after the command "**percebro**" under the video-container:

Specify the **--modelconfig** flag, providing the path to this newly created file, ensuring the path follows the volume definition.

Also specify the model (using the the name after `model` from the model-config) as the camerachain.

```
     command:
      - "percebro"
      ...
      - "--modelconfig=/opt/intel/openvino/deployment_tools/intel_models/my_model_config.json"
      - "--camerachain=mymodel"
```

After this, the container using this new custom model should come up after using `docker compose up`.

