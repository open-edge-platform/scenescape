// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useRef, useState } from "react";
import { WorkspacePanel } from "../components/WorkspacePanel";
import { Button } from "../components/Button";
import {
  PanelLayoutToggle,
  chooseAutoPanelLayout,
  readPanelLayoutMode,
  writePanelLayoutMode,
  type PanelLayout,
  type PanelLayoutMode,
} from "../components/PanelLayoutToggle";
import { useAppToast } from "../components/ToastProvider";
import "../components/PanelLayoutToggle.css";

type Props = {
  open: boolean;
  /** Django DB pk as string (from bootstrap sensors[].id) */
  sensorPk: string;
  onClose: () => void;
  onSaved: () => void;
};

/**
 * Full-viewport sensor calibrate panel.
 * Map / ROI stay in the Django embed; panel layout mirrors camera calibrate.
 */
export function SensorCalibratePanel({
  open,
  sensorPk,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);
  const [layoutMode, setLayoutMode] = useState<PanelLayoutMode>(() =>
    typeof window !== "undefined" ? readPanelLayoutMode() : "auto",
  );
  const [autoLayout, setAutoLayout] = useState<PanelLayout>(() =>
    typeof window !== "undefined" ? chooseAutoPanelLayout() : "stack",
  );

  const resolvedLayout: PanelLayout =
    layoutMode === "auto" ? autoLayout : layoutMode;

  const setPanelLayoutMode = useCallback((mode: PanelLayoutMode) => {
    setLayoutMode(mode);
    writePanelLayoutMode(mode);
  }, []);

  const pushLayoutToIframe = useCallback((layout: PanelLayout) => {
    const win = iframeRef.current?.contentWindow;
    if (!win) {
      return;
    }
    win.postMessage(
      { type: "ss-calibrate-layout", layout },
      window.location.origin,
    );
  }, []);

  useEffect(() => {
    const recompute = () => setAutoLayout(chooseAutoPanelLayout());
    recompute();
    window.addEventListener("resize", recompute);
    return () => window.removeEventListener("resize", recompute);
  }, []);

  useEffect(() => {
    if (!open) {
      setDirty(false);
      setBusy(false);
      setIframeReady(false);
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
        setBusy(false);
        setDirty(false);
        onSaved();
        onClose();
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [open, onClose, onSaved, toast]);

  useEffect(() => {
    if (!open || !iframeReady) {
      return;
    }
    pushLayoutToIframe(resolvedLayout);
  }, [open, iframeReady, resolvedLayout, pushLayoutToIframe]);

  const save = () => {
    setBusy(true);
    iframeRef.current?.contentWindow?.postMessage(
      { type: "ss-calibrate-save-points" },
      window.location.origin,
    );
  };

  return (
    <WorkspacePanel
      open={open && Boolean(sensorPk)}
      title="Calibrate sensor"
      layout="bleed"
      dirty={dirty}
      leaveTitle="Leave calibration?"
      leaveBody="You may have unsaved calibration changes. Leave without saving?"
      onClose={onClose}
      actions={
        <>
          <PanelLayoutToggle
            layoutMode={layoutMode}
            onChange={setPanelLayoutMode}
          />
          <Button
            variant="primary"
            disabled={busy || !dirty}
            onClick={save}
            title={dirty ? "Save changes" : "No unsaved changes"}
            className={dirty ? "ss-btn--dirty" : undefined}
          >
            {busy ? "Saving…" : dirty ? "Save" : "Saved"}
          </Button>
        </>
      }
    >
      {sensorPk ? (
        <iframe
          ref={iframeRef}
          className="ss-cal-workspace--bleed-iframe"
          title="Sensor calibrator"
          src={`/singleton_sensor/calibrate/${sensorPk}?embed=1`}
          onLoad={() => setIframeReady(true)}
        />
      ) : null}
    </WorkspacePanel>
  );
}
