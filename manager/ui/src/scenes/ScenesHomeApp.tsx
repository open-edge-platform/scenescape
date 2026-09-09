// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useMemo } from "react";
import { ToastProvider, useAppToast } from "../components/ToastProvider";
import { LegacyConfirmHost } from "../components/LegacyConfirmHost";
import { PageHeader } from "../components/PageHeader";
import { useSheetFromQuery } from "../hooks/useSheetFromQuery";
import type { SheetAction } from "../lib/sheetQuery";
import { SceneSheet } from "../sheets/SceneSheet";
import { SceneImportDialog } from "../sheets/SceneImportDialog";
import { SceneManagePanel } from "../sheets/SceneManagePanel";
import { ChildSheet } from "../sheets/ChildSheet";
import "./ScenesHomeApp.css";

export type SceneHomeCard = {
  id: string;
  name: string;
  thumbnailUrl: string | null;
  mapUrl: string | null;
  detailUrl: string;
  detail3dUrl: string;
  manageUrl: string;
  deleteUrl: string | null;
  counts: {
    sensors: number;
    regions: number;
    tripwires: number;
  };
};

export type ScenesHomeBootstrap = {
  authToken: string;
  isSuperuser: boolean;
  scenes: SceneHomeCard[];
};

type Props = {
  bootstrap: ScenesHomeBootstrap;
};

const HOME_ACTIONS = new Set([
  "scene-create",
  "scene-import",
  "scene-manage",
  "child-create",
]);

function isHomeAction(v: string | null): v is Exclude<SheetAction, null> {
  return Boolean(v && HOME_ACTIONS.has(v));
}

function SceneThumb({ scene }: { scene: SceneHomeCard }) {
  const src = scene.thumbnailUrl || scene.mapUrl;
  if (src) {
    return <img className="cover" src={src} alt={scene.name} />;
  }
  return <div className="blank-container border" aria-hidden="true" />;
}

