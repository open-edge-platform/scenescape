#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2019 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import math
import os
from argparse import ArgumentParser

import cv2
import numpy as np

matrix_map = [[ -7.97239399e-01,  -4.30985504e-01,  -4.22682903e-01,   3.90266716e+02],
              [  8.82206161e-02,  -7.75861415e-01,   6.24704880e-01,   1.60876672e+02],
              [ -5.97182103e-01,   4.60749997e-01,   6.56569095e-01,   1.76965189e+02]]

def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("images", nargs="+", help="images of lab")
  parser.add_argument("--map", default="map.png", help="image of map")
  return parser

def create_overlay(map_img, cam_img, transform):
  map_img = 255 - map_img
  mask = np.uint8(cv2.cvtColor(map_img, cv2.COLOR_BGR2GRAY) / 128)
  warp = cv2.warpPerspective(map_img, transform,
                             (cam_img.shape[1], cam_img.shape[0]))
  mask = cv2.warpPerspective(mask, transform,
                             (cam_img.shape[1], cam_img.shape[0]))
  mask = np.dstack((mask, mask, mask))
  foreground = warp * mask
  background = cam_img * (1 - mask)
  overlay = cv2.bitwise_xor(foreground, background)
  return overlay

def align_map(name, input_mat, extrinsics, map_img, cam_img, camera_intrinsics):
  x = np.array([[0, 0, 0, 1]])
  mat = np.concatenate((input_mat, x))
  mat = np.matmul(extrinsics, mat)[:3]
  r1_2 = mat[:, :2]
  tvecs = mat[:, 3:]
  hmat = np.concatenate((r1_2, tvecs), axis=1)
  hmat *= 1 / hmat[2, 2]
  transform = np.matmul(camera_intrinsics, hmat)
  overlay = create_overlay(map_img, cam_img, transform)
  cv2.imshow(name, overlay)
  return

def fix_mat(mat):
  mat = np.array(mat)
  x = np.array([[0, 0, 0, 1]])
  mat = np.concatenate((mat, x))
  swap_yz = np.array([[1, 0, 0, 0],
                      [0, 0, 1, 0],
                      [0, 1, 0, 0],
                      [0, 0, 0, 1]])
  fix = np.matmul(mat, swap_yz)
  return fix[:3]

def load_img_mat(path):
  base, ext = os.path.splitext(path)
  mat_path = base + ".txt"
  image = cv2.imread(path)
  with open(mat_path, mode="r") as f:
    jmat = f.read()
  return image, fix_mat(np.array(json.loads(jmat)))

def main():
  global matrix_map

  args = build_argparser().parse_args()

  map_img = cv2.imread(args.map)

  # Load images and matrices
  matrices = []
  for path in args.images:
    img, mat = load_img_mat(path)
    matrices.append((img, mat))

  x = np.array([[0, 0, 0, 1]])
  reg = np.concatenate((matrix_map, x))
  mat = np.concatenate((matrices[0][1], x))
  i = np.linalg.inv(mat)
  extrinsics = np.matmul(reg, i)
  print(extrinsics)

  x, y = matrices[0][0].shape[1::-1]
  fov = 70
  diag = math.sqrt(x**2 + y**2)
  fy = fx = diag / (2 * math.tan(math.radians(fov/2)))
  cx = x/2
  cy = y/2
  camera_intrinsics = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])

  for idx in range(len(matrices)):
    m = matrices[idx]
    name = str(idx+1)
    align_map(name, m[1], extrinsics, map_img, m[0], camera_intrinsics)

  while True:
    key = cv2.waitKey(100)
    if key == 27 or key == ord('q'):
      break
  cv2.destroyAllWindows()

  return

if __name__ == '__main__':
  exit(main() or 0)
