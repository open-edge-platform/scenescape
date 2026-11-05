# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from scenescape-v2-architecture/algorithms/amodalreasoner.
# See NOTICE in this package for provenance requirements.

import numpy as np

PLANE_DECISION_NML_WEIGHT = .7

PRIORS = {
	"Pedestrian": {
		"mu_x": 0.55,
		"mu_y": 0.55,
		"mu_z": 1.70,
		"sigma_x": 0.10,
		"sigma_y": 0.10,
		"sigma_z": 0.15,
	},
	"Cyclist": {
		"mu_x": 0.65,
		"mu_y": 1.10,
		"mu_z": 1.60,
		"sigma_x": 0.10,
		"sigma_y": 0.15,
		"sigma_z": 0.10,
	},
	"Car": {
		"mu_x": 2.00,
		"mu_y": 4.50,
		"mu_z": 1.50,
		"sigma_x": 0.20,
		"sigma_y": 0.50,
		"sigma_z": 0.15,
	},
	"Van / SUV": {
		"mu_x": 2.20,
		"mu_y": 5.00,
		"mu_z": 1.90,
		"sigma_x": 0.25,
		"sigma_y": 0.60,
		"sigma_z": 0.20,
	},
	"Bus": {
		"mu_x": 2.50,
		"mu_y": 9.00,
		"mu_z": 3.20,
		"sigma_x": 0.30,
		"sigma_y": 1.00,
		"sigma_z": 0.30,
	},
	"Drone (consumer)": {
		"mu_x": 0.30,
		"mu_y": 0.30,
		"mu_z": 0.10,
		"sigma_x": 0.05,
		"sigma_y": 0.05,
		"sigma_z": 0.03,
	},
	"Retail product": {
		"mu_x": 0.12,
		"mu_y": 0.08,
		"mu_z": 0.20,
		"sigma_x": 0.05,
		"sigma_y": 0.04,
		"sigma_z": 0.12,
	},
}

MESH_DEFAULT_SIGMA = np.array([[.01, .01, .01],
      				   [.01, .01, .01],
        			   [.01, .01, .01]])

MESH_DEFAULT_VARIANCE = np.array([[.1]])

# --- Algorithm V2 tuning constants ---
# Depth peeling
PEEL_LAYERS = 4           # max surfaces recorded along a ray
PEEL_EPS = 1e-4           # ray-advance nudge past each hit (m)

# Occlusion (Step 8)
OCC_SIGMA_FRAC = 0.1      # naive pre-filter threshold as a fraction of sigma_r
OCC_EPS = 0.1             # expected-vs-actual floor distance tolerance (m)
FLOOR_NORMAL_COS_TOL = np.cos(np.deg2rad(30.0))  # floor-like normal alignment with world-up
FLOOR_CONSISTENCY_RHO = 0.25                     # peeled-vs-expected floor agreement (m)

# Wall (Step 9)
VERT_BAND_LOW_DEG = 75.0   # signed-angle vertical band lower bound
VERT_BAND_HIGH_DEG = 115.0 # signed-angle vertical band upper bound
SPECTRUM_SAMPLES = 5       # centroid -> top spectrum ray count

# Update (Step 10)
ADAPTIVE_DAMPING_K = 2.0   # 1/k damping on unexplained depth innovation

