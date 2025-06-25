#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import json
import re
import numpy as np


def build_args( ):
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-i", "--input", type=str,
                      help="Result file to process", required=True )
  parser.add_argument("-r", "--reference", type=str,
                      help="Result file to process", required=True )
  parser.add_argument("-v", "--verbose", action="store_true")
  parser.add_argument("-p", "--precision", type=int, default=3 )
  return parser


def process_line( line_data, line_ref, precision ):
  result = True
  jdata = json.loads( line_data )
  jref  = json.loads( line_ref )

  if 'id' in jdata:
    jdata['id'] = re.sub( "[0-9]+", "", jdata['id'] )
  if 'id' in jref:
    jref['id']  = re.sub( "[0-9]+", "", jref['id'] )

  if jdata['timestamp'] != jref['timestamp']:
    result = False
    print( "Data and ref have different timestamp! (Got {} expected {})".format )
  else:
    result = compare_item( jdata, jref, precision )

  return result


def compare_item( jdata, jref, precision ):

  comparison_result = True

  if not isinstance( jdata, type( jref ) ):
    print( "{} is of a different type between data ({}) and ref ({})".format(
      jdata,
      type( jdata ),
      type( jref ) ))
    return False

  if isinstance( jdata, int ):
    comparison_result = (jdata == jref)

  if isinstance( jdata, float ):
    tol = 10**(-precision)
    comparison_result = np.isclose( jdata, jref, rtol=tol, atol=tol )
    if comparison_result == False:
      print( "{} v {} : {} tol {} precision {}".format( jdata, jref, comparison_result, tol, precision ) )

  if isinstance( jdata, str ):
    comparison_result = (jdata == jref)

  if isinstance( jdata, list ):
    if len(jdata) != len(jref):
      print( "{} is of a different length in data ({}) and ref ({})".format(
        jdata,
        len( jdata ),
        len( jref ) ))
      return False

    for element in range(len(jdata)):
      if not compare_item(jdata[element], jref[element], precision):
        print( "Element {} mismatch in data ({}) and ref ({})".format(
          element,
          len( jdata ),
          len( jref ) ))
        comparison_result = False
        break

  if isinstance( jdata, dict ):
    if len(jdata) != len(jref):
      print( "{} is of a different length in data ({}) and ref ({})".format(
        jdata,
        len( jdata ),
        len( jref ) ))
      return False
    else:
      for element in jdata:
        if not compare_item(jdata[element], jref[element], precision):
          return False

  if comparison_result == False:
    print( "Jdata {} mismatch w Ref {}".format(jdata, jref) )

  return comparison_result

def compare_dict( line_output, line_reference ):

  if len(line_output) == 0 or len(line_reference) == 0:
    return False

  for obj in line_reference:
    if not obj in line_output:
      print( "Output missing {}".format( obj ) )

    else:
      if obj == 'reid':
        continue

      if not compare_item( line_output[obj], line_reference[obj], precision ):
        print( "Failed comparing entry {}".format(obj))
        return False

  return True

def main():
  parser = build_args().parse_args()
  exit_code = 1

  with open( parser.input, "r" ) as file_data:
    with open( parser.reference, "r" ) as file_ref:
      done = False
      current_line = 1

      while not done:
        line_data = file_data.readline()
        line_ref  = file_ref.readline()
        if line_data is None or line_ref is None or len(line_data) == 0 or len(line_ref) == 0:
          print( "Output matches reference" )
          exit_code = 0

          done = True
        else:
          result = process_line( line_data, line_ref, parser.precision )

          if result == False:
            print( "Comparing line {} result {}".format( current_line, result ) )
            done = True

          current_line += 1


  if exit_code != 0:
    print( "Comparison failed." )

  return exit_code


if __name__ == '__main__':
  exit( main() or 0 )
