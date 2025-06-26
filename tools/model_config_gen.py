#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import os
import xml.etree.ElementTree as ET
from argparse import ArgumentParser
from pathlib import Path

g_volume_path = None
g_container_base_path = None
g_fs_base_path = None
g_models_path = None
g_requested_path = None

def build_args():
  args = ArgumentParser()
  args.add_argument( '--directory', required=True )
  args.add_argument( '--output', required=True )
  args.add_argument( '--name', default='new_model' )
  return args

def warn_entry( obj, entry ):
  print("  Warning entry", entry, "was generated with dummy values (", obj[entry], ").")
  print("  Please make sure to edit and update accordingly.")
  return

def create_config(dirpath, found_geti, model_config_name, found_xml_file):
  global g_container_base_path
  global g_fs_base_path
  global g_models_path
  global g_requested_path

  found_path = dirpath
  model_config = {}
  model_config['model'] = model_config_name
  if found_geti:
    model_config['engine'] = 'GetiDetector'
  else:
    model_config['engine'] = 'Detector'
    model_config['_output_order'] = {}

    model_config['_output_order']['category'] = 1
    model_config['_output_order']['confidence'] = 2
    model_config['_output_order']['originX'] = 3
    model_config['_output_order']['originY'] = 4
    model_config['_output_order']['oppositeX'] = 5
    model_config['_output_order']['oppositeY'] = 6

    model_config['normalize_input'] = False
    model_config['normalized_output'] = True
  model_config['keep_aspect'] = False

  print( )
  print( "Found model", model_config['engine'], "at", found_path )

  model_config['categories'] = ['cat1', 'cat2', 'cat3']
  warn_entry(model_config, 'categories')

  model_config['colorspace'] = "BGR"
  warn_entry(model_config, 'colorspace')

  if not found_geti:
    warn_entry(model_config, 'normalize_input')
    warn_entry(model_config, 'normalized_output')
    warn_entry(model_config, '_output_order')
  warn_entry(model_config, 'keep_aspect')

  g_fs_base_path_str = f"{g_fs_base_path}"
  g_container_base_path_str = f"{g_container_base_path}"
  found_path = found_path.replace(g_fs_base_path_str,g_container_base_path_str)
  model_config['directory'] = f"{found_path}"
  model_config['xml'] = found_xml_file

  return model_config

def resolve_container_path(args_directory, args_name):
  global g_volume_path
  global g_container_base_path
  global g_fs_base_path
  global g_models_path
  global g_requested_path

  config_script_path = os.path.realpath(__file__)
  g_models_path = os.path.realpath( os.path.join( os.path.dirname(config_script_path), '../models') )
  config_script_path = Path(__file__).resolve()
  scenescape_path = config_script_path.parent.joinpath('../').resolve()
  g_models_path = scenescape_path.joinpath('models').resolve()
  g_requested_path = Path(args_directory).resolve()
  # Default models mount target
  models_target_path = '/opt/intel/openvino/deployment_tools/intel_models'

  # If requested path is under the models/ subdirectory, it will already be available in the containers,
  # else, we suggest a path on /workspace
  if g_requested_path.is_relative_to(g_models_path):
    rel_to_g_models_path = g_requested_path.relative_to(g_models_path)
    g_volume_path = Path( './models' )
    g_container_base_path = models_target_path
    g_fs_base_path = g_volume_path
  else:
    g_volume_path = g_requested_path.relative_to( scenescape_path )
    g_container_base_path = f'/workspace/{args_name}'
    g_fs_base_path = g_volume_path

  return

def main():
  global g_volume_path
  global g_container_base_path

  args = build_args().parse_args()

  if not os.path.exists( args.directory ):
    print("Directory ", args.directory, "does not exist!" )
    return 1

  resolve_container_path(args.directory, args.name)

  print( "Please update the docker-compose.yml file, in the video-container section:" )
  print( "1) In the volume subsection, ensure the following volume pair description is present" )
  print( f"     - ./{g_volume_path}:{g_container_base_path}" )
  print( "\n2) In the command subsection, ensure The modelconfig file is provided as an argument to percebro, and that the camerachain (model) is updated" )
  print( f"     - \"--modelconfig={args.output}\"" )
  print( f"     - \"--camerachain={args.name}\"" )

  output_jdata_arr = []
  geti_known_models = ['OTE_SSD', 'OTX_SSD', 'SSD', 'ssd']

  model_idx = 1
  for dirpath, dirnames, filenames in os.walk(args.directory):
    found_geti = False

    for filename in filenames:
      found_model_xml = False
      found_model_bin = False
      found_path = None
      found_xml_file = None

      file_root, file_ext = os.path.splitext(filename)

      if file_ext == '.xml':
        if os.path.exists( dirpath + '/' + file_root + '.bin' ):
          found_model_bin = True
        found_xml_file = filename
        found_model_xml = True

      if file_ext == '.json':
        with open( dirpath+'/'+filename ) as fd:
          jdata = json.load( fd )

          if 'type_of_model' in jdata:
            for geti_model in geti_known_models:
              if geti_model == jdata['type_of_model']:
                found_geti = True

      if found_model_xml and found_model_bin:
        model_config_name = f'{args.name}'
        if model_idx > 1:
          model_config_name = f'{args.name}_{model_idx}'
        mconfig = create_config(dirpath, found_geti, model_config_name, found_xml_file)
        output_jdata_arr.append(mconfig)

        print( "  Run a test with" )
        volume_extra_str = ""
        if not g_requested_path.is_relative_to(g_models_path):
          volume_extra_str = f"--volume ./{g_volume_path}:{g_container_base_path}"
        print( f"    $ tools/scenescape-start {volume_extra_str} --shell" )
        print( f"    $ percebro/percebro -i sample_data/apriltag-cam1.mp4 --modelconfig {args.output} --intrinsics=70 --debug --stats --frames 200 -m {model_config_name}")

        model_idx += 1

  with open( args.output, 'w' ) as fd:
    json.dump( output_jdata_arr, fd, indent=2 )

  return 0

if __name__ == '__main__':
  exit( main() or 0 )
