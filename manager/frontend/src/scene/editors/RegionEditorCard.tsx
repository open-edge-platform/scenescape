// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { copyTextToClipboard } from "./copyText";
import type { RoiEntity } from "./types";

type Props = {
  roi: RoiEntity;
  index: number;
  isSuperuser: boolean;
  onChange: (next: RoiEntity) => void;
  onRemove: (svgId: string) => void;
};

export function RegionEditorCard({
  roi,
  index,
  isSuperuser,
  onChange,
  onRemove,
}: Props) {
  const disabled = !isSuperuser || roi.readOnly;
  const [expanded, setExpanded] = useState(false);
  const detailsId = `roi-details-${roi.svgId}`;

  return (
    <div
      className="form-roi"
      id={`form-${roi.svgId}`}
      ref={(el) => el?.setAttribute("for", roi.svgId)}
    >
      <div
        className={`ss-editor-row count-item col ss-editor-card${expanded ? " is-expanded" : ""}`}
      >
        <div className="ss-editor-row__primary">
          <div className="ss-editor-row__fields">
            <span className="ss-editor-row__index input-group-text roi-number">
              {index + 1}
            </span>
            <input
              type="text"
              className="form-control roi-title ss-editor-row__title"
              id={`input-${roi.svgId}`}
              aria-labelledby={`label-${roi.svgId}`}
              placeholder="ROI Name"
              required
              maxLength={100}
              disabled={disabled}
              value={roi.title}
              onChange={(e) => onChange({ ...roi, title: e.target.value })}
              onBlur={() => {
                if (window.ssUseReactMap) {
                  window.ssMap?.numberRois?.();
                  return;
                }
                if (typeof window.numberRois === "function") {
                  window.numberRois();
                }
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
              className="ss-icon-btn ss-icon-btn--danger roi-remove ss-editor-row__remove"
              type="button"
              title="Remove this ROI"
              aria-label="Remove this ROI"
              onClick={(ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                onRemove(roi.svgId);
              }}
            >
              <i className="bi bi-trash" aria-hidden="true" />
            </button>
          ) : null}
        </div>

        {expanded ? (
          <div className="ss-editor-row__details" id={detailsId}>
            {isSuperuser ? (
              <div className="ss-editor-card-meta">
                <div className="form-check form-check-inline">
                  <input
                    className="form-check-input roi-volumetric"
                    type="checkbox"
                    id={`volumetric-${roi.svgId}`}
                    checked={roi.volumetric}
                    onChange={(e) =>
                      onChange({ ...roi, volumetric: e.target.checked })
                    }
                  />
                  <label
                    className="form-check-label"
                    htmlFor={`volumetric-${roi.svgId}`}
                  >
                    Volumetric
                  </label>
                </div>
                <label className="ss-editor-inline-field">
                  <span>Height</span>
                  <input
                    type="number"
                    className="form-control roi-height"
                    value={roi.height}
                    min={0.1}
                    step={0.1}
                    onChange={(e) =>
                      onChange({
                        ...roi,
                        height: Number(e.target.value) || 1.0,
                      })
                    }
                  />
                </label>
                <label className="ss-editor-inline-field">
                  <span>Buffer</span>
                  <input
                    type="number"
                    className="form-control roi-buffer"
                    value={roi.buffer_size}
                    min={0}
                    step={0.1}
                    onChange={(e) =>
                      onChange({
                        ...roi,
                        buffer_size: Number(e.target.value) || 0,
                      })
                    }
                  />
                </label>
              </div>
            ) : null}

            <div className="roi-visualization ss-editor-sectors">
              <div className="sector-container">
                <div className="color-range">Color Range:</div>
                <div className="sector-config">
                  <input
                    type="number"
                    className="green_min"
                    disabled={disabled}
                    value={roi.greenMin}
                    onChange={(e) =>
                      onChange({
                        ...roi,
                        greenMin: Number(e.target.value) || 0,
                      })
                    }
                  />
                  <div className="green-sec">--</div>
                  <input
                    type="number"
                    className="yellow_min"
                    disabled={disabled}
                    value={roi.yellowMin}
                    onChange={(e) =>
                      onChange({
                        ...roi,
                        yellowMin: Number(e.target.value) || 0,
                      })
                    }
                  />
                  <div className="yellow-sec">--</div>
                  <input
                    type="number"
                    className="red_min"
                    disabled={disabled}
                    value={roi.redMin}
                    onChange={(e) =>
                      onChange({
                        ...roi,
                        redMin: Number(e.target.value) || 0,
                      })
                    }
                  />
                  <div className="red-sec">--</div>
                  <input
                    type="number"
                    className="range_max"
                    disabled={disabled}
                    value={roi.rangeMax}
                    onChange={(e) =>
                      onChange({
                        ...roi,
                        rangeMax: Number(e.target.value) || 0,
                      })
                    }
                  />
                </div>
              </div>
            </div>

            <div className="col form-text text-muted roi-topic">
              <label id={`label-${roi.svgId}`} htmlFor={`input-${roi.svgId}`}>
                Topic:{" "}
              </label>
              <button
                type="button"
                className="ss-editor-copy-id topic-text"
                title="Click to copy the topic"
                onClick={() => void copyTextToClipboard(roi.topic)}
              >
                {roi.topic}
              </button>
            </div>
          </div>
        ) : (
          <span id={`label-${roi.svgId}`} className="sr-only">
            {roi.title || "ROI"}
          </span>
        )}
      </div>
    </div>
  );
}
