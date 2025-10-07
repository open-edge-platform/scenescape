# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from collections import OrderedDict

class Inferizer:

  def __init__(self, spec, params, device="CPU"):
    self.params = params
    self.device = device
    self.dependencies = None

    specParams = spec.split('=')
    self.modelID = specParams[0]
    if len(specParams) > 1:
      self.device = specParams[1]
    else:
      self.device = "CPU"

    return

class ModelChain:
  class Stack:
    def __init__(self, spec):
      self.stack = []
      pos = 0
      while True:
        bidx = spec.find('[')
        eidx = spec.find(']')
        if bidx >= 0 and bidx < eidx:
          self.push(spec[:bidx])
          inner = self.__class__(spec[bidx+1:])
          self.stack.append(inner)
          eidx = inner.pos + 1 + bidx
          spec = spec[eidx:]
          pos += eidx
        elif eidx >= 0:
          self.push(spec[:eidx])
          pos += 1 + eidx
          break
        else:
          self.push(spec)
          pos += len(spec)
          break
      self.pos = pos
      return

    def push(self, spec):
      idx = spec.find('+')
      if idx >= 0 and idx < len(spec) - 1:
        self.push(spec[:idx+1])
        self.push(spec[idx+1:])
      else:
        idx = spec.find(',')
        if idx < 0:
          if len(spec):
            self.stack.append(spec)
        else:
          clist = spec.split(',')
          if len(clist[0]) == 0:
            clist = clist[1:]
          self.stack.extend(clist)
      return

    def groupDependencies(self, idx=0):
      while idx < len(self.stack):
        inner = self.stack[idx]
        idx += 1
        if isinstance(inner, ModelChain.Stack):
          inner.groupDependencies(0)
        elif isinstance(inner, str) and inner[-1] == '+':
          if isinstance(self.stack[idx], ModelChain.Stack) or idx+1 == len(self.stack):
            continue
          self.groupDependencies(idx)
          if self.stack[idx][-1] == '+':
            self.stack[idx] = self.stack[idx:idx+2]
            self.stack.pop(idx+1)
      return

    def setupModels(self, params, device="CPU"):
      models = {}
      idx = 0
      while idx < len(self.stack):
        p = self.stack[idx]
        if isinstance(p, str):
          isParent = False
          if p[-1] == '+':
            isParent = True
            p = p[:-1]
          chain = Inferizer(p, params, device)
          models[chain.modelID] = chain
          if isParent:
            children = self.stack[idx+1]
            if isinstance(children, str):
              children = Inferizer(children, params, device)
              childModels = {children.modelID: children}
            else:
              childModels = children.setupModels(params, chain.device)
            for cm in childModels:
              if childModels[cm].dependencies is None:
                childModels[cm].dependencies = chain.modelID
            models.update(childModels)
            idx += 1
        idx += 1
      return models

  def __init__(self, spec, params, device="CPU"):
    self.pending = 0
    self.orderedModels = {}
    if spec:
      parsed = ModelChain.Stack(spec)
      parsed.groupDependencies()
      models = parsed.setupModels(params, device)

      order = ModelChain.sortDependencies(models)
      self.orderedModels = OrderedDict([(x, models[x]) for x in order])
      print("Models:")
      for name in self.orderedModels:
        print("  ", name, self.orderedModels[name])
      print("Ordered:", order)
    return

  @staticmethod
  def sortDependencies(models):
    ordered = []
    for m in models:
      chain = models[m]
      dep = chain.dependencies
      if dep is None:
        ordered.append(m)
      else:
        try:
          idx = ordered.index(dep)
        except ValueError:
          idx = -1
        if idx < 0:
          ordered.extend([m, dep])
        else:
          ordered.insert(idx, m)
    return ordered
