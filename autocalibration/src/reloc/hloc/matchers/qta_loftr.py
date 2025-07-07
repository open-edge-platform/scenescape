# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from FeatureMatching.src.utils.misc import lower_config
from FeatureMatching.src.config.default import get_cfg_defaults
from FeatureMatching.src.loftr import LoFTR
import sys
from pathlib import Path
from collections import namedtuple
import torch
from addict import Dict
from ..utils.base_model import BaseModel

sys.path.append(str(Path(__file__).parent / "../../third_party/QuadTreeAttention"))

# get_cfg_defaults():
# ##############  ↓  LoFTR Pipeline  ↓  ##############
# _CN.LOFTR = CN()
# _CN.LOFTR.BACKBONE_TYPE = 'ResNetFPN'
# _CN.LOFTR.RESOLUTION = (8, 2)  # options: [(8, 2), (16, 4)]
# _CN.LOFTR.FINE_WINDOW_SIZE = 5  # window_size in fine_level, must be odd
# _CN.LOFTR.FINE_CONCAT_COARSE_FEAT = True
#
# # 1. LoFTR-backbone (local feature CNN) config
# _CN.LOFTR.RESNETFPN = CN()
# _CN.LOFTR.RESNETFPN.INITIAL_DIM = 128
# _CN.LOFTR.RESNETFPN.BLOCK_DIMS = [128, 196, 256]  # s1, s2, s3
#
# # 2. LoFTR-coarse module config
# _CN.LOFTR.COARSE = CN()
# _CN.LOFTR.COARSE.D_MODEL = 256
# _CN.LOFTR.COARSE.D_FFN = 256
# _CN.LOFTR.COARSE.NHEAD = 8
# _CN.LOFTR.COARSE.LAYER_NAMES = ['self', 'cross'] * 4
# _CN.LOFTR.COARSE.ATTENTION = 'linear'  # options: ['linear', 'full']
# _CN.LOFTR.COARSE.TEMP_BUG_FIX = True
# _CN.LOFTR.COARSE.BLOCK_TYPE = 'loftr'
# _CN.LOFTR.COARSE.ATTN_TYPE = 'B'
# _CN.LOFTR.COARSE.TOPKS = [16, 8, 8]
#
# # 3. Coarse-Matching config
# _CN.LOFTR.MATCH_COARSE = CN()
# _CN.LOFTR.MATCH_COARSE.THR = 0.2
# _CN.LOFTR.MATCH_COARSE.BORDER_RM = 2
# _CN.LOFTR.MATCH_COARSE.MATCH_TYPE = 'dual_softmax'  # options: ['dual_softmax, 'sinkhorn']
# _CN.LOFTR.MATCH_COARSE.DSMAX_TEMPERATURE = 0.1
# _CN.LOFTR.MATCH_COARSE.SKH_ITERS = 3
# _CN.LOFTR.MATCH_COARSE.SKH_INIT_BIN_SCORE = 1.0
# _CN.LOFTR.MATCH_COARSE.SKH_PREFILTER = False
# _CN.LOFTR.MATCH_COARSE.TRAIN_COARSE_PERCENT = 0.2  # training tricks: save GPU memory
# _CN.LOFTR.MATCH_COARSE.TRAIN_PAD_NUM_GT_MIN = 200  # training tricks: avoid DDP deadlock
# _CN.LOFTR.MATCH_COARSE.SPARSE_SPVS = True
#
# # 4. LoFTR-fine module config
# _CN.LOFTR.FINE = CN()
# _CN.LOFTR.FINE.D_MODEL = 128
# _CN.LOFTR.FINE.D_FFN = 128
# _CN.LOFTR.FINE.NHEAD = 8
# _CN.LOFTR.FINE.LAYER_NAMES = ['self', 'cross'] * 1
# _CN.LOFTR.FINE.ATTENTION = 'linear'
# _CN.LOFTR.FINE.BLOCK_TYPE = 'loftr'
#
# # 5. LoFTR Losses
# # -- # coarse-level
# _CN.LOFTR.LOSS = CN()
# _CN.LOFTR.LOSS.COARSE_TYPE = 'focal'  # ['focal', 'cross_entropy']
# _CN.LOFTR.LOSS.COARSE_WEIGHT = 1.0
# # _CN.LOFTR.LOSS.SPARSE_SPVS = False
# # -- - -- # focal loss (coarse)
# _CN.LOFTR.LOSS.FOCAL_ALPHA = 0.25
# _CN.LOFTR.LOSS.FOCAL_GAMMA = 2.0
# _CN.LOFTR.LOSS.POS_WEIGHT = 1.0
# _CN.LOFTR.LOSS.NEG_WEIGHT = 1.0
# # _CN.LOFTR.LOSS.DUAL_SOFTMAX = False  # whether coarse-level use dual-softmax or not.
# # use `_CN.LOFTR.MATCH_COARSE.MATCH_TYPE`
#
# # -- # fine-level
# _CN.LOFTR.LOSS.FINE_TYPE = 'l2_with_std'  # ['l2_with_std', 'l2']
# _CN.LOFTR.LOSS.FINE_WEIGHT = 1.0
# _CN.LOFTR.LOSS.FINE_CORRECT_THR = 1.0  # for filtering valid fine-level gts (some gt matches might fall out of the fine-level window)

