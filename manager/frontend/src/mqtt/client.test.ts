// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { afterEach, describe, expect, it, vi } from "vitest";
import { mqttPayloadToString, setMqttConnected } from "./client";

describe("mqttPayloadToString", () => {
  it("returns empty for nullish", () => {
    expect(mqttPayloadToString(null)).toBe("");
    expect(mqttPayloadToString(undefined)).toBe("");
  });

  it("passes through strings", () => {
    expect(mqttPayloadToString('{"ok":true}')).toBe('{"ok":true}');
  });

  it("decodes Uint8Array as UTF-8", () => {
    const bytes = new TextEncoder().encode('{"id":1}');
    expect(mqttPayloadToString(bytes)).toBe('{"id":1}');
  });

  it("decodes ArrayBuffer as UTF-8", () => {
    const bytes = new TextEncoder().encode("hello");
    expect(mqttPayloadToString(bytes.buffer)).toBe("hello");
  });

  it("fails closed on non-binary objects with toString", () => {
    const bogus = {
      toString(enc?: string) {
        return enc === "utf8" ? "[object Buffer]" : "[object Object]";
      },
    };
    expect(mqttPayloadToString(bogus)).toBe("");
  });

  it("fails closed on numbers and plain objects", () => {
    expect(mqttPayloadToString(42)).toBe("");
    expect(mqttPayloadToString({ a: 1 })).toBe("");
  });
});

describe("setMqttConnected", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("marks mqtt_status connected and dispatches ss-mqtt-status", () => {
    class FakeHTMLElement {}
    const classes = new Set<string>();
    const attrs: Record<string, string> = {};
    const el = Object.assign(Object.create(FakeHTMLElement.prototype), {
      id: "mqtt_status",
      classList: {
        toggle(name: string, force?: boolean) {
          if (force === true) {
            classes.add(name);
          } else if (force === false) {
            classes.delete(name);
          } else if (classes.has(name)) {
            classes.delete(name);
          } else {
            classes.add(name);
          }
        },
        contains(name: string) {
          return classes.has(name);
        },
        remove(name: string) {
          classes.delete(name);
        },
      },
      setAttribute(k: string, v: string) {
        attrs[k] = v;
      },
      getAttribute(k: string) {
        return attrs[k] ?? null;
      },
    });

    vi.stubGlobal("HTMLElement", FakeHTMLElement);
    vi.stubGlobal("document", {
      getElementById: (id: string) => (id === "mqtt_status" ? el : null),
      querySelectorAll: () => [el],
    });

    const seen: boolean[] = [];
    const realWindow = globalThis.window;
    const dispatchEvent = vi.fn((ev: Event) => {
      if (ev.type === "ss-mqtt-status" && "detail" in ev) {
        seen.push(Boolean((ev as CustomEvent).detail?.connected));
      }
      return true;
    });
    vi.stubGlobal("window", {
      ...(realWindow ?? {}),
      dispatchEvent,
    });

    setMqttConnected(true);
    expect(classes.has("connected")).toBe(true);
    expect(attrs["data-ss-mqtt"]).toBe("connected");
    expect(seen).toEqual([true]);

    setMqttConnected(false);
    expect(classes.has("connected")).toBe(false);
    expect(attrs["data-ss-mqtt"]).toBe("disconnected");
    expect(seen).toEqual([true, false]);
  });
});
