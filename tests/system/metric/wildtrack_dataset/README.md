<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Wildtrack Preprocessed Artifacts

This directory contains preprocessed [WILDTRACK](https://arxiv.org/pdf/1707.09299.pdf)
dataset artifacts in Scenescape canonical formats, consumed by
[`WildtrackDataset`](../../../../tools/tracker/evaluation/datasets/wildtrack_dataset.py)
in the tracker evaluation pipeline.

## Contents

- `scene_config.json` — Scene and per-camera configuration (explicit intrinsics and extrinsics)
- `cam0.json`–`cam6.json` — Per-camera object detections (JSONL, one frame per line)
- `gtLoc.json` — Ground-truth object locations per frame

These files are generated from the raw dataset with the
`datasets.wildtrack.preprocess` module. See
[wildtrack/preprocess.py](../../../../tools/tracker/evaluation/datasets/wildtrack/preprocess.py).

## Citation

WILDTRACK is a third-party dataset that is adopted and used in this tracker evaluation. Source paper:

> "The WILDTRACK Multi-Camera Person Dataset." T. Chavdarova et al.
> https://arxiv.org/pdf/1707.09299.pdf

Download link: http://documents.epfl.ch/groups/c/cv/cvlab-unit/www/data/Wildtrack/Wildtrack_dataset_full.zip
