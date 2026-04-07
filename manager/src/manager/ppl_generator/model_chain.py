# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from .common_types import PipelineGenerationNotImplementedError, PipelineGenerationValueError, InferenceRegion
from .inference_model import InferenceModel


class CameraChainOperations(Enum):
  SEQUENTIAL = '+'
  PARALLEL = ','
  BRACKET_OPEN = '['
  BRACKET_CLOSE = ']'


class ChainableNode:
  """Base class for all chainable node types in a sub-pipeline."""

  def serialize(self) -> list:
    raise PipelineGenerationNotImplementedError("ChainableNode.serialize method must be implemented by subclasses")

  def set_inference_input(self, region: InferenceRegion):
    raise PipelineGenerationNotImplementedError("ChainableNode.set_inference_input method must be implemented by subclasses")

  def get_metadata_policy(self) -> str:
    raise PipelineGenerationNotImplementedError("ChainableNode.get_metadata_policy method must be implemented by subclasses")

  def get_output_device(self) -> str:
    raise PipelineGenerationNotImplementedError("ChainableNode.get_output_device method must be implemented by subclasses")

  def __str__(self):
    return 'Abstract Chainable Node'


class InferenceNode(ChainableNode):
  """Single model node that wraps InferenceModel."""

  def __init__(self, models_folder: str, model_expr: str, model_config: dict):
    self.inference_model = InferenceModel(models_folder, model_expr, model_config)

  def serialize(self) -> list:
    return self.inference_model.serialize()

  def set_inference_input(self, region: InferenceRegion):
    self.inference_model.set_inference_region(region)

  def get_metadata_policy(self) -> str:
    return self.inference_model.get_metadata_policy()

  def get_output_device(self) -> str:
    return self.inference_model.get_target_device()

  def __str__(self):
    return f'{self.inference_model.inference_element}({self.inference_model.model_name}, {self.inference_model.get_target_device()})'


class SequentialNodes(ChainableNode):
  """Container for sequential chaining of models."""

  def __init__(self, nodes: list):
    self.nodes = nodes

  def serialize(self) -> list:
    result = []
    for i, node in enumerate(self.nodes):
      result.extend(node.serialize())
      if i < len(self.nodes) - 1:
        result.append('queue')
    return result

  def set_inference_input(self, region: InferenceRegion):
    if len(self.nodes):
      self.nodes[0].set_inference_input(region)
      for node in self.nodes[1:]:
        node.set_inference_input(InferenceRegion.ROI_LIST)

  def get_metadata_policy(self) -> str:
    # get the policy from the last node in the sequence
    if len(self.nodes):
      return self.nodes[-1].get_metadata_policy()
    return 'detectionPolicy'

  def get_output_device(self) -> str:
    return self.nodes[-1].get_output_device() if len(self.nodes) else ''

  def __str__(self):
    return ' ( ' + ' -> '.join([str(node) for node in self.nodes]) + ' ) '


class ParallelNodes(ChainableNode):
  """Container for parallel chaining of models."""

  def __init__(self, nodes: list):
    self.nodes = nodes

  def serialize(self) -> list:
    raise PipelineGenerationNotImplementedError("parallel model chaining is not supported yet")

  def set_inference_input(self, region: InferenceRegion):
    for node in self.nodes:
      node.set_inference_input(region)

  def get_metadata_policy(self) -> str:
    policies = [ node.get_metadata_policy() for node in self.nodes ] or ['detectionPolicy']
    if not all(policy == policies[0] for policy in policies):
      raise PipelineGenerationValueError("Parallel nodes with mixed metadata policies are not supported")
    return policies[0]

  def get_output_device(self) -> str:
    return self.nodes[0].get_output_device() if len(self.nodes) else ''

  def __str__(self):
    return ' ( ' + ' || '.join([str(node) for node in self.nodes]) + ' ) '


def parse_model_chain(model_chain: str, models_folder: str, model_config: dict) -> ChainableNode:
  """Parse model_chain string and return a sub-pipeline object."""
  if not model_chain:
    raise PipelineGenerationValueError("model_chain string cannot be empty!")
  model_chain = model_chain.strip()

  # Check for unsupported characters
  if CameraChainOperations.BRACKET_OPEN.value in model_chain or CameraChainOperations.BRACKET_CLOSE.value in model_chain:
    raise PipelineGenerationValueError("Square brackets '[' and ']' are not supported in current version")

  # Check for mixed operators
  has_sequential_operator = CameraChainOperations.SEQUENTIAL.value in model_chain
  has_parallel_operator = CameraChainOperations.PARALLEL.value in model_chain

  if has_sequential_operator and has_parallel_operator:
    raise PipelineGenerationNotImplementedError(f"Mixed sequential ('{CameraChainOperations.SEQUENTIAL.value}') and parallel ('{CameraChainOperations.PARALLEL.value}') chaining is not yet implemented")

  if has_sequential_operator:
    # Sequential chaining
    model_exprs = [expr.strip() for expr in model_chain.split(CameraChainOperations.SEQUENTIAL.value)]
    nodes = [InferenceNode(models_folder, expr, model_config) for expr in model_exprs if expr]
    return SequentialNodes(nodes)
  elif has_parallel_operator:
    # Parallel chaining
    model_exprs = [expr.strip() for expr in model_chain.split(CameraChainOperations.PARALLEL.value)]
    nodes = [InferenceNode(models_folder, expr, model_config) for expr in model_exprs if expr]
    return ParallelNodes(nodes)
  else:
    # Single model
    return InferenceNode(models_folder, model_chain, model_config)
