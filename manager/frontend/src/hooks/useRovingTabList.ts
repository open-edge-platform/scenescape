// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  useCallback,
  useEffect,
  useRef,
  type KeyboardEvent,
} from "react";

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

/** Index of activeId in tabs, or -1 when missing. */
export function findTabIndex(
  tabs: ReadonlyArray<{ id: string }>,
  activeId: string,
): number {
  return tabs.findIndex((tab) => tab.id === activeId);
}

/**
 * Index that should receive tabIndex={0}.
 * Falls back to 0 so the tablist stays reachable when activeId is unknown.
 */
export function focusableTabIndex(
  tabs: ReadonlyArray<{ id: string }>,
  activeId: string,
): number {
  if (tabs.length === 0) {
    return -1;
  }
  const selected = findTabIndex(tabs, activeId);
  return selected >= 0 ? selected : 0;
}

type Options = {
  count: number;
  /** Tab that should own focus / tabIndex 0 (may be a fallback). */
  focusIndex: number;
  onSelectIndex: (index: number) => void;
};

/**
 * Roving tabindex + arrow/Home/End activation for a horizontal tablist.
 * When focusIndex changes while focus is inside the list (e.g. external
 * activateSceneTab), moves focus to the focused tab.
 */
export function useRovingTabList({
  count,
  focusIndex,
  onSelectIndex,
}: Options) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const listRef = useRef<HTMLDivElement | null>(null);

  const setTabRef = useCallback(
    (index: number, node: HTMLButtonElement | null) => {
      tabRefs.current[index] = node;
    },
    [],
  );

  useEffect(() => {
    if (focusIndex < 0) {
      return;
    }
    const list = listRef.current;
    if (!list) {
      return;
    }
    const active = document.activeElement;
    if (!(active instanceof Node) || !list.contains(active)) {
      return;
    }
    const target = tabRefs.current[focusIndex];
    if (target && active !== target) {
      target.focus();
    }
  }, [focusIndex]);

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

  return { listRef, setTabRef, onTabKeyDown };
}