function ScenesGallery({
  scenes,
  isSuperuser,
  onCreate,
}: {
  scenes: SceneHomeCard[];
  isSuperuser: boolean;
  onCreate: () => void;
}) {
  if (scenes.length === 0) {
    return (
      <p className="scene-gallery-empty ss-scene-gallery-empty">
        No scenes are available.
        {isSuperuser ? (
          <>
            {" "}
            <button type="button" className="ss-text-link" onClick={onCreate}>
              Click here
            </button>{" "}
            to add one.
          </>
        ) : (
          " Ask an administrator to add one."
        )}
      </p>
    );
  }

  return (
    <div className="scene-gallery ss-scene-gallery">
      {scenes.map((scene) => (
        <div
          key={scene.id}
          className="card scene-card ss-scene-card"
          data-scene-id={scene.id}
          ref={(el) => {
            if (el) {
              el.setAttribute("name", scene.name);
            }
          }}
        >
          <h5 className="card-header">{scene.name}</h5>
          <div className="card-image">
            <a id={`scene_id_${scene.id}`} href={scene.detailUrl}>
              <SceneThumb scene={scene} />
            </a>
          </div>
          <div className="card-body">
            <table className="table table-sm scene-card-meta">
              <tbody>
                <tr>
                  <td>Cameras &amp; Sensors</td>
                  <td className="sensor-count">{scene.counts.sensors}</td>
                </tr>
                <tr>
                  <td>Regions</td>
                  <td className="region-count">{scene.counts.regions}</td>
                </tr>
                <tr>
                  <td>Tripwires</td>
                  <td className="tripwire-count">{scene.counts.tripwires}</td>
                </tr>
              </tbody>
            </table>
            <div className="scene-card-actions ss-scene-card-actions">
              <a
                className="ss-btn ss-btn--secondary ss-btn--sm"
                id={`scene-manage-${scene.name}`}
                href={scene.detailUrl}
                title={`Configure ${scene.name} Scene`}
              >
                Configure
              </a>
              <a
                className="ss-btn ss-btn--secondary ss-btn--sm"
                id={`scene-3d-${scene.id}`}
                href={scene.detail3dUrl}
                title={`View ${scene.name} Scene in 3D`}
              >
                3D
              </a>
              {isSuperuser ? (
                <>
                  <a
                    className="ss-btn ss-btn--secondary ss-btn--sm"
                    id={`scene-edit-${scene.id}`}
                    href={scene.manageUrl}
                    title={`Edit ${scene.name} Scene Details`}
                  >
                    Edit
                  </a>
                  {scene.deleteUrl ? (
                    <a
                      className="ss-btn ss-btn--danger ss-btn--sm"
                      id={`scene-delete-${scene.id}`}
                      href={scene.deleteUrl}
                      title={`Delete ${scene.name} Scene`}
                    >
                      Delete
                    </a>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ScenesHomeInner({ bootstrap }: Props) {
  const { sheet, open, close } = useSheetFromQuery();
  useAppToast();

  useEffect(() => {
    const onClick = (ev: Event) => {
      const target = ev.target as HTMLElement | null;
      const link = target?.closest("a[href]") as HTMLAnchorElement | null;
      if (!link?.href) {
        return;
      }
      let url: URL;
      try {
        url = new URL(link.href, window.location.origin);
      } catch {
        return;
      }
      const ss = url.searchParams.get("ss");
      if (!ss || !isHomeAction(ss)) {
        if (link.id === "new_scene") {
          ev.preventDefault();
          open("scene-create");
          return;
        }
        if (link.id === "import-scene") {
          ev.preventDefault();
          open("scene-import");
          return;
        }
        return;
      }
      if (url.pathname === "/" || url.pathname === "") {
        ev.preventDefault();
        open(ss, url.searchParams.get("id"));
      }
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [open]);

  const reload = useCallback(() => {
    window.location.reload();
  }, []);

  const openCreate = useCallback(() => open("scene-create"), [open]);
  const sceneOptions = useMemo(
    () => (bootstrap.scenes || []).map((s) => ({ id: s.id, name: s.name })),
    [bootstrap.scenes],
  );
  const manageSceneId =
    sheet.action === "scene-manage" && sheet.id ? sheet.id : "";

  return (
    <>
      <PageHeader
        title="Scenes"
        actions={
          bootstrap.isSuperuser ? (
            <>
              <a
                id="import-scene"
                className="ss-btn ss-btn--secondary"
                href="?ss=scene-import"
              >
                Import Scene
              </a>
              <a
                id="new_scene"
                className="ss-btn ss-btn--primary"
                href="?ss=scene-create"
              >
                + New Scene
              </a>
            </>
          ) : null
        }
      />
      <ScenesGallery
        scenes={bootstrap.scenes || []}
        isSuperuser={bootstrap.isSuperuser}
        onCreate={openCreate}
      />
      {bootstrap.isSuperuser ? (
        <>
          <SceneSheet
            open={sheet.action === "scene-create"}
            mode="create"
            sceneUid={null}
            authToken={bootstrap.authToken}
            onClose={close}
            onSaved={(uid) => {
              if (uid) {
                window.location.href = `/${uid}/`;
                return;
              }
              reload();
            }}
          />
          <SceneImportDialog
            open={sheet.action === "scene-import"}
            authToken={bootstrap.authToken}
            onClose={close}
            onImported={reload}
          />
          <SceneManagePanel
            open={Boolean(manageSceneId)}
            sceneId={manageSceneId}
            authToken={bootstrap.authToken}
            onClose={close}
            onSaved={reload}
          />
          <ChildSheet
            open={sheet.action === "child-create"}
            mode="create"
            parentSceneId=""
            scenes={sceneOptions}
            authToken={bootstrap.authToken}
            onClose={close}
            onSaved={reload}
          />
        </>
      ) : null}
    </>
  );
}

export function ScenesHomeApp({ bootstrap }: Props) {
  return (
    <ToastProvider>
      <LegacyConfirmHost>
        <div className="ss-scenes-home">
          <ScenesHomeInner bootstrap={bootstrap} />
        </div>
      </LegacyConfirmHost>
    </ToastProvider>
  );
}
