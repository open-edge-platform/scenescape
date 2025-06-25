#! env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import re
from subprocess import Popen, PIPE, STDOUT
import os

def run_command(command, wait=True):
  cmdProc = Popen(command, stdout=PIPE, stderr=STDOUT, universal_newlines=True)
  cmdOut = cmdProc.communicate()[0]
  cmdProc.stdout.close()
  result = cmdProc.wait()
  return [result, cmdOut]

def prepare_model( zipFile, modelName):
  cfg_file = None

  if zipFile is not None:
    unzipCommand = [ 'unzip', zipFile, '-d', 'models/' ]
    run_command( unzipCommand )

    cfg_file = "models/{}/{}.conf".format(modelName, modelName)

    if not os.path.exists( cfg_file ):
      print( "Generating {}".format(cfg_file) )
      with open( cfg_file, 'w' ) as cfg_fd:
        cfg_dict = {}
        cfg_dict['model'] = modelName
        cfg_dict['engine'] = 'GetiDetector'
        cfg_dict['keep_aspect'] = 0
        cfg_dict['directory'] = '/workspace/models/{}'.format(modelName)
        cfg_dict['categories'] = []
        with open( 'models/{}/model/config.json'.format(modelName) ) as model_cfg :
          parameters = json.load( model_cfg )
          for label in parameters["model_parameters"]["labels"]["all_labels"]:
            label_info = parameters["model_parameters"]["labels"]["all_labels"][label]
            cfg_dict['categories'].append( label_info['name'] )
            print( "Model has category {}".format( label_info['name'] ) )

        cfg_fd.write( "[\n" )
        json.dump(cfg_dict, cfg_fd, indent=2)
        cfg_fd.write( "\n]" )


  return cfg_file

def clean_model( modelName ):
  delCmd = [ 'rm', 'models/{}'.format(modelName), '-rf' ]
  run_command( delCmd )
  return

def run_and_check_output( testCommand, model, findText = None, expectedText = None ):
  print( "Running test for {}".format( model ) )
  [cmdResult, cmdOut] = run_command( testCommand )

  if cmdResult != 0:
    print(cmdOut)

  if findText is not None:
    outAsLines = cmdOut.splitlines()
    for line in outAsLines:
      foundAt = line.find( findText )
      if foundAt >= 0:
        matchStr = "{} (\w+)".format(findText)
        matched = re.match( matchStr, line )
        if matched is not None:
          if isinstance(expectedText,list):
            cmdResult = 1
            for exp in expectedText:
              if exp == matched.group(1):
                print( "Got expected {} '{}'".format(findText, exp))
                cmdResult = 0
                break
              else:
                print( "Didnt get expected {} '{}'".format(findText, exp))
          else:
            if expectedText != matched.group(1):
              print( "mismatch! exp {} got {}".format(expectedText, matched.group(1)))
              cmdResult = 1
            else:
              print( "Got expected {} '{}'".format(findText, expectedText))


  if cmdResult != 0:
    print( "Test for model {} failed!".format(model))
  print( "Output {}".format(cmdOut))

  return cmdResult

