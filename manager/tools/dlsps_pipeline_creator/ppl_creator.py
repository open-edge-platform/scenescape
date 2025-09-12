import json

class PipelineGenerator:

    class ModelChainSerializer:

        def __init__(self, model_chain : str, model_config_path : str):
            self.model_chain = model_chain
            self.model_config_path = model_config_path
            # hardcoded for now, will be dynamic later
            self.serialized_model_chain = ['gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json']

        def serialize(self) -> list:
            return self.serialized_model_chain

    def __init__(self, camera_settings: dict):
        self.camera_settings = camera_settings
        model_chain = camera_settings.get('modelchain', '')
        self.model_serializer = self.ModelChainSerializer(model_chain, self._load_model_config())
        self.source = camera_settings.get('command', '')
        self.preprocess = ['decodebin', 'videoconvert', 'videoscale']
#        self.timestamp = ['gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync']
        self.postprocess = ['gvametaconvert add-tensor-data=true name=metaconvert', 'gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher', 'gvametapublish name=destination', 'appsink sync=true']
        self.postprocess = ['queue', 'gvawatermark', 'videoconvert', 'queue', 'x264enc', 'mp4mux', 'filesink location=/data/output.mp4']
        self.publish = ['gvametaconvert format=json', 'gvametapublish file-path=/data/output_person.json']
        self.serialized_pipeline = [self.source + self.preprocess + self.model_serializer.serialize() + self.publish + self.postprocess]

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
