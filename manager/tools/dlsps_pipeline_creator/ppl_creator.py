import json

class PipelineGenerator:

    # the path in the docker container, to be mounted
    output_folder = '/output-data'
    models_folder = '/models'
    gva_python_path = '/scripts'

    class ModelChainSerializer:

        def __init__(self, models_folder : str, model_chain : str, model_config_path : str):
            self.model_chain = model_chain
            self.model_config_path = model_config_path
            self.models_folder = models_folder
            # hardcoded for now, will be dynamic later
            self.serialized_model_chain = [f'gvadetect model={self.models_folder}/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc={self.models_folder}/object_detection/person/person-detection-retail-0013.json']

        def serialize(self) -> list:
            return self.serialized_model_chain

    def __init__(self, camera_settings: dict):
        self.camera_settings = camera_settings
        model_chain = camera_settings.get('modelchain', '')
        self.model_serializer = self.ModelChainSerializer(self.models_folder, model_chain, self._load_model_config())
        self.source = [ camera_settings['command'], 'tsdemux' ]
        self.preprocess = ['decodebin', 'videoconvert', 'videoscale']
#        self.timestamp = [f'gvapython class=PostDecodeTimestampCapture function=processFrame module={self.gva_python_path}/sscape_adapter.py name=timesync']
        adapter_param = { 'cameraid' : camera_settings['sensor_id'], 'metadatagenpolicy' : 'detectionPolicy' }
        adapter_param_str = json.dumps(adapter_param)
        self.postprocess = ['gvametaconvert add-tensor-data=true name=metaconvert', f'gvapython class=PostInferenceDataPublish function=processFrame module={self.gva_python_path}/sscape_adapter.py kwarg=\'{adapter_param_str}\'']
#        self.postprocess = ['queue', 'gvawatermark', 'videoconvert', 'queue', 'x264enc', 'mp4mux', f'filesink location={self.output_folder}/output.mp4']
#        self.postprocess = ['fakesink']
        self.publish = [ f'gvametapublish file-path={self.output_folder}/output_person.json', 'appsink sync=true' ]
        self.serialized_pipeline = self.source + self.preprocess + self.model_serializer.serialize() + self.postprocess + self.publish

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
