from typing import Optional, List, Tuple, Union, Sequence
from pathlib import Path
import pprint
import argparse
from collections import defaultdict, Counter
from itertools import chain
from concurrent.futures import Executor, ThreadPoolExecutor
import threading

from tqdm import tqdm
import numpy as np
import h5py
import torch
from addict import Dict
import torchvision.transforms.functional as F
from scipy.spatial import KDTree

from . import matchers, logger
from .utils.base_model import cached_load
from .utils.parsers import parse_retrieval, names_to_pair
from .match_features import find_unique_new_pairs
from .extract_features import resize_image
from .utils.io import list_h5_names, read_image, base64_to_image

confs = {
    "qta_indoor": {
        "output": "matches-qta",
        "model": {
            "name": "qta_loftr",
            "weights": "indoor",
            "match_coarse": {"thr": 0.1},
            "coarse": {"topks": [64, 16, 16]},
        },
        "preprocessing": {"grayscale": True, "resize_max": 832, "dfactor": 32},
        "max_error": 1,  # max error for assigned keypoints (in px)
        "cell_size": 1,  # size of quantization patch
        "init_ref_score": 10.0,
        "top_k": False,
        "batch_size": 1,
    },
    "qta_indoor_fast": {
        "output": "matches-qta",
        "model": {
            "name": "qta_loftr",
            "weights": "indoor",
            "match_threshold": 0.2,
            "topks": [16, 8, 8],
        },
        "preprocessing": {"grayscale": True, "resize_max": 1024, "dfactor": 32},
        "max_error": 0,  # max error for assigned keypoints (in px)
        "cell_size": 0,  # size of quantization patch
        "init_ref_score": 10.0,
        "top_k": False,
        "batch_size": 1,
    },
    "qta_outdoor": {
        "output": "matches-qta",
        "model": {
            "name": "qta_loftr",
            "weights": "outdoor",
            "match_threshold": 0.2,
            "topks": [32, 16, 16],
        },
        "preprocessing": {"grayscale": True, "resize_max": 1024, "dfactor": 32},
        "max_error": 0,  # max error for assigned keypoints (in px)
        "cell_size": 0,  # size of quantization patch
        "init_ref_score": 10.0,
        "top_k": False,
        "batch_size": 1,
    },
    "loftr": {
        "output": "matches-loftr",
        "model": {"name": "loftr", "weights": "outdoor"},
        "preprocessing": {"grayscale": True, "resize_max": 1024, "dfactor": 8},
        "max_error": 1,  # max error for assigned keypoints (in px)
        "cell_size": 1,  # size of quantization patch
        "init_ref_score": 10.0,
        "batch_size": 1,
    },
    "loftr_aachen": {
        "output": "matches-loftr_aachen",
        "model": {"name": "loftr", "weights": "outdoor"},
        "preprocessing": {"grayscale": True, "resize_max": 1024, "dfactor": 8},
        "max_error": 2,  # max error for assigned keypoints (in px)
        "cell_size": 8,  # size of quantization patch
        "init_ref_score": 10.0,
        "batch_size": 1,
    },
    "loftr_inloc": {
        "output": "matches-loftr_inloc",
        "model": {"name": "loftr", "weights": "indoor"},
        "preprocessing": {"grayscale": True, "resize_max": 1024, "dfactor": 8},
        "max_error": 0,  # max error for assigned keypoints (in px)
        "cell_size": 0,  # size of quantization patch
        "init_ref_score": 10.0,
        "top_k": False,
        "batch_size": 1,
    },
}


def add_keypoints(
    kpts: np.ndarray,
    other_cpts: np.ndarray,
    update: bool = False,
    # ref_bins: List = [],
    # scores: np.ndarray = [],
):
  if update:
    kpt_ids = np.arange(
        len(other_cpts), len(other_cpts) + len(kpts), dtype=np.int32
    )
  else:
    kpt_ids = np.arange(len(kpts), dtype=np.int32)
  other_cpts.append(kpts)
  # ref_bins.append(scores)
  return kpt_ids


