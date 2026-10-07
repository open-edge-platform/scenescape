<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Future Work: Run MapAnything on the Intel iGPU (XPU)

Status: proposed, not started. Measurements taken 2026-10-07 on the handheld
demo edge node (Intel Core Ultra X9 388H, 16 threads, 62 GB, Xe3 iGPU
`0xb080`, kernel 7.0 `xe` driver, Docker).

## Problem

The mapping service runs MapAnything on the CPU in fp32 with autocast
disabled (`api_service_base.py` hardcodes `device = "cpu"`; the vendored code's
`torch.autocast("cuda", ...)` is a no-op without CUDA). A 43-view handheld
reconstruction takes 414-475 s of model time. The edge node has an integrated
Xe3 GPU that sits idle during the job.

## Measured headroom

Raw 4096x4096 matmul throughput, same node:

| Device                              | fp32         | bf16          |
| ----------------------------------- | ------------ | ------------- |
| CPU, 16 threads (current path)      | 0.9 TFLOPS   | 1.1 TFLOPS    |
| Xe3 iGPU via `torch==2.12.1+xpu`    | 7.5 TFLOPS   | 38.5 TFLOPS   |

Transformer inference typically reaches 30-50 % of matmul peak, so the
expected job time for the 43-view case is:

| Configuration                            | Estimate      |
| ---------------------------------------- | ------------- |
| CPU fp32 (today)                         | 414-475 s     |
| XPU fp32 (device switch only)            | ~80-100 s     |
| XPU bf16 autocast (device + amp patch)   | ~20-30 s      |

bf16 autocast is how MapAnything is run upstream on CUDA; the fp32 CPU path
is the unusual configuration, so quality should match the published model
rather than degrade. The first GPU result must still be A/B'd against the
last CPU candidate (both stay available in the scene's Map Source list).

## Feasibility test already done

A throwaway `ubuntu:24.04` container on the edge node, started with
`--device /dev/dri --group-add <render gid>`, installed `libze1`,
`libze-intel-gpu1`, `intel-opencl-icd` from
`https://repositories.intel.com/gpu/ubuntu noble unified` (compute runtime
25.18) and `torch==2.12.1` from `https://download.pytorch.org/whl/xpu`.
`torch.xpu.is_available()` returned True, the device reported 96 EUs and
58 GiB of shared memory, and the matmul figures above were recorded. No
extra oneAPI installation was needed beyond what the wheel bundles.

## Plan

1. **Image** (`mapping/Dockerfile`, `mapping/requirements_mapanything.txt`)
   - Build the runtime stage from Ubuntu 24.04 (`RUNTIME_OS_IMAGE` is already
     an ARG; Debian 12 cannot install the Intel GPU packages cleanly).
   - Add Intel's `noble unified` apt repo and install `libze1`
     `libze-intel-gpu1` (and `intel-opencl-icd` for `clinfo` diagnostics).
   - Install torch/torchvision from the `/whl/xpu` index. XPU wheels top out
     at **torch 2.12.1**; the requirements pin 2.13.0 and must be relaxed.
     Re-verify `mapanything-version-fix.patch` against that version.
   - Keep a CPU-only build variant (build ARG `MAPPING_DEVICE=cpu|xpu`) for
     hosts without an Intel GPU.
   - Everything above bakes into the image at build time; nothing new is
     fetched at run time, so the air-gapped start path (cache-first weight
     loading) is unaffected. The HF/torch-hub weight caches are
     device-agnostic and remain valid.

2. **Vendored model patch** (`mapping/mapanything-xpu.patch`, applied in the
   builder stage like `0001-Run-it-on-CPU.patch`)
   - Replace the hardcoded `torch.autocast("cuda", ...)` with the model's
     device type in `mapanything/models/mapanything/model.py` (3 sites),
     `mapanything/utils/inference.py` (2) and
     `mapanything/models/external/vggt/__init__.py` (2). Without this, XPU
     runs fp32 and forfeits most of the gain.
   - Review the `device.type == "cuda"` branches in `model.py` (~L1307,
     L1466, L1501: memory-efficient inference paths) and extend them to
     `"xpu"` where the op is supported.

3. **Service** (`mapping/src/api_service_base.py`, `mapanything_service.py`,
   `mapanything_model.py`)
   - Replace the hardcoded `"cpu"` with env `MAPPING_DEVICE`
     (`auto|cpu|xpu`, default `auto` = `xpu` when
     `torch.xpu.is_available()` else `cpu`).
   - Report the active device in `/v1/health` (already has a `device`
     field) so the manager and operators can see which path ran.
   - Call `torch.xpu.synchronize()` around timing so `processing_time` is
     honest.
   - Reconsider `MAPPING_CPU_SEC_PER_FRAME=10` (used for job-duration
     estimates); make it per device.

4. **Compose** (`scenescape-handheld-en/docker-compose.yml`, upstream
   `docker-compose.yml` mapping service)
   - `devices: ["/dev/dri:/dev/dri"]` and `group_add: ["<render gid>"]`
     (992 on the edge node; derive from `getent group render` in
     `start.sh` as `RENDER_GID` rather than hardcoding).
   - `MAPPING_DEVICE=xpu`.
   - The `dlsps` service already carries the same compute runtime; follow
     its device/group pattern.

5. **Verification**
   - Build, start, confirm `/v1/health` reports `device: xpu` and the log
     shows autocast enabled (no "CUDA is not available ... Disabling
     autocast" warning).
   - Run the 43-view office keyframes job; record `processing_time` and
     compare the mesh against the last CPU candidate (vertex-to-vertex
     nearest-neighbour distance, camera-pose residuals in
     `stats.alignment`).
   - Watch for ops falling back to CPU (`PYTORCH_ENABLE_XPU_FALLBACK=1` logs
     them); any fallback in the hot path erodes the estimate.
   - Check GPU memory headroom when `dlsps` is also running inference on the
     iGPU (shared memory, so pressure shows as system RAM).

## Risks and open questions

- Xe3 / Panther Lake support in compute runtime 25.18 is recent; an op
  without an XPU kernel falls back to CPU with a warning rather than
  failing, which would show up as a smaller-than-expected speedup.
- Torch 2.12.1 vs the pinned 2.13.0: dependency drift in the vendored
  MapAnything tree (and `torchmetrics`, `torchvision 0.27`) needs a test
  pass (`mapping/tests`).
- First-run kernel JIT on XPU adds tens of seconds once per container
  start; consider a warm-up inference at startup so the first user job is
  not penalised.
- Base-image change touches the common `RUNTIME_OS_IMAGE`; confirm the
  other services built from it are unaffected, or scope the override to
  the mapping Dockerfile only.
