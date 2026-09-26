# VIDETEC-2 RadarPillars acceptance notes (P0)

Generated during SceneScape `feature/radar-support` P0 execution.

## Data

| Artifact | Location |
| --- | --- |
| Zenodo | https://zenodo.org/records/17799385 (CC BY 4.0) |
| Radar HDF5 | `VIDETEC-2/radar/radar_dataset_51.h5` (Oct 9 overlap with GNSS) |
| GNSS | `VIDETEC-2/gnss/rosbag2_2025_10_09-14_43_55/*_gps.csv` |
| Converted frames | `VIDETEC-2/converted/frames/` (21625 × (N,5) + timestamps) |
| VoD bins | `VIDETEC-2/converted/pcd_bin/` (21625 × float32 (N,7)) |
| Local origin | `videtec_local_origin.json` (UTM 32N E=695310.500, N=5347376.094) |

Attribution: VIDETEC-2 dataset, Zenodo 17799385, CC BY 4.0.

## Local ENU origin (calibrated)

From the Zenodo record description: shared Cartesian frame origin is
**UTM zone 32N** easting **695310.500 m**, northing **5347376.094 m**
(X-east, Y-north, Z-up). Eval uses `--videtec-origin` (pyproj EPSG:32632)
plus `/sensor` pose to map GNSS into radar-local metres.

## Pipeline health (required)

- `radar-data-init` with `RADAR_RAW_DATASET_DIR=.../converted` copies real
  `pcd_bin` and writes `DATA_SOURCE=real-videtec`.
- GStreamer (DLSPS `…-g3d` + `g3dlidarparse point-features=7` +
  `g3dinference model-type=radarpillars`) on frames 3760–3810:
  - Completes EOS without error.
  - With `score-threshold=0.03`: **51/51** frames nonempty, **727** objects.
  - With default `0.1`: **0** objects (VoD→gantry domain gap; max offline
    score on densest frame ≈ 0.095).

Recommend `RADAR_SCORE_THRESHOLD=0.03` (or lower) for real VIDETEC demos.

## Fixed-input parity (PyTorch vs OV)

Harness: `finetune/compare_radarpillars_parity.py` →
`VIDETEC-2/parity_pytorch_vs_ov.json` (score≥0.03).

| Cloud | PyTorch dets | OV dets | Matched | Matched XY err |
| --- | --- | --- | --- | --- |
| Synthetic ×2 | 3+1 | 100+84 | 3+1 | ~0.58 m mean |
| VIDETEC sample bins | 0–1 | 10–27 | 0 | — |

**Read:** On VoD-like synthetic clusters, matched tops agree within ~0.6 m;
OV postproc keeps many extra low-score boxes. Sparse VIDETEC frames are often
empty on PyTorch while OV still emits low-conf vehicles. Export is not
grossly broken for dense-enough clouds; score/NMS calibration differs.

## GNSS accuracy gate (calibrated origin)

Time alignment remains good (median |Δt| ~ms, p95 ~80 ms).
Stride-5 frames **3000–5000** (401), score≥0.03.

### PyTorch OpenPCDet ckpt (`detections_stride5_pytorch.jsonl`)

| Slice | Det count | VRU@3m | All-class@3m |
| --- | --- | --- | --- |
| Unrestricted | 8 (all `vehicle`) | — | **0.50%** (2/401) |
| FOV + VRU cats only | — | **0%** (0/207) | — |

### OpenVINO host+IR (`detections_stride5.jsonl`)

| Slice | Det count | VRU@3m | All-class@3m |
| --- | --- | --- | --- |
| Unrestricted | 2080 | — | **15.7%** |
| FOV + VRU cats only | — | **0.48%** (1/207) | — |

Almost half the GNSS track is **outside** the VoD forward PC range
(194/401). OV all-class proximity is mostly low-score `vehicle` clutter near
the VRU, not true VRU detections. **PyTorch is worse / quieter**, not better —
so the VIDETEC failure is **not** an OV-only export bug.

## Fine-tune attempt 1 (VoD→VIDETEC GNSS weak labels)

| Item | Value |
| --- | --- |
| Train set | 773 in-range samples (filtered from 3054; stride-2 build) |
| Config | `RadarPillar/.../videtec_radarpillar_gantry.yaml` (expanded PC range) |
| Init | `radarpillar_vod_best_map52.56.pth` (139/139 keys) |
| Saved ckpts | ep5 / 10 / 15 / 20 / 25 |
| Curve | `VIDETEC-2/gnss_ft_epoch_curve.json` + `ft_empty_pred_diagnosis.json` |

