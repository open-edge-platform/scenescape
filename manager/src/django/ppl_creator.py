import json
from string import Template
from pathlib import Path


class ModelChainSerializer:

    def __init__(self, models_folder : str, model_chain : str, model_config : dict):
        self.models_folder = models_folder
        self.chain = model_chain
        self.model_config = model_config

    def _model_representation(self, model_name: str) -> list:
        if not model_name:
            return []
        elif model_name in self.model_config:
          config = self.model_config[model_name]
          color_space = config.get('input-format', {}).get('color-space', 'BGR')
          input_format = f'video/x-raw,format={color_space}'
          inference_element = self._get_inference_element_name(config.get('type'))
          model_params = self._resolve_paths(config.get('params', {}))
          params_str = ' '.join([f'{key}={self._format_value(value)}' for key, value in model_params.items()])
          return [ input_format, f'{inference_element} {params_str}' ]
        else:
            raise ValueError(f"Model {model_name} not found in model config file.")

    def _resolve_paths(self, params: dict) -> dict:
        converted = {}
        for key, value in params.items():
            if key in ['model', 'model_proc']:
                converted[key] = str(Path(self.models_folder) / Path(value))
            else:
                converted[key] = value
        return converted

    def _get_inference_element_name(self, model_type: str) -> str:
        if model_type == 'detect':
            return 'gvadetect'
        elif model_type == 'classify':
            return 'gvaclassify'
        else:
            raise ValueError(f"Unsupported model type: {model_type}. Supported types are 'detect', 'classify'.")

    def serialize(self) -> list:
        # for now it is assumed that model_chain is a single model
        return self._model_representation(self.chain)

    def _format_value(self, value):
        """
        Quote string values if they contain spaces or special characters
        """
        if isinstance(value, str) and (any(c in value for c in ' ;!') or value == ''):
            return f'"{value}"'
        return str(value)


class PipelineGenerator:

    # the path in the docker container, to be mounted
    output_folder = '/home/pipeline-server/output'
    models_folder = '/home/pipeline-server/models'
    gva_python_path = '/home/pipeline-server/user_scripts/gvapython/sscape'
    config_path = '/home/pipeline-server/config.json'
    video_path = '/home/pipeline-server/videos'

    def __init__(self, camera_settings: dict, model_config: dict):
        self.camera_settings = camera_settings
        model_chain = camera_settings.get('camerachain')
        self.model_serializer = ModelChainSerializer(self.models_folder, model_chain, model_config)
        # TODO: make it generic, support http(s) and USB camera inputs etc.
        # for now we assume this is RTSP or file URI
        self.input = self._parse_source(camera_settings['command'], PipelineGenerator.video_path)
        self.timestamp = [f'gvapython class=PostDecodeTimestampCapture function=processFrame module={self.gva_python_path}/sscape_adapter.py name=timesync']
        # TODO: implement undistort as a part of separate undistortion enabling task
        self.undistort = []
        self.postprocess = ['gvametaconvert add-tensor-data=true name=metaconvert', f'gvapython class=PostInferenceDataPublish function=processFrame module={self.gva_python_path}/sscape_adapter.py name=datapublisher']
        self.model_chain = self.model_serializer.serialize()
        self.publish = [ 'gvametapublish name=destination' ]
        self.sink = [ 'appsink sync=true' ]

    def _parse_source(self, source: str, video_volume_path : str) -> list:
        """
        Parses the GStreamer source element type based on the source string.
        Supported source types are 'rtsp', 'file'.

        @param source: The source string as typed by the user (e.g., RTSP URL, file path).
        @return: array of Gstreamer pipeline elements
        """
        if source.startswith('rtsp://'):
            return [ f'rtspsrc location={source} latency=200 name=source', 'rtph264depay', 'h264parse', 'avdec_h264', 'videoconvert' ]
        elif source.startswith('file://'):
            filepath = Path(video_volume_path) / Path(source[len('file://'):])
            return [ f'multifilesrc loop=TRUE location={filepath} name=source', 'decodebin', 'videoconvert' ]
        else:
            raise ValueError(f"Unsupported source type in {source}. Supported types are 'rtsp://...' and 'file://...'.")

    def override_sink(self, new_sink: str):
        """
        Overrides the sink element of the pipeline.
        """
        self.sink = [ new_sink ]
        return self

    def generate(self) -> str:
        """
        Generates a GStreamer pipeline string from the serialized pipeline.
        """
        serialized_pipeline = self.input + self.timestamp + self.undistort + self.model_chain + self.postprocess + self.publish + self.sink
        return ' ! '.join(serialized_pipeline)

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
        self.pipeline =  camera_settings['pipeline']
        # hardcoded for now, will be dynamic later based on model chain
        self.metadata_policy = 'detectionPolicy'
        # once we add pipeline text field in camera settings, it will be used directly instead of generating
        template = Template(PipelineConfigGenerator.CONFIG_TEMPLATE)
        self.config = template.substitute(
            name=self.name,
            pipeline=self.pipeline,
            camera_id=self.camera_id,
            metadata_policy=self.metadata_policy
        )

    def get_config_as_dict(self) -> dict:
        return json.loads(self.config)

    def get_config_as_json(self) -> str:
        return self.config
