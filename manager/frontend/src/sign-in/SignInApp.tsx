// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { FormEvent, useState } from "react";
import { getCsrfToken } from "../lib/session";

export type SignInBootstrap = {
  appName: string;
  appVersion: string;
  intelLogo: string;
  intelHref: string;
  nextUrl?: string;
};

type Props = {
  bootstrap: SignInBootstrap;
};

/**
 * Session sign-in form — hard-contract ids for UI tests (#username, #password,
 * #login-submit). Posts to /sign_in/ with Accept: application/json.
 */
export function SignInApp({ bootstrap }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const nextFromQuery = (() => {
    try {
      return new URLSearchParams(window.location.search).get("next") || "";
    } catch {
      return "";
    }
  })();
  const nextUrl = bootstrap.nextUrl || nextFromQuery;

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    setErrors([]);
    setBusy(true);
    const csrf = getCsrfToken();
    const body = new URLSearchParams();
    body.set("username", username);
    body.set("password", password);
    if (csrf) {
      body.set("csrfmiddlewaretoken", csrf);
    }
    const url = nextUrl
      ? `/sign_in/?next=${encodeURIComponent(nextUrl)}`
      : "/sign_in/";
    try {
      const res = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/x-www-form-urlencoded",
          ...(csrf ? { "X-CSRFToken": csrf } : {}),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: body.toString(),
      });
      const data = (await res.json().catch(() => null)) as {
        ok?: boolean;
        redirect?: string;
        errors?: string[];
      } | null;
      if (res.ok && data?.ok && data.redirect) {
        window.location.href = data.redirect;
        return;
      }
      setErrors(
        data?.errors?.length
          ? data.errors
          : ["Invalid username or password."],
      );
    } catch {
      setErrors(["Could not reach the sign-in service."]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="sign-in-page">
      <div className="sign-in-shell">
        <div className="sign-in-card">
          <div className="sign-in-brand">
            <span className="ss-wordmark ss-wordmark-lg">{bootstrap.appName}</span>
            <p className="sign-in-version">Version {bootstrap.appVersion}</p>
          </div>
          <div className="sign-in-card-body">
            {errors.length > 0 ? (
              <div className="alert alert-danger login-error" role="alert">
                {errors.map((err) => (
                  <p key={err}>{err}</p>
                ))}
              </div>
            ) : null}
            <form
              method="POST"
              className="sign-in-form-fields"
              onSubmit={onSubmit}
            >
              <div className="form-group">
                <label
                  className="sign-in-label"
                  htmlFor="username"
                  id="label-username"
                >
                  User Name
                </label>
                <input
                  type="text"
                  className="form-control"
                  id="username"
                  name="username"
                  aria-labelledby="label-username"
                  value={username}
                  autoComplete="username"
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="form-group">
                <label
                  className="sign-in-label"
                  htmlFor="password"
                  id="label-password"
                >
                  Password
                </label>
                <input
                  type="password"
                  className="form-control"
                  id="password"
                  name="password"
                  aria-labelledby="label-password"
                  value={password}
                  autoComplete="current-password"
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={busy}
                />
              </div>
              <button
                type="submit"
                className="btn btn-primary btn-block sign-in-submit"
                id="login-submit"
                disabled={busy}
              >
                {busy ? "Signing in…" : "Sign In"}
              </button>
            </form>
            <p className="sign-in-help">
              Contact the system administrator for sign in help.
            </p>
            <a
              className="sign-in-powered-by"
              href={bootstrap.intelHref}
              target="_blank"
              rel="noopener noreferrer"
              title="Powered by Intel"
            >
              <span className="powered-by-label">Powered by</span>
              <img
                className="intel-logo"
                src={bootstrap.intelLogo}
                alt="Intel"
              />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
