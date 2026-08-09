// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, type ReactNode } from "react";
import "./FormSection.css";

type Props = {
  title: string;
  description?: string;
  children: ReactNode;
  /** When true, renders a native <details> disclosure (advanced / optional). */
  collapsible?: boolean;
  defaultOpen?: boolean;
  /** Controlled open state (wins over defaultOpen when provided). */
  open?: boolean;
  /** Expand when true (e.g. validation errors in this section). */
  forceOpen?: boolean;
  className?: string;
  id?: string;
};

/**
 * Topic block for multi-field forms (field → group → section hierarchy).
 * Use for distinct topics; use collapsible for advanced / rarely edited fields.
 */
export function FormSection({
  title,
  description,
  children,
  collapsible = false,
  defaultOpen = false,
  open,
  forceOpen = false,
  className = "",
  id,
}: Props) {
  const titleId = id ? `${id}-title` : undefined;
  const descId = id && description ? `${id}-desc` : undefined;
  const extra = className.trim();
  const detailsRef = useRef<HTMLDetailsElement>(null);

  const resolvedOpen =
    forceOpen || (open !== undefined ? open : defaultOpen || undefined);

  useEffect(() => {
    if (!collapsible || !detailsRef.current) {
      return;
    }
    if (forceOpen) {
      detailsRef.current.open = true;
    } else if (open !== undefined) {
      detailsRef.current.open = open;
    }
  }, [collapsible, forceOpen, open]);

  if (collapsible) {
    return (
      <details
        ref={detailsRef}
        id={id}
        className={`ss-form-section ss-form-section--collapsible${extra ? ` ${extra}` : ""}${forceOpen ? " is-forced-open" : ""}`}
        open={resolvedOpen || undefined}
      >
        <summary className="ss-form-section-summary">
          <span className="ss-form-section-title" id={titleId}>
            {title}
          </span>
          {description ? (
            <span className="ss-form-section-desc" id={descId}>
              {description}
            </span>
          ) : null}
        </summary>
        <div className="ss-form-section-body">{children}</div>
      </details>
    );
  }

  return (
    <section
      id={id}
      className={`ss-form-section${extra ? ` ${extra}` : ""}`}
      aria-labelledby={titleId}
      aria-describedby={descId}
    >
      <h3 className="ss-form-section-title" id={titleId}>
        {title}
      </h3>
      {description ? (
        <p className="ss-form-section-desc" id={descId}>
          {description}
        </p>
      ) : null}
      <div className="ss-form-section-body">{children}</div>
    </section>
  );
}
