// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, type ReactNode } from "react";
import { useRovingTabList } from "../hooks/useRovingTabList";
import "./Tabs.css";

export type TabItem = {
  id: string;
  label: string;
  count?: number | string;
  extra?: ReactNode;
};

type Props = {
  tabs: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  children: ReactNode;
};

export function Tabs({ tabs, activeId, onChange, children }: Props) {
  const onSelectIndex = useCallback(
    (index: number) => {
      const tab = tabs[index];
      if (tab) {
        onChange(tab.id);
      }
    },
    [onChange, tabs],
  );
  const { setTabRef, onTabKeyDown } = useRovingTabList({
    count: tabs.length,
    onSelectIndex,
  });

  return (
    <div className="ss-tabs">
      <div className="ss-tabs-list" role="tablist">
        {tabs.map((tab, index) => {
          const selected = tab.id === activeId;
          return (
            <button
              key={tab.id}
              ref={(node) => setTabRef(index, node)}
              type="button"
              role="tab"
              id={`ss-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`ss-tab-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
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
