// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useAppToast } from "../components/ToastProvider";
import {
  checkExists,
  createFolder,
  deleteItem,
  extractZip,
  folderNameError,
  isZipFile,
  joinPath,
  loadTree,
  modelUrlPath,
  sanitizeFolderName,
  uploadFile,
  zipStem,
  type TreeNode,
} from "./modelDirectoryApi";
import "./ModelsDirectoryApp.css";

type PendingDelete = { path: string; name: string; isFile: boolean };
type PendingOverwrite = { path: string; names: string[]; files: File[] };

function sortEntries(
  entries: [string, TreeNode | null][],
): [string, TreeNode | null][] {
  return [...entries].sort(([a, aNode], [b, bNode]) => {
    const aDir = aNode !== null;
    const bDir = bNode !== null;
    if (aDir && !bDir) {
      return -1;
    }
    if (!aDir && bDir) {
      return 1;
    }
    return a.localeCompare(b, undefined, { sensitivity: "base" });
  });
}

function TreeView({
  name,
  node,
  parentPath,
  depth,
  canWrite,
  creatingAt,
  newFolderName,
  dropPath,
  onToggleCreate,
  onNewFolderName,
  onCommitCreate,
  onCancelCreate,
  onUpload,
  onDelete,
  onCopy,
  onDropPath,
  onFilesDropped,
}: {
  name: string;
  node: TreeNode | null;
  parentPath: string;
  depth: number;
  canWrite: boolean;
  creatingAt: string | null;
  newFolderName: string;
  dropPath: string | null;
  onToggleCreate: (parentPath: string) => void;
  onNewFolderName: (value: string) => void;
  onCommitCreate: () => void;
  onCancelCreate: () => void;
  onUpload: (parentPath: string) => void;
  onDelete: (path: string, name: string, isFile: boolean) => void;
  onCopy: (relPath: string) => void;
  onDropPath: (path: string | null) => void;
  onFilesDropped: (parentPath: string, files: File[]) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  const isFile = node === null;
  const relPath = joinPath(parentPath, name);
  const childParent = relPath;
  const creatingHere = creatingAt === childParent;
  const dropping = !isFile && dropPath === childParent;

  return (
    <div className="ss-model-node" style={{ paddingLeft: `${depth}rem` }}>
      <div
        className={`ss-model-row${dropping ? " is-drop" : ""}`}
        onDragOver={
          canWrite && !isFile
            ? (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                onDropPath(childParent);
              }
            : undefined
        }
        onDragLeave={
          canWrite && !isFile
            ? (ev) => {
                ev.stopPropagation();
                onDropPath(null);
              }
            : undefined
        }
        onDrop={
          canWrite && !isFile
            ? (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                onDropPath(null);
                const files = Array.from(ev.dataTransfer.files || []);
                if (files.length) {
                  onFilesDropped(childParent, files);
                }
              }
            : undefined
        }
      >
        <button
          type="button"
          className="ss-model-node-btn"
          onClick={() => !isFile && setOpen((v) => !v)}
        >
          <i
            className={`bi ${isFile ? "bi-file-earmark" : open || creatingHere ? "bi-folder2-open" : "bi-folder2"}`}
            aria-hidden="true"
          />
          <span>{name}</span>
        </button>
        <div className="ss-model-actions">
          {isFile ? (
            <>
              <button
                type="button"
                className="ss-btn ss-btn--ghost ss-btn--sm"
                title="Copy as path"
                onClick={() => onCopy(relPath)}
              >
                <i className="bi bi-clipboard" aria-hidden="true" />
                <span className="sr-only">Copy as path</span>
              </button>
              <a
                className="ss-btn ss-btn--ghost ss-btn--sm"
                href={modelUrlPath(relPath)}
                download
                title="Download file"
              >
                <i className="bi bi-download" aria-hidden="true" />
                <span className="sr-only">Download file</span>
              </a>
            </>
          ) : canWrite ? (
            <>
              <button
                type="button"
                className="ss-btn ss-btn--ghost ss-btn--sm"
                title="New folder"
                onClick={() => {
                  setOpen(true);
                  onToggleCreate(childParent);
                }}
              >
                <i className="bi bi-folder-plus" aria-hidden="true" />
                <span className="sr-only">New folder</span>
              </button>
              <button
                type="button"
                className="ss-btn ss-btn--ghost ss-btn--sm"
                title="Upload file"
                onClick={() => onUpload(childParent)}
              >
                <i className="bi bi-upload" aria-hidden="true" />
                <span className="sr-only">Upload file</span>
              </button>
            </>
          ) : null}
          {canWrite ? (
            <button
              type="button"
              className="ss-btn ss-btn--ghost ss-btn--sm ss-model-action-danger"
              title={isFile ? "Delete file" : "Delete folder"}
              onClick={() => onDelete(parentPath, name, isFile)}
            >
              <i className="bi bi-x-lg" aria-hidden="true" />
              <span className="sr-only">
                {isFile ? "Delete file" : "Delete folder"}
              </span>
            </button>
          ) : null}
        </div>
      </div>
      {creatingHere ? (
        <div
          className="ss-model-node"
          style={{ paddingLeft: `${depth + 1}rem` }}
        >
          <input
            className="form-control ss-model-new-folder"
            placeholder="New folder name"
            value={newFolderName}
            autoFocus
            onChange={(e) =>
              onNewFolderName(sanitizeFolderName(e.target.value))
            }
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onCommitCreate();
              }
              if (e.key === "Escape") {
                e.preventDefault();
                onCancelCreate();
              }
            }}
            onBlur={() => onCommitCreate()}
          />
        </div>
      ) : null}
      {!isFile && (open || creatingHere)
        ? sortEntries(Object.entries(node)).map(([child, sub]) => (
            <TreeView
              key={child}
              name={child}
              node={sub}
              parentPath={childParent}
              depth={depth + 1}
              canWrite={canWrite}
              creatingAt={creatingAt}
              newFolderName={newFolderName}
              dropPath={dropPath}
              onToggleCreate={onToggleCreate}
              onNewFolderName={onNewFolderName}
              onCommitCreate={onCommitCreate}
              onCancelCreate={onCancelCreate}
              onUpload={onUpload}
              onDelete={onDelete}
              onCopy={onCopy}
              onDropPath={onDropPath}
              onFilesDropped={onFilesDropped}
            />
          ))
        : null}
    </div>
  );
}

