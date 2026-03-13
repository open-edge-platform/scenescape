# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Pipeline test scenario descriptors.

Each scenario drives one ``PipelineRunner`` test.  The list is the
single source of truth for which (model chain, source video, required hardware)
combinations are exercised.

Device marks:

requires_gpu     At least one GPU must be available (GPU_DEVICE_COUNT >= 1).
requires_gpu2    At least two GPUs must be available (GPU_DEVICE_COUNT >= 2).
requires_npu     At least one NPU must be available (NPU_DEVICE_COUNT >= 1).

Scenarios without a device mark run on CPU and are always executed.

Source files:

People models   ``file://qcam1.ts``          models: retail, agegender, personattr, reid
Vehicle models  ``file://car-detection.ts``  models: pvbcross16, vehattr
"""

from typing import NamedTuple


class PipelineScenario(NamedTuple):
  """Descriptor for a single pipeline integration test scenario."""
  id: str           # used as pytest param ID and sensor_id in the generated config
  camerachain: str  # value of the ``camerachain`` field
  source_file: str  # video source - relative filename after ``file://``
  marks: tuple      # zero or more pytest mark *names* to apply


_PEOPLE_SRC = "qcam1.ts"

PEOPLE_SCENARIOS: list[PipelineScenario] = [
  # CPU-only baselines (always run)
  PipelineScenario(
    id="retail_cpu",
    camerachain="retail=CPU",
    source_file=_PEOPLE_SRC,
    marks=(),
  ),
  PipelineScenario(
    id="retail_cpu__agegender_cpu",
    camerachain="retail=CPU + agegender=CPU",
    source_file=_PEOPLE_SRC,
    marks=(),
  ),
  PipelineScenario(
    id="retail_cpu__personattr_cpu",
    camerachain="retail=CPU + personattr=CPU",
    source_file=_PEOPLE_SRC,
    marks=(),
  ),
  PipelineScenario(
    id="retail_cpu__reid_cpu",
    camerachain="retail=CPU + reid=CPU",
    source_file=_PEOPLE_SRC,
    marks=(),
  ),
  # Single GPU (GPU_DEVICE_COUNT >= 1)
  PipelineScenario(
    id="retail_gpu__agegender_cpu",
    camerachain="retail=GPU + agegender=CPU",
    source_file=_PEOPLE_SRC,
    marks=("requires_gpu",),
  ),
  PipelineScenario(
    id="retail_cpu__agegender_gpu",
    camerachain="retail=CPU + agegender=GPU",
    source_file=_PEOPLE_SRC,
    marks=("requires_gpu",),
  ),
  PipelineScenario(
    id="retail_gpu__agegender_gpu",
    camerachain="retail=GPU + agegender=GPU",
    source_file=_PEOPLE_SRC,
    marks=("requires_gpu",),
  ),
  PipelineScenario(
    id="retail_gpu__personattr_gpu",
    camerachain="retail=GPU + personattr=GPU",
    source_file=_PEOPLE_SRC,
    marks=("requires_gpu",),
  ),
  PipelineScenario(
    id="retail_gpu__reid_gpu",
    camerachain="retail=GPU + reid=GPU",
    source_file=_PEOPLE_SRC,
    marks=("requires_gpu",),
  ),
  # Multi-GPU (GPU_DEVICE_COUNT >= 2)
  PipelineScenario(
    id="retail_gpu1__agegender_gpu2",
    camerachain="retail=GPU.0 + agegender=GPU.1",
    source_file=_PEOPLE_SRC,
    marks=("requires_gpu2",),
  ),
  PipelineScenario(
    id="retail_gpu1__reid_gpu2",
    camerachain="retail=GPU.0 + reid=GPU.1",
    source_file=_PEOPLE_SRC,
    marks=("requires_gpu2",),
  ),
  # NPU (NPU_DEVICE_COUNT >= 1)
  PipelineScenario(
    id="retail_npu",
    camerachain="retail=NPU",
    source_file=_PEOPLE_SRC,
    marks=("requires_npu",),
  ),
  PipelineScenario(
    id="retail_npu__agegender_cpu",
    camerachain="retail=NPU + agegender=CPU",
    source_file=_PEOPLE_SRC,
    marks=("requires_npu",),
  ),
  PipelineScenario(
    id="retail_npu__agegender_npu",
    camerachain="retail=NPU + agegender=NPU",
    source_file=_PEOPLE_SRC,
    marks=("requires_npu",),
  ),
]

_CAR_SRC = "car-detection.ts"

VEHICLE_SCENARIOS: list[PipelineScenario] = [
  # CPU-only baselines (always run)
  PipelineScenario(
    id="pvbcross16_cpu",
    camerachain="pvbcross16=CPU",
    source_file=_CAR_SRC,
    marks=(),
  ),
  PipelineScenario(
    id="pvbcross16_cpu__vehattr_cpu",
    camerachain="pvbcross16=CPU + vehattr=CPU",
    source_file=_CAR_SRC,
    marks=(),
  ),
  # Single GPU (GPU_DEVICE_COUNT >= 1)
  PipelineScenario(
    id="pvbcross16_gpu__vehattr_cpu",
    camerachain="pvbcross16=GPU + vehattr=CPU",
    source_file=_CAR_SRC,
    marks=("requires_gpu",),
  ),
  PipelineScenario(
    id="pvbcross16_cpu__vehattr_gpu",
    camerachain="pvbcross16=CPU + vehattr=GPU",
    source_file=_CAR_SRC,
    marks=("requires_gpu",),
  ),
  PipelineScenario(
    id="pvbcross16_gpu__vehattr_gpu",
    camerachain="pvbcross16=GPU + vehattr=GPU",
    source_file=_CAR_SRC,
    marks=("requires_gpu",),
  ),
  # Multi-GPU (GPU_DEVICE_COUNT >= 2)
  PipelineScenario(
    id="pvbcross16_gpu1__vehattr_gpu2",
    camerachain="pvbcross16=GPU.0 + vehattr=GPU.1",
    source_file=_CAR_SRC,
    marks=("requires_gpu2",),
  ),
  # NPU (NPU_DEVICE_COUNT >= 1)
  PipelineScenario(
    id="pvbcross16_npu",
    camerachain="pvbcross16=NPU",
    source_file=_CAR_SRC,
    marks=("requires_npu",),
  ),
  PipelineScenario(
    id="pvbcross16_npu__vehattr_cpu",
    camerachain="pvbcross16=NPU + vehattr=CPU",
    source_file=_CAR_SRC,
    marks=("requires_npu",),
  ),
]
