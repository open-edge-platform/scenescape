// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { copyTextToClipboard } from "./copyText";
import type { TripwireEntity } from "./types";

type Props = {
  tripwire: TripwireEntity;
  index: number;
  isSuperuser: boolean;
  onChange: (next: TripwireEntity) => void;
  onRemove: (svgId: string) => void;
};

export function TripwireEditorCard({
  tripwire,
  index,
  isSuperuser,
  onChange,
  onRemove,
}: Props) {
  const canEdit = Boolean(isSuperuser) && !tripwire.readOnly;
  const [expanded, setExpanded] = useState(false);
  const detailsId = `trip-details-${tripwire.svgId}`;

  return (
    <div
      className="form-tripwire"
      id={`form-${tripwire.svgId}`}
      ref={(el) => el?.setAttribute("for", tripwire.svgId)}
    >
      <div
        className={`ss-editor-row count-item col ss-editor-card${expanded ? " is-expanded" : ""}`}
      >
        <div className="ss-editor-row__primary">
          <div className="ss-editor-row__fields">
            <span className="ss-editor-row__index input-group-text tripwire-number">
              {index + 1}
            </span>
            <input
              type="text"
              className="form-control tripwire-title ss-editor-row__title"
              id={`input-${tripwire.svgId}`}
              aria-labelledby={`label-${tripwire.svgId}`}
              placeholder="Tripwire Name"
              required
              maxLength={100}
              readOnly={!canEdit}
              disabled={!canEdit}
              value={tripwire.title}
              onChange={(e) => {
                if (!canEdit) {
                  return;
                }
                onChange({ ...tripwire, title: e.target.value });
              }}
              onBlur={() => {
                if (window.ssUseReactMap) {
                  window.ssMap?.numberTripwires?.();
                  return;
                }
                window.numberTripwires?.();
              }}
            />
            <button
              type="button"
              className="ss-editor-row__toggle"
              aria-expanded={expanded}
              aria-controls={detailsId}
              title={expanded ? "Hide details" : "Show details"}
              onClick={() => setExpanded((v) => !v)}
            >
              <i
                className={`bi ${expanded ? "bi-chevron-up" : "bi-chevron-down"}`}
                aria-hidden="true"
              />
            </button>
          </div>
          {isSuperuser ? (
            <button
              className="ss-icon-btn ss-icon-btn--danger tripwire-remove ss-editor-row__remove"
              type="button"
              title="Remove this Tripwire"
              aria-label="Remove this Tripwire"
              onClick={(ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                onRemove(tripwire.svgId);
              }}
            >
              <i className="bi bi-trash" aria-hidden="true" />
            </button>
          ) : null}
        </div>
        {expanded ? (
          <div className="ss-editor-row__details" id={detailsId}>
            <div
              className="ss-editor-row__meta form-text text-muted topic"
              id={`label-${tripwire.svgId}`}
            >
              <button
                type="button"
                className="ss-editor-copy-id topic-text"
                title="Click to copy the topic"
                onClick={() => void copyTextToClipboard(tripwire.topic)}
              >
                {tripwire.topic}
              </button>
            </div>
          </div>
        ) : (
          <span id={`label-${tripwire.svgId}`} className="sr-only">
            {tripwire.title || "Tripwire"}
          </span>
        )}
      </div>
    </div>
  );
}
