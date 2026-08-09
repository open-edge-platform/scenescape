// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import "./ModelsDirectoryApp.css";

type TreeNode = { [name: string]: TreeNode | null };

type LoadResponse = {
  path: string;
  folder_name: string;
  depth: number;
  tree: TreeNode;
};

function csrfToken(): string {
  const el = document.querySelector(
    'input[name="csrfmiddlewaretoken"]',
  ) as HTMLInputElement | null;
  return el?.value || "";
}

async function loadTree(
  path: string,
  folderName: string,
): Promise<LoadResponse> {
  const params = new URLSearchParams({
    action: "load",
    path,
    folder_name: folderName,
    format: "json",
  });
  const resp = await fetch(`/api/v1/model-directory/?${params}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
  });
  if (!resp.ok) {
    throw new Error(await resp.text());
  }
  return (await resp.json()) as LoadResponse;
}

function TreeView({
  name,
  node,
  depth,
}: {
  name: string;
  node: TreeNode | null;
  depth: number;
}) {
  const [open, setOpen] = useState(depth < 2);
  const isFile = node === null;
  return (
    <div className="ss-model-node" style={{ paddingLeft: `${depth * 1}rem` }}>
      <button
        type="button"
        className="ss-model-node-btn"
        onClick={() => !isFile && setOpen((v) => !v)}
      >
        <i
          className={`bi ${isFile ? "bi-file-earmark" : open ? "bi-folder2-open" : "bi-folder2"}`}
        />
        <span>{name}</span>
      </button>
      {!isFile && open
        ? Object.entries(node)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([child, sub]) => (
              <TreeView key={child} name={child} node={sub} depth={depth + 1} />
            ))
        : null}
    </div>
  );
}

/**
 * React model directory browser (K8s). Uses JSON API from ModelDirectory.
 */
export function ModelsDirectoryApp() {
  const [tree, setTree] = useState<TreeNode>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    setBusy(true);
    setError(null);
    loadTree("", ".")
      .then((data) => {
        const root = data.tree["."] || data.tree;
        setTree(root && typeof root === "object" ? root : data.tree);
      })
      .catch((e: Error) => setError(e.message || "Failed to load directory"))
      .finally(() => setBusy(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return (
    <div className="ss-models-dir">
      <PageHeader
        title="Model Directory"
        actions={
          <Button variant="secondary" disabled={busy} onClick={reload}>
            {busy ? "Loading…" : "Refresh"}
          </Button>
        }
      />
      {error ? <p className="ss-drawer-error">{error}</p> : null}
      <div className="ss-models-dir-tree">
        <Card>
          {Object.keys(tree).length === 0 && !busy ? (
            <p className="ss-workspace-panel-hint">No models found.</p>
          ) : (
            Object.entries(tree)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([name, node]) => (
                <TreeView key={name} name={name} node={node} depth={0} />
              ))
          )}
        </Card>
      </div>
    </div>
  );
}
