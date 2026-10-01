// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

type Props = {
  appName: string;
  appVersion: string;
  appGitCommit: string;
};

/**
 * About dialog — hard-contract ids for skill freeze / Bootstrap data-dismiss.
 */
export function AboutModal({ appName, appVersion, appGitCommit }: Props) {
  return (
    <div
      className="modal fade ss-about-modal"
      id="ss-about-modal"
      tabIndex={-1}
      role="dialog"
      aria-labelledby="ss-about-title"
      aria-hidden="true"
    >
      <div className="modal-dialog modal-dialog-centered" role="document">
        <div className="modal-content">
          <div className="modal-header">
            <h2 className="modal-title h5" id="ss-about-title">
              About
            </h2>
            <button
              type="button"
              className="close"
              data-dismiss="modal"
              aria-label="Close"
            >
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div className="modal-body">
            <p className="ss-about-product">{appName}</p>
            <p className="ss-about-blurb">
              Spatial awareness for multi-camera scenes — track people and
              objects across a shared map.
            </p>
            <dl className="ss-about-meta">
              <div>
                <dt>Version</dt>
                <dd id="ss-about-version">{appVersion}</dd>
              </div>
              <div>
                <dt>Build</dt>
                <dd>
                  <code id="ss-about-commit" className="ss-about-commit">
                    {appGitCommit}
                  </code>
                </dd>
              </div>
              <div>
                <dt>Copyright</dt>
                <dd>© 2026 Intel Corporation</dd>
              </div>
              <div>
                <dt>License</dt>
                <dd>Apache License, Version 2.0</dd>
              </div>
            </dl>
            <p className="ss-about-legal">
              Intel, the Intel logo, and Intel SceneScape are trademarks of
              Intel Corporation or its subsidiaries.
            </p>
          </div>
          <div className="modal-footer">
            <button
              type="button"
              className="btn btn-primary"
              data-dismiss="modal"
              id="ss-about-close"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
