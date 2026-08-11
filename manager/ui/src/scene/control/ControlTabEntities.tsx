// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";
import { createPortal } from "react-dom";
import type {
  SceneCameraBootstrap,
  SceneChildBootstrap,
  SceneSensorBootstrap,
} from "../types";
import "./ControlTabEntities.css";

declare global {
  interface Window {
    ssRefreshCameraSnapshots?: () => void;
    ssDrawSingletonSensors?: () => void;
  }
}

type Props = {
  cameras: SceneCameraBootstrap[];
  sensors: SceneSensorBootstrap[];
  childrenLinks: SceneChildBootstrap[];
  isSuperuser: boolean;
  panelsReady: boolean;
};

function CameraCards({
  cameras,
  isSuperuser,
}: {
  cameras: SceneCameraBootstrap[];
  isSuperuser: boolean;
}) {
  useEffect(() => {
    const refresh = () => window.ssRefreshCameraSnapshots?.();
    refresh();
    // MQTT may connect before React portals mount; retry briefly.
    const t1 = window.setTimeout(refresh, 400);
    const t2 = window.setTimeout(refresh, 1200);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [cameras]);

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
                  className="ss-btn ss-btn--secondary ss-btn--sm"
                  href={cam.calibrateHref}
                  title={`Edit ${cam.name}`}
                >
                  Edit
                </a>
                {cam.deleteUrl ? (
                  <a
                    className="ss-btn ss-btn--danger ss-btn--sm"
                    href={cam.deleteUrl}
                    title={`Delete ${cam.name}`}
                  >
                    Delete
                  </a>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ))}
    </>
  );
}

function SensorCards({
  sensors,
  isSuperuser,
}: {
  sensors: SceneSensorBootstrap[];
  isSuperuser: boolean;
}) {
  useEffect(() => {
    window.ssDrawSingletonSensors?.();
  }, [sensors]);

  if (sensors.length === 0) {
    return (
      <div className="ss-empty-state">
        <p>No sensors in this scene yet.</p>
        {isSuperuser ? (
          <a className="btn btn-primary btn-sm" href="?ss=sensor-create">
            + New Sensor
          </a>
        ) : null}
      </div>
    );
  }

  return (
    <>
      {sensors.map((sensor) => (
        <div
          key={sensor.id}
          className="card singleton count-item ss-control-card"
          data-sensor-name={sensor.name}
        >
          <h5 className="card-header">
            {sensor.iconUrl ? (
              <img
                className="sensor-icon"
                width={24}
                height={24}
                src={sensor.iconUrl}
                alt={`${sensor.name} Icon`}
              />
            ) : null}
            {sensor.name}
          </h5>
          <div className="card-body">
            <table className="table table-sm">
              <tbody>
                <tr>
                  <th>ID</th>
                  <td className="small sensor-id">{sensor.sensorId}</td>
                </tr>
              </tbody>
            </table>
            <input
              type="hidden"
              className="area-json"
              value={sensor.areaJson}
              readOnly
            />
            {isSuperuser ? (
              <div className="text-right ss-entity-actions">
                <a
                  className="ss-btn ss-btn--secondary ss-btn--sm sensor_calibrate"
                  href={sensor.calibrateHref}
                  id={`sensor_calibrate_${sensor.id}`}
                  title="Manage"
                >
                  Manage
                </a>
                <a
                  className="ss-btn ss-btn--secondary ss-btn--sm"
                  href={sensor.editHref}
                  title="Edit"
                >
                  Edit
                </a>
                {sensor.deleteUrl ? (
                  <a
                    className="ss-btn ss-btn--danger ss-btn--sm"
                    href={sensor.deleteUrl}
                    title="Delete"
                  >
                    Delete
                  </a>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ))}
    </>
  );
}

function ChildCards({
  childrenLinks,
  isSuperuser,
}: {
  childrenLinks: SceneChildBootstrap[];
  isSuperuser: boolean;
}) {
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
        return (
          <div key={child.id} className="card ss-control-card">
            <h6 className="card-header">{child.name}</h6>
            {thumb && child.detailUrl ? (
              <div className="card-image">
                <a href={child.detailUrl}>
                  <img className="cover" src={thumb} alt={child.name} />
                </a>
              </div>
            ) : null}
            <div className="card-body">
              <div className="text-right ss-entity-actions">
                {child.childType === "remote" && child.remoteChildId ? (
                  <span
                    id={`mqtt_status_remote_${child.remoteChildId}`}
                    className="child_mqtt_status btn-sm btn"
                  >
                    <i className="bi bi-arrow-down-up" />
                  </span>
                ) : null}
                {child.detailUrl ? (
                  <a
                    className="ss-btn ss-btn--secondary ss-btn--sm"
                    href={child.detailUrl}
                    title="View Scene"
                  >
                    Open
                  </a>
                ) : null}
                {isSuperuser ? (
                  <>
                    <a
                      className="ss-btn ss-btn--secondary ss-btn--sm"
                      href={child.editHref}
                      title={`Manage ${child.name}`}
                      id={`child-update-${child.name}`}
                    >
                      Manage
                    </a>
                    {child.deleteUrl ? (
                      <a
                        className="ss-btn ss-btn--danger ss-btn--sm"
                        href={child.deleteUrl}
                        title={`Delete ${child.name}`}
                        id={`child-delete-${child.name}`}
                      >
                        Delete
                      </a>
                    ) : null}
                  </>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
}

/**
 * React-owned cameras / sensors / children cards, portaled into tab mounts.
 * Preserves MQTT/map DOM contracts (snapshot topics, .singleton/.area-json, ids).
 */
export function ControlTabEntities({
  cameras,
  sensors,
  childrenLinks,
  isSuperuser,
  panelsReady,
}: Props) {
  if (!panelsReady) {
    return null;
  }

  const camMount = document.getElementById("ss-cameras-mount");
  const sensorMount = document.getElementById("ss-sensors-mount");
  const childMount = document.getElementById("ss-children-mount");

  return (
    <>
      {camMount
        ? createPortal(
            <CameraCards cameras={cameras} isSuperuser={isSuperuser} />,
            camMount,
          )
        : null}
      {sensorMount
        ? createPortal(
            <SensorCards sensors={sensors} isSuperuser={isSuperuser} />,
            sensorMount,
          )
        : null}
      {childMount
        ? createPortal(
            <ChildCards
              childrenLinks={childrenLinks}
              isSuperuser={isSuperuser}
            />,
            childMount,
          )
        : null}
    </>
  );
}