### Epoch-wise GNSS (stride-5 3000–5000, score≥0.01)

| Epoch | Finite weights? | Dets | VRU @ 3 m |
| --- | --- | --- | --- |
| 5 | yes (0/118 NaN) | 4910 | **5.7%** (23 hits, mean err 0.29 m) |
| 10 | **no** (116/118 NaN) | 0 | 0% |
| 15 | no | 0 | 0% |
| 20 | no | 0 | 0% |
| 25 | no | 0 | 0% |

**Root cause of empty later preds:** weights exploded to **NaN between ep5 and
ep10** (not score threshold / NMS). Training continued saving poisoned ckpts.

### Fine-tune attempt 2 (NaN guards, LR=3e-4, no heavy aug)

| Item | Value |
| --- | --- |
| Tag | `videtec_gantry_ft2` |
| Guard | skip non-finite loss/grads; abort if weights NaN; no auto-resume |
| Result | **all ep1–12 finite** (0/118 NaN); `skip_nan=0`, `skip_err=0` |
| Curve | `VIDETEC-2/gnss_ft2_epoch_curve.json` |

| Epoch | Dets | VRU @ 3 m | Matched err mean |
| --- | --- | --- | --- |
| 1 | 52000 (mostly vehicle) | 0.2% | 1.13 m |
| 3 | 2825 | 4.7% | 0.39 m |
| 5 | 658 | 5.7% | **0.29 m** |
| 8 | 651 | 5.7% | 0.30 m |
| **11** | 7262 | **11.5%** | 0.94 m |
| 12 | 6785 | 9.0% | 0.61 m |

Named weights: `…/radarpillar_videtec_gantry_ft2_ep11.pth` (max VRU@3m),
`…/radarpillar_videtec_gantry_ft2_ep5.pth` (tighter matches at 5.7%).

**Read:** NaN was the FT1 failure mode; FT2 stays finite and VRU@3m rises to
**11.5%** (still below a demo gate).

### Label/data diagnosis (post-FT2)

On the FT2 train infos (773 samples):

| Check | Result |
| --- | --- |
| Points / cloud | mean ≈ 5 |
| Points within 2 m of GNSS GT | mean 0.36; **72% of frames have zero** |
| Eval window (3000–5000) same filter | 84% of usable frames also have 0 pts within 2 m of GNSS |

So most pseudo-labels sit where radar has **no returns** — that caps recall
even if training is stable.

### Fine-tune attempt 3 (associated labels) — unstable so far

Built `build_videtec_dataset.py` with `--min-points-near-gt 1`, optional
`--snap-gt-to-points` (669 samples, **0%** zero-near-GT). Training on that set
(from VoD or FT2 ep11; with/without snap; BN restore; workers 0/4) consistently
gets **~13 finite steps then non-finite grads** (`skip_nan` floods; weights stay
finite because steps are skipped). FT3 GNSS curve is therefore **not** a valid
improvement (best ep1 ≈ 6.5% VRU@3m, worse than FT2).

**Root cause (isolated):** nan grads in **`backbone_3d` PillarAttention** after
~13 Adam steps on associated batches (loss still finite; loc loss large).

### Fine-tune attempt 4 (associated + freeze PillarAttention)

| Item | Value |
| --- | --- |
| Tag | `videtec_gantry_ft4` |
| Fix | `--freeze-backbone-3d` (VoD attention frozen; train VFE/BEV/head) |
| Train | associated snap set; **skip_nan=0**; loss 11.5 → 0.35; all ckpts finite |
| Curve | `VIDETEC-2/gnss_ft4_epoch_curve.json` |

| Epoch | VRU @ 3 m (full 401) | Matched err |
| --- | --- | --- |
| 1–12 | **5.7%** plateau | ~0.37–0.71 m |

#### Associable-only eval (frames with ≥1 pt within 3 m of GNSS)

Only **10 / 401** stride-5 frames are associable. On that subset:

| Ckpt | VRU @ 3 m | Mean err |
| --- | --- | --- |
| FT2 ep11 | **80%** (8/10) | 0.30 m |
| FT4 ep4 | **80%** (8/10) | 0.50 m |
| FT4 ep12 | **80%** (8/10) | 0.47 m |

