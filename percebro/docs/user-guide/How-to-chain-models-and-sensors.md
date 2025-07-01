
# How to chain models and sensors

## Chaining Multiple Models Together

One of the most powerful features of Percebro is the ability to chain multiple models together and compose the output of each into a single JSON output for each frame. One example of this is running a person detection and then getting an anonymous "fingerprint" of each detection using a reidentification (ReID) model.

To chain the output of one model to a 2nd model use `+`.  The following is how to do that with the retail person detection model (**retail:** person-detection-retail-0013) and the retail reidentification model (**reid:** person-reidentification-retail-0031) using a USB camera:

        tools/scenescape-start percebro/percebro --camera <camera/video> --camerachain retail+reid --intrinsics=70

The example above will use the output of the retail model as the input(s) of the ReID model.

To run two models in parallel off of a given input, create a comma `,` separated list. A simple example would be to run a person detection (retail) and a vehicle detection (v0002) off of the same frame:

        $ tools/scenescape-start percebro 0 192.168.1.23 --camerachain v0002,retail --intrinsics=70

To configure two model chains, combine the options above. In the following example the vehicle detection model is chained with a vehicle attributes model (vattrib), and a 2nd chain is created from retail feeding into ReID:

        $ tools/scenescape-start percebro 0 192.168.1.23 --camerachain v0002+vattrib,retail+reid --intrinsics=70

To nest multiple models off of a single output, compose the list inside square brackets that follow the `+`. In this example vehicle detection model feeds both a vehicle attributes and license plate recognition model (lpr).  Additionally, the retail person detection model feeds to both the reid, a person head recognition model (head) and chained age-gender recognition model (agr):

        $ tools/scenescape-start percebro 0 192.168.1.23 --camerachain v0002+[vattrib,lpr],retail+[reid,head+agr] --intrinsics=70

Note that in this case all models will run on the CPU by default, and that chaining different models together can result in a huge number of additional inferencing calls depending on how many objects are detected at each stage. See the section on GPU Decoding (below) for targeting to different hardware to help improve performance.


## Sensor Chain

Example syntax for a sensorchain:

    percebro/percebro --camera test_out_00.png --sensor Snsr0=[100,100,200,200] --sensorattrib trresnet --sensorchain td0001+trresnet --intrinsics=70 --debug --frames 200

Explanation of the 3 arguments:
- **sensor:** Sensor ID to use for publishing. The values between brackets correspond to the sub frame (x, y, width and height) to crop and run inference on.
- **sensorchain:** Model chain to use to run inference on the sub-frame. In the sample above, two sensors are chained, text detection and text recognition chain.
- **sensorattrib:** Post-detection category with the sensor value of interest. In the example above (td0001+trresnet), the value of interest is in the 'trresnet' attribute.

The `--sensor` argument will crop the input frame starting at 100, 100, and a width + height of 200, 200.
The `--sensorchain` argument will affect a text detection + text recognition on the subframe, resulting in the detection:

    obj {'id': 1, 'category': 'text', 'confidence': 0.55, 'bounding_box': {'x': -0.5826302782837863, 'y': -0.19071367537930814, 'width': 0.028607051306896225, 'height': 0.011442820522758496}, 'trresnet': 'blue', 'bounding_box_px': {'x': 29, 'y': 160, 'width': 30.0, 'height': 12.0}}
    obj {'id': 2, 'category': 'text', 'confidence': 0.51, 'bounding_box': {'x': -0.5511625218462005, 'y': -0.19071367537930814, 'width': 0.04577128209103398, 'height': 0.010489252145861938}, 'trresnet': 'altima', 'bounding_box_px': {'x': 62, 'y': 160, 'width': 48.0, 'height': 11.0}}

In this detection result, the values of interest are in the 'trresnet' category, hence using that for sensorattrib.

With these arguments, percebro will end up publishing an MQTT message with the format:

    {'id': 'Snsr0', 'subtype': 'text', 'timestamp': '2024-04-10T03:34:50.770Z', 'value': ['blue', 'altima']}
