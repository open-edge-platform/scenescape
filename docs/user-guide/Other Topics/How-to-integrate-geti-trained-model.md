# How to Integrate Intel® Geti™ AI Models with Intel® SceneScape

This guide provides step-by-step instructions to train and integrate a custom AI model using the Intel® Geti™ platform with Intel® SceneScape. By completing this guide, you will:

- Train and export a custom AI model from Intel® Geti™.
- Integrate the model into the Intel® SceneScape pipeline.
- Validate inference results visually.

This task is important for deploying and validating custom vision models in production scenarios using Intel® SceneScape. If you’re new to Intel® Geti™, review [Intel® Geti™](https://geti.intel.com)

## Prerequisites

Before You Begin, ensure the following:

- **Dependencies Installed**: Docker, Docker Compose, and required Geti/SceneScape files.
- **Permissions**: Sufficient system access to configure files and run Docker containers.

This guide assumes familiarity with basic machine learning and Docker concepts. If needed, see:

- [Intel® Geti™ Platform Guide](https://geti.intel.com/platform)
- [OpenVINO™ Toolkit Overview](https://docs.openvino.ai/latest/index.html)

## Steps to Integrate Geti AI Models

1. **Train and Export the Model in Intel® Geti™**:
   - **Login to your Geti instance**
     ![Home page](../images/geti/homepage.png)
   - **Create a project in Geti for your use case. Example: Vehicle-detection**
     ![create project](../images/geti/create-project.png)
   - **Create labels**: Add a label for each type of object, by filling in the text box and clicking Create label. Example: vehicle, person
     ![create label](../images/geti/create-label.png)
   - **Upload the data set file/folder**: Upload .mp4 video file for vehicle-detection model training
     ![upload file](../images/geti/upload-videofile.png)
   - **Start interactive annotation on your data**: Annotation of a minimum of 12 frames is required for model training. The default frame skip is 25. Continue to draw bounding boxes and label the objects (vehicle, person) until you are satisfied with the results and then click `Submit >>`
     ![annotate-vehicle](../images/geti/annotate-vehicle.png)
   - **Start model training**: After annotating all the frames, click on `...` beside Annotation required to begin with model training.
     ![start model training](../images/geti/model-training.png)
   - **Your pre-trained model is ready**
     ![trained model training](../images/geti/trained-model.png)
   - **Optimize model**: Intel® Geti™ builds a baseline model and an OpenVINO™ optimized model. You can improve the model performance using OpenVINO™ optimization techniques.
     ![optimized model](../images/geti/optimize-model.png)
   - **Download the trained model**: Each trained model is exported from Intel® Geti™ as a zip archive that includes a simple demo to visualize the results of model inference. We will only utilize a few files from this archive.
     ![download models](../images/geti/download-model.png)

   **Expected Output**:
   - `model.xml`, `model.bin`, and `config.json` under `model/`.

   **Structure of generated zip**:
   - model
     - `model.xml`
     - `model.bin`
     - `config.json`
   - python
     - model_wrappers (Optional)
       - `__init__.py`
       - model_wrappers required to run demo
     - `README.md`
     - `LICENSE`
     - `demo.py`
     - `requirements.txt`

2. **Configuring DLStreamer Pipeline Server with new Geti Model**
   Follow documentation [here](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/dlstreamer-pipeline-server/docs/user-guide/get-started.md) to use the newly trained Geti model with gvadetect and the [How to Configure DLStreamer Video Pipline](How-to-configure-dlstreamer-video-pipeline.md) to configure the entire pipeline for enabling ingestion by SceneScape.

3. **Deploy Intel® SceneScape**:

   ```bash
   docker compose down --remove-orphans
   docker compose up -d
   ```

   Log into the Intel® SceneScape UI and verify that bounding boxes appear correctly.
   ![Verify object detection inference](../images/geti/verify-model-ui.png)

## Supporting Resources

- [Intel® Geti™ Platform](https://geti.intel.com/platform)
- [OpenVINO™ Model Server Docs](https://docs.openvino.ai/latest/ovms_what_is_openvino_model_server.html)
