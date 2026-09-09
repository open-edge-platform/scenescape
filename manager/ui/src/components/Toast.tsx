// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import "./Toast.css";

export type ToastMessage = {
  id: string;
  text: string;
  tone?: "info" | "ok" | "bad";
};

type Props = {
  message: ToastMessage | null;
  onDismiss: () => void;
  timeoutMs?: number;
};

export function Toast({ message, onDismiss, timeoutMs = 4000 }: Props) {
  useEffect(() => {
    if (!message) {
      return;
    }
    const t = window.setTimeout(onDismiss, timeoutMs);
    return () => window.clearTimeout(t);
  }, [message, onDismiss, timeoutMs]);

  if (!message) {
    return null;
  }

  return (
    <div
      className={`ss-toast ss-toast--${message.tone || "info"}`}
      role="status"
    >
      <span>{message.text}</span>
      <button type="button" className="ss-toast-dismiss" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}

export function useToast() {
  const [message, setMessage] = useState<ToastMessage | null>(null);
  return {
    message,
    show: (text: string, tone?: ToastMessage["tone"]) =>
      setMessage({ id: String(Date.now()), text, tone }),
    dismiss: () => setMessage(null),
  };
}
