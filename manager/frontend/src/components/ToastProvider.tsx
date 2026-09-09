// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Toast, type ToastMessage } from "./Toast";

type ToastApi = {
  show: (text: string, tone?: ToastMessage["tone"]) => void;
  dismiss: () => void;
};

const ToastCtx = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<ToastMessage | null>(null);
  const dismiss = useCallback(() => setMessage(null), []);
  const show = useCallback((text: string, tone?: ToastMessage["tone"]) => {
    setMessage({ id: String(Date.now()), text, tone });
  }, []);
  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);

  useEffect(() => {
    return installLegacyToastBridge(api);
  }, [api]);

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <Toast message={message} onDismiss={dismiss} />
    </ToastCtx.Provider>
  );
}

export function useAppToast(): ToastApi {
  const ctx = useContext(ToastCtx);
  if (!ctx) {
    return {
      show: (text) => {
        console.info(text);
      },
      dismiss: () => undefined,
    };
  }
  return ctx;
}

/** Bridge for legacy JS: window.ssToast?.show(text, tone) */
export function installLegacyToastBridge(api: ToastApi): () => void {
  window.ssToast = api;
  return () => {
    if (window.ssToast === api) {
      delete window.ssToast;
    }
  };
}

declare global {
  interface Window {
    ssToast?: ToastApi;
  }
}
