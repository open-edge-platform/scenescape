// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, type ReactNode } from "react";
import {
  focusableTabIndex,
  useRovingTabList,
} from "../hooks/useRovingTabList";
import "./Tabs.css";

export type TabItem = {
  id: string;
  label: string;
  count?: number | string;
  extra?: ReactNode;
};

type TabListProps = {
  tabs: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  id?: string;
  /** DOM id for the tab button (defaults to ss-tab-{id}). */
  tabDomId?: (tab: TabItem) => string;
  /** aria-controls target id (defaults to ss-tab-panel-{id}). */
  tabPanelId?: (tab: TabItem) => string;
};

function defaultTabDomId(tab: TabItem): string {
  return `ss-tab-${tab.id}`;
}

function defaultTabPanelId(tab: TabItem): string {
  return `ss-tab-panel-${tab.id}`;
}

/**
 * Shared horizontal tablist with roving tabindex and arrow/Home/End keys.
 */
export function TabList({
  tabs,
  activeId,
  onChange,
  id,
  tabDomId = defaultTabDomId,
  tabPanelId = defaultTabPanelId,
}: TabListProps) {
  const focusIndex = focusableTabIndex(tabs, activeId);
  const onSelectIndex = useCallback(
    (index: number) => {
      const tab = tabs[index];
      if (tab) {
        onChange(tab.id);
      }
    },
    [onChange, tabs],
  );
  const { listRef, setTabRef, onTabKeyDown } = useRovingTabList({
    count: tabs.length,
    focusIndex,
    onSelectIndex,
  });

  return (
    <div ref={listRef} className="ss-tabs-list" role="tablist" id={id}>
      {tabs.map((tab, index) => {
        const selected = tab.id === activeId;
        return (
          <button
            key={tab.id}
            ref={(node) => setTabRef(index, node)}
            type="button"
            role="tab"
            id={tabDomId(tab)}
            aria-selected={selected}
            aria-controls={tabPanelId(tab)}
            tabIndex={index === focusIndex ? 0 : -1}
            className={`ss-tabs-tab${selected ? " is-active" : ""}`}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onTabKeyDown(event, index)}
          >
            <span className="ss-tabs-main">
              <span className="ss-tabs-label">{tab.label}</span>
            </span>
            {tab.count !== undefined && tab.count !== null ? (
              <span className="ss-tabs-count">{tab.count}</span>
            ) : null}
            {tab.extra}
          </button>
        );
      })}
    </div>
  );
}

type Props = {
  tabs: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  children: ReactNode;
};

export function Tabs({ tabs, activeId, onChange, children }: Props) {
  return (
    <div className="ss-tabs">
      <TabList tabs={tabs} activeId={activeId} onChange={onChange} />
      <div className="ss-tabs-panels">{children}</div>
    </div>
  );
}

type PanelProps = {
  id: string;
  activeId: string;
  children: ReactNode;
};

export function TabPanel({ id, activeId, children }: PanelProps) {
  const selected = id === activeId;
  return (
    <div
      role="tabpanel"
      id={`ss-tab-panel-${id}`}
      aria-labelledby={`ss-tab-${id}`}
      hidden={!selected}
      className="ss-tabs-panel"
      tabIndex={selected ? 0 : undefined}
    >
      {selected ? children : null}
    </div>
  );
}