def assign_keypoints(
    kpts: np.ndarray,
    other_cpts: Union[List[Tuple], np.ndarray],
    max_error: float,
    update: bool = False,
    ref_bins: Optional[List[Counter]] = None,
    scores: Optional[np.ndarray] = None,
    cell_size: Optional[int] = None,
):
  if max_error == 0 or cell_size == 0:
    return add_keypoints(kpts, other_cpts, update)
  if not update:
    # Without update this is just a NN search
    dist, kpt_ids = KDTree(np.array(other_cpts)).query(kpts)
    valid = dist <= max_error
    kpt_ids[~valid] = -1
    return kpt_ids
  else:
    ps = cell_size if cell_size is not None else max_error
    ps = max(cell_size, max_error)
    # With update we quantize and bin (optionally)
    assert isinstance(other_cpts, list)
    kpt_ids = []
    cpts = to_cpts(kpts, ps)
    bpts = to_cpts(kpts, max_error)
    cp_to_id = {val: i for i, val in enumerate(other_cpts)}
    for i, (cpt, bpt) in enumerate(zip(cpts, bpts)):
      try:
        kid = cp_to_id[cpt]
      except KeyError:
        kid = len(cp_to_id)
        cp_to_id[cpt] = kid
        other_cpts.append(cpt)
        if ref_bins is not None:
          ref_bins.append(Counter())
      if ref_bins is not None:
        score = scores[i] if scores is not None else 1
        ref_bins[cp_to_id[cpt]][bpt] += score
      kpt_ids.append(kid)
    return np.array(kpt_ids)


def get_grouped_ids(array):
  # Group array indices based on its values
  # all duplicates are grouped as a set
  idx_sort = np.argsort(array)
  sorted_array = array[idx_sort]
  _, ids, _ = np.unique(sorted_array, return_counts=True, return_index=True)
  res = np.split(idx_sort, ids[1:])
  return res


def get_unique_matches(match_ids, scores):
  if len(match_ids.shape) == 1:
    return [0]

  isets1 = get_grouped_ids(match_ids[:, 0])
  isets2 = get_grouped_ids(match_ids[:, 0])
  uid1s = [ids[scores[ids].argmax()] for ids in isets1 if len(ids) > 0]
  uid2s = [ids[scores[ids].argmax()] for ids in isets2 if len(ids) > 0]
  uids = list(set(uid1s).intersection(uid2s))
  return match_ids[uids], scores[uids]


def to_cpts(kpts, ps):
  cpts = np.round(np.round((kpts + 0.5) / ps) * ps - 0.5, 2)
  return [tuple(cpt) for cpt in cpts]


def matches_to_matches0(matches, scores):
  if matches.shape[0] == 0:
    return (np.zeros([0, 2], dtype=np.uint32), np.zeros([0], dtype=np.float32))
  n_kps0 = np.max(matches[:, 0]) + 1
  matches0 = -np.ones((n_kps0,))
  scores0 = np.zeros((n_kps0,))
  matches0[matches[:, 0]] = matches[:, 1]
  scores0[matches[:, 0]] = scores
  return matches0.astype(np.int32), scores0.astype(np.float16)


def kpids_to_matches0(kpt_ids0, kpt_ids1, scores):
  valid = (kpt_ids0 != -1) & (kpt_ids1 != -1)
  matches = np.dstack([kpt_ids0[valid], kpt_ids1[valid]])
  matches = matches.reshape(-1, 2)
  scores = scores[valid]

  # Remove n-to-1 matches
  matches, scores = get_unique_matches(matches, scores)
  return matches_to_matches0(matches, scores)


def scale_keypoints(kpts, scale):
  if torch.any(scale != 1.0):
    kpts *= scale
  return kpts


class SimpleExecutor(Executor):
  """Simple executor that runs the function in the main thread."""

  def __init__(self, max_workers=0):
    pass

  def submit(self, fn, *args, **kwargs):
    return fn(*args, **kwargs)

  def map(self, fn, *iterables, timeout=None, chunksize=1):
    return map(fn, *iterables)

  def shutdown(self, wait=True):
    pass

  def __enter__(self):
    return self

  def __exit__(self, *args):
    self.shutdown()


