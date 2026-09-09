// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * ViPPET-aligned light tokens (mirror — see .github/plans/manager-ui.md).
 * Runtime light/dark is CSS-driven via html[data-theme]; prefer var(--ss-*).
 */
export const tokens = {
  brand: "#0054ae",
  brandHover: "#004a9d",
  brandSoft: "#0099ec",
  navBg: "#001e50",
  navFg: "#ffffff",
  ink: "#001e50",
  surface: "#f4f5f5",
  cardBg: "#ffffff",
  cardBorder: "#e9e9e9",
  text: "#000000",
  textMuted: "#808080",
  statusOk: "#008a00",
  statusBad: "#da2e56",
  inputBorder: "#aeaeae",
  elevated: "#ffffff",
  onBrand: "#ffffff",
  fontSans: '"Open Sans", "Montserrat", system-ui, -apple-system, sans-serif',
  fontHeading:
    '"Montserrat", "Open Sans", system-ui, -apple-system, sans-serif',
  radius: "0.625rem",
  formCardMax: "48rem",
  formCardMaxWide: "64rem",
  fieldMax: "28rem",
} as const;

export type Tokens = typeof tokens;
