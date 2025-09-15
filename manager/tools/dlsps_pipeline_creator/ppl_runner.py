import json
import os
import argparse

from ppl_creator import PipelineGenerator

class PipelineRunner:

#    dlstreamer_image = 'intel/dlstreamer:2025.1.2-ubuntu24'
    dlstreamer_image = 'intel/dlstreamer-pipeline-server:3.1.0-ubuntu24'
    input_folder_mount = '/sample_data'

    def __init__(self, camera_settings : dict, paths : dict):
        self.camera_settings = camera_settings
        self.paths = paths
        self.generator = PipelineGenerator(camera_settings)

    def run(self):
        pipeline = self.generator.generate()
        print("Generated Pipeline: ")
        print(pipeline)
        volumes = {
            self.paths['input_folder']: PipelineRunner.input_folder_mount,
            self.paths['output_folder']: PipelineGenerator.output_folder,
            self.paths['models_folder']: PipelineGenerator.models_folder,
            self.paths['gva_python_path']: PipelineGenerator.gva_python_path
        }
        self.run_docker_container(pipeline, volumes)

    def run_docker_container(self, pipeline: str, volumes: dict):
        volume_args = []
        for host_path, container_path in volumes.items():
            volume_args.extend(['-v', f'{host_path}:{container_path}'])
        command = [
            'docker', 'run', '--privileged', '--rm', '-it', '--entrypoint=/bin/bash', '-e GST_DEBUG=3'
#            'docker', 'run', '--privileged', '--rm', '-it', '-e GST_DEBUG=3'
        ] + volume_args + [
            self.dlstreamer_image
        ] + [ '-c', 'gst-launch-1.0 ' + pipeline ]
        print("Running command: ")
        print(' '.join(command))
        os.execvp('docker', command)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the pipeline with specified settings.")
    parser.add_argument('--camera-settings', default='./camera_settings.json',
                        help='Path to camera settings JSON file (default: ./camera_settings.json)')
    parser.add_argument('--output', default='./output',
                        help='Output folder (default: ./output)')
    parser.add_argument('--input', default='./input',
                        help='Input folder (default: ./input)')
    args = parser.parse_args()

    camera_settings_path = args.camera_settings
    output_folder = args.output
    input_folder = args.input

    os.makedirs(output_folder, exist_ok=True)
    os.chmod(output_folder, 0o777)

    models_folder = os.environ.get('MODELS_FOLDER', '../../../models')
    gva_python_path = os.environ.get('GVA_PYTHON_PATH', '../../../dlstreamer-pipeline-server/user_scripts/gvapython/sscape')
    if not camera_settings_path or not os.path.isfile(camera_settings_path):
        raise FileNotFoundError("CAMERA_SETTINGS argument (--camera-settings) must be set to a valid file path.")
    with open(camera_settings_path, 'r') as f:
        camera_settings = json.load(f)
    paths = {
        'input_folder': os.path.abspath(input_folder),
        'output_folder': os.path.abspath(output_folder),
        'models_folder': os.path.abspath(models_folder),
        'gva_python_path': os.path.abspath(gva_python_path)
    }
    runner = PipelineRunner(camera_settings, paths)
    runner.run()
