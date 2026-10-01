// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { useAppToast } from "../../components/ToastProvider";
import { ACTION_ICONS } from "../../components/actionIcons";
import { refreshCameraStrip } from "../../mqtt";
import { api, type RestError } from "../../lib/rest";
import { publishSceneTabCounts } from "../../lib/sceneTab";
import { copyTextToClipboard } from "../editors/copyText";
import type {
  SceneCameraBootstrap,
  SceneChildBootstrap,
  SceneSensorBootstrap,
} from "../types";
import "./ControlTabEntities.css";
import "../../components/Button.css";

export function CamerasPanelContent({
  cameras,
  isSuperuser,
  authToken = "",
  onCamerasChange,
}: {
  cameras: SceneCameraBootstrap[];
  isSuperuser: boolean;
  authToken?: string;
  onCamerasChange?: Dispatch<SetStateAction<SceneCameraBootstrap[]>>;
}) {
  const toast = useAppToast();
  const [pendingCamera, setPendingCamera] =
    useState<SceneCameraBootstrap | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const canDelete = Boolean(authToken && onCamerasChange);

  useEffect(() => {
    const refresh = () => refreshCameraStrip();
    refresh();
    const t1 = window.setTimeout(refresh, 400);
    const t2 = window.setTimeout(refresh, 1200);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [cameras]);

  const confirmCameraDelete = useCallback(async () => {
    if (!pendingCamera || !authToken || !onCamerasChange) {
      return;
    }
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await api.deleteCamera(authToken, pendingCamera.sensorId);
      onCamerasChange((prev) =>
        prev.filter(
          (c) =>
            c.id !== pendingCamera.id && c.sensorId !== pendingCamera.sensorId,
        ),
      );
      toast.show("Camera deleted", "ok");
      setPendingCamera(null);
    } catch (err) {
      setDeleteError((err as RestError).message || "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  }, [authToken, onCamerasChange, pendingCamera, toast]);

  if (cameras.length === 0) {
    return (
      <div className="ss-empty-state">
        <p>No cameras in this scene yet.</p>
        {isSuperuser ? (
          <a className="btn btn-primary btn-sm" href="?ss=cam-create">
            + New Camera
          </a>
        ) : null}
      </div>
    );
  }

  return (
    <>
      {cameras.map((cam) => (
        <div key={cam.id} className="card count-item camera-card">
          <h6 className="card-header">
            <span className="rate telemetry-hide" id={`rate-${cam.sensorId}`}>
              --
            </span>
            {cam.name}
          </h6>
          <div className="card-image">
            <a
              className="snapshot-image"
              href={isSuperuser ? cam.calibrateHref : undefined}
              id={`cam_calibrate_${cam.id}`}
              data-topic={cam.cmdTopic}
              data-topic-name={`scenescape/cmd/camera/${cam.name}`}
            >
              <div className="cam-offline">Camera Offline</div>
              <img
                id={`card-preview-${cam.sensorId}`}
                className="display-none"
                alt={`${cam.name} View`}
                data-ss-card-sensor={cam.sensorId}
                data-ss-card-name={cam.name}
              />
            </a>
          </div>
          <div className="card-body hide-live">
            {isSuperuser ? (
              <div className="text-right ss-entity-actions">
                <a
                  className="ss-icon-btn"
                  href={cam.calibrateHref}
                  title={`Configure ${cam.name}`}
                  aria-label={`Configure ${cam.name}`}
                >
                  <i
                    className={`bi ${ACTION_ICONS.configure}`}
                    aria-hidden="true"
                  />
                </a>
                {canDelete ? (
                  <button
                    type="button"
                    className="ss-icon-btn ss-icon-btn--danger"
                    title={`Delete ${cam.name}`}
                    aria-label={`Delete ${cam.name}`}
                    onClick={() => {
                      setDeleteError(null);
                      setPendingCamera(cam);
                    }}
                  >
                    <i
                      className={`bi ${ACTION_ICONS.delete}`}
                      aria-hidden="true"
                    />
                  </button>
                ) : cam.deleteUrl ? (
                  <a
                    className="ss-icon-btn ss-icon-btn--danger"
                    href={cam.deleteUrl}
                    title={`Delete ${cam.name}`}
                    aria-label={`Delete ${cam.name}`}
                  >
                    <i
                      className={`bi ${ACTION_ICONS.delete}`}
                      aria-hidden="true"
                    />
                  </a>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ))}
      <ConfirmDialog
        open={Boolean(pendingCamera)}
        title="Delete camera?"
        confirmLabel="Delete"
        danger
        busy={deleteBusy}
        onConfirm={confirmCameraDelete}
        onCancel={() => {
          if (!deleteBusy) {
            setPendingCamera(null);
            setDeleteError(null);
          }
        }}
      >
        <p>
          Are you sure you want to delete{" "}
          <strong>{pendingCamera?.name || "this camera"}</strong>?
        </p>
        <p>This action cannot be undone.</p>
        {deleteError ? <p className="ss-confirm-error">{deleteError}</p> : null}
      </ConfirmDialog>
    </>
  );
}

export function SensorsPanelContent({
  sensors,
  isSuperuser,
  authToken = "",
  onSensorsChange,
}: {
  sensors: SceneSensorBootstrap[];
  isSuperuser: boolean;
  authToken?: string;
  onSensorsChange?: Dispatch<SetStateAction<SceneSensorBootstrap[]>>;
}) {
  const toast = useAppToast();
  const [pendingSensor, setPendingSensor] =
    useState<SceneSensorBootstrap | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const canDelete = Boolean(authToken && onSensorsChange);

  useEffect(() => {
    publishSceneTabCounts({ sensors: sensors.length });
  }, [sensors.length]);

  const confirmSensorDelete = useCallback(async () => {
    if (!pendingSensor || !authToken || !onSensorsChange) {
      return;
    }
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await api.deleteSensor(authToken, pendingSensor.sensorId);
      onSensorsChange((prev) =>
        prev.filter(
          (s) =>
            s.id !== pendingSensor.id && s.sensorId !== pendingSensor.sensorId,
        ),
      );
      toast.show("Sensor deleted", "ok");
      setPendingSensor(null);
    } catch (err) {
      setDeleteError((err as RestError).message || "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  }, [authToken, onSensorsChange, pendingSensor, toast]);

  return (
    <>
      {sensors.length === 0 ? (
        <div className="ss-empty-state">
          <p>No sensors in this scene yet.</p>
          {isSuperuser ? (
            <a className="btn btn-primary btn-sm" href="?ss=sensor-create">
              + New Sensor
            </a>
          ) : null}
        </div>
      ) : (
        <div className="ss-tab-list">
          {sensors.map((sensor) => (
            <div
              key={sensor.id}
              className="ss-tab-row singleton count-item"
              data-sensor-name={sensor.name}
            >
              {sensor.iconUrl ? (
                <img
                  className="sensor-icon ss-tab-row__icon"
                  width={20}
                  height={20}
                  src={sensor.iconUrl}
                  alt=""
                />
              ) : (
                <span
                  className="ss-tab-row__icon ss-tab-row__icon--empty"
                  aria-hidden="true"
                />
              )}
              <div className="ss-tab-row__main">
                <span className="ss-tab-row__title">{sensor.name}</span>
                <button
                  type="button"
                  className="ss-tab-row__meta sensor-id ss-tab-row__copy-id"
                  title="Click to copy ID"
                  onClick={() =>
                    void copyTextToClipboard(sensor.sensorId, toast.show)
                  }
                >
                  {sensor.sensorId}
                </button>
              </div>
              <input
                type="hidden"
                className="area-json"
                value={sensor.areaJson}
                readOnly
              />
              {isSuperuser ? (
                <div className="ss-tab-row__actions ss-entity-actions">
                  <a
                    className="ss-icon-btn sensor_calibrate"
                    href={sensor.calibrateHref}
                    id={`sensor_calibrate_${sensor.id}`}
                    title={`Configure ${sensor.name}`}
                    aria-label={`Configure ${sensor.name}`}
                  >
                    <i
                      className={`bi ${ACTION_ICONS.configure}`}
                      aria-hidden="true"
                    />
                  </a>
                  {canDelete ? (
                    <button
                      type="button"
                      className="ss-icon-btn ss-icon-btn--danger"
                      title={`Delete ${sensor.name}`}
                      aria-label={`Delete ${sensor.name}`}
                      onClick={() => {
                        setDeleteError(null);
                        setPendingSensor(sensor);
                      }}
                    >
                      <i
                        className={`bi ${ACTION_ICONS.delete}`}
                        aria-hidden="true"
                      />
                    </button>
                  ) : sensor.deleteUrl ? (
                    <a
                      className="ss-icon-btn ss-icon-btn--danger"
                      href={sensor.deleteUrl}
                      title={`Delete ${sensor.name}`}
                      aria-label={`Delete ${sensor.name}`}
                    >
                      <i
                        className={`bi ${ACTION_ICONS.delete}`}
                        aria-hidden="true"
                      />
                    </a>
                  ) : null}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
      <ConfirmDialog
        open={Boolean(pendingSensor)}
        title="Delete sensor?"
        confirmLabel="Delete"
        danger
        busy={deleteBusy}
        onConfirm={confirmSensorDelete}
        onCancel={() => {
          if (!deleteBusy) {
            setPendingSensor(null);
            setDeleteError(null);
          }
        }}
      >
        <p>
          Are you sure you want to delete{" "}
          <strong>{pendingSensor?.name || "this sensor"}</strong>?
        </p>
        <p>This action cannot be undone.</p>
        {deleteError ? <p className="ss-confirm-error">{deleteError}</p> : null}
      </ConfirmDialog>
    </>
  );
}

export function ChildrenPanelContent({
  childrenLinks,
  isSuperuser,
  authToken = "",
  onChildrenChange,
}: {
  childrenLinks: SceneChildBootstrap[];
  isSuperuser: boolean;
  authToken?: string;
  onChildrenChange?: Dispatch<SetStateAction<SceneChildBootstrap[]>>;
}) {
  const toast = useAppToast();
  const [pendingChild, setPendingChild] =
    useState<SceneChildBootstrap | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const canDelete = Boolean(authToken && onChildrenChange);

  const confirmChildDelete = useCallback(async () => {
    if (!pendingChild || !authToken || !onChildrenChange) {
      return;
    }
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await api.deleteChild(authToken, pendingChild.id);
      onChildrenChange((prev) =>
        prev.filter((c) => c.id !== pendingChild.id),
      );
      toast.show("Child link deleted", "ok");
      setPendingChild(null);
    } catch (err) {
      setDeleteError((err as RestError).message || "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  }, [authToken, onChildrenChange, pendingChild, toast]);

  if (childrenLinks.length === 0) {
    return (
      <div className="ss-empty-state">
        <p>No child scenes linked yet.</p>
        {isSuperuser ? (
          <a className="btn btn-primary btn-sm" href="?ss=child-create">
            + Link Child
          </a>
        ) : null}
      </div>
    );
  }

  return (
    <>
      {childrenLinks.map((child) => {
        const thumb = child.thumbnailUrl || child.mapUrl;
        const image = thumb ? (
          <img src={thumb} alt={`${child.name} map`} />
        ) : (
          <div className="blank-container border" aria-hidden="true" />
        );
        return (
          <div
            key={child.id}
            className="card count-item camera-card child-card"
          >
            <h6 className="card-header">
              {child.childType === "remote" && child.remoteChildId ? (
                <span
                  id={`mqtt_status_remote_${child.remoteChildId}`}
                  className="child_mqtt_status btn-sm btn"
                >
                  <i className="bi bi-arrow-down-up" aria-hidden="true" />
                </span>
              ) : null}
              {child.childType === "remote" ? (
                <span className="ss-child-card-badge">Remote</span>
              ) : null}
              {child.name}
            </h6>
            <div className="card-image">
              {child.detailUrl ? (
                <a href={child.detailUrl} title={`Open ${child.name}`}>
                  {image}
                </a>
              ) : (
                image
              )}
            </div>
            <div className="card-body">
              {isSuperuser ? (
                <div className="text-right ss-entity-actions">
                  <a
                    className="ss-icon-btn"
                    href={child.editHref}
                    title={`Configure ${child.name}`}
                    aria-label={`Configure ${child.name}`}
                    id={`child-update-${child.name}`}
                  >
                    <i
                      className={`bi ${ACTION_ICONS.configure}`}
                      aria-hidden="true"
                    />
                  </a>
                  {canDelete ? (
                    <button
                      type="button"
                      className="ss-icon-btn ss-icon-btn--danger"
                      title={`Delete ${child.name}`}
                      aria-label={`Delete ${child.name}`}
                      id={`child-delete-${child.name}`}
                      onClick={() => {
                        setDeleteError(null);
                        setPendingChild(child);
                      }}
                    >
                      <i
                        className={`bi ${ACTION_ICONS.delete}`}
                        aria-hidden="true"
                      />
                    </button>
                  ) : child.deleteUrl ? (
                    <a
                      className="ss-icon-btn ss-icon-btn--danger"
                      href={child.deleteUrl}
                      title={`Delete ${child.name}`}
                      aria-label={`Delete ${child.name}`}
                      id={`child-delete-${child.name}`}
                    >
                      <i
                        className={`bi ${ACTION_ICONS.delete}`}
                        aria-hidden="true"
                      />
                    </a>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        );
      })}
      <ConfirmDialog
        open={Boolean(pendingChild)}
        title="Delete child scene link?"
        confirmLabel="Delete"
        danger
        busy={deleteBusy}
        onConfirm={confirmChildDelete}
        onCancel={() => {
          if (!deleteBusy) {
            setPendingChild(null);
            setDeleteError(null);
          }
        }}
      >
        <p>
          Are you sure you want to delete{" "}
          <strong>{pendingChild?.name || "this child link"}</strong>?
        </p>
        <p>This action cannot be undone.</p>
        {deleteError ? <p className="ss-confirm-error">{deleteError}</p> : null}
      </ConfirmDialog>
    </>
  );
}

/** Publish camera / sensor / children badge counts when entity lists change. */
export function usePublishEntityTabCounts(
  cameras: SceneCameraBootstrap[],
  sensors: SceneSensorBootstrap[],
  childrenLinks: SceneChildBootstrap[],
): void {
  useEffect(() => {
    publishSceneTabCounts({
      cameras: cameras.length,
      sensors: sensors.length,
      children: childrenLinks.length,
    });
  }, [cameras, sensors, childrenLinks]);
}
