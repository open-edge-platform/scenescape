// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./OccupancyColorRange.css";

export type OccupancyThresholds = {
  greenMin: number;
  yellowMin: number;
  redMin: number;
  rangeMax: number;
};

type Props = {
  value: OccupancyThresholds;
  disabled?: boolean;
  /** When false, omit the built-in heading (e.g. FormSection already titled). */
  showLabel?: boolean;
  label?: string;
  /**
   * Keep legacy class names (green_min, …) for sscape.js ROI persistence.
   */
  legacyInputClasses?: boolean;
  idPrefix?: string;
  onChange: (next: OccupancyThresholds) => void;
};

function parseNum(raw: string): number {
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}

/**
 * Shared green / yellow / red / max occupancy threshold control.
 * Used by ROI editor rows and sensor calibrate.
 */
export function OccupancyColorRange({
  value,
  disabled = false,
  showLabel = true,
  label = "Occupancy thresholds",
  legacyInputClasses = false,
  idPrefix = "ss-occupancy",
  onChange,
}: Props) {
  const patch = (key: keyof OccupancyThresholds, raw: string) => {
    onChange({ ...value, [key]: parseNum(raw) });
  };

  return (
    <div className="ss-color-range">
      {showLabel ? (
        <div className="ss-color-range__label">{label}</div>
      ) : null}
      <div className="ss-color-range__track" aria-hidden="true">
        <span className="ss-color-range__seg ss-color-range__seg--green" />
        <span className="ss-color-range__seg ss-color-range__seg--yellow" />
        <span className="ss-color-range__seg ss-color-range__seg--red" />
      </div>
      <div className="ss-color-range__inputs sector-config">
        <label className="ss-color-range__field" htmlFor={`${idPrefix}-green`}>
          <span className="ss-color-range__swatch ss-color-range__swatch--green" />
          <span className="ss-color-range__caption">Green</span>
          <input
            id={`${idPrefix}-green`}
            type="number"
            className={`ss-color-range__input form-control${legacyInputClasses ? " green_min" : ""}`}
            disabled={disabled}
            value={value.greenMin}
            aria-label="Green threshold minimum"
            onChange={(e) => patch("greenMin", e.target.value)}
          />
        </label>
        <label className="ss-color-range__field" htmlFor={`${idPrefix}-yellow`}>
          <span className="ss-color-range__swatch ss-color-range__swatch--yellow" />
          <span className="ss-color-range__caption">Yellow</span>
          <input
            id={`${idPrefix}-yellow`}
            type="number"
            className={`ss-color-range__input form-control${legacyInputClasses ? " yellow_min" : ""}`}
            disabled={disabled}
            value={value.yellowMin}
            aria-label="Yellow threshold minimum"
            onChange={(e) => patch("yellowMin", e.target.value)}
          />
        </label>
        <label className="ss-color-range__field" htmlFor={`${idPrefix}-red`}>
          <span className="ss-color-range__swatch ss-color-range__swatch--red" />
          <span className="ss-color-range__caption">Red</span>
          <input
            id={`${idPrefix}-red`}
            type="number"
            className={`ss-color-range__input form-control${legacyInputClasses ? " red_min" : ""}`}
            disabled={disabled}
            value={value.redMin}
            aria-label="Red threshold minimum"
            onChange={(e) => patch("redMin", e.target.value)}
          />
        </label>
        <label className="ss-color-range__field" htmlFor={`${idPrefix}-max`}>
          <span className="ss-color-range__caption">Max</span>
          <input
            id={`${idPrefix}-max`}
            type="number"
            className={`ss-color-range__input form-control${legacyInputClasses ? " range_max" : ""}`}
            disabled={disabled}
            value={value.rangeMax}
            aria-label="Range maximum"
            onChange={(e) => patch("rangeMax", e.target.value)}
          />
        </label>
      </div>
    </div>
  );
}
