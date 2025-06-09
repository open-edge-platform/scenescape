import sys
from abc import ABCMeta, abstractmethod
from copy import copy
import inspect
from enum import Flag, auto
import numpy as np
import torch
from types import SimpleNamespace as SN
from torch import nn

torch.set_flush_denormal(True)
torch.jit.enable_onednn_fusion(True)


class BaseModel(nn.Module, metaclass=ABCMeta):
  default_conf = {}
  required_inputs = []

  def __init__(self, conf):
    """Perform some logic and call the _init method of the child model."""
    super().__init__()
    self.conf = conf = {**self.default_conf, **conf}
    self.required_inputs = copy(self.required_inputs)
    self._init(conf)
    sys.stdout.flush()

  def forward(self, data):
    """Check the data and call the _forward method of the child model."""
    for key in self.required_inputs:
      assert key in data, "Missing key {} in data".format(key)
    return self._forward(data)

  @abstractmethod
  def _init(self, conf):
    """To be implemented by the child class."""
    raise NotImplementedError

  @abstractmethod
  def _forward(self, data):
    """To be implemented by the child class."""
    raise NotImplementedError


def dynamic_load(root, model):
  module_path = f"{root.__name__}.{model}"
  module = __import__(module_path, fromlist=[""])
  classes = inspect.getmembers(module, inspect.isclass)
  # Filter classes defined in the module
  classes = [c for c in classes if c[1].__module__ == module_path]
  # Filter classes inherited from BaseModel
  classes = [c for c in classes if issubclass(c[1], BaseModel)]
  assert len(classes) == 1, classes
  return classes[0][1]
  # return getattr(module, 'Model')


def cached_load(root, model_conf):
  """Reuse optimized model in repeat calls. Only maintains one model per name, so
  using a different configuration will overwrite a model."""
  name = model_conf["name"]
  if (
      name in cached_load.model_cache
      and cached_load.model_cache[name].conf == model_conf
  ):
    return cached_load.model_cache[name].model
  Model = dynamic_load(root, model_conf["name"])
  model = Model(model_conf).eval().to(cached_load.device)
  if "optimize" in model_conf and "script" in model_conf["optimize"]:
    model = torch.jit.freeze(torch.jit.script(model))
    model = torch.jit.optimize_for_inference(model)
  if cached_load.device == "cpu":
    try:
      import intel_extension_for_pytorch as ipex

      ipex.enable_onednn_fusion(True)

      model = ipex.optimize(model)
    except ImportError:
      pass
  cached_load.model_cache[name] = SN(model=model, conf=model_conf)
  return model


cached_load.device = "cuda" if torch.cuda.is_available() else "cpu"
cached_load.model_cache = {}
"""Cache loaded, optimized models by name"""
