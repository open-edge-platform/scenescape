import copy
import json
from pathlib import Path
from string import Template

import cv2
import numpy as np


class ModelChainSerializer:
    """Generates DLStreamer sub-pipeline elements list from model chain and model config."""

    def __init__(self, models_folder: str, model_chain: str, model_config: dict):
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
          return [input_format, f'{inference_element} {params_str}']
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
    """Generates a GStreamer pipeline string from camera settings and model config."""

    # the paths in the DLSPS container, to be mounted
    models_folder = '/home/pipeline-server/models'
    gva_python_path = '/home/pipeline-server/user_scripts/gvapython/sscape'
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
        self.undistort = self.addCameraUndistort(camera_settings)
        self.postprocess = ['gvametaconvert add-tensor-data=true name=metaconvert', f'gvapython class=PostInferenceDataPublish function=processFrame module={self.gva_python_path}/sscape_adapter.py name=datapublisher']
        self.model_chain = self.model_serializer.serialize()
        self.publish = ['gvametapublish name=destination']
        self.sink = ['appsink sync=true']

    def _parse_source(self, source: str, video_volume_path: str) -> list:
        """
        Parses the GStreamer source element type based on the source string.
        Supported source types are 'rtsp', 'file'.

        @param source: The source string as typed by the user (e.g., RTSP URL, file path).
        @return: array of Gstreamer pipeline elements
        """
        if source.startswith('rtsp://'):
            return [f'rtspsrc location={source} latency=200 name=source', 'rtph264depay', 'h264parse', 'avdec_h264', 'videoconvert']
        elif source.startswith('file://'):
            filepath = Path(video_volume_path) / Path(source[len('file://'):])
            return [f'multifilesrc loop=TRUE location={filepath} name=source', 'decodebin', 'videoconvert']
        else:
            raise ValueError(f"Unsupported source type in {source}. Supported types are 'rtsp://...' and 'file://...'.")

    def addCameraUndistort(self, camera_intrinsics: dict) -> str:
        intrinsics_keys = ['intrinsics_fx', 'intrinsics_fy', 'intrinsics_cx', 'intrinsics_cy']
        dist_coeffs_keys = ['distortion_k1', 'distortion_k2', 'distortion_p1', 'distortion_p2', 'distortion_k3']
        # Validation here can be removed if done prior to this step or we add a flag to enable undistort in calib UI
        if not all(key in camera_intrinsics for key in intrinsics_keys):
            return []
        if not all(key in camera_intrinsics for key in dist_coeffs_keys):
            return []
        dist_coeffs = [camera_intrinsics['distortion_k1'], camera_intrinsics['distortion_k2'],
                       camera_intrinsics['distortion_p1'], camera_intrinsics['distortion_p2'],
                       camera_intrinsics['distortion_k3']]
        if all(coef == 0 for coef in dist_coeffs):
            return []

        intrinsics_matrix = [[camera_intrinsics['intrinsics_fx'], 0, camera_intrinsics['intrinsics_cx']],
                            [0, camera_intrinsics['intrinsics_fy'], camera_intrinsics['intrinsics_cy']],
                            [0, 0, 1]]
        camera_intrinsics['intrinsics_matrix'] = intrinsics_matrix
        camera_intrinsics['dist_coeffs'] = dist_coeffs

        element = f"cameraundistort settings=cameraundistort0"
        return [element]

    def override_sink(self, new_sink: str):
        """
        Overrides the sink element of the pipeline.
        """
        self.sink = [new_sink]
        return self

    def generate(self) -> str:
        """
        Generates a GStreamer pipeline string from the serialized pipeline.
        """
        serialized_pipeline = self.input + self.undistort + self.model_chain[0:1] + self.timestamp + self.model_chain[1:] + self.postprocess + self.publish + self.sink
        return ' ! '.join(serialized_pipeline)

class PipelineConfigGenerator:
    """Generates a DLSPS configuration JSON file from camera settings."""

    CONFIG_TEMPLATE = {
        "config": {
            "logging": {
                "C_LOG_LEVEL": "INFO",
                "PY_LOG_LEVEL": "INFO"
            },
            "pipelines": [
                {
                    "name": "",
                    "source": "gstreamer",
                    "pipeline": "",
                    "auto_start": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "undistort_config": {
                                "element": {
                                    "name": "cameraundistort0",
                                    "property": "settings",
                                    "format": "xml"
                                },
                                "type": "string"
                            },
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
                            "undistort_config": "",
                            "camera_config": {
                                "cameraid": "",
                                "metadatagenpolicy": ""
                            }
                        }
                    }
                }
            ]
        }
    }

    def __init__(self, camera_settings: dict):
        self.name = camera_settings['name']
        self.camera_id = camera_settings['sensor_id']
        self.pipeline = camera_settings['pipeline']
        self.metadata_policy = 'detectionPolicy'  # hardcoded for now

        # Deep copy to avoid mutating the class-level template
        self.config_dict = copy.deepcopy(PipelineConfigGenerator.CONFIG_TEMPLATE)

        pipeline_cfg = self.config_dict["config"]["pipelines"][0]
        pipeline_cfg["name"] = self.name
        pipeline_cfg["pipeline"] = self.pipeline
        if 'cameraundistort' in self.pipeline:
            pipeline_cfg["payload"]["parameters"]["undistort_config"] = self.generate_xml(
                camera_settings['intrinsics_matrix'], camera_settings['dist_coeffs'])
        pipeline_cfg["payload"]["parameters"]["camera_config"]["cameraid"] = self.camera_id
        pipeline_cfg["payload"]["parameters"]["camera_config"]["metadatagenpolicy"] = self.metadata_policy

    def generate_xml(self, camera_intrinsics: list[list[float]], dist_coeffs: list[float]) -> str:
        intrinsics_matrix = np.array(camera_intrinsics, dtype=np.float32)
        dist_coeffs = np.array(dist_coeffs, dtype=np.float32)
        fs = cv2.FileStorage("camera_params.xml", cv2.FILE_STORAGE_WRITE | cv2.FILE_STORAGE_MEMORY)
        fs.write("cameraMatrix", intrinsics_matrix)
        fs.write("distCoeffs", dist_coeffs)
        xml_string = fs.releaseAndGetString()
        xml_string = xml_string.replace('\n', '').replace('\r', '')
        return xml_string

    def get_config_as_dict(self) -> dict:
        return self.config_dict

    def get_config_as_json(self) -> str:
        return json.dumps(self.config_dict, indent=2)
