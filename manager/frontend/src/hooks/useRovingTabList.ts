// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useRef, type KeyboardEvent } from "react";

/**
 * Next index for WAI-ARIA tablist keys (horizontal), or null if unhandled.
 * Wraps at ends for arrows; Home/End jump to first/last.
 */
export function nextTabIndex(
  key: string,
  index: number,
  count: number,
): number | null {
  if (count < 1) {
    return null;
  }
  switch (key) {
    case "ArrowRight":
      return (index + 1) % count;
    case "ArrowLeft":
      return (index - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

type Options = {
  count: number;
  onSelectIndex: (index: number) => void;
};

/**
 * Roving tabindex + arrow/Home/End activation for a horizontal tablist.
 */
export function useRovingTabList({ count, onSelectIndex }: Options) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const setTabRef = useCallback(
    (index: number, node: HTMLButtonElement | null) => {
      tabRefs.current[index] = node;
    },
    [],
  );

  const activateIndex = useCallback(
    (index: number) => {
      onSelectIndex(index);
      tabRefs.current[index]?.focus();
    },
    [onSelectIndex],
  );

  const onTabKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
      const next = nextTabIndex(event.key, index, count);
      if (next === null) {
        return;
      }
      event.preventDefault();
      activateIndex(next);
    },
    [activateIndex, count],
  );

  return { setTabRef, onTabKeyDown };
}
