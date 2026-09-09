// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
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
  return (
    <div className="ss-tabs">
      <div className="ss-tabs-list" role="tablist">
        {tabs.map((tab) => {
          const selected = tab.id === activeId;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`ss-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`ss-tab-panel-${tab.id}`}
              className={`ss-tabs-tab${selected ? " is-active" : ""}`}
              onClick={() => onChange(tab.id)}
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
    >
      {selected ? children : null}
    </div>
  );
}
