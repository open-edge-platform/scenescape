#!/usr/bin/env python
"""
Evaluate 3D MOT PoC dataset using TrackEval with Euclidean distance similarity.
"""

from trackeval import Evaluator
from trackeval.datasets.mot_challenge_3d_point import MotChallenge3DPoint
from trackeval.metrics import HOTA, CLEAR, Identity

dataset_config = MotChallenge3DPoint.get_default_dataset_config()
dataset_config.update({
    'GT_FOLDER': 'data/3DMOT/gt',
    'BENCHMARK': 'Simple3DMOT',
    'TRACKERS_FOLDER': 'data/3DMOT/trackers',
    'SEQMAP_FILE': 'data/3DMOT/seqmaps/3dmot-test.txt',
    'SEQ_INFO': {'seq01': 3},  # Sequence name and length (num timesteps)
    'GT_LOC_FORMAT': '{gt_folder}/{seq}/gt.txt',  # Override default format to match PoC structure
#    'TRACKER_LOC_FORMAT': '{trackers_folder}/{tracker}/{seq}.txt',  # Tracker in subdirectory
    'DO_PREPROC': True,
})

evaluator = Evaluator({
    'USE_PARALLEL': False,
    'PRINT_RESULTS': True,
})

dataset = MotChallenge3DPoint(dataset_config)

metrics = [
    HOTA({'THRESHOLD': -2.0}),
    CLEAR(),
    Identity()
]

evaluator.evaluate([dataset], metrics)