type Props = { isSuperuser: boolean };

/**
 * React model directory browser (K8s): browse, create, upload/extract, delete.
 */
export function ModelsDirectoryApp({ isSuperuser }: Props) {
  const toast = useAppToast();
  const canWrite = isSuperuser;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadPathRef = useRef("");
  const createStateRef = useRef<{ path: string | null; name: string }>({
    path: null,
    name: "",
  });
  const [tree, setTree] = useState<TreeNode>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [creatingAt, setCreatingAt] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const [dropPath, setDropPath] = useState<string | null>(null);
  const [guidanceOpen, setGuidanceOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(
    null,
  );
  const [pendingOverwrite, setPendingOverwrite] =
    useState<PendingOverwrite | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  createStateRef.current = { path: creatingAt, name: newFolderName };

  const reload = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await loadTree("", ".");
      const root = data.tree["."] || data.tree;
      setTree(root && typeof root === "object" ? root : data.tree);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load directory");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const copyPath = useCallback(
    async (relPath: string) => {
      const text = modelUrlPath(relPath);
      try {
        await navigator.clipboard.writeText(text);
        toast.show("Model URL path copied to clipboard.", "ok");
      } catch (err) {
        toast.show(`Could not copy path: ${String(err)}`, "bad");
      }
    },
    [toast],
  );

  const commitCreate = useCallback(async () => {
    const { path, name: raw } = createStateRef.current;
    if (path === null) {
      return;
    }
    createStateRef.current = { path: null, name: "" };
    setCreatingAt(null);
    setNewFolderName("");
    const name = raw.trim();
    if (!name) {
      return;
    }
    const invalid = folderNameError(name);
    if (invalid) {
      toast.show(invalid, "bad");
      return;
    }
    try {
      const msg = await createFolder(path, name);
      toast.show(msg || "Directory created successfully", "ok");
      await reload();
    } catch (e) {
      toast.show(e instanceof Error ? e.message : "Create failed", "bad");
    }
  }, [reload, toast]);

  const cancelCreate = useCallback(() => {
    createStateRef.current = { path: null, name: "" };
    setCreatingAt(null);
    setNewFolderName("");
  }, []);

  const startCreate = useCallback((parentPath: string) => {
    setCreatingAt(parentPath);
    setNewFolderName("");
  }, []);

  const putFiles = useCallback(
    async (path: string, files: File[], overwrite: boolean) => {
      if (!files.length) {
        return;
      }
      setBusy(true);
      try {
        const names = files.map((f) =>
          isZipFile(f) ? zipStem(f.name) : f.name,
        );
        const existing: string[] = [];
        for (const name of names) {
          if (await checkExists(path, name)) {
            existing.push(name);
          }
        }
        if (existing.length && !overwrite) {
          setBusy(false);
          setPendingOverwrite({ path, names: existing, files });
          return;
        }
        if (existing.length) {
          for (const name of existing) {
            await deleteItem(path, name);
          }
        }
        let last = "";
        for (const file of files) {
          if (isZipFile(file)) {
            const stem = zipStem(file.name);
            try {
              await createFolder(path, stem);
            } catch {
              /* recreated after overwrite, or already present */
            }
            last = await extractZip(joinPath(path, stem), file);
          } else {
            last = await uploadFile(path, file);
          }
        }
        toast.show(last || "Upload complete", "ok");
        await reload();
      } catch (e) {
        toast.show(e instanceof Error ? e.message : "Upload failed", "bad");
      } finally {
        setBusy(false);
      }
    },
    [reload, toast],
  );

  const openUpload = useCallback((parentPath: string) => {
    uploadPathRef.current = parentPath;
    const input = fileInputRef.current;
    if (input) {
      input.value = "";
      input.click();
    }
  }, []);

  const onFileChosen = useCallback(
    (ev: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(ev.target.files || []);
      ev.target.value = "";
      void putFiles(uploadPathRef.current, files, false);
    },
    [putFiles],
  );

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) {
      return;
    }
    setDeleteBusy(true);
    try {
      const msg = await deleteItem(pendingDelete.path, pendingDelete.name);
      toast.show(msg || "Deleted", "ok");
      setPendingDelete(null);
      await reload();
    } catch (e) {
      toast.show(e instanceof Error ? e.message : "Delete failed", "bad");
    } finally {
      setDeleteBusy(false);
    }
  }, [pendingDelete, reload, toast]);

  const confirmOverwrite = useCallback(async () => {
    if (!pendingOverwrite) {
      return;
    }
    const next = pendingOverwrite;
    setPendingOverwrite(null);
    await putFiles(next.path, next.files, true);
  }, [pendingOverwrite, putFiles]);

  const onRootDrop = useCallback(
    (ev: React.DragEvent) => {
      if (!canWrite) {
        return;
      }
      ev.preventDefault();
      setDropPath(null);
      const files = Array.from(ev.dataTransfer.files || []);
      if (files.length) {
        void putFiles("", files, false);
      }
    },
    [canWrite, putFiles],
  );

  const treeEntries = sortEntries(Object.entries(tree));

  return (
    <div className="ss-models-dir">
      <PageHeader
        title="Model Directory"
        actions={
          <>
            <Button
              variant="ghost"
              title="Guidance"
              onClick={() => setGuidanceOpen(true)}
            >
              <i className="bi bi-info-circle" aria-hidden="true" />
              <span className="sr-only">Guidance</span>
            </Button>
            {canWrite ? (
              <>
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => startCreate("")}
                >
                  New folder
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => openUpload("")}
                >
                  Upload
                </Button>
              </>
            ) : null}
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => void reload()}
            >
              {busy ? "Loading…" : "Refresh"}
            </Button>
          </>
        }
      />
      {error ? <p className="ss-models-dir-error">{error}</p> : null}
      {!canWrite ? (
        <p className="ss-models-dir-hint">
          Browse only. Creating, uploading, and deleting models requires an
          administrator account.
        </p>
      ) : null}
      <input
        id="ss-model-file-input"
        ref={fileInputRef}
        type="file"
        multiple
        hidden
        onChange={onFileChosen}
      />
      <div
        className={`ss-models-dir-tree${dropPath === "" ? " is-drop" : ""}`}
        onDragOver={
          canWrite
            ? (ev) => {
                ev.preventDefault();
                setDropPath("");
              }
            : undefined
        }
        onDragLeave={canWrite ? () => setDropPath(null) : undefined}
        onDrop={onRootDrop}
      >
        <Card>
          {creatingAt === "" ? (
            <div className="ss-model-node" style={{ paddingLeft: 0 }}>
              <input
                className="form-control ss-model-new-folder"
                placeholder="New folder name"
                value={newFolderName}
                autoFocus
                onChange={(e) =>
                  setNewFolderName(sanitizeFolderName(e.target.value))
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void commitCreate();
                  }
                  if (e.key === "Escape") {
                    e.preventDefault();
                    cancelCreate();
                  }
                }}
                onBlur={() => void commitCreate()}
              />
            </div>
          ) : null}
          {treeEntries.length === 0 && !busy && creatingAt !== "" ? (
            <p className="ss-models-dir-hint">No models found.</p>
          ) : (
            treeEntries.map(([name, node]) => (
              <TreeView
                key={name}
                name={name}
                node={node}
                parentPath=""
                depth={0}
                canWrite={canWrite}
                creatingAt={creatingAt}
                newFolderName={newFolderName}
                dropPath={dropPath}
                onToggleCreate={startCreate}
                onNewFolderName={setNewFolderName}
                onCommitCreate={() => void commitCreate()}
                onCancelCreate={cancelCreate}
                onUpload={openUpload}
                onDelete={(path, itemName, isFile) =>
                  setPendingDelete({ path, name: itemName, isFile })
                }
                onCopy={(rel) => void copyPath(rel)}
                onDropPath={setDropPath}
                onFilesDropped={(parent, files) =>
                  void putFiles(parent, files, false)
                }
              />
            ))
          )}
        </Card>
      </div>

      <ConfirmDialog
        open={guidanceOpen}
        title="Guidance"
        confirmLabel="OK"
        danger={false}
        alert
        onConfirm={() => setGuidanceOpen(false)}
        onCancel={() => setGuidanceOpen(false)}
      >
        <ol className="ss-model-guidance">
          <li>
            Browse folders and files under the models root. Superusers can
            create folders, upload files, extract zip archives, and delete
            items. Use Refresh after changes made outside this page.
          </li>
          <li>
            Zip uploads create a folder named after the archive, then extract
            into that folder. Existing names prompt before overwrite.
          </li>
          <li>
            Copy as path copies <code>/models/…</code> for pipeline config.
            Download fetches the file from the models volume.
          </li>
          <li>
            Renaming is not supported. Delete the existing item and create a new
            one with the desired name.
          </li>
        </ol>
      </ConfirmDialog>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={pendingDelete?.isFile ? "Delete file?" : "Delete folder?"}
        confirmLabel="Delete"
        danger
        busy={deleteBusy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => {
          if (!deleteBusy) {
            setPendingDelete(null);
          }
        }}
      >
        <p>
          Are you sure you want to delete <strong>{pendingDelete?.name}</strong>
          ?
        </p>
        <p>This action cannot be undone.</p>
      </ConfirmDialog>

      <ConfirmDialog
        open={Boolean(pendingOverwrite)}
        title="Overwrite existing items?"
        confirmLabel="Overwrite"
        danger
        onConfirm={() => void confirmOverwrite()}
        onCancel={() => setPendingOverwrite(null)}
      >
        <p>These names already exist and will be replaced:</p>
        <ul>
          {(pendingOverwrite?.names || []).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </ConfirmDialog>
    </div>
  );
}
