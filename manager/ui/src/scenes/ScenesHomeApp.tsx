// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect } from "react";
import { ToastProvider, useAppToast } from "../components/ToastProvider";
import { LegacyConfirmHost } from "../components/LegacyConfirmHost";
import { useSheetFromQuery } from "../hooks/useSheetFromQuery";
import type { SheetAction } from "../lib/sheetQuery";
import { SceneSheet } from "../sheets/SceneSheet";
import { SceneImportDialog } from "../sheets/SceneImportDialog";
import "./ScenesHomeApp.css";

export type ScenesHomeBootstrap = {
  authToken: string;
  isSuperuser: boolean;
};

type Props = {
  bootstrap: ScenesHomeBootstrap;
};

const HOME_ACTIONS = new Set(["scene-create", "scene-import"]);

function isHomeAction(v: string | null): v is Exclude<SheetAction, null> {
  return Boolean(v && HOME_ACTIONS.has(v));
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

  if (!bootstrap.isSuperuser) {
    return null;
  }

  return (
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
    </>
  );
}

export function ScenesHomeApp({ bootstrap }: Props) {
  return (
    <ToastProvider>
      <LegacyConfirmHost>
        <div className="ss-scenes-home-root" hidden />
        <ScenesHomeInner bootstrap={bootstrap} />
      </LegacyConfirmHost>
    </ToastProvider>
  );
}
