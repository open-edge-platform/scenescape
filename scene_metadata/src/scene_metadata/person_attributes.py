# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Score person-attributes-recognition-crossroad-0238 and keep its numbers.

The Open Model Zoo 2023.0 FP32 IR already subtracts the training mean and
scales BGR input. Callers pass a 160x80 BGR frame with values in 0..255.
A head is present only when its score is greater than 0.5. ``confidence`` is
that score, not a rounded stand-in.
"""

import math
import os
from pathlib import Path
import urllib.request

ATTRIBUTE_NAMES = (
  'is_male',
  'has_bag',
  'has_hat',
  'has_longsleeves',
  'has_longpants',
  'has_longhair',
  'has_coat_jacket',
)
MODEL_NAME = 'person-attributes-recognition-crossroad-0238'
PRESENT_ABOVE = 0.5
INPUT_HEIGHT = 160
INPUT_WIDTH = 80
_MIN_XML_BYTES = 200_000
_MIN_BIN_BYTES = 80_000_000
_MODEL_URL = (
  'https://storage.openvinotoolkit.org/repositories/open_model_zoo/2023.0/'
  f'models_bin/1/{MODEL_NAME}/FP32'
)


def default_model_dir() -> Path:
  """Directory for the downloaded IR. Git ignores the default cache."""
  override = os.environ.get('PERSON_ATTR_MODEL_DIR')
  if override:
    return Path(override)
  return Path(__file__).resolve().parents[2] / '.cache' / MODEL_NAME


def model_xml(directory: Path | None = None) -> Path | None:
  """Return the XML path when a full 2023.0 IR is already on disk."""
  directory = directory or default_model_dir()
  xml = directory / f'{MODEL_NAME}.xml'
  weights = directory / f'{MODEL_NAME}.bin'
  if not xml.is_file() or not weights.is_file():
    return None
  if xml.stat().st_size < _MIN_XML_BYTES or weights.stat().st_size < _MIN_BIN_BYTES:
    return None
  return xml


def ensure_model(directory: Path | None = None) -> Path:
  """Download the 2023.0 FP32 xml and bin when the cache does not have them."""
  directory = directory or default_model_dir()
  found = model_xml(directory)
  if found is not None:
    return found
  directory.mkdir(parents=True, exist_ok=True)
  for suffix in ('.xml', '.bin'):
    _download(f'{_MODEL_URL}/{MODEL_NAME}{suffix}', directory / f'{MODEL_NAME}{suffix}')
  found = model_xml(directory)
  if found is None:
    raise RuntimeError(f'{MODEL_NAME} download is incomplete in {directory}')
  return found


def _download(url: str, target: Path) -> None:
  request = urllib.request.Request(url, headers={'User-Agent': 'scenescape-scene-metadata'})
  partial = target.with_suffix(target.suffix + '.partial')
  try:
    with urllib.request.urlopen(request, timeout=300) as response, partial.open('wb') as handle:
      while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
          break
        handle.write(chunk)
    partial.replace(target)
  finally:
    if partial.exists():
      partial.unlink()


def solid_bgr(blue: float, green: float, red: float):
  """160x80 BGR frame. Values stay in 0..255 for the IR's own preprocessing."""
  import numpy as np

  image = np.empty((INPUT_HEIGHT, INPUT_WIDTH, 3), dtype=np.float32)
  image[:, :, 0] = blue
  image[:, :, 1] = green
  image[:, :, 2] = red
  return image


def sample_frames() -> dict:
  """Two fixed frames. Labels come from the model, not from a dataset."""
  return {
    'person-green': solid_bgr(0, 255, 0),
    'person-red': solid_bgr(0, 0, 255),
  }


def metadata_from_scores(scores) -> dict[str, dict]:
  """classificationPolicy object for each official head, in model order."""
  values = [float(score) for score in scores]
  if len(values) != len(ATTRIBUTE_NAMES):
    raise ValueError(
      f'{MODEL_NAME} returned {len(values)} scores, expected {len(ATTRIBUTE_NAMES)}')
  return {
    name: {
      'label': 'true' if value > PRESENT_ABOVE else 'false',
      'model_name': MODEL_NAME,
      'confidence': value,
    }
    for name, value in zip(ATTRIBUTE_NAMES, values)
  }


def _compile(xml_path: Path):
  import openvino as ov

  core = ov.Core()
  return core.compile_model(core.read_model(str(xml_path)), 'CPU')


def _scores(compiled, image):
  import numpy as np

  array = np.asarray(image, dtype=np.float32)
  expected = (INPUT_HEIGHT, INPUT_WIDTH, 3)
  if array.shape != expected:
    raise ValueError(f'expected BGR image {expected}, got {array.shape}')
  tensor = np.ascontiguousarray(array.transpose(2, 0, 1)[None, ...])
  result = compiled(tensor)
  return np.array(result[compiled.output(0)]).reshape(-1)


def recognize(image, xml_path: Path | None = None) -> dict[str, dict]:
  """Run one frame. ``confidence`` is the raw head score."""
  xml_path = Path(xml_path) if xml_path else ensure_model()
  return metadata_from_scores(_scores(_compile(xml_path), image))


def recognize_frames(frames: dict, xml_path: Path | None = None) -> dict[str, dict]:
  """Score each frame with one compiled model. Keys are caller-chosen ids."""
  xml_path = Path(xml_path) if xml_path else ensure_model()
  compiled = _compile(xml_path)
  return {name: metadata_from_scores(_scores(compiled, image)) for name, image in frames.items()}


def confidences_match(left, right, abs_tol: float = 1e-6) -> bool:
  """True when two stored scores still name the same model output."""
  return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=abs_tol)


def assert_same_metadata(expected: dict, actual: dict, where: str) -> None:
  """Require the same name, label, model, and confidence the model emitted."""
  if set(expected) != set(actual):
    raise AssertionError(f'{where} names: got {sorted(actual)}, want {sorted(expected)}')
  for name, want in expected.items():
    got = actual[name]
    if got.get('label') != want['label'] or got.get('model_name') != want['model_name']:
      raise AssertionError(f'{where} {name}: got {got}, want {want}')
    if not confidences_match(got.get('confidence'), want['confidence']):
      raise AssertionError(
        f"{where} {name} confidence: got {got.get('confidence')}, want {want['confidence']}")
