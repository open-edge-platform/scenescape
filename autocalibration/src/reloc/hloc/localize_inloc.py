# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
from pathlib import Path
import csv
import pickle
import numpy as np
import h5py
from scipy.io import loadmat
import torch
from tqdm import tqdm
import cv2
import pycolmap

from . import logger
from .utils.parsers import parse_retrieval, names_to_pair
from .utils.evaluate import evaluate


def interpolate_scan(scan, kp):
  h, w, c = scan.shape
  kp = kp / np.array([[w - 1, h - 1]]) * 2 - 1
  assert np.all(kp > -1) and np.all(kp < 1)
  scan = torch.from_numpy(scan).permute(2, 0, 1)[None]
  kp = torch.from_numpy(kp)[None, None]
  grid_sample = torch.nn.functional.grid_sample

  # To maximize the number of points that have depth:
  # do bilinear interpolation first and then nearest for the remaining points
  interp_lin = grid_sample(scan, kp, align_corners=True,
                           mode='bilinear')[0, :, 0]
  interp_nn = torch.nn.functional.grid_sample(scan,
                                              kp,
                                              align_corners=True,
                                              mode='nearest')[0, :, 0]
  interp = torch.where(torch.isnan(interp_lin), interp_nn, interp_lin)
  valid = ~torch.any(torch.isnan(interp), 0)

  kp3d = interp.T.numpy()
  valid = valid.numpy()
  return kp3d, valid


def get_scan_pose(dataset_dir, rpath):
  split_image_rpath = rpath.split('/')
  floor_name = split_image_rpath[-3]
  scan_id = split_image_rpath[-2]
  image_name = split_image_rpath[-1]
  building_name = image_name[:3]

  path = Path(dataset_dir, 'database/alignments', floor_name,
              f'transformations/{building_name}_trans_{scan_id}.txt')
  with open(path) as f:
    raw_lines = f.readlines()

  P_after_GICP = np.array([
      np.fromstring(raw_lines[7], sep=' '),
      np.fromstring(raw_lines[8], sep=' '),
      np.fromstring(raw_lines[9], sep=' '),
      np.fromstring(raw_lines[10], sep=' ')
  ])

  return P_after_GICP


def pose_from_cluster(dataset_dir,
                      q,
                      retrieved,
                      feature_file,
                      match_file,
                      skip=None,
                      match_dense=False):
  height, width = cv2.imread(str(dataset_dir / q)).shape[:2]
  cx = .5 * width
  cy = .5 * height
  focal_length = 4032. * 28. / 36.

  all_mkpq = []
  all_mkpr = []
  all_mkp3d = []
  all_indices = []
  kpq = feature_file[q]['keypoints'].__array__()
  num_matches = 0

  for i, r in enumerate(retrieved):
    pair = names_to_pair(q, r)
    if match_dense:
      mkpq = match_file[pair]['keypoints0'].__array__()
      mkpr = match_file[pair]['keypoints1'].__array__()
      if skip and (mkpr.shape[0] < skip):
        continue
    else:
      kpr = feature_file[r]['keypoints'].__array__()
      m = match_file[pair]['matches0'].__array__()
      v = (m > -1)
      if skip and (np.count_nonzero(v) < skip):
        continue
      mkpq, mkpr = kpq[v], kpr[m[v]]

    num_matches += len(mkpq)

    scan_r = loadmat(Path(dataset_dir, r + '.mat'))["XYZcut"]
    mkp3d, valid = interpolate_scan(scan_r, mkpr)
    Tr = get_scan_pose(dataset_dir, r)
    mkp3d = (Tr[:3, :3] @ mkp3d.T + Tr[:3, -1:]).T

    all_mkpq.append(mkpq[valid])
    all_mkpr.append(mkpr[valid])
    all_mkp3d.append(mkp3d[valid])
    all_indices.append(np.full(np.count_nonzero(valid), i))

  all_mkpq = np.concatenate(all_mkpq, 0)
  all_mkpr = np.concatenate(all_mkpr, 0)
  all_mkp3d = np.concatenate(all_mkp3d, 0)
  all_indices = np.concatenate(all_indices, 0)

  cfg = {
      'model': 'SIMPLE_PINHOLE',
      'width': width,
      'height': height,
      'params': [focal_length, cx, cy]
  }
  ret = pycolmap.absolute_pose_estimation(all_mkpq, all_mkp3d, cfg, 48.00)
  ret['cfg'] = cfg
  return ret, all_mkpq, all_mkpr, all_mkp3d, all_indices, num_matches


