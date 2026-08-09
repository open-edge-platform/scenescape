// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { WorkspacePanel } from "../components/WorkspacePanel";
import { useAppToast } from "../components/ToastProvider";

type Props = {
  open: boolean;
  /** Django DB pk as string (from bootstrap sensors[].id) */
  sensorPk: string;
  onClose: () => void;
  onSaved: () => void;
};

/**
 * Full-viewport sensor calibrate panel.
 * ROI / area drawing stays in the legacy Django embed until a native editor exists.
 */
export function SensorCalibratePanel({
  open,
  sensorPk,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!open) {
      setDirty(false);
      return;
    }
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) {
        return;
      }
      if (!ev.data || typeof ev.data !== "object") {
        return;
      }
      const type = (ev.data as { type?: string }).type;
      if (type === "ss-calibrate-dirty") {
        setDirty(true);
        return;
      }
      if (type === "ss-calibrate-cancel") {
        onClose();
        return;
      }
      if (type === "ss-calibrate-done") {
        toast.show("Sensor calibration saved", "ok");
        onSaved();
        onClose();
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [open, onClose, onSaved, toast]);

  return (
    <WorkspacePanel
      open={open && Boolean(sensorPk)}
      title="Calibrate sensor"
      layout="bleed"
      dirty={dirty}
      leaveTitle="Leave calibration?"
      leaveBody="You may have unsaved calibration changes. Leave without saving?"
      onClose={onClose}
    >
      <iframe
        title="Sensor calibrator"
        src={`/singleton_sensor/calibrate/${sensorPk}?embed=1`}
        style={{
          flex: 1,
          width: "100%",
          minHeight: 0,
          border: 0,
          display: "block",
        }}
      />
    </WorkspacePanel>
  );
}
