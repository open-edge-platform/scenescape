#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse

import library.json_helper as json_helper
import library.metrics as metrics


def build_argparser():
  """! command line arguments for plot_tracker_results.
  """
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("ground_truth", help="ground truth tracked data file", type=str)
  parser.add_argument("predicted", help="predicted tracked data file", type=str)
  parser.add_argument('--convert_json', action='store_true')

  return parser

def getMetrics(gt_data, pred_data, pred_gid_map, gt_track_data):
  """!Compute and return multiple tracker related metrics
  @param    gt_data             ground truth json data
  @param    pred_data           predicted json data
  @param    pred_gid_map        dict of predicted GIDs
                                used to determine GID associations.
  @param    gt_track_data       dict object that has ground truth track data.
  @return   predMse             dict of mean squared error values
  @return   msoce               mean squared object count error
  @return   idc_error           mean id change error
  """

  gt_tracks = {}
  msoce = 0.0
  idc_error = 0.0
  std_velocity = 0.0
  std_max_velocity = 0.0

  for id in gt_track_data.keys():
    gt_track = metrics.getTrack(gt_track_data[id], id)
    gt_tracks[id] = gt_track

  pred_gid_tracks = metrics.associateGIDs(pred_gid_map, gt_tracks)
  pred_fused_tracks, _ = metrics.associateTracks(gt_tracks, pred_gid_tracks)

  if len(pred_fused_tracks) > 0 or len(pred_gid_tracks) > 0:
    std_velocity, std_max_velocity = metrics.getVelocity(pred_data)
    msoce = metrics.getMeanSquareObjCountError(gt_data, pred_data)
    idc_error = metrics.getMeanIdChangeErrors(gt_data, pred_data)

  return msoce, idc_error, std_velocity, std_max_velocity

def main():
  """! Takes in predicted file and ground truth file. Accociates the
  predicted track with the ground truth track and calculates metrics.
  """
  args = build_argparser().parse_args()
  pred_data, pred_track_data, _ = json_helper.loadData(args.predicted, args.convert_json)
  gt_data, gt_track_data, gt_info = json_helper.loadData(args.ground_truth)
  pred_gid_map = metrics.getGIDLocs(pred_track_data)
  msoce, idc_error, std_velocity, std_max_velocity = getMetrics(gt_data, pred_data, pred_gid_map, gt_track_data)

  print()
  print('Mean Square Object Count Error: \t{:0.5f}'.format(msoce))
  print('ID Change Error (Mean ID Change Error): {:0.5f}'.format(idc_error))
  print('Standard deviation velocity: \t\t{:0.5f}'.format(std_velocity))
  print('max velocity: \t\t\t\t{:0.5f}'.format(std_max_velocity))

  return

if __name__ == '__main__':
  exit(main() or 0)