class ImagePairDataset(torch.utils.data.Dataset):
  """Dataset and dataloader class for image pairs. Features:
  - multi-threaded data loading.
  - batch-size
  - prefetch
  """

  default_conf = {
      "grayscale": True,
      "resize_max": 1024,
      "dfactor": 8,
      "prefetch_factor": 2,  # number of prefetched batches
      "num_workers": 1,
  }

  def __init__(
      self,
      image_dir: Union[Path, Tuple[Path, Path]],
      conf: Dict,
      pairs: Sequence,
      batch_size: int = 1,
      image_cache: Dict = None,
  ):
    self.image_dir = (
        (image_dir, image_dir) if isinstance(image_dir, Path) else image_dir
    )
    self.conf = self.default_conf | Dict(conf)
    self.pairs = pairs
    self.batch_size = batch_size
    self.cache_size = (1 + self.conf.prefetch_factor) * batch_size * 2
    self.imsize = None
    self.n_keep = 0
    self.images = {}
    self.images_cv = threading.Condition()
    if self.conf.num_workers > 0:
      self.pool = ThreadPoolExecutor(
          max_workers=self.conf.num_workers,
          thread_name_prefix=self.__class__.__name__,
      )
    else:
      self.pool = SimpleExecutor()
    # preprocess first dataset image to get image size
    self.preprocess(self.pairs[0][1], None, self.image_dir[1] / self.pairs[0][1])
    if image_cache is not None:  # SceneScape message
      self.n_keep = len(image_cache)
      for name, b64im in image_cache.items():
        self.pool.submit(self.preprocess, name, b64im)

  def preprocess(self, name: str, b64im=None, filepath: Path = None):
    """Reading, decoding and pre-processing runs in worker threads."""
    if filepath is not None:
      image = read_image(filepath, self.conf.grayscale)
    else:
      image = base64_to_image(b64im, self.conf.grayscale, log_as=name)
    image = image.astype(np.float32, copy=False)
    size = image.shape[:2][::-1]
    scale = np.array([1.0, 1.0])
    size_new = np.array(size)

    if self.imsize is not None:
      size_new = self.imsize
    else:
      if self.conf.resize_max < max(size):
        scale = self.conf.resize_max / max(size)
        size_new = tuple(int(round(x * scale)) for x in size)
      # assure that the size is divisible by dfactor
      size_new = tuple(
          int(x // self.conf.dfactor * self.conf.dfactor) for x in size_new
      )
    scale = torch.Tensor(size) / torch.Tensor(size_new)
    image = resize_image(image, size_new, "cv2_area")

    if self.conf.grayscale:
      assert image.ndim == 2, image.shape
      image = image[None, None]
    else:
      image = image.transpose((2, 0, 1))[None]  # HxWxC to CxHxW
    image = torch.from_numpy(image / 255.0).float()

    with self.images_cv:
      if self.imsize is None:
        self.imsize = size_new
      self.images[name] = (image, scale[None])
      self.images_cv.notify_all()

  def __len__(self):
    return (len(self.pairs) + self.batch_size - 1) // self.batch_size

  def __getitem__(self, b_idx):
    if b_idx >= len(self):
      raise IndexError()
    images0, images1, scales0, scales1, names0, names1 = ([] for _ in range(6))
    stop = min(
        len(self.pairs), (b_idx + 1 + self.conf.prefetch_factor) * self.batch_size
    )
    with self.images_cv:
      for idx in range(b_idx * self.batch_size, stop):
        name0, name1 = self.pairs[idx]
        for i, name in enumerate((name0, name1)):
          if name not in self.images and self.image_dir[i] is not None:
            self.pool.submit(
                self.preprocess, name, None, self.image_dir[i] / name
            )

      for idx in range(
          b_idx * self.batch_size,
          min(len(self.pairs), (b_idx + 1) * self.batch_size),
      ):
        name0, name1 = self.pairs[idx]
        names0.append(name0)
        names1.append(name1)
        if name0 not in self.images:
          self.images_cv.wait_for(lambda: name0 in self.images)
        ims = self.images[name0]
        images0.append(ims[0])
        scales0.append(ims[1])
        if name1 not in self.images:
          self.images_cv.wait_for(lambda: name1 in self.images)
        ims = self.images[name1]
        images1.append(ims[0])
        scales1.append(ims[1])

      if len(self.images) > self.cache_size:
        remove_names = tuple(self.images.keys())[
            self.n_keep: self.n_keep + self.cache_size
        ]
        for name in remove_names:
          self.images.pop(name)

    if self.batch_size == 1:
      return images0[0], images1[0], scales0[0], scales1[0], names0, names1
    return (  # torch.cat copies data, even for single elements
        torch.cat(images0),
        torch.cat(images1),
        torch.cat(scales0),
        torch.cat(scales1),
        names0,
        names1,
    )


@torch.no_grad()
def match_dense_from_paths(
    conf: Dict,
    pairs_path: Path,
    image_dir: Union[Path, Tuple[Path, Path]],
    match_path: Path,  # out
    feature_path_q: Path,  # out
    feature_paths_refs: Optional[List[Path]] = (),
    # use reassign to reduce quant error (not in loc)
    reassign: Union[bool, float] = True,
    max_kps: Optional[int] = None,
    overwrite: bool = False,
    image_cache: Dict = None,
) -> Path:
  conf = {"psize": 1} | Dict(conf)
  pairs = parse_retrieval(pairs_path)
  pairs = [(q, r) for q, rs in pairs.items() for r in rs]
  pairs = find_unique_new_pairs(pairs, None if overwrite else match_path)
  required_queries = set(sum(pairs, ()))

  name2ref = {
      n: i for i, p in enumerate(feature_paths_refs) for n in list_h5_names(p)
  }
  existing_refs = required_queries.intersection(set(name2ref.keys()))
  required_queries = required_queries - existing_refs

  if feature_path_q.exists() and not overwrite:
    feature_paths_refs += (feature_path_q,)
    existing_refs = set.union(existing_refs, list_h5_names(feature_path_q))
    q_name2ref = {n: -1 for n in list_h5_names(feature_path_q)}
    name2ref = {**name2ref, **q_name2ref}

  if len(pairs) == 0 and len(required_queries) == 0:
    logger.info("All pairs exist. Skipping dense matching.")
    return

  model = cached_load(matchers, conf["model"])

  # Load query keypoins
  cpdict = defaultdict(list)
  bindict = defaultdict(list)

  if len(existing_refs) > 0:
    logger.info(f"Pre-loaded keypoints from {len(existing_refs)} images.")
  for name in existing_refs:
    with h5py.File(str(feature_paths_refs[name2ref[name]]), "r") as fd:
      kps = fd[name]["keypoints"].__array__()
      if name not in required_queries:
        cpdict[name] = kps
      else:
        if "scores" in fd[name].keys():
          kp_scores = fd[name]["scores"].__array__()
        else:
          kp_scores = [conf.init_ref_score for _ in range(kps.shape[0])]
        assign_keypoints(
            kps,
            cpdict[name],
            conf.max_error,
            True,
            bindict[name],
            kp_scores,
            conf.cell_size,
        )

  # sort pairs for reduced RAM
  pairs_per_q = Counter(list(chain(*pairs)))
  pairs_score = [min(pairs_per_q[i], pairs_per_q[j]) for i, j in pairs]
  pairs = [p for _, p in sorted(zip(pairs_score, pairs))]

  dataset = ImagePairDataset(
      image_dir, conf.preprocessing, pairs, conf.batch_size, image_cache
  )
  logger.info(f"Performing dense matching for {len(dataset)} image pairs...")
  n_kps = 0
  with h5py.File(str(match_path), "a") as fd:
    for data in tqdm(dataset, smoothing=0.1):
      # load image-pair data
      images0, images1, scales0, scales1, names0, names1 = data
      images0 = images0.to(cached_load.device)
      images1 = images1.to(cached_load.device)
      scales0 = scales0.to(cached_load.device)
      scales1 = scales1.to(cached_load.device)

      # match semi-dense
      pred = model({"image0": images0, "image1": images1})

      for kpts0, kpts1, scores, scale0, scale1, name0, name1 in zip(
          pred.keypoints0,
          pred.keypoints1,
          pred.scores,
          scales0,
          scales1,
          names0,
          names1,
      ):
        # Rescale keypoints and move to cpu
        kpts0 = scale_keypoints(kpts0 + 0.5, scale0) - 0.5
        kpts1 = scale_keypoints(kpts1 + 0.5, scale1) - 0.5
        kpts0 = kpts0.cpu().numpy()
        kpts1 = kpts1.cpu().numpy()
        scores = scores.cpu().numpy()

        # Aggregate local features
        update0 = name0 in required_queries
        update1 = name1 in required_queries
        kpt_ids0 = assign_keypoints(
            kpts0,
            cpdict[name0],
            conf.max_error,
            update0,
            bindict[name0],
            scores,
            conf.cell_size,
        )
        kpt_ids1 = assign_keypoints(
            kpts1,
            cpdict[name1],
            conf.max_error,
            update1,
            bindict[name1],
            scores,
            conf.cell_size,
        )

        # Build matches from assignments
        matches0, scores0 = kpids_to_matches0(kpt_ids0, kpt_ids1, scores)

        # Write matches and matching scores in hloc format
        pair = names_to_pair(name0, name1)
        if pair in fd:
          del fd[pair]
        grp = fd.create_group(pair)
        assert kpts0.shape[0] == scores.shape[0]

        grp.create_dataset("matches0", data=matches0)
        grp.create_dataset("matching_scores0", data=scores0)

        # Write dense matching output
        grp.create_dataset("keypoints0", data=kpts0)
        grp.create_dataset("keypoints1", data=kpts1)
        grp.create_dataset("scores", data=scores)

        # Convert bins to kps if finished, and store them
        for name in (name0, name1):
          pairs_per_q[name] -= 1
          if pairs_per_q[name] > 0 or name not in required_queries:
            continue
          if conf.cell_size == 0 or conf.max_error == 0:
            kp_score = bindict[name]
            cpdict[name] = np.vstack(cpdict[name])
          else:
            kp_score = [c.most_common(1)[0][1] for c in bindict[name]]
            cpdict[name] = [c.most_common(1)[0][0] for c in bindict[name]]
            cpdict[name] = np.array(cpdict[name], dtype=np.float32)
          if max_kps:
            top_k = min(max_kps, cpdict[name].shape[0])
            top_k = np.argsort(kp_score)[::-1][:top_k]
            cpdict[name] = cpdict[name][top_k]
            kp_score = np.array(kp_score)[top_k]
          with h5py.File(feature_path_q, "a") as kfd:
            if name in kfd:
              del kfd[name]
            kgrp = kfd.create_group(name)
            kgrp.create_dataset("keypoints", data=cpdict[name])
            kgrp.create_dataset("score", data=kp_score)
            n_kps += cpdict[name].shape[0]
          del bindict[name]

  if len(required_queries) > 0:
    avg_kp_per_image = round(n_kps / len(required_queries), 1)
    logger.info(
        f"Finished assignment, found {avg_kp_per_image} "
        f"keypoints/image (avg.), total {n_kps}."
    )

  # Invalidate matches that are far from selected bin by reassignment
  if reassign or conf.top_k:
    max_error = conf.max_error
    if not isinstance(reassign, bool):
      max_error = reassign
    logger.info(f"Reassign matches with max_error={max_error}.")
    with h5py.File(str(match_path), "a") as fd:
      for name0, name1 in tqdm(pairs):
        pair = names_to_pair(name0, name1)
        grp = fd[pair]
        kpts0 = grp["keypoints0"].__array__()
        kpts1 = grp["keypoints1"].__array__()
        scores = grp["scores"].__array__()
        if len(scores) == 0:
          continue

        kpids0 = assign_keypoints(kpts0, cpdict[name0], max_error)
        kpids1 = assign_keypoints(kpts1, cpdict[name1], max_error)
        matches0, scores0 = kpids_to_matches0(kpids0, kpids1, scores)

        del grp["matches0"], grp["matching_scores0"]

        # overwrite matches0 and matching_scores0
        grp.create_dataset("matches0", data=matches0)
        grp.create_dataset("matching_scores0", data=scores0)


@torch.no_grad()
def main(
    conf: Dict,
    pairs: Path,
    image_dir: Path,
    export_dir: Optional[Path] = None,
    matches: Optional[Path] = None,  # out
    features: Optional[Path] = None,  # out
    features_ref: Union[Path, Sequence[Path]] = (),
    reassign: Union[bool, float] = True,
    overwrite: bool = False,
    image_cache: Dict = None,
) -> Path:
  """
  Args:
      image_cache (Dict): Mapping of image name to base64 encoded jpeg
          compressed image data.
  """
  logger.info(
      "Extracting semi-dense features with configuration:\n%s", pprint.pformat(conf)
  )

  if features is None:
    features = "feats_"

  if isinstance(features, Path):
    features_q = features
    if matches is None:
      raise ValueError(
          "Either provide both features and matches as Path or both as names."
      )
  else:
    if export_dir is None:
      raise ValueError(
          "Provide an export_dir if features and matches"
          f" are not file paths: {features}, {matches}."
      )
    features_q = Path(export_dir, f'{features}_{conf["output"]}_.h5')
    if matches is None:
      matches = Path(export_dir, f'{conf["output"]}_{pairs.stem}.h5')

  if isinstance(features_ref, Path):
    features_ref = (features_ref,)

  match_dense_from_paths(
      conf,
      pairs,
      image_dir,
      matches,
      features_q,
      feature_paths_refs=features_ref,
      reassign=reassign,
      overwrite=overwrite,
      image_cache=image_cache,
  )

  return features_q, matches


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--pairs", type=Path, required=True)
  parser.add_argument("--image_dir", type=Path, required=True)
  parser.add_argument("--export_dir", type=Path, required=True)
  parser.add_argument("--matches", type=Path, default=confs["loftr"]["output"])
  parser.add_argument(
      "--features", type=str, default="feats_" + confs["loftr"]["output"]
  )
  parser.add_argument("--conf", type=str, default="loftr", choices=list(confs.keys()))
  args = parser.parse_args()
  main(
      confs[args.conf],
      args.pairs,
      args.image_dir,
      args.export_dir,
      args.matches,
      args.features,
  )
