import json
import open3d as o3d
import os
from argparse import ArgumentParser


def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("--bag_file", help="path to bag file")
  parser.add_argument("--bag_frames", help="path to output folder")
  return parser


def convert_json(bag_frames):
  with open(os.path.join(bag_frames, "intrinsic.json")) as json_str:
    data = json.load(json_str)
    txt = open(os.path.join(bag_frames, "cameras.txt"), "w")
    txt.write("#camera_id model width height params\n")
    intrinsic = data['intrinsic_matrix']
    txt.write(f"0 OPENCV {data['width']} {data['height']} {intrinsic[0]} {
              intrinsic[4]} {intrinsic[6]} {intrinsic[7]} 0 0 0 0")
    txt.close()


def main():
  args = build_argparser().parse_args()
  if args.bag_file != None:
    bag_reader = o3d.t.io.RSBagReader()
    opened = bag_reader.open(args.bag_file)
    if opened:
      bag_reader.save_frames(args.bag_frames)
      bag_reader.close()
  convert_json(args.bag_frames)
  os.rename(args.bag_frames+"/color", args.bag_frames+"/rgb")


if __name__ == '__main__':
  exit(main() or 0)
