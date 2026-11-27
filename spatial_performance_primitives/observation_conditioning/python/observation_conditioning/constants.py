# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from scenescape-v2-architecture/algorithms/amodalreasoner.
# See NOTICE in this package for provenance requirements.

"""Every tuning value in effect, in one place.

The values are exactly those the original implementation used as inline literals and
default arguments (see implementation.md §3); the C++ library mirrors this table 1:1.
"""

# Depth map
DEFAULT_NUM_LAYERS = 4    # AmodalReasoner depth-peeling layers (DepthMap itself defaults to 1)
PEEL_EPS = 1e-4           # ray-advance nudge past each hit (m)

# Frames and probes (Steps 1-6)
DEGENERATE_CROSS_TOL = 1e-6    # |r x up| below this: ray (anti)parallel to up, use the X axis
PROBE_DEVS_AT_PREMISE = 2.0    # probe offset in sigmas
PROBE_DEVS_OVER_PREMISE = 2.1  # probe offset in sigmas, just beyond the at-premise probes

# Occlusion (Step 8, naive check)
OCC_SIGMA_FRAC = 0.1      # occlusion threshold as a fraction of sigma_d

# Wall (Step 9)
VERT_BAND_LOW_DEG = 75.0   # vertical band lower bound (signed test; unsigned in the spectrum)
VERT_BAND_HIGH_DEG = 115.0 # vertical band upper bound (signed test)
SPECTRUM_SAMPLES = 8       # centroid -> top spectrum ray count
SPECTRUM_MIN_RISE_M = 0.1  # height gain that makes a horizontal hit a rising support (m)

# Total occlusion (Step 9.5)
TOTAL_OCC_SAMPLES = 9           # targets along the lower -> top probe column
TOTAL_OCC_FRACTION = 0.9        # blocked fraction that counts as total occlusion
TOTAL_OCC_BLOCK_MARGIN_M = 0.1  # a target is blocked if a surface is nearer by more than this (m)

# Update (Step 10)
ADAPTIVE_DAMPING_K = 2.0         # 1/k damping on unexplained depth innovation
OCC_RESIDUAL_R = 0.0             # r_occ: residual added to the prior variance before inflation
WALL_OCCLUDER_MARGIN_M = 0.1     # a wall within this of the occluder is the occluder's own face (m)
