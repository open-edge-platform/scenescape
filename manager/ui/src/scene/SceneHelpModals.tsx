// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Modal } from "../components/Modal";

const HELP: { id: string; title: string; items: string[] }[] = [
  {
    id: "cameraHelpModal",
    title: "Camera Help",
    items: [
      "All cameras and sensors must be associated with a scene.",
      "Use Manage to calibrate camera pose against the scene map.",
      "Live View requests fresh snapshots over MQTT while enabled.",
    ],
  },
  {
    id: "sensorHelpModal",
    title: "Sensor Help",
    items: [
      "Generic sensors report scalar or area occupancy on the map.",
      "Use Edit to place and size the sensor coverage area.",
    ],
  },
  {
    id: "roiHelpModal",
    title: "Region Help",
    items: [
      "Draw a region on the map, then set thresholds and topic.",
      "Save writes all regions for this scene in one submit.",
      "Occupancy coloring uses the configured sector thresholds.",
    ],
  },
  {
    id: "tripwireHelpModal",
    title: "Tripwire Help",
    items: [
      "Draw a tripwire line on the map between two endpoints.",
      "The green flag points toward +1 crossings.",
      "Name the tripwire in the side panel, then Save.",
      "Save writes all tripwires for this scene in one submit.",
      "Crossing events publish on the configured MQTT topic.",
    ],
  },
  {
    id: "childrenHelpModal",
    title: "Children Help",
    items: [
      "Child scenes aggregate detections into this parent scene.",
      "A scene may have any number of children but only one parent.",
      "The child scene must already exist before creating the link.",
    ],
  },
];

/** Bootstrap-compatible help dialogs for scene control tabs. */
export function SceneHelpModals() {
  return (
    <>
      {HELP.map((h) => (
        <Modal
          key={h.id}
          id={h.id}
          title={h.title}
          footer={
            <button
              type="button"
              className="ss-btn ss-btn--secondary"
              data-dismiss="modal"
            >
              Close
            </button>
          }
        >
          <ul>
            {h.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Modal>
      ))}
    </>
  );
}
