# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

def get_matcher(matcher):
  mod = __import__(f'{__name__}.{matcher}', fromlist=[''])
  return getattr(mod, 'Model')
