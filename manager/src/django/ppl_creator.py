import json
from string import Template

class PipelineGenerator:

    # the path in the docker container, to be mounted
    output_folder = '/home/pipeline-server/output'
    models_folder = '/home/pipeline-server/models'
    gva_python_path = '/home/pipeline-server/user_scripts/gvapython/sscape'
    config_path = '/home/pipeline-server/config.json'

    class ModelChainSerializer:

        def __init__(self, models_folder : str, model_chain : str, model_config_path : str):
            self.models_folder = models_folder
            self.model_chain = model_chain
            self.model_config_path = model_config_path
            # hardcoded for now, will be dynamic later based on model_config provided
            self.serialized_model_chain = ['video/x-raw,format=BGR', f'gvadetect model={self.models_folder}/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc={self.models_folder}/object_detection/person/person-detection-retail-0013.json']

        def serialize(self) -> list:
            return self.serialized_model_chain

    def __init__(self, camera_settings: dict):
        self.camera_settings = camera_settings
        model_chain = camera_settings.get('modelchain', '')
        self.model_serializer = self.ModelChainSerializer(self.models_folder, model_chain, self._load_model_config())
        # TODO: make it generic, support video files, rtsp, etc.
        # for now we assume this is RTSP URI
        rtsp_source = camera_settings['command']
        self.source = [ f'rtspsrc location={rtsp_source} latency=200' ]
        self.preprocess = [ 'rtph264depay', 'h264parse', 'avdec_h264', 'videoconvert' ]
        self.timestamp = [f'gvapython class=PostDecodeTimestampCapture function=processFrame module={self.gva_python_path}/sscape_adapter.py name=timesync']
        self.postprocess = ['gvametaconvert add-tensor-data=true name=metaconvert', f'gvapython class=PostInferenceDataPublish function=processFrame module={self.gva_python_path}/sscape_adapter.py name=datapublisher']
#        self.postprocess = ['queue', 'gvawatermark', 'videoconvert', 'queue', 'x264enc', 'mp4mux', f'filesink location={self.output_folder}/output.mp4']
#        self.postprocess = [ 'gvametaconvert add-tensor-data=true name=metaconvert' ]
        self.model_chain = self.model_serializer.serialize()
#        self.publish = [ f'gvametapublish file-path={self.output_folder}/output_person.json' ]
        self.publish = [ 'gvametapublish name=destination' ]
        self.sink = [ 'appsink sync=true' ]
#        self.sink = ['fakesink']
        self.serialized_pipeline = self.source + self.preprocess + self.timestamp + self.model_chain + self.postprocess + self.publish + self.sink

    def _load_model_config(self) -> dict:
        if self.camera_settings.get('modelconfig'):
            with open(self.camera_settings['modelconfig'], 'r') as f:
                return json.load(f)
        else:
            return {}

    def generate(self) -> str:
        """
        Generates a GStreamer pipeline string from the serialized pipeline.
        """
        return ' ! '.join(self.serialized_pipeline)

    def _format_value(self, value):
        # Quote string values if they contain spaces or special characters
        if isinstance(value, str) and (any(c in value for c in ' ;!') or value == ''):
            return f'"{value}"'
        return str(value)


class PipelineConfigGenerator:

    CONFIG_TEMPLATE = '''
{
  "config": {
    "logging": {
      "C_LOG_LEVEL": "INFO",
      "PY_LOG_LEVEL": "INFO"
    },
    "pipelines": [
      {
        "name": "$name",
        "source": "gstreamer",
        "pipeline": "$pipeline",
        "auto_start": true,
        "parameters": {
          "type": "object",
          "properties": {
            "camera_config": {
              "element": {
                "name": "datapublisher",
                "property": "kwarg",
                "format": "json"
              },
              "type": "object",
              "properties": {
                "cameraid": {
                  "type": "string"
                },
                "metadatagenpolicy": {
                  "type": "string",
                  "description": "Meta data generation policy, one of detectionPolicy(default),reidPolicy,classificationPolicy"
                },
                "publish_frame": {
                  "type": "boolean",
                  "description": "Publish frame to mqtt"
                }
              }
            }
          }
        },
        "payload": {
          "parameters": {
            "camera_config": {
              "cameraid": "$camera_id",
              "metadatagenpolicy": "$metadata_policy"
            }
          }
        }
      }
    ]
  }
}
'''

    def __init__(self, camera_settings: dict):
        self.name = camera_settings['name']
        self.camera_id = camera_settings['sensor_id']
        # hardcoded for now, will be dynamic later based on model chain
        self.metadata_policy = 'detectionPolicy'
        # once we add pipeline text field in camera settings, it will be used directly instead of generating
        self.pipeline_generator = PipelineGenerator(camera_settings)
        template = Template(PipelineConfigGenerator.CONFIG_TEMPLATE)
        self.config = template.substitute(
            name=self.name,
            pipeline=self.pipeline_generator.generate(),
            camera_id=self.camera_id,
            metadata_policy=self.metadata_policy
        )

    def get_config_as_dict(self) -> dict:
        return json.loads(self.config)

    def get_config_as_json(self) -> str:
        return self.config
