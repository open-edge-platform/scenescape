// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./TabToolbar.css";

type Props = {
  activeTab: string;
  isSuperuser: boolean;
};

function HelpButton({
  id,
  modalId,
  title,
}: {
  id: string;
  modalId: string;
  title: string;
}) {
  return (
    <button
      type="button"
      className="scene-detail-help"
      id={id}
      data-toggle="modal"
      data-target={`#${modalId}`}
      title={title}
      aria-label={title}
    >
      <i className="bi bi-question-circle" aria-hidden="true" />
    </button>
  );
}

function LiveToggle({
  id,
  labelId,
  label,
  title,
}: {
  id: string;
  labelId: string;
  label: string;
  title: string;
}) {
  return (
    <div className="custom-control custom-switch switch scene-detail-live-toggle">
      <input
        type="checkbox"
        className="custom-control-input"
        id={id}
        aria-labelledby={labelId}
      />
      <label
        className="custom-control-label"
        htmlFor={id}
        title={title}
        id={labelId}
      >
        {label}
      </label>
    </div>
  );
}

/**
 * Active-tab toolbar controls with stable DOM ids for sscape.js handlers.
 */
export function TabToolbar({ activeTab, isSuperuser }: Props) {
  return (
    <div className="ss-tab-toolbar-inner" data-active-tab={activeTab}>
      {activeTab === "cameras" ? (
        <>
          <HelpButton
            id="camera-help"
            modalId="cameraHelpModal"
            title="How cameras work in this scene"
          />
          <LiveToggle
            id="live-view"
            labelId="live-view-label"
            label="Live View"
            title="Toggle Live View"
          />
          <LiveToggle
            id="show-telemetry"
            labelId="show-telemetry-label"
            label="Show Telemetry"
            title="Toggle Show Telemetry"
          />
          {isSuperuser ? (
            <a
              className="btn btn-primary btn-sm"
              id="new-camera"
              title="Add a new camera"
              href="?ss=cam-create"
            >
              + New Camera
            </a>
          ) : null}
        </>
      ) : null}

      {activeTab === "sensors" ? (
        <>
          <HelpButton
            id="sensor-help"
            modalId="sensorHelpModal"
            title="How sensors work in this scene"
          />
          {isSuperuser ? (
            <a
              className="btn btn-primary btn-sm"
              id="new-sensor"
              title="Add a new sensor"
              href="?ss=sensor-create"
            >
              + New Sensor
            </a>
          ) : null}
        </>
      ) : null}

      {activeTab === "regions" ? (
        <>
          <HelpButton
            id="roi-help"
            modalId="roiHelpModal"
            title="How regions of interest work"
          />
          {isSuperuser ? (
            <>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                id="new-roi"
                title="Create a new region"
              >
                + New Region
              </button>
              <input
                type="button"
                className="btn btn-sm btn-primary ss-save-clean"
                id="save-rois"
                value="Save"
                title="No unsaved changes"
                disabled
              />
            </>
          ) : null}
        </>
      ) : null}

      {activeTab === "tripwires" ? (
        <>
          <HelpButton
            id="tripwire-help"
            modalId="tripwireHelpModal"
            title="How tripwires work"
          />
          {isSuperuser ? (
            <>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                id="new-tripwire"
                title="Create a new tripwire"
              >
                + New Tripwire
              </button>
              <input
                type="button"
                className="btn btn-sm btn-primary ss-save-clean"
                id="save-trips"
                value="Save"
                title="No unsaved changes"
                disabled
              />
            </>
          ) : null}
        </>
      ) : null}

      {activeTab === "children" ? (
        <>
          <HelpButton
            id="children-help"
            modalId="childrenHelpModal"
            title="How child scenes work"
          />
          {isSuperuser ? (
            <a
              className="btn btn-primary btn-sm"
              id="new-child"
              title="Add a new child scene"
              href="?ss=child-create"
            >
              + Link Child
            </a>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