**Read:** When radar actually returns near the VRU, both FT2 and FT4 hit **80%**.
Full-window scores are dominated by the **~97.5% of frames with no near-GT
radar support**. FT2 ep11’s higher full-window 11.5% comes from extra hits on
**non-associable** frames (not more associable coverage). Demo gate needs denser
returns, a wider time/FOV slice with support, or fusion — not more epochs alone.

Current best **full-window** weight remains FT2 ep11. FT4 is the stable associated
recipe (`…/radarpillar_videtec_gantry_ft4_ep4.pth`).

### Window + density (post-FT4)

Scan (`VIDETEC-2/associability_scan.json`): stride-5 over the Oct-9 overlap,
best **401-frame** windows are **2100–4100 / 2200–4200 / 2300–4300** (~106
frames with any return within 3 m of GNSS) vs only ~10 in the old **3000–5000**
slice. Re-eval on **2100–4100** (score≥0.01):

| Ckpt | Window | Acc | VRU @ 1 m | VRU @ 3 m | Hits |
| --- | --- | --- | --- | --- | --- |
| FT2 ep11 | 3000–5000 | 0 | — | **11.5%** | — |
| FT2 ep11 | 2100–4100 | 0 | 13.2% | **18.5%** | 74 |
| FT4 ep4 | 2100–4100 | 0 | 11.2% | **11.5%** | 46 |
| FT2 ep11 | 2100–4100 | ±2 | 40.6% | **46.4%** | 186 |
| FT4 ep4 | 2100–4100 | ±2 | 32.9% | **34.9%** | 140 |
| FT2 ep11 | 2100–4100 | ±5 | 44.6% | **51.4%** | 206 |
| FT4 ep4 | 2100–4100 | ±5 | 35.4% | **37.4%** | 150 |
| FT2 ep11 | 2100–4100 | ±10 | 24.7% | **35.2%** | 141 |

Multi-frame stack = concatenate gantry-static neighbor indices
(`[fi−H, fi+H]`) via `--accumulate-half-window` in
`finetune/batch_pytorch_radarpillars_infer.py`. Doppler-filtered associability
on 2100–4100 rises **25 → 131 → 152** frames for H=0/2/5; on those subsets
FT2/FT4 stay **≥92%** VRU@3m (H=2 reaches **99%** on 131 frames). **H=10
regresses** (motion smear / clutter) vs H=5. Summary:
`VIDETEC-2/gnss_w2100_4100_multiframe_summary.json`.

**Read:** Choosing the denser GNSS window alone lifts FT2 to **18.5%**; adding
±5-frame accumulation reaches **51.4%** VRU@3m without new training. Remaining
gap to a demo gate is mostly frames that still lack near-GT returns even after
stacking — next levers are train-time densify (FT5), runtime ±5 accumulate in
the g3d path, or fusion.

```bash
# Parity
~/mainline/RadarPillar/.venv/bin/python \
  sample_data/radar_intersection/finetune/compare_radarpillars_parity.py \
  --synthetic 2 --bins VIDETEC-2/converted/pcd_bin/003785.bin \
  -o sample_data/radar_intersection/VIDETEC-2/parity_pytorch_vs_ov.json

# Epoch curve (FT1 poisoned run)
~/mainline/RadarPillar/.venv/bin/python \
  sample_data/radar_intersection/finetune/eval_ft_epoch_curve.py \
  --score-threshold 0.01

# Best-window + multi-frame (example)
~/mainline/RadarPillar/.venv/bin/python \
  sample_data/radar_intersection/finetune/batch_pytorch_radarpillars_infer.py \
  --ckpt ~/mainline/RadarPillar/weights/radarpillar_videtec_gantry_ft2_ep11.pth \
  --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames \
  --start-index 2100 --stop-index 4100 --stride 5 \
  --accumulate-half-window 5 --score-threshold 0.01 \
  -o sample_data/radar_intersection/VIDETEC-2/detections_w2100_4100_ft2ep11_acc5.jsonl
```

## Full SceneScape E2E (MQTT / regulated tracks)

Blocked on host `SUPASS`. After setting it (and after quality gate):

```bash
RADAR_REQUIRE_REAL=true RADAR_SCORE_THRESHOLD=0.03 CAM_MUTE=true \
  SUPASS=<password> make demo-radar
```
