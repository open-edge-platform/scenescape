#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import argparse
import sys

parser = argparse.ArgumentParser()

# Input ERROR Files
parser.add_argument("--recalculated_error_file", type=str, help="Output JSON file containing the error for each frame")
parser.add_argument("--expected_error_file", type=str, help="JSON file containing precalculated errors for each frame")

# Comparison Options
parser.add_argument("--compare_mse", action="store_true", help="Compare Mean Square Error")
parser.add_argument("--mse_error_margin", type=float, default=0.0, help="Mean Square Error Margin")
parser.add_argument("--compare_reprojection_error", action="store_true", help="Compare Reprojection Error")
parser.add_argument("--reprojection_error_margin", type=float, default=0.0, help="Reprojection Error Margin")
parser.add_argument("--compare_only_average", action="store_true", help="Compare only the average error")

def readErrorFile(file):
  errors_dict = {}
  # Read each line of file as json string
  with open(file, 'r') as f:
    lines = f.readlines()
    for line in lines:
      json_object = json.loads(line)
      if(json_object["image_recieved"] == "false"):
        errors_dict[json_object["input_image"]] = {
          "image_recieved": json_object["image_recieved"],
          "mean_square_error": None,
          "reprojection_error": None
        }
        continue
      elif "reprojection_error" not in json_object:
        errors_dict[json_object["input_image"]] = {
          "image_recieved": json_object["image_recieved"],
          "mean_square_error": json_object["mean_square_error"],
          "reprojection_error": None
        }
      else:
        errors_dict[json_object["input_image"]] = {
          "image_recieved": json_object["image_recieved"],
          "mean_square_error": json_object["mean_square_error"],
          "reprojection_error": json_object["reprojection_error"]
        }

  return errors_dict

def compareMse(precalculated_errors, recalculated_errors, mse_error_margin):
  for frame in precalculated_errors:
    if precalculated_errors[frame]["image_recieved"] == "false":
      print(f"Frame: {frame} : Image not recieved", flush=True)
      continue
    if precalculated_errors[frame]["mean_square_error"] is None:
      print(f"Frame: {frame} : Mean Square Error not present in precalculated error", flush=True)
      continue
    if recalculated_errors[frame]["mean_square_error"] is None:
      print(f"Frame: {frame} : Mean Square Error not calculated", flush=True)
      continue
    print(f"Mean Square Error for Frame: {frame} : Precalculated {precalculated_errors[frame]['mean_square_error']} / Recalculated {recalculated_errors[frame]['mean_square_error']}", flush=True)
    if abs(precalculated_errors[frame]["mean_square_error"] - recalculated_errors[frame]["mean_square_error"]) > mse_error_margin:
      return False
  return True

def compareReprojectionError(precalculated_errors, recalculated_errors, reprojection_error_margin):
  for frame in precalculated_errors:
    if precalculated_errors[frame]["image_recieved"] == "false":
      print(f"Frame: {frame} : Image not recieved", flush=True)
      continue
    if precalculated_errors[frame]["reprojection_error"] is None:
      print(f"Frame: {frame} : Reprojection Error not present in precalculated error", flush=True)
      continue
    if recalculated_errors[frame]["reprojection_error"] is None:
      print(f"Frame: {frame} : Reprojection Error not calculated", flush=True)
      continue
    print(f"Reprojection Error for Frame: {frame} : Precalculated {precalculated_errors[frame]['reprojection_error']} / Recalculated {recalculated_errors[frame]['reprojection_error']}", flush=True)
    if abs(precalculated_errors[frame]["reprojection_error"] - recalculated_errors[frame]["reprojection_error"]) > reprojection_error_margin:
      return False
  return True

def compareAverageMseError(precalculated_average_error, recalculated_average_error, mse_error_margin):
  if abs(precalculated_average_error["mean_square_error"] - recalculated_average_error["mean_square_error"]) > mse_error_margin:
    return False
  return True

def compareAverageReprojectionError(precalculated_average_error, recalculated_average_error, reprojection_error_margin):
  if abs(precalculated_average_error["reprojection_error"] - recalculated_average_error["reprojection_error"]) > reprojection_error_margin:
    return False
  return True

def calculateAverageErrors(errors_dict):
  total_mse_frames = 0
  total_reprojection_error_frames = 0
  total_mse = 0
  total_reprojection_error = 0
  for frame in errors_dict:
    if errors_dict[frame]["image_recieved"] == "false":
      continue
    if errors_dict[frame]["reprojection_error"] is not None:
      total_reprojection_error += errors_dict[frame]["reprojection_error"]
      total_reprojection_error_frames += 1
    if errors_dict[frame]["mean_square_error"] is not None:
      total_mse_frames += 1
      total_mse += errors_dict[frame]["mean_square_error"]
  average_error = {
    "mean_square_error": total_mse/total_mse_frames if total_mse_frames > 0 else None,
    "reprojection_error": total_reprojection_error/total_reprojection_error_frames if total_reprojection_error_frames > 0 else None
  }
  return average_error

def main(args):
  TEST_PASS = False

  # Check if precalculated error file is provided
  if args.expected_error_file is None:
    print("Please provide precalculated error file", flush=True)
    sys.exit(1)
  else:
    precalculated_errors = readErrorFile(args.expected_error_file)

  # Check if recalculated error file is provided
  if args.recalculated_error_file is None:
    print("Please provide recalculated error file", flush=True)
    sys.exit(1)
  else:
    recalculated_errors = readErrorFile(args.recalculated_error_file)

  precalculated_average_error = calculateAverageErrors(precalculated_errors)
  recalculated_average_error = calculateAverageErrors(recalculated_errors)


  average_mse_comparison = compareAverageMseError(precalculated_average_error, recalculated_average_error, args.mse_error_margin)
  average_reprojection_error_comparison = compareAverageReprojectionError(precalculated_average_error, recalculated_average_error, args.reprojection_error_margin)

  mse_error_comparison = compareMse(precalculated_errors, recalculated_errors, args.mse_error_margin)
  reprojection_error_comparison = compareReprojectionError(precalculated_errors, recalculated_errors, args.reprojection_error_margin)

  if args.compare_only_average:
    if average_mse_comparison and average_reprojection_error_comparison:
      print("Average errors are within the margin", flush=True)
      TEST_PASS = True
    else:
      if args.compare_mse and not average_mse_comparison:
        print("Average Mean Square Errors are not within the margin", flush=True)
        TEST_PASS = False
      if args.compare_reprojection_error and not average_reprojection_error_comparison:
        print("Average Reprojection Errors are not within the margin", flush=True)
        TEST_PASS = False
  else:
    if mse_error_comparison and reprojection_error_comparison:
      print("All errors are within the margin", flush=True)
      TEST_PASS = True
    else:
      if args.compare_mse and not mse_error_comparison:
        print("Mean Square Errors are not within the margin", flush=True)
        TEST_PASS = False
      if args.compare_reprojection_error and not reprojection_error_comparison:
        print("Reprojection Errors are not within the margin", flush=True)
        TEST_PASS = False
  print(f"Average Mean Square Error: {recalculated_average_error['mean_square_error']}", flush=True)
  print(f"Average Reprojection Error: {recalculated_average_error['reprojection_error']}", flush=True)
  if TEST_PASS:
    print("Verification Passed", flush=True)
    return(0)
  else:
    print("Verification Failed", flush=True)
  return(1)

if __name__ == "__main__":
  args = parser.parse_args()
  sys.exit(main(args))
