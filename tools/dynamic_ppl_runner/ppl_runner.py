import json
import os
import argparse

from ppl_creator import PipelineConfigGenerator


class PipelineRunner:

    docker_compose_file = './docker-compose-ppl.yaml'
    input_folder_mount = '/sample_data'

    def __init__(self, camera_settings : dict, paths : dict):
        self.camera_settings = camera_settings
        self.paths = paths
        self.config_generator = PipelineConfigGenerator(camera_settings)

    def generate_config_file(self, filepath: str):
        config_str = self.config_generator.get_config_as_json()
        with open(filepath, 'w') as f:
            f.write(config_str)
        print(f"Pipeline config written to {filepath}")

    def run(self):
        PipelineRunner._write_env_file(self.paths, './.env')
        self.run_containers()

    def run_containers(self):
        command = [
            'docker', 'compose', '-f', PipelineRunner.docker_compose_file, 'up', '-d'
        ]
        os.execvp(command[0], command)

    def _write_env_file(env_vars: dict, filepath: str):
        with open(filepath, 'w') as f:
            for key, value in env_vars.items():
                f.write(f'{key}={value}\n')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the pipeline with specified settings.")
    parser.add_argument('--camera-settings', default='./camera_settings.json',
                        help='Path to camera settings JSON file (default: ./camera_settings.json)')
    parser.add_argument('--output', default='./output',
                        help='Output folder (default: ./output)')
    parser.add_argument('--input', default='../../sample_data',
                        help='Input folder (default: ../../sample_data)')
    args = parser.parse_args()

    camera_settings_path = args.camera_settings
    output_folder = args.output
    input_folder = args.input

    os.makedirs(output_folder, exist_ok=True)
    os.chmod(output_folder, 0o777)

    models_folder = os.environ.get('MODELS_DIR', '../../models')
    root_folder = os.environ.get('ROOT_DIR', '../../')
    secrets_folder = os.environ.get('SECRETS_DIR', '../../manager/secrets')

    if not camera_settings_path or not os.path.isfile(camera_settings_path):
        raise FileNotFoundError("CAMERA_SETTINGS argument (--camera-settings) must be set to a valid file path.")
    with open(camera_settings_path, 'r') as f:
        camera_settings = json.load(f)
    paths = {
        'SECRETS_DIR': os.path.abspath(secrets_folder),
        'ROOT_DIR': os.path.abspath(root_folder),
        'INPUT_DIR': os.path.abspath(input_folder),
        'OUTPUT_DIR': os.path.abspath(output_folder),
        'MODELS_DIR': os.path.abspath(models_folder),
    }
    runner = PipelineRunner(camera_settings, paths)
    runner.generate_config_file('./dlsps-config.json')
    runner.run()
