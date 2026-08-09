// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useState } from "react";

/**
 * Shared dirty / reset helpers for React workspace and drawer forms.
 */
export function useFormDirty(enabled = true) {
  const [dirty, setDirty] = useState(false);

  const markDirty = useCallback(() => {
    if (enabled) {
      setDirty(true);
    }
  }, [enabled]);

  const resetDirty = useCallback(() => setDirty(false), []);

  return { dirty, setDirty, markDirty, resetDirty };
}
