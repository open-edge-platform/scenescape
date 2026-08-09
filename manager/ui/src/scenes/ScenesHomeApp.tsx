// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect } from "react";
import { ToastProvider, useAppToast, installLegacyToastBridge } from "../components/ToastProvider";
import { useSheetFromQuery } from "../hooks/useSheetFromQuery";
import type { SheetAction } from "../lib/sheetQuery";
import { SceneSheet } from "../sheets/SceneSheet";
import { SceneImportDialog } from "../sheets/SceneImportDialog";
import { EmbedFormOverlay, embedFormUrl } from "../sheets/EmbedFormOverlay";
import "./ScenesHomeApp.css";

export type ScenesHomeBootstrap = {
  authToken: string;
  isSuperuser: boolean;
};

type Props = {
  bootstrap: ScenesHomeBootstrap;
};

function isAction(v: string | null): v is Exclude<SheetAction, null> {
  return Boolean(v);
}

function ScenesHomeInner({ bootstrap }: Props) {
  const { sheet, open, close } = useSheetFromQuery();
  const toast = useAppToast();

  useEffect(() => installLegacyToastBridge(toast), [toast]);

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
      if (!ss || !isAction(ss)) {
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
        if (/\/scene\/update\//.test(url.pathname)) {
          const m = url.pathname.match(/\/scene\/update\/([^/]+)/);
          if (m) {
            ev.preventDefault();
            open("scene-edit", m[1]);
          }
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

  if (!bootstrap.isSuperuser) {
    return null;
  }

  return (
    <>
      <SceneSheet
        open={sheet.action === "scene-create"}
        mode="create"
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
      <EmbedFormOverlay
        open={sheet.action === "scene-edit"}
        src={
          sheet.action === "scene-edit" && sheet.id
            ? embedFormUrl(`/scene/update/${sheet.id}/`)
            : null
        }
        title="Edit scene"
        onClose={close}
      />
      <SceneImportDialog
        open={sheet.action === "scene-import"}
        authToken={bootstrap.authToken}
        onClose={close}
        onImported={reload}
      />
    </>
  );
}

export function ScenesHomeApp({ bootstrap }: Props) {
  return (
    <ToastProvider>
      <div className="ss-scenes-home-root" hidden />
      <ScenesHomeInner bootstrap={bootstrap} />
    </ToastProvider>
  );
}