PredDict = namedtuple("PredDict", ["scores", "keypoints0", "keypoints1"])


class QTA_LoFTR_(BaseModel):
  required_inputs = ["image0", "image1"]

  def _init(self, conf_):

    cfg = get_cfg_defaults().LOFTR
    # from: configs/loftr/indoor/scannet/loftr_ds_quadtree_eval.py
    # cfg.COARSE.TEMP_BUG_FIX = False
    cfg.MATCH_COARSE.MATCH_TYPE = "dual_softmax"
    cfg.MATCH_COARSE.SPARSE_SPVS = False
    cfg.RESNETFPN.INITIAL_DIM = 128
    cfg.RESNETFPN.BLOCK_DIMS = [128, 196, 256]
    cfg.COARSE.D_MODEL = 256
    cfg.COARSE.BLOCK_TYPE = "quadtree"
    cfg.COARSE.ATTN_TYPE = "B"
    cfg.COARSE.TOPKS = [32, 16, 16]
    cfg.FINE.D_MODEL = 128
    # SS
    cfg.CACHE_BACKBONE = True
    conf = Dict(lower_config(cfg))
    conf.update(conf_)

    self.net = LoFTR(config=conf)
    ckpt_path = Path(__file__).parent / (
        "../../third_party/QuadTreeAttention/FeatureMatching/weights/"
        + conf["weights"]
        + ".ckpt"
    )
    self.net.load_state_dict(
        torch.load(ckpt_path, map_location=torch.device("cpu"))["state_dict"]
    )

  def _forward(self, data):
    self.net(data)
    # Assign matches to individual image pairs in batch
    b_ids = data["b_ids"]
    batch_start = (
        b_ids.diff(
            prepend=-torch.ones(1, device=b_ids.device, dtype=b_ids.dtype),
            append=torch.full(
                (1,), b_ids.shape[0], device=b_ids.device, dtype=b_ids.dtype
            ),
        )
        .nonzero()
        .cpu()
        .numpy()
        .reshape(-1)
    )
    bs = [None] * data["image0"].shape[0]
    for i, j in zip(batch_start[:-1], batch_start[1:]):
      bs[b_ids[i]] = (i, j)
    prev = b_ids.shape[0]
    for b_id in range(len(bs) - 1, -1, -1):
      if bs[b_id] is None:  # no kpts from this image pair
        bs[b_id] = (prev, prev)
      else:
        prev = bs[b_id][0]

    pred = PredDict(
        scores=tuple(data["mconf"][st:en] for (st, en) in bs),
        keypoints0=tuple(data["mkpts0_f"][st:en] for (st, en) in bs),
        keypoints1=tuple(data["mkpts1_f"][st:en] for (st, en) in bs),
    )

    return pred


# /home/ssheorey/Documents/Open3D/Code/Hierarchical-Localization/hloc/matchers/../../third_party/QuadTreeAttention/FeatureMatching/src/loftr/loftr.py:45:
# TracerWarning: Converting a tensor to a Python boolean might cause the trace to be
# incorrect. We can't record the data flow of Python values, so this value will be
# treated as a constant in the future. This means that the trace might not generalize
# to other inputs!
#  if data['hw0_i'] == data['hw1_i']:  # faster & better BN convergence

# /home/ssheorey/Documents/Open3D/Code/Hierarchical-Localization/hloc/matchers/../../third_party/QuadTreeAttention/FeatureMatching/src/loftr/loftr_module/fine_preprocess.py:34: TracerWarning: Converting a tensor to a Python boolean might cause the trace to be incorrect. We can't record the data flow of Python values, so this value will be treated as a constant in the future. This means that the trace might not generalize to other inputs!
#   if data['b_ids'].shape[0] == 0:

#: TracerWarning: Converting a tensor to a Python number might cause the trace to be incorrect. We can't record the data flow of Python values, so this value will be treated as a constant in the future. This means that the trace might not generalize to other inputs!
#  stride = (data['hw0_f'][0] // data['hw0_c'][0]).item()
