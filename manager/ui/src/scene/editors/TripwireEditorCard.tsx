// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

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
  const disabled = !isSuperuser || tripwire.readOnly;

  return (
    <div
      className="form-tripwire"
      id={`form-${tripwire.svgId}`}
      ref={(el) => el?.setAttribute("for", tripwire.svgId)}
    >
      <div className="input-group mb-3 count-item col ss-editor-card">
        <div className="input-group-prepend">
          <label className="input-group-text tripwire-number">{index + 1}</label>
        </div>
        <input
          type="text"
          className="form-control tripwire-title"
          id={`input-${tripwire.svgId}`}
          aria-labelledby={`label-${tripwire.svgId}`}
          placeholder="Tripwire Name"
          required
          disabled={disabled}
          value={tripwire.title}
          onChange={(e) => onChange({ ...tripwire, title: e.target.value })}
          onBlur={() => {
            if (typeof window.numberTripwires === "function") {
              window.numberTripwires();
            }
          }}
        />
        {isSuperuser ? (
          <div className="input-group-append">
            <button
              className="btn btn-secondary tripwire-remove"
              type="button"
              title="Remove this Tripwire"
              onClick={() => onRemove(tripwire.svgId)}
            >
              <i className="bi bi-trash" aria-hidden="true" />
            </button>
          </div>
        ) : null}
        <div className="col form-text text-muted topic" id={`label-${tripwire.svgId}`}>
          <i>{tripwire.topic}</i>
        </div>
      </div>
    </div>
  );
}