def main(dataset_dir,
         retrieval,
         features,
         matches,
         results,
         skip_matches=None,
         match_dense=False,
         poses_gt_file=None):

  assert retrieval.exists(), retrieval
  assert features.exists(), features
  assert matches.exists(), matches

  retrieval_dict = parse_retrieval(retrieval)
  queries = list(retrieval_dict.keys())

  feature_file = h5py.File(features, 'r', libver='latest')
  match_file = h5py.File(matches, 'r', libver='latest')

  poses = {}
  logs = {
      'features': features,
      'matches': matches,
      'retrieval': retrieval,
      'loc': {},
  }
  logger.info('Starting localization...')
  for q in tqdm(queries):
    db = retrieval_dict[q]
    ret, mkpq, mkpr, mkp3d, indices, num_matches = pose_from_cluster(
        dataset_dir, q, db, feature_file, match_file, skip_matches,
        match_dense)

    poses[q] = (ret['qvec'], ret['tvec'])
    logs['loc'][q] = {
        'db': db,
        'PnP_ret': ret,
        'keypoints_query': mkpq,
        'keypoints_db': mkpr,
        '3d_points': mkp3d,
        'indices_db': indices,
        'num_matches': num_matches,
    }

  if poses_gt_file is not None:
    logger.info('Evaluating...')
    poses_gt = {}
    with open(dataset_dir / poses_gt_file, 'r') as poses_gt_csv:
      for row in csv.reader(poses_gt_csv, delimiter=' '):
        if row[0] in retrieval_dict:  # queries
          qtvec = np.fromiter(
              (float(row[idx]) for idx in range(1, 8)), dtype=float)
          poses_gt[row[0]] = (qtvec[:4], qtvec[4:7])

    thresholds_tRdeg = ((0.01, 1.), (0.02, 2.), (0.05, 5.), (0.1, 10.))
    med_err_t, med_err_R, ratio_localized = evaluate(
        poses, poses_gt, thresholds_tRdeg=thresholds_tRdeg)
    out = f'Median errors: {med_err_t:.3f}m, {med_err_R:.3f}deg'
    out += '\nImages localized within threshold:'
    for (th_t, th_R), ratio_loc in zip(thresholds_tRdeg, ratio_localized):
      out += f'\n{th_t*100:.0f}cm, {th_R:.0f}deg : {ratio_loc*100:.2f}%'
    logger.info(out)

  logger.info(f'Writing poses to {results}...')
  with open(results, 'w') as f:
    for q in queries:
      qvec, tvec = poses[q]
      qvec = ' '.join(map(str, qvec))
      tvec = ' '.join(map(str, tvec))
      f.write(f'{q} {qvec} {tvec}\n')

  logs_path = f'{results}_logs.pkl'
  logger.info(f'Writing logs to {logs_path}...')
  with open(logs_path, 'wb') as f:
    pickle.dump(logs, f)
  logger.info('Done!')


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--dataset_dir', type=Path, required=True)
  parser.add_argument('--retrieval', type=Path, required=True)
  parser.add_argument('--features', type=Path, required=True)
  parser.add_argument('--matches', type=Path, required=True)
  parser.add_argument('--results', type=Path, required=True)
  parser.add_argument('--skip_matches', type=int)
  args = parser.parse_args()
  main(**args.__dict__)
